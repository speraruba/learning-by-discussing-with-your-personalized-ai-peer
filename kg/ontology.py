# -*- coding: utf-8 -*-
"""
本体(ontology)加载与校验。本体内容在 ontology.yaml,这里只负责:
- 校验结构(类别存在、关系类型名合法、同一写法不归属两个概念、同一触发词不归属两种关系);
- 把概念同义写法按与正文相同的方式归一化,构造匹配用的词表;
- 提供"谓词 → 关系类型"的映射。

关系类型名会直接作为 Neo4j 的关系类型写入(Cypher 不支持参数化关系类型),
因此必须在这里用正则严格校验,杜绝注入。
"""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_PATH = Path(__file__).parent / "ontology.yaml"
UNCLASSIFIED = "Unclassified"
UNTYPED = "RELATED_TO"

_REL_TYPE_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,63}$")
_CLASS_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}$")
_KEY_RE = re.compile(r"^[a-z0-9_]{1,64}$")


@dataclass
class Ontology:
    version: str
    classes: dict[str, str]
    concept_class: dict[str, str]                     # concept key -> class
    concept_label: dict[str, str]                     # concept key -> 首个 term,作展示名
    terms: dict[tuple[str, ...], str] = field(default_factory=dict)   # 归一化词序列 -> concept key
    triggers: dict[str, str] = field(default_factory=dict)            # 谓词 -> 关系类型
    keep_unclassified_concepts: bool = True
    keep_untyped_relations: bool = True

    @property
    def max_term_len(self) -> int:
        return max((len(t) for t in self.terms), default=0)

    def relation_type(self, predicate: str) -> str | None:
        """谓词(如 reduce、rely_on)→ 关系类型,未登记返回 None。
        带介词的谓词必须整体登记,不退回到动词本身:介词常改变语义
        ("learn_through experience" 不是 LEARNS experience)。"""
        return self.triggers.get(predicate)


def load(path: str | Path | None = None, normalize_term=None) -> Ontology:
    """加载并校验本体。normalize_term(str) -> tuple[str, ...] 由调用方提供
    (需与正文使用同一个 spaCy 管线,否则词形还原结果对不上)。"""
    path = Path(path or os.environ.get("KG_ONTOLOGY", DEFAULT_PATH))
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}

    classes = raw.get("classes") or {}
    for c in classes:
        if not _CLASS_RE.match(c):
            raise ValueError(f"ontology: invalid class name {c!r}")
    if UNCLASSIFIED in classes:
        raise ValueError(f"ontology: {UNCLASSIFIED!r} is reserved")

    policy = raw.get("policy") or {}
    onto = Ontology(
        version=str(raw.get("version", "0")),
        classes=dict(classes),
        concept_class={}, concept_label={},
        keep_unclassified_concepts=bool(policy.get("keep_unclassified_concepts", True)),
        keep_untyped_relations=bool(policy.get("keep_untyped_relations", True)),
    )

    for key, spec in (raw.get("concepts") or {}).items():
        if not _KEY_RE.match(key):
            raise ValueError(f"ontology: concept key {key!r} must match {_KEY_RE.pattern}")
        cls = spec.get("class")
        if cls not in classes:
            raise ValueError(f"ontology: concept {key!r} has unknown class {cls!r}")
        terms = spec.get("terms") or []
        if not terms:
            raise ValueError(f"ontology: concept {key!r} has no terms")
        onto.concept_class[key] = cls
        onto.concept_label[key] = str(terms[0])
        for term in terms:
            for norm in (normalize_term(str(term)) if normalize_term else [tuple(str(term).lower().split())]):
                if not norm:
                    continue
                other = onto.terms.get(norm)
                if other and other != key:
                    raise ValueError(f"ontology: term {term!r} maps to both {other!r} and {key!r}")
                onto.terms[norm] = key

    for rtype, spec in (raw.get("relations") or {}).items():
        if not _REL_TYPE_RE.match(rtype):
            raise ValueError(f"ontology: relation type {rtype!r} must match {_REL_TYPE_RE.pattern}")
        for trig in spec.get("triggers") or []:
            trig = str(trig).strip().lower().replace(" ", "_")
            other = onto.triggers.get(trig)
            if other and other != rtype:
                raise ValueError(f"ontology: trigger {trig!r} maps to both {other} and {rtype}")
            onto.triggers[trig] = rtype
    if UNTYPED in (raw.get("relations") or {}):
        raise ValueError(f"ontology: {UNTYPED!r} is reserved for unmapped predicates")
    return onto


def valid_rel_type(rtype: str) -> bool:
    return bool(_REL_TYPE_RE.match(rtype))
