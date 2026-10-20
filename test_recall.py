"""自由回忆录音模块回归测试:用假转写函数,不需要 Whisper 模型,也不需要真实音频。

覆盖:上传 → 轮询 → done;重复上传覆盖(幂等);转写失败 → retranscribe 恢复;
转写途中重新上传时旧任务结果作废;参数/状态错误码。

运行(务必用独立的测试库,脚本会先清空它):
    MYSQL_DB=lp_test_recall OPENAI_API_KEY=sk-test python test_recall.py
"""
import os
import sys

import pymysql
from fastapi.testclient import TestClient

DB = os.environ.get("MYSQL_DB", "")
if not DB.startswith("lp_test"):
    sys.exit("请用独立测试库运行,例如 MYSQL_DB=lp_test_recall(脚本会清空该库)")

import database as db                                    # noqa: E402  (先校验库名再连接)
_c = pymysql.connect(host=db.DB_HOST, port=db.DB_PORT, user=db.DB_USER, password=db.DB_PASSWORD)
_c.cursor().execute(f"DROP DATABASE IF EXISTS `{DB}`")
_c.close()

import shutil, tempfile                                  # noqa: E402
from pathlib import Path                                 # noqa: E402
import app, transcribe                                   # noqa: E402  (import app 会建库建表)

# 录音写到临时目录,不污染真实的 recordings/
app.RECORDINGS_DIR = Path(tempfile.mkdtemp(prefix="recall_test_"))

FAKE = {"fail": False}
def fake_transcribe(path):
    if FAKE["fail"]:
        raise RuntimeError("simulated transcription failure")
    return f"transcript of {Path(path).read_bytes().decode()}"
transcribe.transcribe_file = fake_transcribe

c = TestClient(app.app)
ok = 0
def check(cond, label):
    global ok
    assert cond, label
    ok += 1
    print("PASS", label)

s = db.create_session("RT001")
sid = s["id"]
url = f"/api/session/{sid}/recall"
def upload(body: bytes, kind="baseline", ctype="audio/webm"):
    return c.post(url, params={"kind": kind}, files={"audio": ("recall.webm", body, ctype)})

# 1. 正常上传:TestClient 会在响应后同步跑完 BackgroundTask
r = upload(b"take-1")
check(r.status_code == 200 and r.json()["status"] == "uploaded", "upload accepted")
row = c.get(url).json()
check(row["status"] == "done" and row["transcript"] == "transcript of take-1", "transcribed")
check("audio_path" not in row, "disk path not exposed")
first_id = row["id"]

# 2. 重复上传:同一 (session, kind) 覆盖,不新增行
upload(b"take-2")
row = c.get(url).json()
check(row["id"] == first_id and row["transcript"] == "transcript of take-2", "re-upload overwrites same row")
check(len(db.get_free_recalls(sid)) == 1, "still one row")

# 3. 转写失败 → 状态 failed,音频仍在;retranscribe 恢复
FAKE["fail"] = True
upload(b"take-3")
row = c.get(url).json()
check(row["status"] == "failed" and "simulated" in row["error"], "failure recorded")
FAKE["fail"] = False
r = c.post(url + "/retranscribe")
check(r.status_code == 200, "retranscribe accepted")
row = c.get(url).json()
check(row["status"] == "done" and row["transcript"] == "transcript of take-3", "retranscribe recovers")

# 4. 竞态:旧任务在新上传之后才回写 → 应被丢弃
stale = db.get_free_recall(sid, "baseline")
upload(b"take-4")
db.set_free_recall_transcript(stale["id"], stale["uploaded_at"], "STALE")
db.set_free_recall_status(stale["id"], stale["uploaded_at"], "failed", "STALE")
row = c.get(url).json()
check(row["status"] == "done" and row["transcript"] == "transcript of take-4", "stale task write ignored")

# 5. 不同 kind 互不影响
upload(b"post-take", kind="post")
check(c.get(url, params={"kind": "post"}).json()["transcript"] == "transcript of post-take", "post kind separate")
check(c.get(url).json()["transcript"] == "transcript of take-4", "baseline untouched")

# 6. 错误码
check(upload(b"x", kind="bogus").status_code == 400, "bad kind -> 400")
check(upload(b"").status_code == 400, "empty audio -> 400")
check(c.post("/api/session/nope/recall", files={"audio": ("a.webm", b"x", "audio/webm")}).status_code == 404,
      "unknown session -> 404")
s2 = db.create_session("RT002")
check(c.get(f"/api/session/{s2['id']}/recall").status_code == 404, "no recall yet -> 404")
old_max = app.MAX_RECALL_BYTES
app.MAX_RECALL_BYTES = 10
check(upload(b"x" * 11).status_code == 413, "oversize -> 413")
app.MAX_RECALL_BYTES = old_max
for f in app.RECORDINGS_DIR.rglob("baseline.*"):
    f.unlink()
check(c.post(url + "/retranscribe").status_code == 409, "missing audio file -> 409")

shutil.rmtree(app.RECORDINGS_DIR, ignore_errors=True)
print(f"\nALL {ok} CHECKS PASSED")
