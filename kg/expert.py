# -*- coding: utf-8 -*-
"""
专家概念图(expert_maps/topic_<n>.yaml)加载,以及受试者图与专家图的对照打分。

打分只用图上已有的信息,规则透明、可复核:
- 概念覆盖:受试者图里出现了哪些必学概念(required: false 的不计);
- 命题核对:只核对"概念 → 概念"的命题(目标是一段描述的命题图上无法逐边核对,只计数不打分)。
  每条命题的状态按优先级取:
    matched   同方向、关系类型在 accept 里、未否定 —— 受试者用自己的话说出了这条命题
    negated   同一对概念、关系类型在 accept 里,但受试者否认了它
    linked    两个概念之间有别的边(方向或关系类型不同)—— 连上了,但说法不同
    missing   两个概念之间没有边
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import ontology as onto_mod

DEFAULT_DIR = Path(__file__).parent / "expert_maps"
STATUS_ORDER = ("matched", "negated", "linked", "missing")


@dataclass
class Proposition:
    id: str
    source: str
    verb: str
    statement: str
    target: str | None = None          # 目标是必学概念时的 key
    target_text: str | None = None     # 目标是一段描述时的原文
    accept: list[str] = field(default_factory=list)

    @property
    def scorable(self) -> bool:
        return self.target is not None


@dataclass
class ExpertMap:
    topic: int
    title: str
    concepts: dict[str, dict]          # key -> {round, contributor, required}
    propositions: list[Proposition]

    def required(self, rnd: int | None = None) -> list[str]:
        return [k for k, v in self.concepts.items()
                if v.get("required", True) and (rnd is None or v.get("round") == rnd)]


def load(topic: int, onto, directory: str | Path | None = None) -> ExpertMap | None:
    """读取某主题的专家图并对照本体校验;该主题没有专家图时返回 None。"""
    path = Path(directory or os.environ.get("KG_EXPERT_DIR", DEFAULT_DIR)) / f"topic_{topic}.yaml"
    if not path.exists():
        return None
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    concepts = raw.get("concepts") or {}
    for key in concepts:
        if key not in onto.concept_class:
            raise ValueError(f"{path.name}: concept {key!r} is not in ontology.yaml")
    props = []
    for p in raw.get("propositions") or []:
        prop = Proposition(id=str(p["id"]), source=p["source"], verb=str(p.get("verb", "")),
                           statement=str(p.get("statement", "")), target=p.get("target"),
                           target_text=p.get("target_text"), accept=list(p.get("accept") or []))
        for key in (prop.source, prop.target):
            if key is not None and key not in concepts:
                raise ValueError(f"{path.name}: proposition {prop.id} uses {key!r}, not in concepts")
        if prop.scorable and not prop.accept:
            raise ValueError(f"{path.name}: proposition {prop.id} needs an accept list")
        if not prop.scorable and not prop.target_text:
            raise ValueError(f"{path.name}: proposition {prop.id} needs target or target_text")
        for rtype in prop.accept:
            if not onto_mod.valid_rel_type(rtype):
                raise ValueError(f"{path.name}: proposition {prop.id} has invalid type {rtype!r}")
        props.append(prop)
    return ExpertMap(int(raw.get("topic", topic)), str(raw.get("title", "")), dict(concepts), props)


def _prop_status(prop: Proposition, relations) -> tuple[str, list[str]]:
    best, evidence = "missing", []
    for r in relations:
        if {r.source, r.target} != {prop.source, prop.target}:
            continue
        same_dir = r.source == prop.source
        if same_dir and r.type in prop.accept:
            status = "negated" if r.negated else "matched"
        else:
            status = "linked"
        if STATUS_ORDER.index(status) < STATUS_ORDER.index(best):
            best, evidence = status, list(r.evidence)
    return best, evidence


def score(graph, emap: ExpertMap, rnd: int | None = None) -> dict:
    """受试者图(extract.KnowledgeGraph)对照专家图。rnd 给定时另算该轮必学概念的覆盖。"""
    present = set(graph.concepts)
    required = emap.required()
    covered = [k for k in required if k in present]

    props = []
    for p in emap.propositions:
        if not p.scorable:
            continue
        status, evidence = _prop_status(p, graph.relations)
        props.append({"id": p.id, "statement": p.statement, "status": status, "evidence": evidence})
    counts = {s: sum(1 for p in props if p["status"] == s) for s in STATUS_ORDER}

    out = {
        "topic": emap.topic,
        "required_concepts": len(required),
        "concepts_covered": covered,
        "concepts_missing": [k for k in required if k not in present],
        "coverage_rate": round(len(covered) / len(required), 3) if required else None,
        "propositions_scored": len(props),
        "propositions_unscored": sum(1 for p in emap.propositions if not p.scorable),
        "proposition_counts": counts,
        "propositions": props,
        "emergent_concepts": sorted(k for k, c in graph.concepts.items() if c.status == "emergent"),
    }
    if rnd is not None:
        rreq = emap.required(rnd)
        out["round"] = rnd
        out["round_concepts_covered"] = [k for k in rreq if k in present]
        out["round_concepts_missing"] = [k for k in rreq if k not in present]
    return out
