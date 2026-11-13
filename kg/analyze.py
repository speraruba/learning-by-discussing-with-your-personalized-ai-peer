# -*- coding: utf-8 -*-
"""
一段受试者文本的完整分析,命令行、入库(pipeline.py)和评测(evaluate.py)共用,保证三者行为一致。

  1. 规则抽取建图(extract.py)
  2. 对照专家图打分:图上核对 + 语义相似度,可选 LLM 核对(expert.py / similarity.py / llm.py)
  3. 给图上每条边标记:对应哪条预设命题(prepared_id),或是受试者自己提出的新命题(None)
  4. 可选:用 LLM 抽取预设之外的新命题,作为 extractor="llm" 的边并进图里

组会决定(2026-10-23):预设命题用传统 NLP,新内容用 LLM。默认两项 LLM 都关闭,
用 --llm(或环境变量 KG_LLM=1)打开;没有 OPENAI_API_KEY 时自动跳过并在结果里注明。
"""
import os

from . import expert, extract
from .extract import Concept, Relation


def llm_enabled_by_default() -> bool:
    return os.environ.get("KG_LLM", "") == "1"


def label_prepared(graph, emap) -> None:
    """每条边对应的预设命题 id(同一对概念、任一方向);对不上的是新命题。"""
    pairs = {frozenset((p.source, p.target)): p.id for p in emap.propositions if p.target} if emap else {}
    for r in graph.relations:
        r.prepared_id = pairs.get(frozenset((r.source, r.target)))


def add_llm_statements(graph, statements: list[dict], onto) -> None:
    """把 LLM 抽到的新命题并进图:缺的概念补上(词表外的记为 emergent),边标 extractor=llm。"""
    for s in statements:
        for key, label, in_onto in ((s["source"], s["source_label"], s["source_in_ontology"]),
                                    (s["target"], s["target_label"], s["target_in_ontology"])):
            c = graph.concepts.get(key)
            if c is None:
                c = graph.concepts[key] = Concept(
                    key=key, label=onto.concept_label.get(key, label), in_ontology=in_onto,
                    cls=onto.concept_class.get(key, "Unclassified"),
                    status="core" if in_onto else "emergent")
            c.count = max(c.count, 1)
            if "llm" not in c.sources:
                c.sources.append("llm")
            if s["evidence"] not in c.examples and len(c.examples) < 2:
                c.examples.append(s["evidence"])
        graph.relations.append(Relation(
            s["source"], s["target"], s["relation"], s["negated"], 1, [], [], [s["stance"]],
            [s["evidence"]], extractor="llm", prepared_id=None))


def analyze(text: str, topic: int | None, rnd: int | None = None,
            llm_check: bool = False, llm_new: bool = False) -> dict:
    """返回 {"graph", "score"(无专家图时为 None), "llm_new"(未启用时为 None)}。"""
    onto = extract.get_ontology()
    graph = extract.build_graph(text, onto)
    emap = expert.load(topic, onto) if topic else None
    sc = expert.score(graph, emap, rnd, text=text, onto=onto, llm_check=llm_check) if emap else None
    label_prepared(graph, emap)

    llm_info = None
    if llm_new:
        from . import llm
        try:
            res = llm.extract_new(text, emap, onto)
            add_llm_statements(graph, res["statements"], onto)
            llm_info = {"model": llm.MODEL, "statements": res["statements"], "dropped_unverified": res["dropped"]}
        except llm.Unavailable as e:
            llm_info = {"model": None, "unavailable": str(e), "statements": [], "dropped_unverified": 0}
    return {"graph": graph, "score": sc, "llm_new": llm_info}
