# -*- coding: utf-8 -*-
"""
LLM 只用在规则覆盖不到的地方(2026-10-23 组会决定:预设命题用传统 NLP,受试者自己提出的新内容用 LLM)。

两个用途:
- extract_new     从受试者的话里抽取"预设命题以外"的新命题(源概念 → 关系 → 目标概念)。
- judge_prepared  可选的中间核对:规则判为没说到的预设命题,让 LLM 再判断受试者是否表达过/否认过。

防编造:每条结果必须带 evidence(受试者原话的逐字摘录),程序核对它确实出现在原文里,
对不上的一律丢弃并计数。关系类型只能从本体里选(写进 Cypher 前还会再校验)。

配置沿用研究系统本身的 OpenAI 设置(agent.py):OPENAI_API_KEY、OPENAI_MODEL;
KG_LLM_MODEL 可单独指定本模块用的模型。测试时用 set_client() 注入假客户端。
"""
import json
import os
import re

from . import extract
from . import ontology as onto_mod

MODEL = os.environ.get("KG_LLM_MODEL") or os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")

_client = None


class Unavailable(Exception):
    """没有可用的 LLM(未装 openai / 未设 OPENAI_API_KEY)。"""


def set_client(client):
    """注入客户端(测试用假客户端);需提供 chat.completions.create(...)。"""
    global _client
    _client = client


def client():
    global _client
    if _client is None:
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise Unavailable("OPENAI_API_KEY is not set")
        try:
            from openai import OpenAI
        except ImportError as e:
            raise Unavailable("pip install openai") from e
        _client = OpenAI(api_key=key, timeout=float(os.environ.get("OPENAI_TIMEOUT", "60")),
                         max_retries=int(os.environ.get("OPENAI_MAX_RETRIES", "3")))
    return _client


def _ask_json(system: str, user: str) -> dict:
    resp = client().chat.completions.create(
        model=MODEL,
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
    )
    try:
        return json.loads(resp.choices[0].message.content or "{}")
    except (json.JSONDecodeError, AttributeError, IndexError):
        return {}


# ---------------------------------------------------------------- 证据核对
def _norm(s: str) -> str:
    s = (s or "").replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
    return re.sub(r"\s+", " ", s).strip().lower().strip(" .,;:!?\"'")


def verified(evidence: str, text: str) -> bool:
    """evidence 必须是原文(或去掉 um/uh 后的原文)里的逐字片段,至少 3 个词。"""
    ev = _norm(evidence)
    if len(ev.split()) < 3:
        return False
    return ev in _norm(text) or ev in _norm(extract.preprocess(text))


# ---------------------------------------------------------------- 概念/关系映射
def _concept_key(label: str, onto) -> tuple[str, bool]:
    """LLM 给的概念名 → (key, 是否词表内)。词表内的走同义词表,否则归一化成 emergent key。"""
    nlp = extract.get_nlp()
    doc = nlp(label)
    for form in extract.make_term_normalizer(nlp)(label):
        key = onto.terms.get(form)
        if key:
            return key, True
    key = extract.normalize_span(doc) or label.strip().lower()
    return key, key in onto.concept_class


def _relation_types(onto) -> list[str]:
    return sorted(set(onto.triggers.values()))


def _prepared_pairs(emap) -> set[frozenset]:
    return {frozenset((p.source, p.target)) for p in emap.propositions if p.target}


# ---------------------------------------------------------------- 1. 新命题抽取
_EXTRACT_SYSTEM = """You extract the ideas a study participant expressed, as statements of the form
source concept -> relation -> target concept.

Rules:
- Only extract what the participant actually said. Never add your own knowledge or fill in gaps.
- Skip anything that restates one of the PREPARED statements listed below; those are scored separately.
- Use a listed concept name when the participant's concept matches it; otherwise use their short noun phrase.
- relation must be one of the listed relation types, or RELATED_TO if none fits.
- negated is true if the participant denies the statement.
- stance is "attributed" if they only report someone else's claim ("the article says"), otherwise "asserted".
- If they change their mind, output only their final position, quoting the later sentence.
- evidence must be copied word for word from the participant's text (one sentence or clause).

Return JSON: {"statements": [{"source": "...", "relation": "...", "target": "...",
"negated": false, "stance": "asserted", "evidence": "..."}]}. Return {"statements": []} if there are none."""


def extract_new(text: str, emap, onto) -> dict:
    """返回 {"statements": [...], "dropped": n}。每条已核对证据、映射到本体 key、去掉了预设命题。"""
    concept_names = sorted({onto.concept_label[k] for k in onto.concept_class})
    rels = _relation_types(onto)
    prepared = "\n".join(f"- {p.statement}" for p in emap.propositions if p.target) if emap else "(none)"
    user = (f"PREPARED statements (skip these):\n{prepared}\n\n"
            f"Listed concepts: {', '.join(concept_names)}\n\n"
            f"Relation types: {', '.join(rels)}, RELATED_TO\n\n"
            f"Participant's text:\n\"\"\"\n{text}\n\"\"\"")
    raw = _ask_json(_EXTRACT_SYSTEM, user).get("statements") or []

    skip_pairs = _prepared_pairs(emap) if emap else set()
    out, dropped = [], 0
    for s in raw if isinstance(raw, list) else []:
        if not isinstance(s, dict) or not s.get("source") or not s.get("target"):
            dropped += 1
            continue
        ev = str(s.get("evidence", ""))
        if not verified(ev, text):
            dropped += 1                       # 证据对不上原文:当作编造,丢弃
            continue
        src, src_in = _concept_key(str(s["source"]), onto)
        tgt, tgt_in = _concept_key(str(s["target"]), onto)
        if not src or not tgt or src == tgt or frozenset((src, tgt)) in skip_pairs:
            continue
        rel = str(s.get("relation", "")).strip().upper().replace(" ", "_")
        if rel not in rels:
            rel = onto_mod.UNTYPED
        out.append({
            "source": src, "source_label": str(s["source"]).strip(), "source_in_ontology": src_in,
            "target": tgt, "target_label": str(s["target"]).strip(), "target_in_ontology": tgt_in,
            "relation": rel, "negated": bool(s.get("negated", False)),
            "stance": "attributed" if s.get("stance") == "attributed" else "asserted",
            "evidence": ev.strip(),
        })
    return {"statements": out, "dropped": dropped}


# ---------------------------------------------------------------- 2. 预设命题的 LLM 核对
_JUDGE_SYSTEM = """You check whether a study participant expressed specific statements.

For each statement, decide:
- "said": the participant expressed this idea, in any wording.
- "denied": the participant rejected it (use their final position if they changed their mind).
- "not_said": otherwise. Being related or on topic is not enough.

For "said" and "denied", evidence must be copied word for word from the participant's text.
Return JSON: {"results": [{"id": "...", "status": "said|denied|not_said", "evidence": "..."}]}."""


def judge_prepared(text: str, props) -> dict[str, dict]:
    """props: expert.Proposition 列表。返回 {id: {status, evidence}};证据对不上原文的记为 not_said。"""
    if not props:
        return {}
    listing = "\n".join(f"{p.id}: {p.statement}" for p in props)
    user = f"Statements:\n{listing}\n\nParticipant's text:\n\"\"\"\n{text}\n\"\"\""
    raw = _ask_json(_JUDGE_SYSTEM, user).get("results") or []
    want = {p.id for p in props}
    out = {pid: {"status": "not_said", "evidence": []} for pid in want}
    for r in raw if isinstance(raw, list) else []:
        if not isinstance(r, dict) or str(r.get("id")) not in want:
            continue
        status, ev = r.get("status"), str(r.get("evidence", ""))
        if status in ("said", "denied") and verified(ev, text):
            out[str(r["id"])] = {"status": status, "evidence": [ev.strip()]}
    return out
