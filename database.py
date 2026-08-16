# -*- coding: utf-8 -*-
"""
后端数据库(MySQL)。
表结构:
- users:    受试者账号与背景问卷(用户名/邮箱唯一,密码加盐哈希)
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
import uuid
import json
import hashlib
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
    "users": {
        "columns": [
            ("id", "VARCHAR(32) NOT NULL"),
            ("username", "VARCHAR(64) NOT NULL"),
            ("email", "VARCHAR(255) NOT NULL"),
            ("password_hash", "CHAR(64) NOT NULL"),
            ("salt", "CHAR(32) NOT NULL"),
            ("age", "INT NULL"),
            ("education", "VARCHAR(32) NULL"),
            ("major", "VARCHAR(128) NULL"),
            ("ai_level", "TINYINT NULL"),                       # 0-10 整体熟悉度
            ("ai_principle_level", "TINYINT NULL"),             # 0-10 原理了解度
            ("ai_frequency", "VARCHAR(32) NULL"),
            ("ai_purpose", "JSON NULL"),                        # 多选,存字符串数组
            ("ai_purpose_other", "VARCHAR(255) NULL"),           # 用途选 other 时的自填内容
            ("ai_used_for_learning", "TINYINT(1) NOT NULL DEFAULT 0"),
            ("created_at", "DATETIME(6) NOT NULL"),
        ],
        "primary_key": "`id`",
        "indexes": {
            "uq_users_username": "UNIQUE KEY `uq_users_username` (`username`)",
            "uq_users_email": "UNIQUE KEY `uq_users_email` (`email`)",
        },
    },
    "sessions": {
        "columns": [
            ("id", "VARCHAR(32) NOT NULL"),
            ("participant", "VARCHAR(64) NULL"),
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
    # AI 推测的受试者因果关联图(搜索环节结束后生成并展示),含受试者 0-10 评分
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
def create_session(participant: str = "") -> dict:
    sid = uuid.uuid4().hex
    with _conn().cursor() as cur:
        cur.execute(
            "INSERT INTO sessions (id, participant, phase, state, conflicts, created_at, updated_at) "
            "VALUES (%s, %s, 1, 'reading', 0, %s, %s)",
            (sid, participant, _now(), _now()),
        )
    return get_session(sid)


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


# ---------------------------------------------------------------- users
def _hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt = salt or os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return digest.hex(), salt.hex()


def create_user(username: str, email: str, password: str, age: int | None,
                 education: str, major: str, ai_level: int | None, ai_principle_level: int | None,
                 ai_frequency: str, ai_purpose: str, ai_purpose_other: str,
                 ai_used_for_learning: bool) -> dict:
    uid = uuid.uuid4().hex
    password_hash, salt = _hash_password(password)
    with _conn().cursor() as cur:
        cur.execute(
            "INSERT INTO users (id, username, email, password_hash, salt, age, education, "
            "major, ai_level, ai_principle_level, ai_frequency, ai_purpose, ai_purpose_other, "
            "ai_used_for_learning, created_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (uid, username, email, password_hash, salt, age, education, major, ai_level,
             ai_principle_level, ai_frequency, ai_purpose, ai_purpose_other or None,
             int(ai_used_for_learning), _now()),
        )
    return get_user(uid)


def get_user(uid: str) -> dict | None:
    with _conn().cursor() as cur:
        cur.execute("SELECT * FROM users WHERE id=%s", (uid,))
        return cur.fetchone()


def get_user_by_username(username: str) -> dict | None:
    with _conn().cursor() as cur:
        cur.execute("SELECT * FROM users WHERE username=%s", (username,))
        return cur.fetchone()


def get_user_by_email(email: str) -> dict | None:
    with _conn().cursor() as cur:
        cur.execute("SELECT * FROM users WHERE email=%s", (email,))
        return cur.fetchone()


def verify_user(username: str, password: str) -> dict | None:
    user = get_user_by_username(username)
    if not user:
        return None
    digest, _ = _hash_password(password, bytes.fromhex(user["salt"]))
    if digest != user["password_hash"]:
        return None
    return user
