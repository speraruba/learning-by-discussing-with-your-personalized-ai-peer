# -*- coding: utf-8 -*-
"""
后端数据库(MySQL)。
表结构:
- participants: 受试者(participant_id 为研究者分配的唯一身份码 + 姓名 + 人口学信息)
- sessions: 一次受试者实验会话(记录当前阶段、状态、冲突计数)
- messages: 全部对话历史(含阶段、环节、角色、是否触发认知冲突、模型判定理由)

表结构以下方 SCHEMA 为唯一事实来源;应用启动时调用 init_db() 会:
1. 若数据库不存在则创建(utf8mb4);
2. 若表不存在则创建;
3. 若表已存在,自动补齐 SCHEMA 中新增的列、索引与外键(不会删除或修改已有列)。

连接参数通过环境变量配置:
MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD / MYSQL_DB
"""
import os
import time
import functools
import uuid
import json
import threading
from datetime import datetime, timezone

import pymysql
from pymysql.cursors import DictCursor

# ====== MySQL 连接配置:在下面引号内填入,或用同名环境变量覆盖(环境变量优先) ======
DB_HOST     = os.environ.get("MYSQL_HOST", "127.0.0.1")
DB_PORT     = int(os.environ.get("MYSQL_PORT", "3306"))
DB_USER     = os.environ.get("MYSQL_USER", "root")
DB_PASSWORD = os.environ.get("MYSQL_PASSWORD", "root")          #
DB_NAME     = os.environ.get("MYSQL_DB", "learning_partner")  # 库不存在会自动创建

_TABLE_OPTIONS = "ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci"

# ---------------------------------------------------------------- 表结构声明
# columns 按声明顺序建表;新增列时追加到列表中即可,启动时会自动 ADD COLUMN。
SCHEMA: dict[str, dict] = {
    # 受试者:无账号密码,participant_id 是研究者分配的唯一身份码。
    # 唯一性由 uq_participants_pid 保证(列排序规则 utf8mb4_unicode_ci,大小写不敏感)。
    # 人口学信息(Demographic Information)在同意知情同意书后、实验开始前采集。
    "participants": {
        "columns": [
            ("id", "VARCHAR(32) NOT NULL"),
            ("participant_id", "VARCHAR(64) NOT NULL"),
            ("name", "VARCHAR(64) NULL"),               # 受试者姓名,老用户重新进入时核对
            ("birth_date", "DATE NULL"),
            ("age", "INT NULL"),
            ("gender", "VARCHAR(16) NULL"),             # male | female
            ("education_years", "VARCHAR(16) NULL"),    # 正规教育年限档位:1-7.5/8/9-11.5/12/12.5-15.5/16/18/20
            ("native_english", "TINYINT(1) NULL"),
            ("first_language", "VARCHAR(64) NULL"),     # 非英语母语时填写
            ("english_age", "INT NULL"),                # 非英语母语时:开始学英语的年龄
            ("hispanic", "TINYINT(1) NULL"),            # 是否 Hispanic or Latino
            ("race", "VARCHAR(40) NULL"),               # 种族类别(单选)
            ("major", "VARCHAR(100) NULL"),             # 主修专业
            ("second_major", "VARCHAR(100) NULL"),      # 第二主修专业(如有)
            ("minor", "VARCHAR(100) NULL"),             # 辅修(如有)
            # AI Literacy Scale(Wang et al.)12 条目,7 点李克特。
            # 每列存受试者的原始作答(1-7,不做反转);ails_score 存反向计分后的总分:
            # AW_8/US_3/ET_2 为反向条目,计入总分前按 8-原始分 反转(7→1,6→2,…,4→4)。
            ("ails_aw_1", "TINYINT NULL"),
            ("ails_aw_8", "TINYINT NULL"),              # R 反向条目
            ("ails_aw_9", "TINYINT NULL"),
            ("ails_us_1", "TINYINT NULL"),
            ("ails_us_3", "TINYINT NULL"),              # R 反向条目
            ("ails_us_5", "TINYINT NULL"),
            ("ails_ev_2", "TINYINT NULL"),
            ("ails_ev_3", "TINYINT NULL"),
            ("ails_ev_6", "TINYINT NULL"),
            ("ails_et_1", "TINYINT NULL"),
            ("ails_et_2", "TINYINT NULL"),              # R 反向条目
            ("ails_et_5", "TINYINT NULL"),
            ("ails_score", "SMALLINT NULL"),            # 反向计分后 12 条目总分(12-84)
            # 大语言模型（LLM）使用及学习方式；多选题以 JSON 数组保存。
            ("llm_use_frequency", "VARCHAR(32) NULL"),
            ("llm_use_purposes", "JSON NULL"),
            ("llm_use_other", "VARCHAR(255) NULL"),
            ("llm_used_for_learning", "TINYINT(1) NULL"),
            ("llm_learning_frequency", "VARCHAR(32) NULL"),
            ("llm_learning_methods", "JSON NULL"),
            ("llm_learning_other", "VARCHAR(255) NULL"),
            ("created_at", "DATETIME(6) NOT NULL"),
        ],
        "primary_key": "`id`",
        "indexes": {
            "uq_participants_pid": "UNIQUE KEY `uq_participants_pid` (`participant_id`)",
        },
    },
    "sessions": {
        "columns": [
            ("id", "VARCHAR(32) NOT NULL"),
            # participants.participant_id;老受试者靠它找回上次会话(每主题一条、每人至多两条,见 app.start_session / end_rest)
            ("participant", "VARCHAR(64) NULL"),
            ("topic", "INT NOT NULL DEFAULT 1"),           # 本会话对应的主题号(一个主题一条 session)
            ("phase", "INT NOT NULL DEFAULT 1"),
            ("state", "VARCHAR(20) NOT NULL DEFAULT 'reading'"),
            ("conflicts", "INT NOT NULL DEFAULT 0"),
            ("created_at", "DATETIME(6) NOT NULL"),
            ("updated_at", "DATETIME(6) NOT NULL"),
        ],
        "primary_key": "`id`",
        "indexes": {
            "idx_sessions_participant": "KEY `idx_sessions_participant` (`participant`)",
        },
    },
    "messages": {
        "columns": [
            ("id", "BIGINT NOT NULL AUTO_INCREMENT"),
            ("session_id", "VARCHAR(32) NOT NULL"),
            ("phase", "INT NOT NULL"),
            ("state", "VARCHAR(20) NOT NULL"),
            ("role", "VARCHAR(16) NOT NULL"),                   # participant | agent | system
            ("content", "TEXT NOT NULL"),
            ("conflict", "TINYINT(1) NOT NULL DEFAULT 0"),      # 该条 agent 发言是否触发认知冲突
            ("meta", "JSON NULL"),                              # 模型自评理由等
            ("created_at", "DATETIME(6) NOT NULL"),
        ],
        "primary_key": "`id`",
        "indexes": {
            # get_messages 按 session_id (+phase) 过滤、按 id 排序
            "idx_messages_session_phase": "KEY `idx_messages_session_phase` (`session_id`, `phase`, `id`)",
        },
        "foreign_keys": {
            "fk_messages_session": "CONSTRAINT `fk_messages_session` FOREIGN KEY (`session_id`) "
                                   "REFERENCES `sessions` (`id`) ON DELETE CASCADE",
        },
    },
    # search agent 实际发出的搜索词(每条一行,便于研究者导出分析;
    # 完整交互记录仍在 messages 表,state='search')
    "search_queries": {
        "columns": [
            ("id", "BIGINT NOT NULL AUTO_INCREMENT"),
            ("session_id", "VARCHAR(32) NOT NULL"),
            ("phase", "INT NOT NULL"),                          # 即将进入的讨论阶段
            ("query", "VARCHAR(512) NOT NULL"),
            ("created_at", "DATETIME(6) NOT NULL"),
        ],
        "primary_key": "`id`",
        "indexes": {
            "idx_search_queries_session": "KEY `idx_search_queries_session` (`session_id`, `id`)",
        },
        "foreign_keys": {
            "fk_search_queries_session": "CONSTRAINT `fk_search_queries_session` FOREIGN KEY (`session_id`) "
                                         "REFERENCES `sessions` (`id`) ON DELETE CASCADE",
        },
    },
    # 考试页作答(主题 2 的 3 轮讨论+搜索结束后):每题一行,题目文本随答案一并存档
    "exam_answers": {
        "columns": [
            ("id", "BIGINT NOT NULL AUTO_INCREMENT"),
            ("session_id", "VARCHAR(32) NOT NULL"),
            ("question_no", "INT NOT NULL"),
            ("question", "TEXT NOT NULL"),
            ("answer", "TEXT NOT NULL"),
            ("created_at", "DATETIME(6) NOT NULL"),
        ],
        "primary_key": "`id`",
        "indexes": {
            "idx_exam_answers_session": "KEY `idx_exam_answers_session` (`session_id`, `question_no`)",
        },
        "foreign_keys": {
            "fk_exam_answers_session": "CONSTRAINT `fk_exam_answers_session` FOREIGN KEY (`session_id`) "
                                       "REFERENCES `sessions` (`id`) ON DELETE CASCADE",
        },
    },
    # AI 推测的受试者因果关联图(旧流程遗留数据;当前流程不再生成),含受试者 0-10 评分
    "causal_graphs": {
        "columns": [
            ("id", "BIGINT NOT NULL AUTO_INCREMENT"),
            ("session_id", "VARCHAR(32) NOT NULL"),
            ("phase", "INT NOT NULL"),                          # 即将进入的讨论阶段
            ("graph", "JSON NOT NULL"),                         # {"nodes": [...], "edges": [...]}
            ("rating", "TINYINT NULL"),                         # 受试者评分 0-10,未评为 NULL
            ("created_at", "DATETIME(6) NOT NULL"),
            ("rated_at", "DATETIME(6) NULL"),
        ],
        "primary_key": "`id`",
        "indexes": {
            "idx_causal_graphs_session": "KEY `idx_causal_graphs_session` (`session_id`, `id`)",
        },
        "foreign_keys": {
            "fk_causal_graphs_session": "CONSTRAINT `fk_causal_graphs_session` FOREIGN KEY (`session_id`) "
                                        "REFERENCES `sessions` (`id`) ON DELETE CASCADE",
        },
    },
}


# ---------------------------------------------------------------- 连接管理
def _connect(database: str | None = None):
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
        database=database, charset="utf8mb4", cursorclass=DictCursor, autocommit=True,
    )


# 每个线程复用一条连接(FastAPI 的同步端点运行在线程池中)
_local = threading.local()


def _conn():
    conn = getattr(_local, "conn", None)
    if conn is not None:
        try:
            conn.ping(reconnect=True)       # 连接超时被服务端断开时自动重连
            return conn
        except Exception:
            try:
                conn.close()
            except Exception:
                pass
            _local.conn = None
    conn = _local.conn = _connect(DB_NAME)
    return conn


def _drop_conn():
    conn = getattr(_local, "conn", None)
    _local.conn = None
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass


# 连接在查询途中被服务端掐断时的错误号
_LOST_CONN_ERRNOS = {2006, 2013, 2055}      # server has gone away / lost connection / 连接被重置


def _retrying(fn):
    """连接中途断开时重连并重试一次。只用于读操作:写操作重试可能造成重复入库,
    交给上层的幂等接口(/retry-turn 等)处理。"""
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except (pymysql.err.OperationalError, pymysql.err.InterfaceError) as e:
            if e.args and e.args[0] not in _LOST_CONN_ERRNOS:
                raise
            print(f"[db] 连接中断({e.args[0] if e.args else '?'}),重连后重试 {fn.__name__}")
            _drop_conn()
            return fn(*args, **kwargs)
    return wrapper


def _now():
    # MySQL DATETIME 不带时区,统一存 naive UTC
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------- 启动检查
# 仅这些错误值得重试(服务还在启动中);账号/权限等错误重试无意义,应立即报错
_RETRYABLE_ERRNOS = {2002, 2003, 2013}      # 无法连接 / socket 错误 / 连接丢失


def init_db(retries: int = 10, delay: float = 1.5):
    """启动时检查数据库:创建缺失的库/表,并补齐新增的列、索引与外键。"""
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            _ensure_database()
            break
        except pymysql.err.OperationalError as e:
            if e.args[0] not in _RETRYABLE_ERRNOS:
                raise RuntimeError(_conn_err_msg(e)) from e
            last_err = e
            if attempt < retries:
                print(f"[db] MySQL 未就绪({e.args[0]}),{delay}s 后重试 ({attempt}/{retries})")
                time.sleep(delay)
    else:
        raise RuntimeError(_conn_err_msg(last_err))
    _ensure_schema()


def _conn_err_msg(err) -> str:
    return (
        f"无法连接 MySQL ({DB_USER}@{DB_HOST}:{DB_PORT}, db={DB_NAME}): {err}\n"
        "请检查 MySQL 是否已启动,以及环境变量 "
        "MYSQL_HOST / MYSQL_PORT / MYSQL_USER / MYSQL_PASSWORD / MYSQL_DB 是否正确。"
    )


def _ensure_database():
    conn = _connect(None)
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{DB_NAME}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        conn.close()


def _ensure_schema():
    conn = _connect(DB_NAME)
    try:
        with conn.cursor() as cur:
            for table, spec in SCHEMA.items():
                if _table_exists(cur, table):
                    _sync_table(cur, table, spec)
                else:
                    _create_table(cur, table, spec)
                    print(f"[db] 已创建表 `{table}`")
    finally:
        conn.close()


def _table_exists(cur, table: str) -> bool:
    cur.execute(
        "SELECT 1 FROM information_schema.tables WHERE table_schema=%s AND table_name=%s",
        (DB_NAME, table),
    )
    return cur.fetchone() is not None


def _create_table(cur, table: str, spec: dict):
    parts = [f"`{name}` {ddl}" for name, ddl in spec["columns"]]
    parts.append(f"PRIMARY KEY ({spec['primary_key']})")
    parts += list(spec.get("indexes", {}).values())
    parts += list(spec.get("foreign_keys", {}).values())
    cur.execute(f"CREATE TABLE `{table}` (\n  " + ",\n  ".join(parts) + f"\n) {_TABLE_OPTIONS}")


def _sync_table(cur, table: str, spec: dict):
    """表已存在:补齐 SCHEMA 中新增的列、索引、外键。不改动/删除已有定义。"""
    # 注意:必须用别名。MySQL 8.0 的 information_schema 返回大写列标签(COLUMN_NAME),
    # 5.7 返回小写,加 AS 后两个版本一致。
    cur.execute(
        "SELECT column_name AS name FROM information_schema.columns "
        "WHERE table_schema=%s AND table_name=%s",
        (DB_NAME, table),
    )
    existing = {r["name"].lower() for r in cur.fetchall()}

    prev = None                                     # 用 AFTER 保持与声明一致的列顺序
    for name, ddl in spec["columns"]:
        if name.lower() not in existing:
            after = f" AFTER `{prev}`" if prev else " FIRST"
            cur.execute(f"ALTER TABLE `{table}` ADD COLUMN `{name}` {ddl}{after}")
            print(f"[db] 已为 `{table}` 添加列 `{name}`")
        prev = name

    cur.execute(
        "SELECT DISTINCT index_name AS name FROM information_schema.statistics "
        "WHERE table_schema=%s AND table_name=%s",
        (DB_NAME, table),
    )
    existing_idx = {r["name"].lower() for r in cur.fetchall()}
    for name, ddl in spec.get("indexes", {}).items():
        if name.lower() not in existing_idx:
            cur.execute(f"ALTER TABLE `{table}` ADD {ddl}")
            print(f"[db] 已为 `{table}` 添加索引 `{name}`")

    cur.execute(
        "SELECT constraint_name AS name FROM information_schema.table_constraints "
        "WHERE table_schema=%s AND table_name=%s AND constraint_type='FOREIGN KEY'",
        (DB_NAME, table),
    )
    existing_fk = {r["name"].lower() for r in cur.fetchall()}
    for name, ddl in spec.get("foreign_keys", {}).items():
        if name.lower() not in existing_fk:
            try:
                cur.execute(f"ALTER TABLE `{table}` ADD {ddl}")
                print(f"[db] 已为 `{table}` 添加外键 `{name}`")
            except pymysql.err.Error as e:
                # 已有脏数据(孤儿行)时加外键会失败,不阻塞启动
                print(f"[db] 警告:`{table}` 外键 `{name}` 添加失败({e.args[0]}),已跳过")


# ---------------------------------------------------------------- sessions
def create_session(participant: str = "", topic: int = 1, phase: int = 1) -> dict:
    """建一条会话。一个主题对应一条独立 session:主题 1 在受试者点"开始"时建,
    主题 2 在休息页结束时建(见 app.end_rest);phase 沿用全局 1-6 编号。"""
    sid = uuid.uuid4().hex
    with _conn().cursor() as cur:
        cur.execute(
            "INSERT INTO sessions (id, participant, topic, phase, state, conflicts, created_at, updated_at) "
            "VALUES (%s, %s, %s, %s, 'reading', 0, %s, %s)",
            (sid, participant, topic, phase, _now(), _now()),
        )
    return get_session(sid)


def get_latest_session(participant: str) -> dict | None:
    """该 participant 最近一次会话。老受试者重新进入时据此恢复到上次停留的环节。"""
    with _conn().cursor() as cur:
        cur.execute(
            "SELECT * FROM sessions WHERE participant=%s ORDER BY created_at DESC, id DESC LIMIT 1",
            (participant,),
        )
        return cur.fetchone()


def get_session(sid: str) -> dict | None:
    with _conn().cursor() as cur:
        cur.execute("SELECT * FROM sessions WHERE id=%s", (sid,))
        return cur.fetchone()


def update_session(sid: str, **fields):
    fields["updated_at"] = _now()
    keys = ", ".join(f"`{k}`=%s" for k in fields)
    with _conn().cursor() as cur:
        cur.execute(f"UPDATE sessions SET {keys} WHERE id=%s", (*fields.values(), sid))


# ---------------------------------------------------------------- messages
def add_message(sid: str, phase: int, state: str, role: str, content: str,
                conflict: bool = False, meta: dict | None = None):
    with _conn().cursor() as cur:
        cur.execute(
            "INSERT INTO messages (session_id, phase, state, role, content, conflict, meta, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (sid, phase, state, role, content, int(conflict),
             json.dumps(meta, ensure_ascii=False) if meta else None, _now()),
        )


def get_messages(sid: str, phase: int | None = None) -> list[dict]:
    q = "SELECT * FROM messages WHERE session_id=%s"
    args: list = [sid]
    if phase is not None:
        q += " AND phase=%s"
        args.append(phase)
    q += " ORDER BY id ASC"
    with _conn().cursor() as cur:
        cur.execute(q, args)
        return list(cur.fetchall())


# ---------------------------------------------------------------- search queries
def add_search_query(sid: str, phase: int, query: str):
    with _conn().cursor() as cur:
        cur.execute(
            "INSERT INTO search_queries (session_id, phase, query, created_at) VALUES (%s, %s, %s, %s)",
            (sid, phase, query[:512], _now()),
        )


def get_search_queries(sid: str) -> list[dict]:
    with _conn().cursor() as cur:
        cur.execute("SELECT * FROM search_queries WHERE session_id=%s ORDER BY id ASC", (sid,))
        return list(cur.fetchall())


# ---------------------------------------------------------------- exam answers
def add_exam_answer(sid: str, question_no: int, question: str, answer: str):
    with _conn().cursor() as cur:
        cur.execute(
            "INSERT INTO exam_answers (session_id, question_no, question, answer, created_at) "
            "VALUES (%s, %s, %s, %s, %s)",
            (sid, question_no, question, answer, _now()),
        )


def get_exam_answers(sid: str) -> list[dict]:
    with _conn().cursor() as cur:
        cur.execute("SELECT * FROM exam_answers WHERE session_id=%s ORDER BY question_no ASC, id ASC", (sid,))
        return list(cur.fetchall())


# ---------------------------------------------------------------- causal graphs
def add_causal_graph(sid: str, phase: int, graph: dict) -> int:
    with _conn().cursor() as cur:
        cur.execute(
            "INSERT INTO causal_graphs (session_id, phase, graph, created_at) VALUES (%s, %s, %s, %s)",
            (sid, phase, json.dumps(graph, ensure_ascii=False), _now()),
        )
        return cur.lastrowid


def get_latest_causal_graph(sid: str) -> dict | None:
    with _conn().cursor() as cur:
        cur.execute("SELECT * FROM causal_graphs WHERE session_id=%s ORDER BY id DESC LIMIT 1", (sid,))
        row = cur.fetchone()
    if row and isinstance(row["graph"], str):
        row["graph"] = json.loads(row["graph"])
    return row


def set_causal_rating(graph_id: int, rating: int):
    with _conn().cursor() as cur:
        cur.execute("UPDATE causal_graphs SET rating=%s, rated_at=%s WHERE id=%s",
                    (rating, _now(), graph_id))


def get_causal_graphs(sid: str) -> list[dict]:
    with _conn().cursor() as cur:
        cur.execute("SELECT * FROM causal_graphs WHERE session_id=%s ORDER BY id ASC", (sid,))
        rows = list(cur.fetchall())
    for r in rows:
        if isinstance(r["graph"], str):
            r["graph"] = json.loads(r["graph"])
    return rows


# ---------------------------------------------------------------- participants
class DuplicateParticipantId(Exception):
    """participant_id 已被占用(唯一索引冲突)。"""


def create_participant(participant_id: str, name: str, demo: dict | None = None) -> dict:
    """写入受试者(姓名 + 唯一 id + 人口学信息)。participant_id 重复时抛 DuplicateParticipantId。

    唯一性最终由 uq_participants_pid 决定:先查后插会有竞态,因此这里直接
    依赖数据库报错,而不是只靠 get_participant() 的预检。"""
    uid = uuid.uuid4().hex
    demo = demo or {}
    cols = ["id", "participant_id", "name", "created_at"]
    vals = [uid, participant_id, name or None, _now()]
    for k in ("birth_date", "age", "gender", "education_years", "native_english",
              "first_language", "english_age", "hispanic", "race",
              "major", "second_major", "minor",
              "ails_aw_1", "ails_aw_8", "ails_aw_9", "ails_us_1", "ails_us_3", "ails_us_5",
              "ails_ev_2", "ails_ev_3", "ails_ev_6", "ails_et_1", "ails_et_2", "ails_et_5",
              "ails_score", "llm_use_frequency", "llm_use_purposes", "llm_use_other", "llm_used_for_learning",
              "llm_learning_frequency", "llm_learning_methods", "llm_learning_other"):
        if k in demo:
            cols.append(k)
            # PyMySQL 不会自动把 Python list 编码为 MySQL JSON。
            vals.append(json.dumps(demo[k], ensure_ascii=False) if k in ("llm_use_purposes", "llm_learning_methods") else demo[k])
    try:
        with _conn().cursor() as cur:
            cur.execute(
                f"INSERT INTO participants ({', '.join(cols)}) "
                f"VALUES ({', '.join(['%s'] * len(cols))})",
                vals,
            )
    except pymysql.err.IntegrityError as e:
        if e.args[0] == 1062:                       # ER_DUP_ENTRY
            raise DuplicateParticipantId(participant_id) from e
        raise
    return get_participant_row(uid)


def set_participant_name(uid: str, name: str):
    """补记姓名(此功能上线前注册的老受试者没有姓名,首次带姓名进入时写入)。"""
    with _conn().cursor() as cur:
        cur.execute("UPDATE participants SET name=%s WHERE id=%s", (name, uid))


def get_participant_row(uid: str) -> dict | None:
    with _conn().cursor() as cur:
        cur.execute("SELECT * FROM participants WHERE id=%s", (uid,))
        return cur.fetchone()


def get_participant(participant_id: str) -> dict | None:
    with _conn().cursor() as cur:
        cur.execute("SELECT * FROM participants WHERE participant_id=%s", (participant_id,))
        return cur.fetchone()


# 读操作统一加一层"断线重连后重试一次"。写操作不自动重试,避免重复入库。
for _name in ("get_session", "get_latest_session", "get_messages", "get_search_queries",
              "get_exam_answers", "get_latest_causal_graph", "get_causal_graphs",
              "get_participant", "get_participant_row"):
    globals()[_name] = _retrying(globals()[_name])
