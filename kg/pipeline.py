# -*- coding: utf-8 -*-
"""
按会话与阶段构建知识图谱:从 MySQL 取文本 → 抽取 → 写入 Neo4j。

每个主题会话有四个构建点(stage):
  recall   自由回忆转写稿(free_recalls,kind=baseline,status=done)
  phase1   本主题第 1 轮讨论中受试者自己的发言
  phase2   第 2 轮
  phase3   第 3 轮

讨论阶段只取受试者发言(role=participant,state 为 debate/summary):
agent 的发言来自它的材料,混进来就不是"受试者的知识"了;onboarding 是流程寒暄,搜索是另一种活动。

何时触发构建由流程控制方决定(不在本模块范围内),调用 build_for_session(sid, stage) 即可。

该主题有专家概念图(expert_maps/topic_<n>.yaml)时,构建后顺带对照打分,
结果写在 Graph 节点上(覆盖率、命中的命题等),见 expert.py。
"""
import hashlib
from datetime import datetime, timezone

import database as db
from materials import ROUNDS_PER_TOPIC

from . import expert, extract

PIPELINE_VERSION = "kg-0.2.0"
STAGES = ("recall", "phase1", "phase2", "phase3")
DISCUSSION_STATES = ("debate", "summary")


class NotReady(Exception):
    """该阶段还没有可用文本(未录音/转写未完成/该轮还没发言)。"""


def load_stage_text(sid: str, stage: str) -> tuple[str, dict]:
    """返回 (文本, 元数据)。元数据会写到 Neo4j 的 Graph 节点上。"""
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {STAGES}")
    s = db.get_session(sid)
    if not s:
        raise ValueError(f"session {sid} not found")
    topic = s["topic"]
    meta = {"session_id": sid, "participant": s.get("participant") or None,
            "topic": topic, "stage": stage}

    if stage == "recall":
        row = db.get_free_recall(sid, "baseline")
        if not row or row["status"] != "done" or not (row["transcript"] or "").strip():
            raise NotReady(f"no finished recall transcript for session {sid}"
                           + (f" (status: {row['status']})" if row else ""))
        meta.update(source="free_recall", source_id=row["id"])
        return row["transcript"], meta

    rnd = int(stage[-1])
    phase = (topic - 1) * ROUNDS_PER_TOPIC + rnd             # 与 app.py 一致的全局 phase 编号
    msgs = [m for m in db.get_messages(sid, phase)
            if m["role"] == "participant" and m["state"] in DISCUSSION_STATES]
    if not msgs:
        raise NotReady(f"no participant messages in phase {phase} for session {sid}")
    meta.update(source="discussion", phase=phase, messages=len(msgs))
    # 每条发言补上句末标点再拼接,避免上一条末尾和下一条开头被句法分析粘成一句
    parts = [m["content"].strip() for m in msgs if m["content"].strip()]
    return "\n\n".join(p if p[-1] in ".!?" else p + "." for p in parts), meta


def build_for_session(sid: str, stage: str, write: bool = True) -> dict:
    """构建一个阶段的图。write=False 时只抽取不写库(调试用)。
    抛 NotReady 表示该阶段还没有文本,调用方可稍后重试。"""
    text, meta = load_stage_text(sid, stage)
    graph = extract.build_graph(text)
    summary = {**meta, "concepts": len(graph.concepts), "relations": len(graph.relations),
               "emergent": sum(1 for c in graph.concepts.values() if c.status == "emergent")}
    emap = expert.load(meta["topic"], extract.get_ontology())
    sc = expert.score(graph, emap, None if stage == "recall" else int(stage[-1])) if emap else None
    if sc:
        summary["score"] = sc
    if not write:
        return {**summary, "graph": graph.to_dict()}

    from . import neo4j_store
    props = {
        **{k: v for k, v in meta.items() if k != "participant"},
        "participant_id": meta["participant"],
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text_chars": len(text),
        "sentences": graph.sentences,
        "ontology_version": graph.ontology_version,
        "pipeline_version": PIPELINE_VERSION,
        "spacy_model": extract.SPACY_MODEL,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "emergent_count": summary["emergent"],
    }
    if sc:
        # Neo4j 属性只能是标量或标量列表,命题按状态拆成 id 列表
        props.update(
            coverage_rate=sc["coverage_rate"],
            concepts_covered=sc["concepts_covered"],
            concepts_missing=sc["concepts_missing"],
            propositions_scored=sc["propositions_scored"],
            **{f"propositions_{s}": [p["id"] for p in sc["propositions"] if p["status"] == s]
               for s in expert.STATUS_ORDER},
        )
    out = neo4j_store.write_graph(graph, f"{sid}:{stage}", props, participant=meta["participant"])
    return {**summary, **out}


def build_all(sid: str, write: bool = True) -> list[dict]:
    """把一个会话里所有已就绪的阶段都(重新)构建一遍,未就绪的阶段记 skipped。"""
    results = []
    for stage in STAGES:
        try:
            results.append(build_for_session(sid, stage, write=write))
        except NotReady as e:
            results.append({"session_id": sid, "stage": stage, "skipped": str(e)})
    return results


def rebuild_existing() -> list[dict]:
    """重建 Neo4j 里已有的每一张图。改了 ontology.yaml 或专家图之后用,
    让新加进词表的概念在所有受试者的图里都变成 core、覆盖率按新图重算。"""
    from . import neo4j_store
    results = []
    for sid, stage in neo4j_store.list_graphs():
        try:
            r = build_for_session(sid, stage)
            results.append({k: r[k] for k in ("session_id", "stage", "concepts", "relations", "emergent")})
        except (NotReady, ValueError) as e:
            results.append({"session_id": sid, "stage": stage, "skipped": str(e)})
    return results
