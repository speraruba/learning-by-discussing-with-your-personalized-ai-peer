"""知识图谱流水线回归测试。

第一部分只测抽取(不需要任何数据库);第二部分端到端:MySQL 测试库 → 抽取 → Neo4j,
仅在设置了 NEO4J_PASSWORD 时运行,结束后删除测试写入的图。

运行(务必用独立的 MySQL 测试库,脚本会先清空它):
    MYSQL_DB=lp_test_kg NEO4J_PASSWORD=... python test_kg.py
"""
import os
import sys

DB = os.environ.get("MYSQL_DB", "")
if not DB.startswith("lp_test"):
    sys.exit("请用独立测试库运行,例如 MYSQL_DB=lp_test_kg(脚本会清空该库)")

from kg.extract import build_graph, get_ontology        # noqa: E402

ok = 0
def check(cond, label):
    global ok
    assert cond, label
    ok += 1
    print("PASS", label)

def rels(text):
    g = build_graph(text)
    return {(r.source, r.type, r.target, r.negated) for r in g.relations}, g

# ---------------------------------------------------------------- 1. 抽取
onto = get_ontology()
check(onto.concept_class["ai"] == "Technology", "ontology loads")

r, g = rels("Um, so AI reduces memory and weakens reasoning skills.")
check(("ai", "REDUCES", "memory", False) in r, "SVO + ontology mapping")
check(("ai", "REDUCES", "reasoning", False) in r, "coordinated verb inherits subject")
check(g.concepts["ai"].cls == "Technology", "NER mislabel (AI as GPE) overridden by ontology")

r, _ = rels("Memory is weakened by cognitive offloading.")
check(("cognitive_offloading", "REDUCES", "memory", False) in r, "passive with agent flips direction")

r, _ = rels("Large language models are trained on huge amounts of text.")
check(("llm", "TRAINED_ON", "training_data", False) in r, "passive + prep; light noun 'amounts of'")

r, _ = rels("The Turing test does not measure real understanding.")
check(("turing_test", "MEASURES", "understanding", True) in r, "negation")

r, _ = rels("I don't think AI understands language.")
check(any(s == "ai" and t == "UNDERSTANDS" and neg for s, t, _, neg in r), "negation raised from 'don't think'")

r, _ = rels("Students rely on ChatGPT, which bypasses productive struggle.")
check(("learner", "DEPENDS_ON", "llm", False) in r, "prepositional predicate rely_on")
check(("llm", "REPLACES", "desirable_difficulty", False) in r, "relative clause subject")

_, g = rels("The article says AI creates cognitive dependency.")
check(g.relations and g.relations[0].stances == ["attributed"], "reported claim marked attributed")

r, _ = rels("AI learning is different from human learning.")
check(("ai learning", "DIFFERS_FROM", "learning", False) in r, "compound concept keeps contrast")

r, _ = rels("It can't really understand language. They use it a lot.")
check(not r, "pronoun subjects produce no relations (no guessing)")

_, g = rels("AI is a tool.")
check(g.relations[0].evidence == ["AI is a tool."], "evidence sentence kept")

check(build_graph("").relations == [] and build_graph("").concepts == {}, "empty text")

# ---- emergent(词表外)概念
_, g = rels("Testing, testing, testing. Yeah, so use the topics vocabulary. See any gaps.")
check(not [c for c in g.concepts.values() if c.status == "emergent"], "junk and meta-talk filtered")

r, g = rels("AI tutors help students.")
c = g.concepts.get("ai tutor")
check(c is not None and c.status == "emergent" and c.core_parts == ["ai"], "emergent concept linked to its core part")
check(("ai tutor", "ENHANCES", "learner", False) in r, "emergent concept takes part in relations")

_, g = rels("I like calculators.")
check("calculator" not in g.concepts, "emergent mentioned once and unconnected is dropped")
_, g = rels("Calculators are old. Calculators are everywhere.")
check(g.concepts.get("calculator") and g.concepts["calculator"].status == "emergent", "emergent mentioned twice is kept")

_, g = rels("Any gaps hurt learning.")
check(g.concepts.get("gap") and g.concepts["gap"].label == "gaps", "emergent label drops leading quantifier")
check(g.concepts["gap"].examples == ["Any gaps hurt learning."], "emergent concept keeps example sentence")
check(g.concepts["learning"].status == "core", "ontology concept is core")

# ---- 专家概念图对照
from kg import expert                                    # noqa: E402
emap = expert.load(2, onto)
check(emap is not None and len(emap.required()) == 8 and len(emap.required(2)) == 2, "expert map loads")
check(expert.load(99, onto) is None, "topic without expert map -> None")
emap1 = expert.load(1, onto)
check(emap1 is not None and emap1.draft and len(emap1.required()) == 8, "AGI draft map loads, flagged draft")

def statuses(text, rnd=None):
    sc = expert.score(build_graph(text), emap, rnd)
    return {p["id"]: p["status"] for p in sc["propositions"]}, sc

st, sc = statuses("Core delegation leads to performance reliance. "
                  "I don't think performance reliance improves independent capability.", rnd=2)
check(st["5.3"] == "matched", "proposition matched in participant's own words")
check(st["7.3"] == "negated", "denied proposition marked negated")
check(st["1.3"] == "missing", "unstated proposition missing")
check(sc["concepts_covered"] == ["core_delegation", "performance_reliance"] and sc["coverage_rate"] == 0.25,
      "coverage excludes non-required endpoint concept")
check(sc["round_concepts_missing"] == ["peripheral_delegation"], "per-round coverage")
st, _ = statuses("Performance reliance comes from core delegation.")
check(st["5.3"] == "linked", "connected differently -> linked")

def statuses1(text):
    return {p["id"]: p["status"] for p in expert.score(build_graph(text), emap1)["propositions"]}
check(statuses1("The Turing test does not measure understanding.")["3.3"] == "matched",
      "negative statement matched by a negative sentence")
check(statuses1("The Turing test can measure understanding.")["3.3"] == "negated",
      "negative statement contradicted by a positive sentence")

# ---- 语义相似度(定义类命题 + 图上 missing 的兜底)
from kg import similarity                                # noqa: E402
text = ("Cognitive labor is the mental effort a task needs. Cognitive labor can be done by a person or by AI. "
        "Extended mind is when a tool works like part of your brain. I like pizza and cognitive offloading is hard.")
sc = expert.score(build_graph(text), emap, text=text)
defs = {d["id"]: d for d in sc["definitions"]}
check(defs["3.1"]["status"] == "similar" and defs["3.2"]["status"] == "similar", "paraphrased definitions -> similar")
check(defs["3.1"]["evidence"] == ["Cognitive labor is the mental effort a task needs."], "similarity keeps evidence")
check(defs["4.1"]["status"] == "similar", "analogy paraphrase -> similar")
check(defs["2.1"]["status"] == "not_found", "concept mentioned but statement not said -> not_found")
check(defs["7.1"]["status"] == "not_mentioned", "concept never mentioned -> not_mentioned")
check(sc["definition_counts"]["similar"] == 3, "one sentence counts for one statement only")

text1 = "Behavioral evaluation measures AGI."
sc1 = expert.score(build_graph(text1), emap1, text=text1)
check({p["id"]: p["status"] for p in sc1["propositions"]}["2.3"] == "similar",
      "misparsed link statement caught by similarity")
check(sc1["map_draft"] is True, "score flags draft map")

_saved = (similarity.SIM_MODEL, similarity._backend)
similarity.SIM_MODEL, similarity._backend = "no_such_model_xyz", None
sc_na = expert.score(build_graph(text), emap, text=text)
similarity.SIM_MODEL, similarity._backend = _saved
check(sc_na["similarity"].startswith("unavailable") and "definitions" not in sc_na,
      "missing similarity model -> scoring still works")

# ---------------------------------------------------------------- 2. 端到端
if not os.environ.get("NEO4J_PASSWORD"):
    print(f"\n{ok} extraction checks passed; NEO4J_PASSWORD not set, skipping end-to-end")
    sys.exit(0)

import pymysql                                           # noqa: E402
import database as db                                    # noqa: E402
_c = pymysql.connect(host=db.DB_HOST, port=db.DB_PORT, user=db.DB_USER, password=db.DB_PASSWORD)
_c.cursor().execute(f"DROP DATABASE IF EXISTS `{DB}`")
_c.close()
db.init_db()

from kg import pipeline, neo4j_store                     # noqa: E402

s = db.create_session("KG001", topic=1, phase=1)
sid = s["id"]
try:
    pipeline.build_for_session(sid, "recall")
    check(False, "recall without transcript should be NotReady")
except pipeline.NotReady:
    check(True, "recall without transcript -> NotReady")

rid, up = db.add_free_recall(sid, 1, f"{sid}/baseline.webm", 100)
db.set_free_recall_transcript(rid, up, "AI is a tool. AI reduces memory. Students rely on ChatGPT.")
db.add_message(sid, 1, "debate", "participant", "I think AI weakens reasoning")
db.add_message(sid, 1, "debate", "agent", "AGI enhances creativity.")        # agent 发言不应入图
db.add_message(sid, 1, "summary", "participant", "Memory is weakened by cognitive offloading.")

results = pipeline.build_all(sid)
by_stage = {r["stage"]: r for r in results}
check(by_stage["recall"]["relations"] == 3, "recall graph built")
check(by_stage["phase1"]["relations"] == 2, "phase1 graph built from participant turns only")
check("skipped" in by_stage["phase2"], "phase2 not ready -> skipped")

def q(cypher, **kw):
    with neo4j_store.driver().session(database=neo4j_store.NEO4J_DATABASE) as ses:
        return [r.data() for r in ses.run(cypher, **kw)]

gid = f"{sid}:recall"
counts = lambda: q("MATCH (g:Graph {id:$g})-[m:MENTIONS]->() WITH g, count(m) AS m "
                   "OPTIONAL MATCH ()-[r {graph_id:$g}]->() RETURN m, count(r) AS r", g=gid)[0]
before = counts()
check(before == {"m": 5, "r": 3}, f"neo4j contents {before}")
check(q("MATCH (:Participant {id:'KG001'})-[:HAS_GRAPH]->(g:Graph) RETURN count(g) AS n")[0]["n"] == 2,
      "participant linked to both graphs")
check(not q("MATCH ()-[r {graph_id:$g}]->() WHERE r.evidence IS NULL RETURN r", g=gid), "edges carry evidence")
check(not q("MATCH (:Concept {key:'agi'})<-[:MENTIONS]-(g:Graph) WHERE g.session_id=$s RETURN g", s=sid),
      "agent text excluded")

pipeline.build_for_session(sid, "recall")
check(counts() == before, "rebuild is idempotent")

db.set_free_recall_transcript(rid, up, "AI is a tool.")
pipeline.build_for_session(sid, "recall")
check(counts() == {"m": 2, "r": 1}, "rebuild replaces old edges")

# 主题 2 有专家图:构建时顺带打分,写到 Graph 节点上;emergent 概念可被汇总
s2 = db.create_session("KG001", topic=2, phase=4)
sid2 = s2["id"]
rid2, up2 = db.add_free_recall(sid2, 2, f"{sid2}/baseline.webm", 100)
db.set_free_recall_transcript(rid2, up2, "Core delegation leads to performance reliance. "
                              "AI tutors help students. Calculators are old. Calculators are everywhere. "
                              "Cognitive labor is the mental effort a task needs.")
out = pipeline.build_for_session(sid2, "recall")
check(out["score"]["proposition_counts"]["matched"] == 1, "build returns expert-map score")
g2 = q("MATCH (g:Graph {id:$g}) RETURN g.coverage_rate AS cr, g.propositions_matched AS pm, "
       "g.emergent_count AS ec", g=f"{sid2}:recall")[0]
check(g2 == {"cr": 0.5, "pm": ["5.3"], "ec": 2}, f"score stored on graph node {g2}")
check(q("MATCH (g:Graph {id:$g}) RETURN g.definitions_similar AS d", g=f"{sid2}:recall")[0]["d"] == ["3.1"],
      "similar definitions stored on graph node")
cands = {c["key"]: c for c in neo4j_store.emergent_candidates(topic=2)}
check({"ai tutor", "calculator"} <= set(cands) and cands["ai tutor"]["participants"] == 1
      and cands["ai tutor"]["examples"] == ["AI tutors help students."], "emergent candidates report")
rep = {x["stage"]: x for x in neo4j_store.session_report(sid2)}
check(rep["recall"]["matched"] == ["5.3"] and rep["recall"]["relations"] == 3, "session report")

for s_ in (sid, sid2):
    for stage in pipeline.STAGES:
        neo4j_store.delete_graph(f"{s_}:{stage}")
q("MATCH (p:Participant {id:'KG001'}) DETACH DELETE p")
check(not q("MATCH ()-[r]->() WHERE r.graph_id STARTS WITH $s OR r.graph_id STARTS WITH $s2 RETURN r",
            s=sid, s2=sid2), "cleanup")
neo4j_store.close()
print(f"\nALL {ok} CHECKS PASSED")
