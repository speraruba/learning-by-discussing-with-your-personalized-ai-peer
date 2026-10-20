# -*- coding: utf-8 -*-
"""
语义相似度核对:给图上无法逐边核对的命题打分。

两类命题用得上它:
- 定义类命题(目标是一段描述,如 "Cognitive Labor is the mental work a task requires");
- 概念 → 概念命题在图上是 missing 时的兜底(句法分析偶尔会读错,如把 "evaluation measures" 当成名词短语)。

做法(只比较,不生成任何文字):
1. 只看提到了该命题源概念的句子(概念 → 概念命题还要求目标概念出现在同一句里);
2. 句子与命题原文各算一个向量,去掉停用词和概念名本身的词(否则同一概念的所有命题都"很像");
3. 每个句子只归给与它最像的那条命题,分数达到阈值才算 similar。

后端(环境变量 KG_SIM_MODEL):
  en_core_web_md(默认)  spaCy 词向量取平均,离线可用:python -m spacy download en_core_web_md
  sbert:<模型名>           sentence-transformers 句向量,效果更好,需 pip install sentence-transformers
                          且首次运行要从 Hugging Face 下载模型(如 sbert:all-MiniLM-L6-v2)
阈值:KG_SIM_THRESHOLD,默认 spaCy 0.70 / sbert 0.55。spaCy 的 0.70 是用主题 2 的改写句校准的。
"""
import os
from collections import defaultdict

import numpy as np

from . import extract

SIM_MODEL = os.environ.get("KG_SIM_MODEL", "en_core_web_md")
_DEFAULT_THRESHOLD = {"spacy": 0.70, "sbert": 0.55}

_backend = None   # (kind, model)


class Unavailable(Exception):
    """相似度模型没装:打分照常进行,只是不做相似度核对。"""


def backend():
    global _backend
    if _backend is None:
        if SIM_MODEL.startswith("sbert:"):
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as e:
                raise Unavailable("pip install sentence-transformers") from e
            _backend = ("sbert", SentenceTransformer(SIM_MODEL.split(":", 1)[1]))
        else:
            import spacy
            try:
                _backend = ("spacy", spacy.load(SIM_MODEL))
            except OSError as e:
                raise Unavailable(f"python -m spacy download {SIM_MODEL}") from e
    return _backend


def threshold() -> float:
    env = os.environ.get("KG_SIM_THRESHOLD")
    return float(env) if env else _DEFAULT_THRESHOLD[backend()[0]]


def _embed(texts: list[str], drop: set[str]) -> list:
    kind, model = backend()
    if kind == "sbert":
        return list(model.encode(texts, normalize_embeddings=True))
    out = []
    for doc in model.pipe(texts):
        vs = [t.vector for t in doc if t.has_vector and not t.is_stop and not t.is_punct
              and t.lower_ not in drop and t.lemma_.lower() not in drop]
        if vs:
            v = np.mean(vs, axis=0)
            n = np.linalg.norm(v)
            out.append(v / n if n else None)
        else:
            out.append(None)
    return out


def _cos(a, b) -> float:
    return float(np.dot(a, b)) if a is not None and b is not None else 0.0


def match(text: str, emap, onto, props) -> dict[str, dict]:
    """返回 {命题 id: {status, score, evidence}};status 为 similar | not_found | not_mentioned。
    props 是要核对的命题(expert.Proposition 列表)。"""
    doc = extract.get_nlp()(extract.preprocess(text))
    sents = [s.text.strip() for s in doc.sents]
    mentions, _ = extract.extract_mentions(doc, onto)
    sents_of: dict[str, set[int]] = defaultdict(set)
    for m in mentions:
        sents_of[m.key].add(m.sent_idx)

    # 概念名本身的词不参与比较(只去规范名,不去同义写法:"mental effort" 之类正是要比较的内容)
    drop = {w for key in emap.concepts
            for t in extract.get_nlp()(onto.concept_label.get(key, key)) for w in (t.lower_, t.lemma_.lower())}
    thr = threshold()

    concepts_in: dict[int, set[str]] = defaultdict(set)
    for key, idxs in sents_of.items():
        for i in idxs:
            concepts_in[i].add(key)

    results = {p.id: {"status": "not_mentioned", "score": None, "evidence": []} for p in props}
    for p in props:
        if sents_of.get(p.source):
            results[p.id]["status"] = "not_found"
    cand = sorted({i for p in props for i in sents_of.get(p.source, ())})
    if not cand:
        return results
    stmt_vecs = dict(zip([p.id for p in props], _embed([p.statement for p in props], drop)))
    sent_vecs = dict(zip(cand, _embed([sents[i] for i in cand], drop)))
    for i in cand:
        # 源概念要在这句里;概念 → 概念命题还要求目标概念也在这句里
        eligible = [p for p in props if p.source in concepts_in[i]
                    and (p.target is None or p.target in concepts_in[i])]
        scores = {p.id: _cos(sent_vecs[i], stmt_vecs[p.id]) for p in eligible}
        if not scores:
            continue
        for pid, sc in scores.items():                     # 记录每条命题的最高分,便于复核
            r = results[pid]
            if r["status"] != "similar" and (r["score"] is None or sc > r["score"]):
                r["score"], r["evidence"] = round(sc, 3), [sents[i]]
        best = max(scores, key=scores.get)                 # 一个句子只算给全局最像的那条命题
        sc = scores[best]
        r = results[best]
        if sc >= thr and (r["status"] != "similar" or sc > r["score"]):
            results[best] = {"status": "similar", "score": round(sc, 3), "evidence": [sents[i]]}
    return results
