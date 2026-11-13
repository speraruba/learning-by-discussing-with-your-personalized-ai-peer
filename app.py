# -*- coding: utf-8 -*-
"""
实验后端服务。

状态机(start 页之后,两个主题,每个主题:阅读→(讨论→搜索)×3):
主题 1: reading(阅读文章 1) → onboarding(agent 介绍研究,受试者确认后继续)
  → [debate(计冲突) → summary(总结) → search(自主搜索)] ×3 → rest(休息页)
主题 2: reading(阅读文章 2) → topic_open(agent 直接开场)
  → [debate → summary → search] ×3 → exam(考试页) → finished(结束再见)

phase 为全局讨论轮编号 1-6:主题 = (phase-1)//3+1,轮次 = (phase-1)%3+1。
一个主题对应一条独立 session:主题 1 的会话在休息页结束时标记 done,
end-rest 为受试者新建主题 2 的会话(phase 从 4 开始),两个主题的对话记录彼此隔离。
每轮讨论累计 CONFLICTS_REQUIRED 次认知冲突后进入总结,总结后进入本轮搜索环节;
end-search 开启下一轮讨论,或(第 3/6 轮后)进入休息页/考试页。

运行: uvicorn app:app --reload --port 8000
"""
import json
import re

from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pathlib import Path

import database as db
import agent
import transcribe
from materials import (PHASES, CONFLICTS_REQUIRED, TOPICS, ROUNDS_PER_TOPIC,
                       TOTAL_TOPICS, EXAM_QUESTIONS, article_for)

app = FastAPI(title="Learning Partner Agent")
db.init_db()


@app.exception_handler(RuntimeError)
def runtime_err(request, exc):
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=503, content={"detail": str(exc)})

TOTAL_PHASES = len(PHASES)          # 6 = 2 个主题 × 每主题 3 轮讨论


def phase_cfg(phase: int) -> dict:
    return PHASES[phase - 1]


def topic_of(phase: int) -> int:
    return (phase - 1) // ROUNDS_PER_TOPIC + 1


def round_of(phase: int) -> int:
    return (phase - 1) % ROUNDS_PER_TOPIC + 1


def topic_cfg(phase: int) -> dict:
    return TOPICS[topic_of(phase) - 1]


def next_phase_cfg(phase: int) -> dict | None:
    """同一主题内下一轮的完整配置(学习目标 + 双方材料);当前轮的讨论要自然地把受试者引向它。
    每个主题的最后一轮返回 None(不跨主题引导)。agent 只把它当作前瞻上下文,不得据此发言。"""
    return PHASES[phase] if round_of(phase) < ROUNDS_PER_TOPIC else None


# onboarding 开场白(英文存档文本;前端按界面语言展示本地化版本)
ONBOARDING_INTRO = (
    "Hi! Great job finishing the article. Before we start, let me quickly introduce how this works: "
    "for this topic we will have three rounds of discussion, each focusing on one question, and after "
    "each round you will get some free time to search for anything you are curious about. You and I "
    "have read different articles on the topic, so we may well see things differently -- that's "
    "exactly the point of discussing. Throughout our conversation, please speak up actively, share "
    "your own opinions boldly, and feel free to question or push back on anything I say. Don't be "
    "shy -- there are no wrong answers here. "
    "Are you ready to start the first discussion? Just let me know!"
)

# 搜索环节开场白(英文存档文本;前端按界面语言展示本地化版本)
SEARCH_INTRO = (
    "Nice work finishing that discussion! You now have some free time to look things up. I'm a search "
    "assistant: ask me anything you're curious about, and I'll search authoritative sources on the web "
    "and report back what they say, with references. You decide what to explore -- anything that came "
    "up in the discussion, anything you doubted, anything you want to verify. When you feel ready, "
    "click the button above to continue. So -- what would you like to look up first?"
)


class StartReq(BaseModel):
    participant: str = ""


class MsgReq(BaseModel):
    content: str


class ParticipantIdReq(BaseModel):
    participant_id: str
    name: str = ""


EDUCATION_YEARS = {"1-7.5", "8", "9-11.5", "12", "12.5-15.5", "16", "18", "20"}
RACES = {"native_american", "asian", "pacific_islander", "black", "white", "multiple"}
# AI Literacy Scale 条目 id(顺序与呈现顺序一致)
AILS_ITEMS = ["AW_1", "AW_8", "AW_9", "US_1", "US_3", "US_5",
              "EV_2", "EV_3", "EV_6", "ET_1", "ET_2", "ET_5"]
# 反向计分条目(表 5 中标注 R):计入总分前按 8-原始分 反转(7→1,6→2,5→3,4→4)
AILS_REVERSED = {"AW_8", "US_3", "ET_2"}
LLM_FREQUENCIES = {"never", "monthly_several_times", "weekly_several_times", "almost_daily"}
LLM_LEARNING_FREQUENCIES = {"never", "monthly_several_times", "weekly_several_times", "almost_daily"}
LLM_PURPOSES = {"work", "coursework", "personal_learning", "writing", "programming", "brainstorming", "information", "personal_tasks", "other"}
LLM_LEARNING_METHODS = {"explanations", "examples", "practice", "feedback", "summaries", "planning", "translation", "other"}


class EnrollReq(BaseModel):
    participant_id: str
    name: str = ""
    birth_month: int
    birth_day: int
    birth_year: int
    age: int
    gender: str                      # male | female
    education_years: str             # EDUCATION_YEARS 之一
    native_english: bool
    first_language: str = ""         # native_english=false 时必填
    english_age: int | None = None   # native_english=false 时必填
    hispanic: bool
    race: str                        # RACES 之一
    major: str                       # 主修专业
    second_major: str = ""           # 第二主修专业(如有)
    minor: str = ""                  # 辅修(如有)
    ails: dict[str, int]             # AILS 12 条目原始作答,1-7
    llm_use_frequency: str
    llm_use_purposes: list[str] = []
    llm_use_other: str = ""
    llm_used_for_learning: bool
    llm_learning_frequency: str | None = None
    llm_learning_methods: list[str] = []
    llm_learning_other: str = ""


def participant_view(u: dict) -> dict:
    return {
        "id": u["id"],
        "participant_id": u["participant_id"],
        "name": u["name"] or "",
    }


PID_RE = re.compile(r"^[A-Za-z0-9._-]{3,64}$")
PID_TAKEN = "This Participant ID has already been used. Please check with the researcher."


def _clean_name(raw: str) -> str:
    name = " ".join(raw.split())            # 压掉多余空白
    if not name:
        raise HTTPException(400, "Name is required")
    if len(name) > 64:
        raise HTTPException(400, "Name must be at most 64 characters")
    return name


def _clean_pid(raw: str) -> str:
    """校验并规范化 participant id。唯一性大小写不敏感(列排序规则为 utf8mb4_unicode_ci)。"""
    pid = raw.strip()
    if not pid:
        raise HTTPException(400, "Participant ID is required")
    if not PID_RE.match(pid):
        raise HTTPException(400, "Participant ID must be 3-64 characters: letters, digits, . _ or -")
    return pid


@app.post("/api/participant/resolve")
def resolve_participant(req: ParticipantIdReq):
    """首页"登录":姓名 + participant id。
    - 新 id → new=true,前端带着姓名走知情同意书 + 人口学信息页,提交后建档开始;
    - 已存在的 id → 核对姓名后返回受试者、上次会话与对话记录:
      已完成全部流程的直接进再见页,否则恢复到中断的环节。
    """
    pid = _clean_pid(req.participant_id)
    name = _clean_name(req.name)
    p = db.get_participant(pid)
    if not p:
        return {"participant_id": pid, "name": name, "new": True}
    stored = (p["name"] or "").strip()
    if not stored:
        # 姓名字段上线前注册的老受试者:首次带姓名进入时补记
        db.set_participant_name(p["id"], name)
        p = db.get_participant(pid)
    elif stored.lower() != name.lower():
        raise HTTPException(400, "Name and Participant ID do not match. Please check with the researcher.")
    out = {"participant_id": p["participant_id"], "new": False,
           "participant": participant_view(p), "session": None, "messages": []}
    s = db.get_latest_session(p["participant_id"])
    if s:
        out["session"] = session_view(s)
        out["messages"] = transcript_view(s["id"])
        out["pending"] = pending_state(s)     # 有悬空回合 → 前端自动补齐
    return out


@app.post("/api/participant")
def enroll(req: EnrollReq):
    """知情同意 + 人口学信息提交 → 建立受试者记录(participant_id 唯一)。"""
    pid = _clean_pid(req.participant_id)
    name = _clean_name(req.name)
    import datetime as _dt
    try:
        birth = _dt.date(req.birth_year, req.birth_month, req.birth_day)
    except ValueError:
        raise HTTPException(400, "Please enter a valid date of birth")
    if not (1900 <= req.birth_year <= _dt.date.today().year):
        raise HTTPException(400, "Please enter a valid year of birth")
    if not (15 <= req.age <= 120):
        raise HTTPException(400, "Please enter a valid age")
    if req.gender not in ("male", "female"):
        raise HTTPException(400, "Please select your gender")
    if req.education_years not in EDUCATION_YEARS:
        raise HTTPException(400, "Please select your years of education")
    if req.race not in RACES:
        raise HTTPException(400, "Please select an ethnic or racial category")
    first_language, english_age = "", None
    if not req.native_english:
        first_language = " ".join(req.first_language.split())[:64]
        if not first_language:
            raise HTTPException(400, "Please enter your first language")
        if req.english_age is None or not (0 <= req.english_age <= 120):
            raise HTTPException(400, "Please enter the age at which you began to acquire English")
        english_age = req.english_age
    major = " ".join(req.major.split())[:100]
    if not major:
        raise HTTPException(400, "Please enter your major")
    second_major = " ".join(req.second_major.split())[:100] or None
    minor = " ".join(req.minor.split())[:100] or None
    ails_cols, ails_score = {}, 0
    for item in AILS_ITEMS:
        v = req.ails.get(item)
        if not isinstance(v, int) or not (1 <= v <= 7):
            raise HTTPException(400, "Please answer all background questions (1-7)")
        ails_cols["ails_" + item.lower()] = v            # 每列存原始作答
        ails_score += (8 - v) if item in AILS_REVERSED else v
    if req.llm_use_frequency not in LLM_FREQUENCIES:
        raise HTTPException(400, "Please select how often you use LLMs")
    purposes = set(req.llm_use_purposes)
    if not purposes.issubset(LLM_PURPOSES):
        raise HTTPException(400, "Please select valid LLM use purposes")
    use_other = None
    if "other" in purposes:
        use_other = " ".join(req.llm_use_other.split())[:255]
        if not use_other:
            raise HTTPException(400, "Please describe the other purpose for which you use LLMs")
    if req.llm_use_frequency == "never":
        if purposes or req.llm_used_for_learning:
            raise HTTPException(400, "Please check your LLM use responses")
    elif not purposes:
        raise HTTPException(400, "Please select at least one LLM use purpose")
    learning_frequency, learning_methods, learning_other = None, [], None
    if req.llm_used_for_learning:
        if req.llm_learning_frequency not in LLM_LEARNING_FREQUENCIES - {"never"}:
            raise HTTPException(400, "Please select how often you use LLMs for learning")
        methods = set(req.llm_learning_methods)
        if not methods or not methods.issubset(LLM_LEARNING_METHODS):
            raise HTTPException(400, "Please select at least one way you use LLMs for learning")
        learning_frequency = req.llm_learning_frequency
        learning_methods = sorted(methods)
        if "other" in methods:
            learning_other = " ".join(req.llm_learning_other.split())[:255]
            if not learning_other:
                raise HTTPException(400, "Please describe the other way you use LLMs for learning")
    demo = {"birth_date": birth, "age": req.age, "gender": req.gender,
            **ails_cols, "ails_score": ails_score,
            "education_years": req.education_years, "native_english": int(req.native_english),
            "first_language": first_language or None, "english_age": english_age,
            "hispanic": int(req.hispanic), "race": req.race,
            "major": major, "second_major": second_major, "minor": minor,
            "llm_use_frequency": req.llm_use_frequency, "llm_use_purposes": sorted(purposes), "llm_use_other": use_other,
            "llm_used_for_learning": int(req.llm_used_for_learning),
            "llm_learning_frequency": learning_frequency, "llm_learning_methods": learning_methods,
            "llm_learning_other": learning_other}
    try:
        p = db.create_participant(pid, name, demo)
    except db.DuplicateParticipantId:
        raise HTTPException(400, PID_TAKEN)
    return participant_view(p)


def _meta(raw) -> dict:
    """meta 存于 MySQL JSON 列,驱动可能返回字符串或已解析的 dict。"""
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return raw if isinstance(raw, dict) else {}


def transcript_view(sid: str) -> list[dict]:
    """重新进入时用于重建聊天界面的对话记录:只含受试者与 agent 的可见发言。
    system 提示与考试答案不重放(前者从不显示,后者属于考试页,不进聊天界面)。"""
    out = []
    for m in db.get_messages(sid):
        if m["role"] not in ("participant", "agent") or m["state"] in ("causal", "exam"):
            continue
        item = {"phase": m["phase"], "state": m["state"], "role": m["role"], "content": m["content"]}
        sources = _meta(m["meta"]).get("sources")
        if sources:
            item["sources"] = sources
        out.append(item)
    return out


def session_view(s: dict) -> dict:
    """返回给前端的会话状态(不含 agent 的材料,防泄露)。"""
    out = {
        "session_id": s["id"],
        "phase": s["phase"],
        "state": s["state"],
        "conflicts": s["conflicts"],
        "conflicts_required": CONFLICTS_REQUIRED,
        "total_phases": TOTAL_PHASES,
        "topic_no": topic_of(s["phase"]),
        "round": round_of(s["phase"]),
        "rounds_per_topic": ROUNDS_PER_TOPIC,
        "total_topics": TOTAL_TOPICS,
    }
    if s["state"] != "finished":
        cfg = phase_cfg(s["phase"])
        out["topic"] = cfg["topic"]
        out["learning_goal"] = cfg["learning_goal"]
        if s["state"] == "reading":
            out["article"] = article_for(topic_of(s["phase"]))
        if s["state"] == "exam":
            out["exam_questions"] = EXAM_QUESTIONS
    return out


@app.post("/api/session")
def start_session(req: StartReq):
    # 会话必须挂在一个已完成同意书与问卷的 participant id 上
    pid = _clean_pid(req.participant)
    p = db.get_participant(pid)
    if not p:
        raise HTTPException(400, "Unknown Participant ID; please complete the consent form first")
    # 每人至多一次实验:已开始过的受试者一律恢复原会话,不新建
    s = db.get_latest_session(p["participant_id"])
    if s:
        return {**session_view(s), "resumed": True, "messages": transcript_view(s["id"]),
                "pending": pending_state(s)}
    s = db.create_session(p["participant_id"])
    db.add_message(s["id"], 1, "reading", "system", "Session started; entering Phase 1 reading stage")
    return session_view(s)


CHAT_STATES = ("onboarding", "debate", "summary")

# 教育年限档位 → 提示词中的可读描述(用于受试者画像)
EDUCATION_LABELS = {
    "1-7.5": "fewer than 8 years of formal education",
    "8": "completed 8th grade",
    "9-11.5": "some high school",
    "12": "high school graduate",
    "12.5-15.5": "some college",
    "16": "college graduate (bachelor's degree)",
    "18": "master's degree",
    "20": "doctoral or medical degree",
}


def participant_profile(s: dict) -> dict | None:
    """受试者画像(年龄/教育水平/专业),注入讨论 agent 提示词以校准语言难度。
    只取与措辞相关的字段,不含姓名等身份信息。"""
    p = db.get_participant(s["participant"]) if s.get("participant") else None
    if not p:
        return None
    profile = {}
    if p.get("age"):
        profile["Age"] = p["age"]
    if p.get("education_years"):
        profile["Education"] = EDUCATION_LABELS.get(p["education_years"], p["education_years"])
    if p.get("major"):
        major = p["major"]
        if p.get("second_major"):
            major += f" (second major: {p['second_major']})"
        profile["Field of study / major"] = major
    if p.get("minor"):
        profile["Minor"] = p["minor"]
    return profile or None


def _state_conflict(s: dict) -> HTTPException:
    """客户端状态落后于服务端(响应丢失/断线重发)。前端收到 409 会自动重新同步,
    而不是把错误当成失败弹给受试者。"""
    return HTTPException(409, f"This step was already completed (current stage: {s['state']})")


def _pending_turn(sid: str, phase: int, states: tuple) -> dict | None:
    """返回一条"只有受试者发言、agent 还没回"的悬空消息(断线或模型调用失败留下的),
    没有则返回 None。恢复会话时据此补齐,受试者不会卡在自己的发言上。"""
    msgs = [m for m in db.get_messages(sid, phase)
            if m["role"] in ("participant", "agent") and m["state"] in states]
    return msgs[-1] if msgs and msgs[-1]["role"] == "participant" else None


def pending_state(s: dict) -> str | None:
    """当前会话是否有待补的 agent 回复(chat / search)。"""
    if s["state"] in CHAT_STATES and _pending_turn(s["id"], s["phase"], CHAT_STATES):
        return "chat"
    if s["state"] == "search" and _pending_turn(s["id"], s["phase"], ("search",)):
        return "search"
    return None


@app.get("/api/session/{sid}")
def get_session(sid: str):
    s = db.get_session(sid)
    if not s:
        raise HTTPException(404, "session not found")
    return {**session_view(s), "pending": pending_state(s)}


@app.post("/api/session/{sid}/done-reading")
def done_reading(sid: str):
    """受试者点击"我读完了"。
    主题 1(phase 1):进入 onboarding,agent 用固定脚本介绍研究;
    主题 2(phase 4):agent 生成开场(topic_open)并直接进入本主题第一轮讨论。"""
    s = _require(sid)
    if s["state"] == "onboarding":
        # 重复点击/响应丢失后重发:上次其实已经成功,直接返回当前状态
        return {**session_view(s), "prompt": ONBOARDING_INTRO}
    if s["state"] == "debate" and topic_of(s["phase"]) > 1 and round_of(s["phase"]) == 1:
        # 主题 2 的重复点击:开场已生成;对话记录由前端恢复机制重放
        return {**session_view(s), "agent_messages": []}
    if s["state"] != "reading":
        raise _state_conflict(s)
    phase = s["phase"]
    if phase == 1:
        db.update_session(sid, state="onboarding")
        db.add_message(sid, phase, "onboarding", "system",
                       "Participant finished reading; entering onboarding stage")
        # 开场白为固定脚本(保证所有受试者一致),入库存档;前端展示本地化版本
        db.add_message(sid, phase, "onboarding", "agent", ONBOARDING_INTRO, meta={"scripted": True})
        return {**session_view(db.get_session(sid)), "prompt": ONBOARDING_INTRO}
    # 主题 2:先生成开场再改状态,模型失败时状态留在 reading,受试者可重试
    cfg = phase_cfg(phase)
    r = agent.generate_reply(cfg, "topic_open", [], 0, CONFLICTS_REQUIRED,
                             next_cfg=next_phase_cfg(phase), profile=participant_profile(s))
    db.update_session(sid, state="debate")
    db.add_message(sid, phase, "debate", "system",
                   f"Participant finished reading Topic {topic_of(phase)} article; entering discussion round 1")
    db.add_message(sid, phase, "debate", "agent", r["reply"], meta={"reason": r["reason"]})
    return {**session_view(db.get_session(sid)), "agent_messages": [r["reply"]]}


@app.post("/api/session/{sid}/message")
def post_message(sid: str, req: MsgReq):
    """受试者发言 → agent 按当前环节回应。返回本轮 agent 的一条或多条消息。

    容错:上一轮若因断线/模型失败没写成回复,受试者重发同一句话时不会重复入库,
    而是直接补上那一轮的回复。"""
    s = _require(sid)
    if s["state"] not in CHAT_STATES:
        raise _state_conflict(s)
    pending = _pending_turn(sid, s["phase"], CHAT_STATES)
    if not (pending and pending["content"] == req.content):
        db.add_message(sid, s["phase"], s["state"], "participant", req.content)
    return _chat_turn(sid)


def _chat_turn(sid: str) -> dict:
    """按当前环节生成 agent 的这一轮回复(前提:最后一条是受试者发言)。"""
    s = _require(sid)
    state, phase = s["state"], s["phase"]
    cfg = phase_cfg(phase)
    history = db.get_messages(sid, phase)
    agent_msgs = []
    ng = next_phase_cfg(phase)
    prof = participant_profile(s)

    if state == "onboarding":
        # 引导环节:回应疑问、鼓励积极发言;受试者明确确认(advance=true)后 agent 分享己方要点并直接开辩
        r = agent.generate_reply(cfg, "onboarding", history, 0, CONFLICTS_REQUIRED, next_cfg=ng, profile=prof)
        db.add_message(sid, phase, "onboarding", "agent", r["reply"],
                       meta={"reason": r["reason"], "advance": r["advance"]})
        agent_msgs.append(r["reply"])
        if r["advance"]:
            db.update_session(sid, state="debate")

    elif state == "debate":
        # 辩论的同时,提示词层引导话题走向下一阶段学习目标(next_cfg)
        r = agent.generate_reply(cfg, "debate", history, s["conflicts"], CONFLICTS_REQUIRED, next_cfg=ng, profile=prof)
        conflicts = s["conflicts"] + (1 if r["conflict_triggered"] else 0)
        db.add_message(sid, phase, "debate", "agent", r["reply"],
                       conflict=r["conflict_triggered"], meta={"reason": r["reason"]})
        agent_msgs.append(r["reply"])
        db.update_session(sid, conflicts=conflicts)

        if conflicts >= CONFLICTS_REQUIRED:
            # 达到3次认知冲突 → 追加一条"引导总结"消息,进入总结环节
            history = db.get_messages(sid, phase)
            r2 = agent.generate_reply(cfg, "summary_invite", history, conflicts, CONFLICTS_REQUIRED, profile=prof)
            db.add_message(sid, phase, "summary", "agent", r2["reply"], meta={"reason": r2["reason"]})
            agent_msgs.append(r2["reply"])
            db.update_session(sid, state="summary")

    elif state == "summary":
        # 受试者提交总结 → agent 收尾 → 进入本轮的自主搜索环节
        r = agent.generate_reply(cfg, "summary_close", history, s["conflicts"], CONFLICTS_REQUIRED, profile=prof)
        db.add_message(sid, phase, "summary", "agent", r["reply"], meta={"reason": r["reason"]})
        agent_msgs.append(r["reply"])

        # 每轮讨论结束后都有搜索环节(留在同一 phase),之后由 /end-search 推进
        db.update_session(sid, state="search")
        db.add_message(sid, phase, "search", "system",
                       f"Discussion round {round_of(phase)} of Topic {topic_of(phase)} finished; "
                       "entering self-directed search stage")
        # 搜索环节开场白为固定脚本(所有受试者一致),入库存档;前端展示本地化版本
        db.add_message(sid, phase, "search", "agent", SEARCH_INTRO, meta={"scripted": True})

    return {**session_view(db.get_session(sid)), "agent_messages": agent_msgs}


@app.post("/api/session/{sid}/search-message")
def post_search_message(sid: str, req: MsgReq):
    """搜索环节:受试者向 search agent 提问 → 联网检索权威资料后回复。
    交互记录入 messages(state='search'),实际搜索词另存 search_queries 表。"""
    s = _require(sid)
    if s["state"] != "search":
        raise _state_conflict(s)
    pending = _pending_turn(sid, s["phase"], ("search",))
    if not (pending and pending["content"] == req.content):
        db.add_message(sid, s["phase"], "search", "participant", req.content)
    return _search_turn(sid)


def _search_turn(sid: str) -> dict:
    """搜索环节的一轮检索回复(前提:最后一条是受试者提问)。"""
    s = _require(sid)
    phase = s["phase"]
    cfg = phase_cfg(phase)
    history = [m for m in db.get_messages(sid, phase) if m["state"] == "search"]
    r = agent.generate_search_reply(cfg["topic"], cfg["learning_goal"], history)
    db.add_message(sid, phase, "search", "agent", r["reply"],
                   meta={"queries": r["queries"], "sources": r["sources"]})
    for q in r["queries"]:
        db.add_search_query(sid, phase, q)
    return {**session_view(db.get_session(sid)),
            "agent_messages": [r["reply"]], "sources": r["sources"]}


@app.post("/api/session/{sid}/retry-turn")
def retry_turn(sid: str):
    """断线重连后调用:上一轮 agent 回复若没写成就补上,否则原样返回当前状态。
    幂等,重复调用安全。"""
    s = _require(sid)
    kind = pending_state(s)
    if kind == "chat":
        return _chat_turn(sid)
    if kind == "search":
        return _search_turn(sid)
    return {**session_view(s), "agent_messages": []}


@app.post("/api/session/{sid}/end-search")
def end_search(sid: str):
    """受试者点击"结束搜索":
    - 本主题还有下一轮 → agent 开场并进入下一轮讨论;
    - 主题 1 的 3 轮已毕(phase 3)→ 休息页(rest);
    - 主题 2 的 3 轮已毕(phase 6)→ 考试页(exam)。"""
    s = _require(sid)
    if s["state"] in ("rest", "exam"):
        # 上次其实已经成功(响应在路上丢了),直接返回当前状态
        return session_view(s)
    if s["state"] != "search":
        raise _state_conflict(s)
    phase = s["phase"]

    if round_of(phase) < ROUNDS_PER_TOPIC:
        # 下一轮讨论:先生成开场再改状态,模型失败时状态留在 search,受试者可重试
        new_phase = phase + 1
        cfg = phase_cfg(new_phase)
        prev_history = db.get_messages(sid, phase)      # 上一轮的讨论+搜索作衔接上下文
        r = agent.generate_reply(cfg, "phase_open", prev_history, 0, CONFLICTS_REQUIRED,
                                 next_cfg=next_phase_cfg(new_phase), profile=participant_profile(s))
        db.update_session(sid, phase=new_phase, state="debate", conflicts=0)
        db.add_message(sid, new_phase, "debate", "system",
                       f"Search stage ended; entering discussion round {round_of(new_phase)} "
                       f"of Topic {topic_of(new_phase)}")
        db.add_message(sid, new_phase, "debate", "agent", r["reply"], meta={"reason": r["reason"]})
        return {**session_view(db.get_session(sid)), "agent_messages": [r["reply"]]}

    if topic_of(phase) < TOTAL_TOPICS:
        db.update_session(sid, state="rest")
        db.add_message(sid, phase, "rest", "system",
                       f"Topic {topic_of(phase)} finished; entering rest stage")
    else:
        db.update_session(sid, state="exam")
        db.add_message(sid, phase, "exam", "system",
                       f"Topic {topic_of(phase)} finished; entering exam stage")
    return session_view(db.get_session(sid))


@app.post("/api/session/{sid}/end-rest")
def end_rest(sid: str):
    """休息页点击"继续" → 为受试者新建主题 2 的独立会话并进入其阅读页。
    主题 1 的会话标记为 done(终态),两个主题的对话记录彼此隔离。"""
    s = _require(sid)
    # 重复提交:主题 2 会话已建(含上次建完但没来得及标记旧会话的情况),直接返回它
    if s["participant"]:
        latest = db.get_latest_session(s["participant"])
        if latest and topic_of(latest["phase"]) > 1:
            return session_view(latest)
    if s["state"] != "rest":
        raise _state_conflict(s)
    new_phase = s["phase"] + 1                # 3 → 4:主题 2 第一轮
    s2 = db.create_session(s["participant"] or "", topic=topic_of(new_phase), phase=new_phase)
    db.add_message(s2["id"], new_phase, "reading", "system",
                   f"Rest finished; new session for Topic {topic_of(new_phase)}; entering reading stage")
    db.update_session(sid, state="done")      # 主题 1 会话收尾
    return session_view(s2)


# ---------------------------------------------------------------- 自由回忆录音
# 受试者口述回忆 -> 浏览器 MediaRecorder 录音 -> 上传落盘 -> 本地 Whisper 转写 -> 入库。
# 音频不出本机(不调用外部转写 API)。转写在后台线程进行,前端轮询 GET 取结果。
RECORDINGS_DIR = Path(__file__).parent / "recordings"
RECALL_KINDS = ("baseline", "post")
MAX_RECALL_BYTES = 50 * 1024 * 1024          # 约 50MB,远超正常回忆时长所需
_AUDIO_EXTS = {
    "audio/webm": ".webm", "audio/ogg": ".ogg",
    "audio/mp4": ".m4a", "audio/mpeg": ".mp3", "audio/wav": ".wav",
}


def _transcribe_recall(recall_id: int, uploaded_at, abs_path: str):
    """后台任务:转写并回写 transcript。失败只记状态,不影响受试者继续实验。
    uploaded_at 标识本任务对应的那次上传;期间若有新上传,本任务的回写不生效。"""
    try:
        db.set_free_recall_status(recall_id, uploaded_at, "transcribing")
        text = transcribe.transcribe_file(abs_path)
        db.set_free_recall_transcript(recall_id, uploaded_at, text)
    except Exception as e:                    # noqa: BLE001 - 转写失败需完整记录原因
        db.set_free_recall_status(recall_id, uploaded_at, "failed", str(e))


def _recall_view(row: dict | None) -> dict | None:
    """对外视图:不暴露服务器磁盘路径。"""
    if not row:
        return None
    return {
        "id": row["id"], "kind": row["kind"], "topic": row["topic"],
        "status": row["status"], "transcript": row["transcript"],
        "audio_bytes": row["audio_bytes"], "error": row["error"],
    }


@app.post("/api/session/{sid}/recall")
def upload_recall(sid: str, background: BackgroundTasks,
                  kind: str = "baseline", audio: UploadFile = File(...)):
    """上传一段自由回忆录音。同一 (session, kind) 重复上传会覆盖,幂等。"""
    s = _require(sid)
    if kind not in RECALL_KINDS:
        raise HTTPException(400, f"kind must be one of {RECALL_KINDS}")

    data = audio.file.read(MAX_RECALL_BYTES + 1)     # 多读 1 字节即可判断超限,不把超大文件整个读进内存
    if not data:
        raise HTTPException(400, "empty audio upload")
    if len(data) > MAX_RECALL_BYTES:
        raise HTTPException(413, "audio file too large")

    ext = _AUDIO_EXTS.get((audio.content_type or "").split(";")[0].strip(), ".webm")
    session_dir = RECORDINGS_DIR / sid
    session_dir.mkdir(parents=True, exist_ok=True)
    rel_path = f"{sid}/{kind}{ext}"
    (RECORDINGS_DIR / rel_path).write_bytes(data)

    recall_id, uploaded_at = db.add_free_recall(sid, topic_of(s["phase"]), rel_path, len(data), kind)
    background.add_task(_transcribe_recall, recall_id, uploaded_at, str(RECORDINGS_DIR / rel_path))
    return {"id": recall_id, "kind": kind, "status": "uploaded", "audio_bytes": len(data)}


@app.get("/api/session/{sid}/recall")
def get_recall(sid: str, kind: str = "baseline"):
    """轮询转写结果。status: uploaded|transcribing|done|failed。"""
    _require(sid)
    row = db.get_free_recall(sid, kind)
    if not row:
        raise HTTPException(404, "no recall recorded for this session")
    return _recall_view(row)


@app.post("/api/session/{sid}/recall/retranscribe")
def retranscribe_recall(sid: str, background: BackgroundTasks, kind: str = "baseline"):
    """重跑转写:服务重启丢了后台任务,或换模型后想重新生成时使用。音频仍在磁盘上。"""
    _require(sid)
    row = db.get_free_recall(sid, kind)
    if not row:
        raise HTTPException(404, "no recall recorded for this session")
    abs_path = RECORDINGS_DIR / row["audio_path"]
    if not abs_path.exists():
        raise HTTPException(409, "audio file is missing on disk")
    background.add_task(_transcribe_recall, row["id"], row["uploaded_at"], str(abs_path))
    return {"id": row["id"], "kind": kind, "status": "transcribing"}


class ExamReq(BaseModel):
    answers: list[str]


@app.post("/api/session/{sid}/exam")
def submit_exam(sid: str, req: ExamReq):
    """考试页提交全部答案 → 入库 → 实验结束(finished)。"""
    s = _require(sid)
    if s["state"] == "finished":
        return session_view(s)                # 重复提交:上次已成功
    if s["state"] != "exam":
        raise _state_conflict(s)
    answers = [" ".join(a.split()) for a in req.answers]
    if len(answers) != len(EXAM_QUESTIONS) or any(not a for a in answers):
        raise HTTPException(400, "Please answer every question before submitting")
    for i, (q, a) in enumerate(zip(EXAM_QUESTIONS, answers), start=1):
        db.add_exam_answer(sid, i, q, a)
        db.add_message(sid, s["phase"], "exam", "participant", a,
                       meta={"question_no": i, "question": q})
    db.update_session(sid, state="finished")
    db.add_message(sid, s["phase"], "finished", "system",
                   "Exam submitted; experiment fully completed")
    return session_view(db.get_session(sid))


@app.get("/api/session/{sid}/history")
def history(sid: str):
    """研究者导出:完整对话历史(含冲突标记与模型判定理由)与考试作答。"""
    _require(sid)
    return {"messages": db.get_messages(sid), "search_queries": db.get_search_queries(sid),
            "exam_answers": db.get_exam_answers(sid),
            "causal_graphs": db.get_causal_graphs(sid)}


def _require(sid: str) -> dict:
    s = db.get_session(sid)
    if not s:
        raise HTTPException(404, "session not found")
    return s


# 前端页面
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


FRONTEND_ROUTES = (
    "/",
    "/entry",
    "/consent",
    "/demographics",
    "/background",
    "/start",
    "/reading",
    "/chat",
    "/search",
    "/rest",
    "/exam",
    "/finish",
)


@app.get("/")
@app.get("/entry")
@app.get("/consent")
@app.get("/demographics")
@app.get("/background")
@app.get("/start")
@app.get("/reading")
@app.get("/chat")
@app.get("/search")
@app.get("/rest")
@app.get("/exam")
@app.get("/finish")
def index():
    # no-store:防止浏览器缓存旧版页面去调用已改动的接口(前后端不同步会报 Not Found)
    return FileResponse(static_dir / "index.html", headers={"Cache-Control": "no-store"})
