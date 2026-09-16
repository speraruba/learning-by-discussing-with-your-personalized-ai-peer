# 学习伙伴实验 Agent

[English version](README.md)

一个"双主题 × 三轮讨论"实验的学习伙伴 agent。受试者通过网页与 agent 对话,全部对话历史(含认知冲突标记)、搜索记录与考试作答存入后端 MySQL 数据库。

## 实验流程

start 页之后,实验按两个主题依次进行,每个主题:**阅读一篇文章 → (讨论 → 自主搜索)× 3 轮**;主题 1 结束后是**休息页**,主题 2 结束后是**考试页**,提交答案后进入致谢结束页。页面顶部实时展示当前主题/讨论轮与环节。

```
主题 1: 阅读文章 1 → 讨论 1 → 搜索 1 → 讨论 2 → 搜索 2 → 讨论 3 → 搜索 3 → 休息页
主题 2: 阅读文章 2 → 讨论 1 → 搜索 1 → 讨论 2 → 搜索 2 → 讨论 3 → 搜索 3 → 考试页 → 结束再见
```

1. **阅读** — 每个主题开始时受试者阅读该主题的正方文章(`materials/article_{t}_P1_user` 的 Reading Material,编辑后刷新页面即生效);agent 的系统提示词中注入相反观点的材料(`materials/article_{t}_ai`,受试者不可见,每轮各一篇)。
2. **Onboarding 引导(仅主题 1)** — 读完文章 1 后 agent 先介绍流程,鼓励受试者积极发言、大胆表达观点;受试者明确确认准备好后(模型经 `advance` 字段判定)才进入第一轮讨论。主题 2 读完后 agent 直接开场(`topic_open`)进入讨论。
3. **讨论(辩论)** — agent 基于且仅基于自己本轮的材料与受试者辩论(允许推理,禁止引入材料外事实),每轮自评"是否触发认知冲突",服务端计数。同时,提示词注入 **BRIDGING GOAL**:讨论本轮学习目标的过程中,自然地把话题引向**同主题下一轮**的学习目标(不跨主题),不向受试者言明。
4. **引导总结** — 累计触发 **3 次**认知冲突后,agent 邀请受试者总结分歧与思考,明确无需达成一致。
5. **自主搜索** — 每轮讨论总结后进入搜索环节:受试者向中立的 search agent 提问,由其联网检索权威资料并附来源回答;点击"结束搜索"进入下一轮讨论(agent 开场衔接),或在第 3 轮后进入休息页/考试页。
6. **考试** — 主题 2 的 3 轮结束后,受试者在考试页逐题作答(题目见 `materials.py` 的 `EXAM_QUESTIONS`),提交后实验结束。

## 部署运行

密钥与连接信息**只从环境变量读取**,不写在代码里。可参考 `.env.example`:

```bash
cp .env.example .env      # 填入真实值(.env 已被 .gitignore 忽略)
set -a && source .env && set +a
```

或逐项 export:

```bash
pip install -r requirements.txt

# 1) OpenAI 密钥(必填,未设置时调用会返回 503 并提示)
export OPENAI_API_KEY="sk-..."        # 可选:export OPENAI_MODEL="gpt-4o"
# 可选:模型调用超时与重试(容错默认值)
export OPENAI_TIMEOUT=60              # 单次请求超时(秒),搜索环节用 OPENAI_SEARCH_TIMEOUT(默认 120)
export OPENAI_MAX_RETRIES=3           # SDK 对 429/5xx/连接错误的指数退避重试次数

# 2) MySQL 连接(未设置时用下方默认值)
export MYSQL_HOST=127.0.0.1           # 默认 127.0.0.1
export MYSQL_PORT=3306                # 默认 3306
export MYSQL_USER=root                # 默认 root
export MYSQL_PASSWORD=yourpassword    # 默认空
export MYSQL_DB=learning_partner      # 默认 learning_partner

uvicorn app:app --port 8000
```

浏览器打开 `http://localhost:8000`,首页输入姓名和研究者分配的 Participant ID 登录:
- 新 id:阅读并同意知情同意书 → 填写 Demographic Information(出生日期、年龄、性别、教育年限、
  英语母语情况、族裔)→ 填写 Background Information(AI Literacy Scale 12 条目,7 点李克特)
  → 建档并进入主题 1 的阅读页;
- 已存在的 id:核对姓名(大小写不敏感;不匹配则拒绝登录)后——已完成全部流程的直接进入致谢结束页,
  否则恢复到中断的环节(对话记录一并重放)。每人至多一次实验、不会重开。

### 断线容错

网页断开、浏览器崩溃、换电脑、服务重启都不会丢进度 —— 进度全部保存在服务端,客户端只是显示层。

- **重新进入**:回到首页输入同一个 Participant ID,即恢复到上次停留的环节,并重放全部对话记录(讨论页按主题/讨论轮分隔,搜索页显示当前轮的问答与来源)。刷新页面时浏览器会自动完成这一步,无需重新输入。
- **半路断在模型回复上**:受试者的发言先入库,若 agent 回复因断线/模型故障没写成,恢复时服务端会标记 `pending`,前端自动调用 `POST /api/session/{sid}/retry-turn` 补齐这一轮,受试者不会卡在自己的消息上。
- **重复提交安全**:重发同一句话不会重复入库;`done-reading`、`end-search`、`end-rest`、`exam` 重复调用幂等(不会重复入库或重复推进);已完成的步骤返回 `409`,前端据此重新同步而不是把错误抛给受试者。
- **发言不丢**:请求失败时输入框里的内容会还给受试者,顶部显示"连接中断,正在重新连接",后台按退避策略自动重试;网络恢复(`online` 事件)或切回页面时自动同步。
- **模型调用**:超时 + 指数退避重试(见上方环境变量),避免上游卡死导致受试者长时间空等。
- **数据库连接**:空闲被 MySQL 断开时自动重连;读操作断线后重连重试一次(写操作不自动重试,避免重复入库,由上述幂等接口兜底)。

回归测试(用假 agent 模拟各种失败,不消耗 API 额度):

```bash
MYSQL_DB=lp_test OPENAI_API_KEY=sk-test python test_fault_tolerance.py
```

### 数据库自动初始化

需要 MySQL 5.7+ / 8.0(使用了 `JSON` 列)。**无需手动建库建表**:应用启动时 `database.init_db()` 会自动检查并完成:

1. 数据库不存在 → `CREATE DATABASE`(utf8mb4 / utf8mb4_unicode_ci);
2. 表不存在 → 按声明创建 `participants`、`sessions`、`messages`;
3. 表已存在 → 对比声明,自动 `ADD COLUMN` / `ADD KEY` / `ADD CONSTRAINT` 补齐缺失的列、索引与外键(**只增不改不删**,已有数据不受影响);
4. 结构已最新 → 零改动。

启动时 MySQL 尚未就绪会自动重试(默认 10 次,间隔 1.5s),仍失败则报错退出并提示检查连接配置。

表结构的唯一事实来源是 `database.py` 顶部的 `SCHEMA` 字典 —— 以后新增字段只需在其中追加一行,重启应用即自动升级线上表结构。

## 实验材料

材料全部放在 `materials/` 目录,按文件组织(由 `materials.py` 启动时解析):

- **`article_{t}_ai`** — 主题 t 的 AI 学习伙伴材料(反方,只注入系统提示词、不向受试者展示):`# Topic:` 标题(即 agent 的立场命题)+ `## Phase 1-3` 分节,每节含 `### Learning Goal` 与 `### Reading Material`。
- **`article_{t}_P{n}_user(.md)`** — 主题 t 第 n 轮受试者一方(正方)的材料,供 agent 预判受试者立场:`# Topic:` 标题(即界面显示的辩题)+ `# Learning Goal` + `# Reading Material`。**P1 的 Reading Material 同时是该主题阅读页展示的文章**(每次请求现读文件,编辑后刷新页面即生效;其余材料改动需重启服务)。
- **考试题目**:`materials.py` 的 `EXAM_QUESTIONS`(当前为占位题目,请替换)。
- `CONFLICTS_REQUIRED = 3` 可调整每轮讨论所需认知冲突次数。

## 数据导出

- **一个主题对应一条独立 session**(`sessions.topic` 标注主题号):主题 1 的会话在休息页结束时标记 `done`,随后为受试者新建主题 2 的会话;两个主题的对话记录、搜索记录按 session 彼此隔离,恢复时只重放当前主题的记录。
- 数据库:MySQL 库 `learning_partner`(表 `participants`、`sessions`、`messages`、`search_queries`、`exam_answers`,以及旧流程遗留的 `causal_graphs`——当前流程不再生成,仅历史数据随 `history` 接口一并导出)
- 受试者存于 `participants` 表(`participant_id` 唯一索引,大小写不敏感):姓名 + id + 人口学信息(出生日期、年龄、性别、教育年限档位、是否英语母语、第一语言、英语习得年龄、是否 Hispanic/Latino、种族类别),专业背景(主修专业、第二主修专业、辅修,后两者可为空),AILS 量表（12 个原始作答列及反向计分后的 `ails_score`，范围 12–84），以及 LLM 使用信息（总体频率、使用目的、是否用于学习、学习频率和学习方式）。多选的 LLM 用途与学习方式以 JSON 数组存储。
- 单个会话导出:`GET /api/session/{session_id}/history`
  每条消息含:阶段、环节、角色、内容、`conflict`(是否被判定为触发认知冲突)、`meta.reason`(模型的判定理由)、时间戳。
- 冲突计数与判定理由仅存后端,**受试者界面不显示**,避免干扰实验。

## 认知冲突判定说明

采用"模型结构化自评"方案:agent 每轮以 JSON 输出 `{reply, conflict_triggered, reason}`,系统提示词中给出了严格的判定标准(必须是针对受试者已表达立场的、此前未提出过的新论点/证据/质疑;重复论点、澄清性追问、受试者已认同的点均不计)。如需更严格,可在 `agent.py` 中改为独立"裁判"模型二次判定。

## 结构

```
app.py         FastAPI 后端、受试者 ID 接口与"双主题×三轮"状态机
agent.py       提示词构建 + GPT 调用(密钥只从环境变量读取)
.env.example   环境变量模板(复制为 .env 填写;.env 已被 git 忽略)
materials.py   两个主题(各 3 轮)的讨论配置与考试题目
materials/     实验材料:article_{t}_ai(AI 伙伴每轮材料)与 article_{t}_P{n}_user(受试者每轮材料)
database.py    MySQL 存储:SCHEMA 声明 + 启动时自动建库/建表/补列
static/        受试者网页界面(登录、知情同意、人口学信息、阅读、对话、搜索、休息、考试、致谢结束页;含断线自动恢复)
test_fault_tolerance.py  断线容错回归测试(需独立测试库,见"断线容错")
```
