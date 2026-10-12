# -*- coding: utf-8 -*-
"""
把抽取结果写入 Neo4j。

图模型:
  (:Participant {id})-[:HAS_GRAPH]->(:Graph {id, session_id, topic, stage, ...})
  (:Graph)-[:MENTIONS {count, surface_forms, sources, ner_labels, examples}]->
      (:Concept {key, label, class, status, core_parts, ...})      status: core | emergent
  (:Concept)-[:<关系类型> {graph_id, negated, count, predicates, modals, stances, evidence}]->(:Concept)

- Concept 节点全局共享(同一个 key 只有一个节点),方便跨受试者/跨阶段比较;
  每张图"有哪些概念"由 MENTIONS 表示,"有哪些关系"由边上的 graph_id 区分。
- Graph.id = "{session_id}:{stage}"。同一阶段重复构建会先删掉旧的 MENTIONS 与关系边再重建,
  整个过程在一个事务里完成,幂等。
- 关系类型名来自本体并已用正则校验(Cypher 不能参数化关系类型),写入前再校验一次。

环境变量: NEO4J_URI(默认 bolt://localhost:7687)/ NEO4J_USER(默认 neo4j)/
          NEO4J_PASSWORD / NEO4J_DATABASE(默认 neo4j)
"""
import os
from collections import defaultdict

from . import ontology as onto_mod

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.environ.get("NEO4J_DATABASE", "neo4j")

_driver = None
_constraints_ready = False

CONSTRAINTS = (
    "CREATE CONSTRAINT concept_key IF NOT EXISTS FOR (c:Concept) REQUIRE c.key IS UNIQUE",
    "CREATE CONSTRAINT graph_id IF NOT EXISTS FOR (g:Graph) REQUIRE g.id IS UNIQUE",
    "CREATE CONSTRAINT participant_id IF NOT EXISTS FOR (p:Participant) REQUIRE p.id IS UNIQUE",
)


def driver():
    global _driver
    if _driver is None:
        if not NEO4J_PASSWORD:
            raise RuntimeError("NEO4J_PASSWORD is not set; see kg/README.md")
        from neo4j import GraphDatabase
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver


def close():
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


def ensure_constraints():
    global _constraints_ready
    if _constraints_ready:
        return
    with driver().session(database=NEO4J_DATABASE) as s:
        for stmt in CONSTRAINTS:
            s.run(stmt).consume()
    _constraints_ready = True


def _write_tx(tx, graph_id: str, props: dict, participant: str | None,
              concepts: list[dict], rels_by_type: dict[str, list[dict]]):
    # 1. 删除这张图旧的关系边与 MENTIONS(重建幂等)
    tx.run(
        "MATCH (g:Graph {id: $gid})-[:MENTIONS]->(c:Concept)-[r]->(:Concept) "
        "WHERE r.graph_id = $gid DELETE r",
        gid=graph_id,
    ).consume()
    tx.run("MATCH (g:Graph {id: $gid})-[m:MENTIONS]->() DELETE m", gid=graph_id).consume()

    # 2. 图节点 + 受试者
    tx.run("MERGE (g:Graph {id: $gid}) SET g += $props", gid=graph_id, props=props).consume()
    if participant:
        tx.run(
            "MERGE (p:Participant {id: $pid}) WITH p MATCH (g:Graph {id: $gid}) "
            "MERGE (p)-[:HAS_GRAPH]->(g)",
            pid=participant, gid=graph_id,
        ).consume()

    # 3. 概念 + MENTIONS
    tx.run(
        "MATCH (g:Graph {id: $gid}) "
        "UNWIND $concepts AS c "
        "MERGE (n:Concept {key: c.key}) "
        "SET n.label = c.label, n.class = c.class, n.in_ontology = c.in_ontology, n.head = c.head, "
        "    n.status = c.status, n.core_parts = c.core_parts "
        "MERGE (g)-[m:MENTIONS]->(n) "
        "SET m.count = c.count, m.surface_forms = c.surface_forms, "
        "    m.sources = c.sources, m.ner_labels = c.ner_labels, m.examples = c.examples",
        gid=graph_id, concepts=concepts,
    ).consume()

    # 4. 关系边(按类型分批;类型名已校验)
    for rtype, rels in rels_by_type.items():
        if not onto_mod.valid_rel_type(rtype):
            raise ValueError(f"refusing to write invalid relationship type {rtype!r}")
        tx.run(
            "UNWIND $rels AS r "
            "MATCH (a:Concept {key: r.source}), (b:Concept {key: r.target}) "
            f"CREATE (a)-[x:`{rtype}`]->(b) "
            "SET x.graph_id = $gid, x.negated = r.negated, x.count = r.count, "
            "    x.predicates = r.predicates, x.modals = r.modals, "
            "    x.stances = r.stances, x.evidence = r.evidence",
            gid=graph_id, rels=rels,
        ).consume()


def write_graph(graph, graph_id: str, props: dict, participant: str | None = None) -> dict:
    """写入(或覆盖)一张图。props 写到 Graph 节点上(session_id/topic/stage/...)。"""
    ensure_constraints()
    concepts = [{
        "key": c.key, "label": c.label, "class": c.cls, "in_ontology": c.in_ontology,
        "head": c.head, "count": c.count, "surface_forms": c.surface_forms,
        "sources": c.sources, "ner_labels": c.ner_labels,
        "status": c.status, "core_parts": c.core_parts, "examples": c.examples,
    } for c in graph.concepts.values()]
    rels_by_type: dict[str, list[dict]] = defaultdict(list)
    for r in graph.relations:
        rels_by_type[r.type].append({
            "source": r.source, "target": r.target, "negated": r.negated, "count": r.count,
            "predicates": r.predicates, "modals": r.modals, "stances": r.stances,
            "evidence": r.evidence,
        })
    props = {k: v for k, v in props.items() if v is not None}
    with driver().session(database=NEO4J_DATABASE) as s:
        s.execute_write(_write_tx, graph_id, props, participant, concepts, dict(rels_by_type))
    return {"graph_id": graph_id, "concepts": len(concepts), "relations": len(graph.relations)}


def _read(cypher: str, **params) -> list[dict]:
    with driver().session(database=NEO4J_DATABASE) as s:
        return [r.data() for r in s.run(cypher, **params)]


def list_graphs() -> list[tuple[str, str]]:
    """库里所有图的 (session_id, stage)。"""
    rows = _read("MATCH (g:Graph) WHERE g.session_id IS NOT NULL AND g.stage IS NOT NULL "
                 "RETURN g.session_id AS sid, g.stage AS stage ORDER BY sid, stage")
    return [(r["sid"], r["stage"]) for r in rows]


def emergent_candidates(topic: int | None = None, min_participants: int = 1) -> list[dict]:
    """跨受试者汇总词表外(emergent)概念,供研究者决定哪些加进 ontology.yaml。
    按提到它的受试者人数、再按总提及次数排序。"""
    rows = _read(
        "MATCH (g:Graph)-[m:MENTIONS]->(c:Concept {status: 'emergent'}) "
        "WHERE $topic IS NULL OR g.topic = $topic "
        "WITH c, count(DISTINCT g) AS graphs, "
        "     count(DISTINCT coalesce(g.participant_id, g.session_id)) AS participants, "
        "     sum(m.count) AS mentions, collect(DISTINCT g.stage) AS stages, "
        "     collect(m.examples) AS ex, collect(m.surface_forms) AS sf "
        "WHERE participants >= $minp "
        "RETURN c.key AS key, c.label AS label, c.core_parts AS core_parts, "
        "       participants, graphs, mentions, stages, ex, sf "
        "ORDER BY participants DESC, mentions DESC, key",
        topic=topic, minp=min_participants,
    )
    for r in rows:
        r["examples"] = list(dict.fromkeys(e for lst in r.pop("ex") for e in (lst or [])))[:3]
        r["surface_forms"] = list(dict.fromkeys(s for lst in r.pop("sf") for s in (lst or [])))
    return rows


def session_report(session_id: str) -> list[dict]:
    """一个会话各阶段的图摘要(覆盖率、命题、emergent 数),按阶段排序。"""
    return _read(
        "MATCH (g:Graph {session_id: $sid}) "
        "OPTIONAL MATCH (g)-[m:MENTIONS]->(:Concept) "
        "WITH g, count(m) AS concepts "
        "OPTIONAL MATCH ()-[r {graph_id: g.id}]->() "
        "RETURN g.stage AS stage, g.topic AS topic, concepts, count(r) AS relations, "
        "       g.emergent_count AS emergent, g.coverage_rate AS coverage_rate, "
        "       g.concepts_covered AS concepts_covered, g.propositions_matched AS matched, "
        "       g.propositions_negated AS negated, g.propositions_linked AS linked, "
        "       g.propositions_similar AS similar, g.propositions_scored AS scored, "
        "       g.definitions_similar AS definitions_similar, g.map_draft AS map_draft "
        "ORDER BY stage",
        sid=session_id,
    )


def delete_graph(graph_id: str):
    """删除一张图(关系边、MENTIONS、Graph 节点)。共享的 Concept 节点保留。"""
    def tx_fn(tx):
        tx.run(
            "MATCH (g:Graph {id: $gid})-[:MENTIONS]->(:Concept)-[r]->(:Concept) "
            "WHERE r.graph_id = $gid DELETE r", gid=graph_id,
        ).consume()
        tx.run("MATCH (g:Graph {id: $gid}) DETACH DELETE g", gid=graph_id).consume()
    with driver().session(database=NEO4J_DATABASE) as s:
        s.execute_write(tx_fn)
