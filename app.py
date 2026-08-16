# -*- coding: utf-8 -*-
"""
实验后端服务。

状态机(阅读只在第一阶段进行,后续阶段直接讨论):
reading(仅阶段1,受试者阅读) → onboarding(agent 介绍研究并鼓励积极发言,受试者确认后继续)
→ debate(agent 分享己方要点后辩论,计数认知冲突;同时把话题引向下一阶段学习目标)
→ summary(引导受试者总结) → search(阶段1/2结束后:自主搜索环节,search agent 联网检索权威资料)
→ causal(end-search 后:展示 AI 推测的受试者因果关联图,受试者评分 0-10)
→ 评分后进入下一阶段 debate(agent 开场衔接) / 最后阶段结束 finished

运行: uvicorn app:app --reload --port 8000
"""
import json

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path

import database as db
import agent
from materials import PHASES, CONFLICTS_REQUIRED

app = FastAPI(title="Learning Partner Agent")
db.init_db()


@app.exception_handler(RuntimeError)
def runtime_err(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=503, content={"detail": str(exc)})

TOTAL_PHASES = len(PHASES)


def phase_cfg(phase: int) -> dict:
    return PHASES[phase - 1]


def next_phase_cfg(phase: int) -> dict | None:
    """下一阶段的完整配置(学习目标 + 双方材料);当前阶段的讨论要自然地把受试者引向它。
    最后一阶段返回 None。agent 只把它当作前瞻上下文,不得据此发言。"""
    return PHASES[phase] if phase < TOTAL_PHASES else None


# onboarding 开场白(英文存档文本;前端按界面语言展示本地化版本)
ONBOARDING_INTRO = (
    "Hi! Great job finishing the article. Before we start, let me quickly introduce how this study "
    "works: it has three discussion phases, and each phase focuses on one question about AI and "
    "intelligence. You and I have read different articles on the topic, so we may well see things "
    "differently -- that's exactly the point of discussing. Throughout our conversation, please "
    "speak up actively, share your own opinions boldly, and feel free to question or push back on "
    "anything I say. Don't be shy -- there are no wrong answers here. "
    "Are you ready to start the first discussion? Just let me know!"
)

# 搜索环节开场白(英文存档文本;前端按界面语言展示本地化版本)
SEARCH_INTRO = (
    "Nice work finishing that discussion! Before the next one starts, you now have some free time to "
    "look things up. I'm a search assistant: ask me anything you're curious about, and I'll search "
    "authoritative sources on the web and report back what they say, with references. You decide what "
    "to explore -- anything that came up in the discussion, anything you doubted, anything you want to "
    "verify. When you feel ready, click the button above to return to your learning partner. "
    "So -- what would you like to look up first?"
)


class StartReq(BaseModel):
    participant: str = ""


class MsgReq(BaseModel):
    content: str
    lang: str = "en"          # 受试者当前界面语言(en/zh),agent 以该语言回复


class LangReq(BaseModel):
    lang: str = "en"


class RegisterReq(BaseModel):
    username: str
    email: str
    password: str
    age: int | None = None
    education: str = ""
    major: str = ""
    ai_level: int = 0
    ai_principle_level: int = 0
    ai_frequency: str = ""
    ai_purpose: list[str] = []
    ai_purpose_other: str = ""
    ai_used_for_learning: bool = False


class LoginReq(BaseModel):
    username: str
    password: str


def _ai_purpose(raw) -> list[str]:
    """ai_purpose 存于 MySQL JSON 列,驱动可能返回字符串或已解析的列表。"""
    if not raw:
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    return list(raw) if isinstance(raw, list) else []


def user_view(u: dict) -> dict:
    return {
        "id": u["id"],
        "username": u["username"],
        "email": u["email"],
        "age": u["age"],
        "education": u["education"],
        "major": u["major"],
        "ai_level": u["ai_level"],
        "ai_principle_level": u["ai_principle_level"],
        "ai_frequency": u["ai_frequency"],
        "ai_purpose": _ai_purpose(u["ai_purpose"]),
        "ai_purpose_other": u["ai_purpose_other"] or "",
        "ai_used_for_learning": bool(u["ai_used_for_learning"]),
    }


@app.post("/api/register")
def register(req: RegisterReq):
    username = req.username.strip()
    email = req.email.strip()
    if not username or not email or not req.password:
        raise HTTPException(400, "Username, email and password are required")
    if len(req.password) < 6:
        raise HTTPException(400, "Password must be at least 6 characters")
    if not (0 <= req.ai_level <= 10):
        raise HTTPException(400, "AI familiarity must be between 0 and 10")
    if not (0 <= req.ai_principle_level <= 10):
        raise HTTPException(400, "AI principles familiarity must be between 0 and 10")
    if db.get_user_by_username(username):
        raise HTTPException(400, "Username already taken")
    if db.get_user_by_email(email):
        raise HTTPException(400, "Email already registered")
    purposes = [p.strip() for p in req.ai_purpose if p.strip()]
    # 只有勾选了 other 才保留自填内容
    other = req.ai_purpose_other.strip()[:255] if "other" in purposes else ""
    if "other" in purposes and not other:
        raise HTTPException(400, "Please specify your other use of AI")
    user = db.create_user(username, email, req.password, req.age,
                          req.education.strip(), req.major.strip(), req.ai_level, req.ai_principle_level,
                          req.ai_frequency.strip(), json.dumps(purposes), other,
                          req.ai_used_for_learning)
    return user_view(user)


@app.post("/api/login")
def login(req: LoginReq):
    user = db.verify_user(req.username.strip(), req.password)
    if not user:
        raise HTTPException(401, "Incorrect username or password")
    return user_view(user)


def session_view(s: dict) -> dict:
    """返回给前端的会话状态(不含 agent 的材料,防泄露)。"""
    out = {
        "session_id": s["id"],
        "phase": s["phase"],
        "state": s["state"],
        "conflicts": s["conflicts"],
        "conflicts_required": CONFLICTS_REQUIRED,
        "total_phases": TOTAL_PHASES,
    }
    if s["state"] != "finished":
        cfg = phase_cfg(s["phase"])
        # 同时下发中英两版,前端切换语言无需再请求服务端
        out["topic"] = cfg["topic"]
        out["topic_zh"] = cfg.get("topic_zh", "")
        out["learning_goal"] = cfg["learning_goal"]
        out["learning_goal_zh"] = cfg.get("learning_goal_zh", "")
        if s["state"] == "reading":
            out["article"] = cfg["participant_article"]
            out["article_zh"] = cfg.get("participant_article_zh", "")
        if s["state"] == "causal":
            g = db.get_latest_causal_graph(s["id"])
            if g:
                out["causal_graph"] = g["graph"]
    return out


@app.post("/api/session")
def start_session(req: StartReq):
    s = db.create_session(req.participant)
    db.add_message(s["id"], 1, "reading", "system", "Session started; entering Phase 1 reading stage")
    return session_view(s)


@app.get("/api/session/{sid}")
def get_session(sid: str):
    s = db.get_session(sid)
    if not s:
        raise HTTPException(404, "session not found")
    return session_view(s)


@app.post("/api/session/{sid}/done-reading")
def done_reading(sid: str):
    """受试者点击"我读完了" → 进入 onboarding:agent 介绍研究并鼓励积极发言。"""
    s = _require(sid, state="reading")
    db.update_session(sid, state="onboarding")
    db.add_message(sid, s["phase"], "onboarding", "system",
                   "Participant finished reading; entering onboarding stage")
    # 开场白为固定脚本(保证所有受试者一致),入库存档;前端展示本地化版本
    db.add_message(sid, s["phase"], "onboarding", "agent", ONBOARDING_INTRO, meta={"scripted": True})
    return {**session_view(db.get_session(sid)), "prompt": ONBOARDING_INTRO}


@app.post("/api/session/{sid}/message")
def post_message(sid: str, req: MsgReq):
    """受试者发言 → agent 按当前环节回应。返回本轮 agent 的一条或多条消息。"""
    s = _require(sid)
    state, phase = s["state"], s["phase"]
    cfg = phase_cfg(phase)

    if state not in ("onboarding", "debate", "summary"):
        raise HTTPException(400, f"Messages are not accepted in the current stage ({state})")

    db.add_message(sid, phase, state, "participant", req.content)
    history = db.get_messages(sid, phase)
    agent_msgs = []
    ng = next_phase_cfg(phase)

    if state == "onboarding":
        # 引导环节:回应疑问、鼓励积极发言;受试者明确确认(advance=true)后 agent 分享己方要点并直接开辩
        r = agent.generate_reply(cfg, "onboarding", history, 0, CONFLICTS_REQUIRED, next_cfg=ng, lang=req.lang)
        db.add_message(sid, phase, "onboarding", "agent", r["reply"],
                       meta={"reason": r["reason"], "advance": r["advance"]})
        agent_msgs.append(r["reply"])
        if r["advance"]:
            db.update_session(sid, state="debate")

    elif state == "debate":
        # 辩论的同时,提示词层引导话题走向下一阶段学习目标(next_cfg)
        r = agent.generate_reply(cfg, "debate", history, s["conflicts"], CONFLICTS_REQUIRED, next_cfg=ng, lang=req.lang)
        conflicts = s["conflicts"] + (1 if r["conflict_triggered"] else 0)
        db.add_message(sid, phase, "debate", "agent", r["reply"],
                       conflict=r["conflict_triggered"], meta={"reason": r["reason"]})
        agent_msgs.append(r["reply"])
        db.update_session(sid, conflicts=conflicts)

        if conflicts >= CONFLICTS_REQUIRED:
            # 达到3次认知冲突 → 追加一条"引导总结"消息,进入总结环节
            history = db.get_messages(sid, phase)
            r2 = agent.generate_reply(cfg, "summary_invite", history, conflicts, CONFLICTS_REQUIRED, lang=req.lang)
            db.add_message(sid, phase, "summary", "agent", r2["reply"], meta={"reason": r2["reason"]})
            agent_msgs.append(r2["reply"])
            db.update_session(sid, state="summary")

    elif state == "summary":
        # 受试者提交总结 → agent 收尾 → 直接开启下一阶段讨论(不再阅读)或结束
        r = agent.generate_reply(cfg, "summary_close", history, s["conflicts"], CONFLICTS_REQUIRED, lang=req.lang)
        db.add_message(sid, phase, "summary", "agent", r["reply"], meta={"reason": r["reason"]})
        agent_msgs.append(r["reply"])

        if phase < TOTAL_PHASES:
            # 阶段 1/2 结束 → 进入自主搜索环节(search agent),之后由 /end-search 开启下一阶段讨论
            new_phase = phase + 1
            db.update_session(sid, phase=new_phase, state="search", conflicts=0)
            db.add_message(sid, new_phase, "search", "system",
                           f"Phase {phase} finished; entering self-directed search stage before Phase {new_phase}")
            # 搜索环节开场白为固定脚本(所有受试者一致),入库存档;前端展示本地化版本
            db.add_message(sid, new_phase, "search", "agent", SEARCH_INTRO, meta={"scripted": True})
        else:
            db.update_session(sid, state="finished")
            db.add_message(sid, phase, "finished", "system", "Experiment fully completed")

    return {**session_view(db.get_session(sid)), "agent_messages": agent_msgs}


@app.post("/api/session/{sid}/search-message")
def post_search_message(sid: str, req: MsgReq):
    """搜索环节:受试者向 search agent 提问 → 联网检索权威资料后回复。
    交互记录入 messages(state='search'),实际搜索词另存 search_queries 表。"""
    s = _require(sid, state="search")
    phase = s["phase"]
    cfg = phase_cfg(phase)
    db.add_message(sid, phase, "search", "participant", req.content)
    history = [m for m in db.get_messages(sid, phase) if m["state"] == "search"]
    r = agent.generate_search_reply(cfg["topic"], cfg["learning_goal"], history, lang=req.lang)
    db.add_message(sid, phase, "search", "agent", r["reply"],
                   meta={"queries": r["queries"], "sources": r["sources"]})
    for q in r["queries"]:
        db.add_search_query(sid, phase, q)
    return {**session_view(db.get_session(sid)),
            "agent_messages": [r["reply"]], "sources": r["sources"]}


def _transcript(sid: str) -> str:
    """给因果图提取用的全程记录:辩论 + 搜索的全部发言,标注阶段/环节/角色。"""
    lines = []
    for m in db.get_messages(sid):
        if m["role"] not in ("participant", "agent"):
            continue
        who = "PARTICIPANT" if m["role"] == "participant" else (
            "SEARCH-ASSISTANT" if m["state"] == "search" else "LEARNING-PARTNER")
        lines.append(f"[phase {m['phase']} | {m['state']}] {who}: {m['content']}")
    qs = [q["query"] for q in db.get_search_queries(sid)]
    if qs:
        lines.append("[web searches actually issued] " + "; ".join(qs))
    return "\n".join(lines)


@app.post("/api/session/{sid}/end-search")
def end_search(sid: str):
    """受试者点击"结束搜索" → 生成 AI 推测的因果关联图,进入 causal 评分环节。"""
    s = _require(sid, state="search")
    phase = s["phase"]
    cfg = phase_cfg(phase)
    graph = agent.generate_causal_graph(cfg["topic"], _transcript(sid))
    db.add_causal_graph(sid, phase, graph)
    db.update_session(sid, state="causal")
    db.add_message(sid, phase, "causal", "system",
                   "Search stage ended; showing AI-predicted causal diagram for rating")
    return session_view(db.get_session(sid))


class RatingReq(BaseModel):
    score: int
    lang: str = "en"


@app.post("/api/session/{sid}/causal-rating")
def causal_rating(sid: str, req: RatingReq):
    """受试者对因果图评分(0-10) → 入库 → agent 开场并进入本阶段辩论。"""
    if not (0 <= req.score <= 10):
        raise HTTPException(400, "score must be between 0 and 10")
    s = _require(sid, state="causal")
    phase = s["phase"]
    cfg = phase_cfg(phase)
    g = db.get_latest_causal_graph(sid)
    if not g:
        raise HTTPException(500, "no causal graph found for this session")
    db.set_causal_rating(g["id"], req.score)
    db.add_message(sid, phase, "causal", "participant", f"(causal diagram rating: {req.score}/10)",
                   meta={"causal_graph_id": g["id"], "rating": req.score})
    db.update_session(sid, state="debate")
    db.add_message(sid, phase, "debate", "system",
                   f"Causal diagram rated; entering Phase {phase} discussion stage (no new reading)")
    # agent 开场:用上一阶段的讨论历史作衔接上下文,引出本阶段学习目标
    prev_history = db.get_messages(sid, phase - 1)
    r = agent.generate_reply(cfg, "phase_open", prev_history, 0, CONFLICTS_REQUIRED,
                             next_cfg=next_phase_cfg(phase), lang=req.lang)
    db.add_message(sid, phase, "debate", "agent", r["reply"], meta={"reason": r["reason"]})
    return {**session_view(db.get_session(sid)), "agent_messages": [r["reply"]]}


@app.get("/api/session/{sid}/history")
def history(sid: str):
    """研究者导出:完整对话历史(含冲突标记与模型判定理由)。"""
    _require(sid)
    return {"messages": db.get_messages(sid), "search_queries": db.get_search_queries(sid),
            "causal_graphs": db.get_causal_graphs(sid)}


def _require(sid: str, state: str | None = None) -> dict:
    s = db.get_session(sid)
    if not s:
        raise HTTPException(404, "session not found")
    if state and s["state"] != state:
        raise HTTPException(400, f"Current state is {s['state']}; this action requires {state}")
    return s


# 前端页面
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
def index():
    return FileResponse(static_dir / "index.html")
