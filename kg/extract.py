# -*- coding: utf-8 -*-
"""
从文本抽取知识图谱 —— 只用传统 NLP(spaCy 词性/依存句法/NER + 规则),不调用任何 LLM。
每一条关系都对应原文中一个真实存在的句法结构,并附原句作证据,不会"编造"关系。

流水线(每步一个函数,便于单独测试与替换):
  preprocess        去掉口语填充词(um/uh ...),Whisper 转写稿里很常见
  extract_mentions  NER:本体词表匹配 + spaCy 命名实体 + 名词短语
  normalize         归一化:词形还原、去限定词/代词、同义写法并到本体规范 id
  extract_relations 关系抽取:基于依存句法的 主-谓-宾 / 被动 / 系表 / 介词宾语 模式
  apply_ontology    本体阶段:概念分类、谓词映射为关系类型、按 policy 过滤
  assemble          聚合成图(去重计数,保留证据句)

概念分两种:core(在 ontology.yaml 词表里)和 emergent(词表外,受试者自己提出的)。
emergent 概念要过质量门槛才入图:中心词是名词、不是泛词/元话语词,
且被提到至少 policy.emergent_min_mentions 次或参与了某条关系(随口一提的词不算受试者的知识)。

已知局限(有意为之,宁缺毋滥):
- 不做指代消解:主语/宾语是 it/they/this 的句子不出关系;
- 不跨句;不处理从句作宾语("X shows that ...");
- 小模型(en_core_web_sm)的句法分析在口语上会出错,可用 KG_SPACY_MODEL 换更大的模型。
"""
import os
import re
from collections import Counter
from dataclasses import dataclass, field

from . import ontology as onto_mod

SPACY_MODEL = os.environ.get("KG_SPACY_MODEL", "en_core_web_sm")

_nlp = None


def get_nlp():
    """懒加载 spaCy 模型并复用。"""
    global _nlp
    if _nlp is None:
        import spacy
        try:
            _nlp = spacy.load(SPACY_MODEL)
        except OSError as e:
            raise RuntimeError(
                f"spaCy model {SPACY_MODEL!r} is not installed. "
                f"Run: python -m spacy download {SPACY_MODEL}"
            ) from e
    return _nlp


# ---------------------------------------------------------------- 词表/常量
# 名词短语里只保留这些词性的词参与归一化
_CONTENT_POS = {"NOUN", "PROPN", "ADJ", "VERB", "X"}
# 这些实体类型是数量/时间,不是概念
_SKIP_ENT_LABELS = {"CARDINAL", "ORDINAL", "PERCENT", "QUANTITY", "MONEY", "TIME", "DATE"}
# 太泛、单独成不了概念的名词(归一化后整串等于其中之一即丢弃)
GENERIC = {
    "thing", "something", "anything", "everything", "nothing", "stuff", "lot", "way",
    "kind", "sort", "type", "part", "bit", "fact", "point", "idea", "question", "case",
    "time", "year", "day", "one", "number", "amount", "use", "usage", "reason", "aspect",
    "side", "argument", "article", "reading", "passage", "example", "sense", "matter",
    "issue", "problem", "situation", "et al", "al", "lot of", "end", "level", "degree",
    # 元话语:谈论任务/对话本身,而不是学习内容
    "topic", "vocabulary", "word", "term", "sentence", "statement", "concept", "material",
    "testing", "yeah", "okay", "ok",
}
# emergent 概念的展示名去掉这些开头的词("the topics" → "topics","how quality" → "quality")
_LEADING_JUNK_POS = {"DET", "PRON", "ADV", "SCONJ", "CCONJ", "PART", "INTJ", "PUNCT", "NUM"}
_LEADING_JUNK_TAGS = {"WDT", "WP", "WP$", "WRB", "PRP$"}
# "the use of AI" / "a lot of data" 这类短语,语义中心在 of 的宾语上
LIGHT_NOUNS = {"use", "usage", "amount", "lot", "number", "kind", "type", "sort", "form",
               "deal", "bunch", "piece", "set", "collection", "majority", "variety"}
_FILLERS = re.compile(r"\b(?:u+m+|u+h+|e+r+m+|h+m+|m+h*m+|a+h+)\b[,.]?\s*", re.IGNORECASE)
_MODALS = {"can", "could", "may", "might", "must", "shall", "should", "will", "would"}
# "I don't think X" ≈ "I think not X":否定提升到从句
_NEG_RAISING = {"think", "believe", "suppose", "expect", "feel", "agree", "say", "guess"}
# 受试者转述他人观点("the article says ...")时,关系标为 attributed
_REPORTING = {"say", "argue", "claim", "suggest", "state", "mention", "write", "find", "show",
              "believe", "think", "propose", "report", "explain"}
_FIRST_PERSON = {"i", "we", "me", "us"}


# ---------------------------------------------------------------- 数据结构
@dataclass
class Mention:
    key: str                 # 归一化后的概念 key(本体 id 或名词短语)
    surface: str             # 原文写法
    sent_idx: int
    source: str              # ontology | ner | noun_chunk
    ner_label: str | None = None
    head: str | None = None
    core_parts: list[str] = field(default_factory=list)   # 短语里包含的词表概念("AI tutor" → [ai])


@dataclass
class RawRelation:
    source: str
    target: str
    predicate: str           # 词形还原后的谓词,如 reduce / rely_on / be
    negated: bool
    modal: str | None
    stance: str              # asserted | attributed
    sentence: str
    sent_idx: int


@dataclass
class Concept:
    key: str
    label: str
    cls: str
    in_ontology: bool
    head: str | None = None  # 复合概念("ai learning")的中心词所属本体概念("learning")
    count: int = 0
    surface_forms: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)
    ner_labels: list[str] = field(default_factory=list)
    status: str = "core"     # core(词表内)| emergent(词表外,已过质量门槛)
    core_parts: list[str] = field(default_factory=list)
    examples: list[str] = field(default_factory=list)      # 最多两句原文,供研究者审阅 emergent 概念


@dataclass
class Relation:
    source: str
    target: str
    type: str
    negated: bool
    count: int
    predicates: list[str]
    modals: list[str]
    stances: list[str]
    evidence: list[str]


@dataclass
class KnowledgeGraph:
    concepts: dict[str, Concept]
    relations: list[Relation]
    ontology_version: str
    sentences: int

    def to_dict(self) -> dict:
        return {
            "ontology_version": self.ontology_version,
            "sentences": self.sentences,
            "concepts": [vars(c) for c in sorted(self.concepts.values(), key=lambda c: -c.count)],
            "relations": [vars(r) for r in self.relations],
        }


# ---------------------------------------------------------------- 归一化
def _tok_form(tok) -> str:
    """单个词的规范形式:普通名词用词形还原(models→model),其余用小写原文
    (专有名词的词形还原不可靠,如 Turing→ture)。"""
    if tok.pos_ == "NOUN":
        return tok.lemma_.lower()
    return tok.lower_


def normalize_span(tokens) -> str:
    """名词短语 → 概念 key:去掉限定词/代词/副词/标点/数词,保留实词的规范形式。"""
    words = [_tok_form(t) for t in tokens
             if t.pos_ in _CONTENT_POS and not (t.is_stop and t.pos_ not in ("NOUN", "PROPN"))]
    key = " ".join(w for w in words if w.strip())
    return re.sub(r"\s+", " ", key).strip(" -'")


def _usable(key: str) -> bool:
    words = key.split()
    if len(words) > 1 and len(set(words)) == 1:          # "testing testing testing"
        return False
    return len(key) >= 2 and key not in GENERIC and not key.isdigit()


def clean_surface(tokens) -> str:
    """原文写法去掉开头的限定词/代词/疑问词/副词,作 emergent 概念的展示名。"""
    toks = list(tokens)
    while toks and (toks[0].pos_ in _LEADING_JUNK_POS or toks[0].tag_ in _LEADING_JUNK_TAGS):
        toks = toks[1:]
    return "".join(t.text_with_ws for t in toks).strip(" ,.;:'\"") or "".join(
        t.text_with_ws for t in tokens).strip()


def make_term_normalizer(nlp):
    """供本体加载用:同一个写法给出两种匹配形式(规范形式 / 纯小写),与正文窗口一一对应。"""
    def normalize_term(term: str) -> list[tuple[str, ...]]:
        doc = nlp(term)
        toks = [t for t in doc if not t.is_punct or t.text == "-"]
        return list({tuple(_tok_form(t) for t in toks), tuple(t.lower_ for t in toks)})
    return normalize_term


# ---------------------------------------------------------------- 1. 预处理
def preprocess(text: str) -> str:
    text = _FILLERS.sub("", text or "")
    return re.sub(r"\s+", " ", text).strip()


# ---------------------------------------------------------------- 2. NER + 3. 归一化
_NOUN_SLOTS = {"dobj", "pobj", "nsubj", "nsubjpass", "attr"}


def _nounish(tok) -> bool:
    """名词,或处在名词位置(宾语/主语/表语)上的动名词。"""
    return tok.pos_ in ("NOUN", "PROPN") or (tok.tag_ == "VBG" and tok.dep_ in _NOUN_SLOTS)


def extract_mentions(doc, onto) -> tuple[list[Mention], dict[int, str]]:
    """返回 (mentions, token 下标 → 概念 key)。优先级:本体词表 > 命名实体 > 名词短语。
    本体优先是因为小模型的 NER 在本领域常错(会把 AI 标成地名 GPE、AGI 标成机构 ORG)。"""
    mentions: list[Mention] = []
    tokmap: dict[int, str] = {}
    sent_of = {t.i: si for si, s in enumerate(doc.sents) for t in s}

    # 本体词表:同一句内最长匹配。窗口里至少要有一个名词,单个词必须本身是名词
    # (避免把动词 "test"、"I think" 的 think 当成概念)。
    # 处在名词位置上的动名词也算名词:小模型常把 "measure understanding" 的 understanding 标成动词。
    maxlen = onto.max_term_len
    i, n = 0, len(doc)
    while i < n:
        matched = 0
        for L in range(min(maxlen, n - i), 0, -1):
            span = doc[i:i + L]
            if sent_of[span[0].i] != sent_of[span[-1].i] or span[0].is_punct or span[-1].is_punct:
                continue
            if not any(_nounish(t) for t in span):
                continue
            if L == 1 and not _nounish(span[0]):
                continue
            toks = [t for t in span if not t.is_punct or t.text == "-"]
            key = (onto.terms.get(tuple(_tok_form(t) for t in toks))
                   or onto.terms.get(tuple(t.lower_ for t in toks)))
            if key:
                mentions.append(Mention(key, span.text, sent_of[span[0].i], "ontology"))
                for t in span:
                    tokmap[t.i] = key
                matched = L
                break
        i += matched or 1

    # 命名实体(词表未覆盖的部分)
    for ent in doc.ents:
        if ent.label_ in _SKIP_ENT_LABELS or any(t.i in tokmap for t in ent):
            continue
        key = normalize_span(ent)
        if _usable(key):
            mentions.append(Mention(key, clean_surface(ent), sent_of[ent.start], "ner", ent.label_))
            for t in ent:
                tokmap[t.i] = key

    # 名词短语。三种情况:
    # - 中心词未覆盖 → 整个短语成为一个概念("AI literacy" → "ai literacy";AI 仍单独计一次提及);
    # - 中心词已覆盖,且短语里只有一个本体概念 → 就是该概念("reasoning skills" → reasoning);
    # - 短语里有两个以上不同的本体概念 → 复合概念("AI learning" 不能并成 learning,
    #   否则 "AI learning is different from human learning" 会变成自环而丢失)。
    # 轻名词/泛词作中心的短语不立概念,由 _resolve 顺着 of 找真正的中心。
    # 中心词必须是名词:小模型偶尔把动词/形容词("tweak"、"refining")当短语中心。
    for chunk in doc.noun_chunks:
        root = chunk.root
        if root.pos_ not in ("NOUN", "PROPN") or root.lemma_.lower() in LIGHT_NOUNS | GENERIC:
            continue
        onto_keys = {tokmap[t.i] for t in chunk if t.i in tokmap and tokmap[t.i] in onto.concept_class}
        if root.i in tokmap and len(onto_keys) < 2:
            continue
        key = normalize_span(chunk)
        if not _usable(key) or key in onto.concept_class:
            continue
        head = tokmap.get(root.i) if root.i in tokmap else None
        mentions.append(Mention(key, clean_surface(chunk), sent_of[chunk.start], "noun_chunk",
                                head=head, core_parts=sorted(onto_keys)))
        for t in chunk:
            tokmap.setdefault(t.i, key)
        tokmap[root.i] = key
    return mentions, tokmap


# ---------------------------------------------------------------- 4. 关系抽取
def _resolve(tok, tokmap, depth=0) -> str | None:
    """依存树上的一个词 → 它所属的概念。轻名词("the use of AI")顺着 of 找真正的中心。"""
    if tok.i in tokmap:
        return tokmap[tok.i]
    if depth < 3 and tok.lemma_.lower() in LIGHT_NOUNS:
        for prep in tok.children:
            if prep.dep_ == "prep" and prep.lower_ == "of":
                for pobj in prep.children:
                    if pobj.dep_ == "pobj":
                        return _resolve(pobj, tokmap, depth + 1)
    return None


def _with_conjuncts(tokens):
    out = []
    for t in tokens:
        out.append(t)
        out.extend(t.conjuncts)
    return list(dict.fromkeys(out))


def _subjects(verb, depth=0):
    """(主语词, 是否被动)。并列动词("AI reduces X and weakens Y")无主语时继承前一个动词的主语;
    关系从句("ChatGPT, which bypasses ...")的 which/that 指向被修饰的名词。"""
    subs = [(c, c.dep_ in ("nsubjpass", "csubjpass")) for c in verb.children
            if c.dep_ in ("nsubj", "csubj", "nsubjpass", "csubjpass")]
    if not subs and verb.dep_ == "conj" and verb.head.pos_ in ("VERB", "AUX") and depth < 5:
        return _subjects(verb.head, depth + 1)
    out = []
    for s, passive in subs:
        if verb.dep_ == "relcl" and (s.tag_ in ("WDT", "WP") or s.lower_ in ("that", "which", "who")):
            s = verb.head
        out.append((s, passive))
    return out


def _negated(verb) -> bool:
    if any(c.dep_ == "neg" for c in verb.children):
        return True
    # 否定提升:"I don't think AI understands language" → understands 取否定
    head = verb
    while head.dep_ == "ccomp":
        head = head.head
        if head.lemma_.lower() in _NEG_RAISING and any(c.dep_ == "neg" for c in head.children):
            return True
    return False


def _stance(verb) -> str:
    """从句挂在非第一人称主语的转述动词下("the article says AI reduces memory")→ attributed。"""
    head = verb
    while head.dep_ == "ccomp":
        head = head.head
        if head.lemma_.lower() in _REPORTING:
            subj = [c for c in head.children if c.dep_ in ("nsubj", "nsubjpass")]
            if subj and subj[0].lower_ not in _FIRST_PERSON:
                return "attributed"
    return "asserted"


def extract_relations(doc, tokmap) -> list[RawRelation]:
    rels: list[RawRelation] = []
    sents = list(doc.sents)
    sent_of = {t.i: si for si, s in enumerate(sents) for t in s}

    for verb in doc:
        if verb.pos_ not in ("VERB", "AUX") or verb.dep_ in ("aux", "auxpass"):
            continue
        subjects = _subjects(verb)
        if not subjects:
            continue
        base = verb.lemma_.lower()
        prt = [c for c in verb.children if c.dep_ == "prt"]
        if prt:
            base += "_" + prt[0].lower_
        negated = _negated(verb)
        modal = next((c.lemma_.lower() for c in verb.children
                      if c.dep_ == "aux" and c.lemma_.lower() in _MODALS), None)
        stance = _stance(verb)
        si = sent_of[verb.i]
        sentence = sents[si].text.strip()

        triples = []          # (源词, 谓词, 目标词)
        passive = any(p for _, p in subjects) or any(c.dep_ == "auxpass" for c in verb.children)
        patients = _with_conjuncts([s for s, _ in subjects])
        preps = [c for c in verb.children if c.dep_ == "prep"]

        if passive:
            # 被动句:by 短语是真正的施事;没有施事时只取介词宾语("trained on text")
            agents = [p for a in verb.children if a.dep_ == "agent"
                      for p in a.children if p.dep_ == "pobj"]
            for a in _with_conjuncts(agents):
                for p in patients:
                    triples.append((a, base, p))
            for prep in preps:
                for pobj in _with_conjuncts([c for c in prep.children if c.dep_ == "pobj"]):
                    for p in patients:
                        triples.append((p, f"{base}_{prep.lower_}", pobj))
        else:
            objs = _with_conjuncts([c for c in verb.children
                                    if c.dep_ in ("dobj", "attr", "oprd", "dative")])
            for s in patients:
                for o in objs:
                    triples.append((s, base, o))
                for prep in preps:
                    for pobj in _with_conjuncts([c for c in prep.children if c.dep_ == "pobj"]):
                        triples.append((s, f"{base}_{prep.lower_}", pobj))
                # 系表 + 形容词 + 介词:"AI is different from human learning" → different_from
                for acomp in (c for c in verb.children if c.dep_ == "acomp"):
                    for prep in (c for c in acomp.children if c.dep_ == "prep"):
                        for pobj in _with_conjuncts([c for c in prep.children if c.dep_ == "pobj"]):
                            triples.append((s, f"{acomp.lemma_.lower()}_{prep.lower_}", pobj))

        for src_tok, pred, tgt_tok in triples:
            src, tgt = _resolve(src_tok, tokmap), _resolve(tgt_tok, tokmap)
            if not src or not tgt or src == tgt:
                continue
            # "AI has no understanding":宾语带 no 也算否定
            neg = negated or any(c.dep_ == "det" and c.lower_ == "no" for c in tgt_tok.children)
            rels.append(RawRelation(src, tgt, pred, neg, modal, stance, sentence, si))
    return rels


# ---------------------------------------------------------------- 5. 本体阶段 + 6. 聚合
def apply_ontology(mentions: list[Mention], raw: list[RawRelation], onto,
                   sentences: list[str]) -> KnowledgeGraph:
    concepts: dict[str, Concept] = {}
    surfaces: dict[str, Counter] = {}
    for m in mentions:
        in_onto = m.key in onto.concept_class
        if not in_onto and not onto.keep_unclassified_concepts:
            continue
        c = concepts.get(m.key)
        if c is None:
            c = concepts[m.key] = Concept(
                key=m.key, label=onto.concept_label.get(m.key, m.key),
                cls=onto.concept_class.get(m.key, onto_mod.UNCLASSIFIED), in_ontology=in_onto,
                head=m.head, status="core" if in_onto else "emergent")
            surfaces[m.key] = Counter()
        c.count += 1
        surfaces[m.key][m.surface.strip()] += 1
        if m.source not in c.sources:
            c.sources.append(m.source)
        if m.ner_label and m.ner_label not in c.ner_labels:
            c.ner_labels.append(m.ner_label)
        for k in m.core_parts:
            if k not in c.core_parts:
                c.core_parts.append(k)
        sent = sentences[m.sent_idx] if m.sent_idx < len(sentences) else ""
        if sent and sent not in c.examples and len(c.examples) < 2:
            c.examples.append(sent)
    for key, cnt in surfaces.items():
        c = concepts[key]
        c.surface_forms = [s for s, _ in cnt.most_common()]
        if not c.in_ontology:
            c.label = c.surface_forms[0]          # 词表外概念用最常见的原文写法作展示名

    typed = []
    for r in raw:
        if r.source not in concepts or r.target not in concepts:
            continue
        rtype = onto.relation_type(r.predicate) or onto_mod.UNTYPED
        if rtype == onto_mod.UNTYPED and not onto.keep_untyped_relations:
            continue
        typed.append((r, rtype))

    # emergent 概念的门槛:参与了关系,或被提到足够多次。未过门槛的不入图。
    connected = {k for r, _ in typed for k in (r.source, r.target)}
    for key in [k for k, c in concepts.items() if c.status == "emergent"]:
        if key not in connected and concepts[key].count < onto.emergent_min_mentions:
            del concepts[key]

    agg: dict[tuple, Relation] = {}
    for r, rtype in typed:
        k = (r.source, rtype, r.target, r.negated)
        rel = agg.get(k)
        if rel is None:
            rel = agg[k] = Relation(r.source, r.target, rtype, r.negated, 0, [], [], [], [])
        rel.count += 1
        for lst, v in ((rel.predicates, r.predicate), (rel.modals, r.modal),
                       (rel.stances, r.stance), (rel.evidence, r.sentence)):
            if v and v not in lst:
                lst.append(v)
    return KnowledgeGraph(concepts, list(agg.values()), onto.version, len(sentences))


# ---------------------------------------------------------------- 入口
_onto_cache: dict = {}


def get_ontology(path=None):
    key = str(path or "")
    if key not in _onto_cache:
        _onto_cache[key] = onto_mod.load(path, make_term_normalizer(get_nlp()))
    return _onto_cache[key]


def build_graph(text: str, onto=None) -> KnowledgeGraph:
    """文本 → 知识图谱(纯计算,不碰数据库)。"""
    onto = onto or get_ontology()
    doc = get_nlp()(preprocess(text))
    mentions, tokmap = extract_mentions(doc, onto)
    raw = extract_relations(doc, tokmap)
    return apply_ontology(mentions, raw, onto, [s.text.strip() for s in doc.sents])
