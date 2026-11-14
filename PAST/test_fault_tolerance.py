"""断线容错回归测试:用假 agent 模拟模型调用成功/失败,不消耗任何 API 额度。

运行(务必用独立的测试库,脚本会先清空它):
    MYSQL_DB=lp_test OPENAI_API_KEY=sk-test python test_fault_tolerance.py
"""
import os
import sys

import pymysql
from fastapi.testclient import TestClient

DB = os.environ.get("MYSQL_DB", "")
if not DB.startswith("lp_test"):
    sys.exit("请用独立测试库运行,例如 MYSQL_DB=lp_test(脚本会清空该库)")

import database as db                                    # noqa: E402  (先校验库名再连接)
_c = pymysql.connect(host=db.DB_HOST, port=db.DB_PORT, user=db.DB_USER, password=db.DB_PASSWORD)
_c.cursor().execute(f"DROP DATABASE IF EXISTS `{DB}`")    # 每次从干净状态开始
_c.close()

import agent, app                                        # noqa: E402  (import app 会建库建表)

FAIL = {"on": False}
def fake_reply(cfg, state, history, conflicts, required, next_cfg=None, profile=None):
    if FAIL["on"]: raise RuntimeError("simulated LLM/network failure")
    return {"reply": f"[agent:{state}]", "conflict_triggered": state == "debate",
            "reason": "test", "advance": True}
def fake_search(topic, goal, history):
    if FAIL["on"]: raise RuntimeError("simulated search failure")
    return {"reply": "[search reply]", "queries": ["q"], "sources": [{"title":"T","url":"http://x"}]}
def fake_graph(topic, transcript):
    if FAIL["on"]: raise RuntimeError("simulated graph failure")
    return {"nodes":[{"id":"n1","label":"A"},{"id":"n2","label":"B"}],
            "edges":[{"source":"n1","target":"n2"}]}
agent.generate_reply, agent.generate_search_reply, agent.generate_causal_graph = fake_reply, fake_search, fake_graph

c = TestClient(app.app, raise_server_exceptions=False)
PID = "FT001"
c.post("/api/participant", json={"participant_id": PID, "name": "Fault Tester",
       "birth_month": 5, "birth_day": 17, "birth_year": 2000, "age": 26, "gender": "female",
       "education_years": "16", "native_english": False, "first_language": "Mandarin",
       "english_age": 8, "hispanic": False, "race": "asian",
       "major": "Information Sciences", "second_major": "", "minor": "Statistics",
       "ails": {k: 4 for k in ("AW_1","AW_8","AW_9","US_1","US_3","US_5",
                               "EV_2","EV_3","EV_6","ET_1","ET_2","ET_5")},
       "llm_use_frequency": "almost_daily", "llm_use_purposes": ["personal_learning", "information"],
       "llm_use_other": "",
       "llm_used_for_learning": True, "llm_learning_frequency": "weekly_several_times",
       "llm_learning_methods": ["explanations", "practice"], "llm_learning_other": ""})
sid = c.post("/api/session", json={"participant": PID}).json()["session_id"]
ok = lambda label, cond: print(("PASS  " if cond else "FAIL  ") + label)

# --- done-reading 幂等(受试者双击 / 响应丢失后重发)
r1 = c.post(f"/api/session/{sid}/done-reading"); r2 = c.post(f"/api/session/{sid}/done-reading")
ok("done-reading 重复调用幂等", r1.status_code == 200 and r2.status_code == 200
   and r2.json()["state"] == "onboarding"
   and sum(1 for m in db.get_messages(sid) if m["role"]=="agent") == 1)

# --- 发言途中模型/网络失败 → 受试者发言留库,标记为待补
FAIL["on"] = True
r = c.post(f"/api/session/{sid}/message", json={"content": "I am ready"})
ok("模型失败返回 5xx", r.status_code >= 500)
res = c.post("/api/participant/resolve", json={"participant_id": PID, "name": "Fault Tester"}).json()
ok("resolve 报告 pending=chat", res["pending"] == "chat")
ok("受试者发言没有丢", any(m["content"]=="I am ready" for m in res["messages"]))

# --- 受试者重发同一句(前端把话还回输入框的情形)→ 不重复入库
r = c.post(f"/api/session/{sid}/message", json={"content": "I am ready"})
ok("重发时仍失败", r.status_code >= 500)
same = [m for m in db.get_messages(sid) if m["content"] == "I am ready"]
ok("同一句话没有被重复入库", len(same) == 1)

# --- 网络恢复 → retry-turn 补齐那一轮
FAIL["on"] = False
r = c.post(f"/api/session/{sid}/retry-turn").json()
ok("retry-turn 补上 agent 回复", r["agent_messages"] == ["[agent:onboarding]"] and r["state"] == "debate")
r = c.post(f"/api/session/{sid}/retry-turn").json()
ok("retry-turn 幂等(无待补则空转)", r["agent_messages"] == [])
ok("resolve 不再有 pending", c.post("/api/participant/resolve", json={"participant_id": PID, "name": "Fault Tester"}).json()["pending"] is None)

# --- 辩论到总结,进入本轮搜索环节(phase 不变)
for i in range(3):
    c.post(f"/api/session/{sid}/message", json={"content": f"point {i}"})
st = c.post(f"/api/session/{sid}/message", json={"content": "my summary"}).json()
ok("第 1 轮结束进入搜索环节", st["state"] == "search" and st["phase"] == 1)

# --- 搜索环节断线
FAIL["on"] = True
c.post(f"/api/session/{sid}/search-message", json={"content": "what is AGI"})
res = c.post("/api/participant/resolve", json={"participant_id": PID, "name": "Fault Tester"}).json()
ok("搜索环节 pending=search", res["pending"] == "search")
c.post(f"/api/session/{sid}/search-message", json={"content": "what is AGI"})
ok("搜索提问没有重复入库",
   len([m for m in db.get_messages(sid) if m["content"]=="what is AGI"]) == 1)
FAIL["on"] = False
r = c.post(f"/api/session/{sid}/retry-turn").json()
ok("retry-turn 补上搜索回复", r["agent_messages"] == ["[search reply]"])

# --- end-search:开启下一轮讨论(agent 开场);重复提交 → 409(前端据此重新同步)
r1 = c.post(f"/api/session/{sid}/end-search"); r2 = c.post(f"/api/session/{sid}/end-search")
ok("end-search 进入第 2 轮讨论", r1.status_code == 200 and r1.json()["state"] == "debate"
   and r1.json()["phase"] == 2 and r1.json()["agent_messages"] == ["[agent:phase_open]"])
ok("end-search 重复提交返回 409", r2.status_code == 409)

# --- 换设备/浏览器崩溃:只凭 id 恢复到第 2 轮讨论
res = c.post("/api/participant/resolve", json={"participant_id": "ft001", "name": "fault tester"}).json()
ok("重新输入 id 恢复到第 2 轮讨论", res["session"]["phase"] == 2 and res["session"]["state"] == "debate")
ok("完整记录可重放", len(res["messages"]) >= 10)


# --- 跑完一轮讨论(3 次冲突 + 总结)并结束搜索,返回 end-search 的响应
def run_round():
    for i in range(3):
        c.post(f"/api/session/{sid}/message", json={"content": f"point {i}"})
    c.post(f"/api/session/{sid}/message", json={"content": "my summary"})
    return c.post(f"/api/session/{sid}/end-search").json()


st = run_round()
ok("进入主题 1 第 3 轮讨论", st["state"] == "debate" and st["phase"] == 3)
st = run_round()
ok("主题 1 结束进入休息页", st["state"] == "rest" and st["phase"] == 3)

# --- 休息页继续 → 新建主题 2 的独立会话并进入阅读;重复提交幂等
r1 = c.post(f"/api/session/{sid}/end-rest"); r2 = c.post(f"/api/session/{sid}/end-rest")
ok("休息后进入主题 2 阅读", r1.status_code == 200 and r1.json()["state"] == "reading"
   and r1.json()["phase"] == 4 and "article" in r1.json())
sid_topic1, sid = sid, r1.json()["session_id"]
ok("主题 2 是独立的新会话", sid != sid_topic1)
ok("end-rest 重复调用幂等(返回同一新会话)", r2.status_code == 200
   and r2.json()["state"] == "reading" and r2.json()["session_id"] == sid)
ok("主题 1 会话已收尾(done)", db.get_session(sid_topic1)["state"] == "done")
ok("新会话不含主题 1 的对话记录", db.get_messages(sid) is not None
   and all(m["phase"] >= 4 for m in db.get_messages(sid)))
res = c.post("/api/participant/resolve", json={"participant_id": PID, "name": "Fault Tester"}).json()
ok("resolve 恢复到主题 2 的新会话", res["session"]["session_id"] == sid
   and all(m["phase"] >= 4 for m in res["messages"]))

# --- 主题 2 读完 → agent 直接开场进入讨论(不再 onboarding)
r1 = c.post(f"/api/session/{sid}/done-reading")
ok("主题 2 读完直接开场讨论", r1.status_code == 200 and r1.json()["state"] == "debate"
   and r1.json()["phase"] == 4 and r1.json()["agent_messages"] == ["[agent:topic_open]"])
r2 = c.post(f"/api/session/{sid}/done-reading")
ok("主题 2 done-reading 重复调用幂等", r2.status_code == 200 and r2.json()["state"] == "debate")

# --- 主题 2 三轮讨论 → 考试页
st = run_round()
ok("进入主题 2 第 2 轮讨论", st["state"] == "debate" and st["phase"] == 5)
st = run_round()
ok("进入主题 2 第 3 轮讨论", st["state"] == "debate" and st["phase"] == 6)
st = run_round()
ok("主题 2 结束进入考试页", st["state"] == "exam" and st["phase"] == 6
   and len(st.get("exam_questions", [])) == len(app.EXAM_QUESTIONS))

# --- 考试:漏答被拒;提交后结束;重复提交幂等
r = c.post(f"/api/session/{sid}/exam",
           json={"answers": ["a"] * (len(app.EXAM_QUESTIONS) - 1) + [""]})
ok("考试漏答被拒", r.status_code == 400)
answers = [f"answer {i}" for i in range(len(app.EXAM_QUESTIONS))]
r1 = c.post(f"/api/session/{sid}/exam", json={"answers": answers})
r2 = c.post(f"/api/session/{sid}/exam", json={"answers": answers})
ok("考试提交后实验结束", r1.status_code == 200 and r1.json()["state"] == "finished")
ok("考试重复提交幂等", r2.status_code == 200 and r2.json()["state"] == "finished")
ok("考试答案只记一次", [a["answer"] for a in db.get_exam_answers(sid)] == answers)

# --- 完成后恢复:会话状态为 finished(前端直接进再见页)
res = c.post("/api/participant/resolve", json={"participant_id": PID, "name": "Fault Tester"}).json()
ok("完成后恢复为 finished", res["session"]["state"] == "finished")

print("\n所有断线容错检查通过。")
