# -*- coding: utf-8 -*-
"""
实验材料配置(两个主题)。

实验流程(start 页之后):
  主题 1:阅读(article_1_P1_user 的 Reading Material) → (讨论→搜索)×3 → 休息页
  主题 2:阅读(article_2_P1_user 的 Reading Material) → (讨论→搜索)×3 → 考试页 → 结束再见

材料全部放在 materials/ 目录,按文件组织:
- article_{t}_ai:该主题 AI 学习伙伴的材料(反方,只注入系统提示词,不向受试者展示),
  按 ## Phase 1-3 分节,每节含 Learning Goal 与 Reading Material;
- article_{t}_P{n}_user(.md):该主题第 n 轮受试者一方(正方)的材料,供 agent 预判受试者
  立场;其中 P1 的 Reading Material 同时是该主题阅读页展示的文章;
- 界面显示的辩题(motion)取受试者材料的 "# Topic:" 标题,agent 立场取 ai 材料的标题;
- 第 N 轮讨论中 agent 会自然地把话题引向第 N+1 轮的 Learning Goal(见 app.py next_phase_cfg),
  跨主题不引导。
"""
import re
from pathlib import Path

MATERIALS_DIR = Path(__file__).parent / "materials"


def _article(fname: str) -> str:
    return (MATERIALS_DIR / fname).read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------- 材料文件解析
# 文件组织(materials/ 目录):
#   article_{t}_ai            该主题 AI 学习伙伴的材料:# Topic 标题 + ## Phase N 分节,
#                             每节含 ### Learning Goal 与 ### Reading Material
#   article_{t}_P{n}_user(.md) 该主题第 n 轮受试者一方的材料:# Topic / # Learning Goal /
#                             # Reading Material;P1 的 Reading Material 同时是阅读页文章

def _section(text: str, heading: str) -> str:
    """取 markdown 中某个标题(任意 # 级别)之后、下一个标题之前的正文。"""
    m = re.search(rf"^#+\s*{heading}\s*$\n(.*?)(?=^#+\s|\Z)", text, re.S | re.M)
    if not m:
        raise ValueError(f"heading '{heading}' not found in material file")
    return m.group(1).strip()


def _title(text: str) -> str:
    m = re.search(r"^#\s*Topic:\s*(.+)$", text, re.M)
    if not m:
        raise ValueError("'# Topic:' title not found in material file")
    return m.group(1).strip()


def _user_file(topic_id: int, rnd: int) -> str:
    """受试者一方材料文件(带不带 .md 后缀均可)。"""
    for fname in (f"article_{topic_id}_P{rnd}_user", f"article_{topic_id}_P{rnd}_user.md"):
        if (MATERIALS_DIR / fname).exists():
            return _article(fname)
    raise FileNotFoundError(f"materials/article_{topic_id}_P{rnd}_user(.md) not found")


def _parse_ai(topic_id: int) -> tuple[str, list[dict]]:
    """解析 article_{t}_ai → (agent 一方的主题命题, 每轮 {learning_goal, agent_article})。"""
    text = _article(f"article_{topic_id}_ai")
    title = _title(text)
    rounds = []
    for seg in re.split(r"^##\s*Phase\s*\d+\s*$", text, flags=re.M)[1:]:
        rounds.append({"learning_goal": _section(seg, "Learning Goal"),
                       "agent_article": _section(seg, "Reading Material")})
    if len(rounds) != 3:
        raise ValueError(f"article_{topic_id}_ai must contain 3 '## Phase N' sections, got {len(rounds)}")
    return title, rounds


def _build_topic(topic_id: int) -> dict:
    ai_title, ai_rounds = _parse_ai(topic_id)
    rounds, motion = [], None
    for i, ai_round in enumerate(ai_rounds, start=1):
        user_text = _user_file(topic_id, i)
        if motion is None:
            motion = _title(user_text)         # 受试者一方的主题命题作为界面上显示的辩题
        rounds.append({
            **ai_round,
            "participant_article": _section(user_text, "Reading Material"),
            "agent_stance": f'You argue for the opposing thesis: "{ai_title}."',
        })
    return {"id": topic_id, "motion": motion, "rounds": rounds}


# ---------------------------------------------------------------- 汇总结构
# 讨论轮配置在服务启动时读入(改动 ai / P2 / P3 材料需重启);
# 阅读页文章经 article_for() 每次现读(改 P1 材料刷新页面即生效)
TOPICS = [_build_topic(1), _build_topic(2)]


def article_for(topic_id: int) -> str:
    """阅读页文章:该主题第 1 轮受试者材料的 Reading Material(每次调用现读文件)。"""
    return _section(_user_file(topic_id, 1), "Reading Material")

ROUNDS_PER_TOPIC = 3
TOTAL_TOPICS = len(TOPICS)

# PHASES:全局讨论轮(1-6)的扁平配置,phase = (topic-1)*3 + round。
# 每项含 topic(辩题)/topic_id/round 及该轮双方材料,供 app.py / agent.py 使用。
PHASES = [
    {**round_cfg, "topic": topic["motion"], "topic_id": topic["id"], "round": i + 1}
    for topic in TOPICS
    for i, round_cfg in enumerate(topic["rounds"])
]

# 考试页题目(主题 2 的 3 轮搜索全部结束后作答;占位内容,请替换)
EXAM_QUESTIONS = [
    "[PLACEHOLDER] In your own words, what does it mean for an AI system to be an AGI, and what evidence would convince you that AGI has (or has not) been achieved?",
    "[PLACEHOLDER] Explain how large language models are trained, and why some researchers argue this process does (or does not) amount to genuine understanding.",
    "[PLACEHOLDER] Describe one way that using LLMs might weaken human learning and one way it might strengthen it. Which do you find more convincing, and why?",
]

# 每轮讨论需要引发的认知冲突次数,达到后进入总结环节
CONFLICTS_REQUIRED = 3
