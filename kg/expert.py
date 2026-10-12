# -*- coding: utf-8 -*-
"""
专家概念图(expert_maps/topic_<n>.yaml)加载,以及受试者图与专家图的对照打分。

打分只用图上已有的信息,规则透明、可复核:
- 概念覆盖:受试者图里出现了哪些必学概念(required: false 的不计);
- 命题核对:只核对"概念 → 概念"的命题(目标是一段描述的命题图上无法逐边核对,只计数不打分)。
  每条命题的状态按优先级取:
    matched   同方向、关系类型在 accept 里、肯定/否定与材料一致 —— 受试者用自己的话说出了这条命题
    negated   同一对概念、关系类型在 accept 里,但受试者说了反话(材料肯定而他否认,或反之)
    linked    两个概念之间有别的边(方向或关系类型不同)—— 连上了,但说法不同
    similar   图上没有边,但有句子与命题足够相似(语义相似度兜底,见 similarity.py)
    missing   两个概念之间没有边
- 定义类命题(给了原文时):similar | not_found(提到了源概念但没有足够相似的句子)| not_mentioned。
"""
import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import ontology as onto_mod

DEFAULT_DIR = Path(__file__).parent / "expert_maps"
STATUS_ORDER = ("matched", "negated", "linked", "similar", "missing")
DEFINITION_STATUSES = ("similar", "not_found", "not_mentioned")


@dataclass
class Proposition:
    id: str
    source: str
    verb: str
    statement: str
    target: str | None = None          # 目标是必学概念时的 key
    target_text: str | None = None     # 目标是一段描述时的原文
    accept: list[str] = field(default_factory=list)
    negated: bool = False              # 材料里的命题本身是否定句("X does not measure Y")

    @property
    def scorable(self) -> bool:
        return self.target is not None


@dataclass
class ExpertMap:
    topic: int
    title: str
    concepts: dict[str, dict]          # key -> {round, contributor, required}
    propositions: list[Proposition]
    draft: bool = False                # 研究团队尚未审定(打分结果要带上这个标记)

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
                           target_text=p.get("target_text"), accept=list(p.get("accept") or []),
                           negated=bool(p.get("negated", False)))
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
    return ExpertMap(int(raw.get("topic", topic)), str(raw.get("title", "")), dict(concepts), props,
                     draft=bool(raw.get("draft", False)))


def _prop_status(prop: Proposition, relations) -> tuple[str, list[str]]:
    best, evidence = "missing", []
    for r in relations:
        if {r.source, r.target} != {prop.source, prop.target}:
            continue
        same_dir = r.source == prop.source
        if same_dir and r.type in prop.accept:
            # 受试者的肯定/否定与材料一致才算 matched;相反则是 negated(说了反话)
            status = "matched" if r.negated == prop.negated else "negated"
        else:
            status = "linked"
        if STATUS_ORDER.index(status) < STATUS_ORDER.index(best):
            best, evidence = status, list(r.evidence)
    return best, evidence


def score(graph, emap: ExpertMap, rnd: int | None = None, text: str | None = None, onto=None) -> dict:
    """受试者图(extract.KnowledgeGraph)对照专家图。rnd 给定时另算该轮必学概念的覆盖。
    给了原文 text 时再做语义相似度核对(similarity.py):定义类命题打分,
    概念 → 概念命题在图上 missing 的,句子足够相似则记为 similar。"""
    present = set(graph.concepts)
    required = emap.required()
    covered = [k for k in required if k in present]

    props = []
    for p in emap.propositions:
        if not p.scorable:
            continue
        status, evidence = _prop_status(p, graph.relations)
        props.append({"id": p.id, "statement": p.statement, "status": status, "evidence": evidence})

    sim_note, definitions = None, None
    if text is not None:
        from . import extract, similarity
        onto = onto or extract.get_ontology()
        by_id = {p.id: p for p in emap.propositions}
        to_check = [by_id[p["id"]] for p in props if p["status"] == "missing"]
        to_check += [p for p in emap.propositions if not p.scorable]
        try:
            sim = similarity.match(text, emap, onto, to_check)
            sim_note = f"{similarity.SIM_MODEL} (threshold {similarity.threshold():.2f})"
        except similarity.Unavailable as e:
            sim, sim_note = None, f"unavailable: {e}"
        if sim is not None:
            for p in props:
                r = sim.get(p["id"])
                if r and r["status"] == "similar":
                    p.update(status="similar", evidence=r["evidence"], similarity=r["score"])
            definitions = [{"id": p.id, "statement": p.statement, **sim[p.id]}
                           for p in emap.propositions if not p.scorable]
    counts = {s: sum(1 for p in props if p["status"] == s) for s in STATUS_ORDER}

    out = {
        "topic": emap.topic,
        "map_draft": emap.draft,
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
    if sim_note:
        out["similarity"] = sim_note
    if definitions is not None:
        out["definition_counts"] = {s: sum(1 for d in definitions if d["status"] == s)
                                    for s in DEFINITION_STATUSES}
        out["definitions"] = definitions
    if rnd is not None:
        rreq = emap.required(rnd)
        out["round"] = rnd
        out["round_concepts_covered"] = [k for k in rreq if k in present]
        out["round_concepts_missing"] = [k for k in rreq if k not in present]
    return out
