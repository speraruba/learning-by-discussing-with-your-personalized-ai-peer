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

for stage in pipeline.STAGES:
    neo4j_store.delete_graph(f"{sid}:{stage}")
q("MATCH (p:Participant {id:'KG001'}) DETACH DELETE p")
check(not q("MATCH ()-[r]->() WHERE r.graph_id STARTS WITH $s RETURN r", s=sid), "cleanup")
neo4j_store.close()
print(f"\nALL {ok} CHECKS PASSED")
