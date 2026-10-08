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
"""
import hashlib
from datetime import datetime, timezone

import database as db
from materials import ROUNDS_PER_TOPIC

from . import extract

PIPELINE_VERSION = "kg-0.1.0"
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
    summary = {**meta, "concepts": len(graph.concepts), "relations": len(graph.relations)}
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
    }
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
