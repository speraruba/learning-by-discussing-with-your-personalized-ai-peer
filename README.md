# 学习伙伴实验 Agent

一个用于三阶段"阅读—阐述—辩论—总结"实验的学习伙伴 agent。受试者通过网页与 agent 对话,全部对话历史(含认知冲突标记)存入后端 MySQL 数据库。

## 实验流程

**阅读只在第一阶段进行**;后续阶段不再阅读新文章,新内容通过讨论产生。页面顶部实时展示当前阶段与环节。

1. **阅读(仅阶段 1)** — 受试者在网页上阅读文章 A;agent 的系统提示词中注入相反观点的材料(受试者不可见,每阶段各一篇)。
2. **Onboarding 引导** — 读完后 agent 先介绍研究流程,鼓励受试者积极发言、大胆表达观点、勇于提问不要害羞;受试者明确确认准备好后(模型经 `advance` 字段判定)才进入讨论。
3. **回顾分享** — agent 引导受试者 recall 所学;充分后 agent 分享自己材料的核心观点并过渡进入辩论。
4. **辩论** — agent 基于且仅基于自己的材料与受试者辩论(允许推理,禁止引入材料外事实),每轮自评"是否触发认知冲突",服务端计数。同时,提示词注入 **BRIDGING GOAL**:讨论当前阶段学习目标的过程中,自然地把话题引向**下一阶段**的学习目标(阶段1→阶段2,阶段2→阶段3),不向受试者言明。
5. **引导总结** — 累计触发 **3 次**认知冲突后,agent 邀请受试者总结分歧与思考,明确无需达成一致。
6. **阶段推进** — 受试者提交总结、agent 收尾后,**直接开启下一阶段讨论**:agent 发一条开场消息,衔接上一阶段内容并引出新阶段学习目标;三阶段完成后实验结束。

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

# 2) MySQL 连接(未设置时用下方默认值)
export MYSQL_HOST=127.0.0.1           # 默认 127.0.0.1
export MYSQL_PORT=3306                # 默认 3306
export MYSQL_USER=root                # 默认 root
export MYSQL_PASSWORD=yourpassword    # 默认空
export MYSQL_DB=learning_partner      # 默认 learning_partner

uvicorn app:app --port 8000
```

浏览器打开 `http://localhost:8000`,注册账号后自动进入第一阶段的阅读页。

### 数据库自动初始化

需要 MySQL 5.7+ / 8.0(使用了 `JSON` 列)。**无需手动建库建表**:应用启动时 `database.init_db()` 会自动检查并完成:

1. 数据库不存在 → `CREATE DATABASE`(utf8mb4 / utf8mb4_unicode_ci);
2. 表不存在 → 按声明创建 `users`、`sessions`、`messages`;
3. 表已存在 → 对比声明,自动 `ADD COLUMN` / `ADD KEY` / `ADD CONSTRAINT` 补齐缺失的列、索引与外键(**只增不改不删**,已有数据不受影响);
4. 结构已最新 → 零改动。

启动时 MySQL 尚未就绪会自动重试(默认 10 次,间隔 1.5s),仍失败则报错退出并提示检查连接配置。

表结构的唯一事实来源是 `database.py` 顶部的 `SCHEMA` 字典 —— 以后新增字段只需在其中追加一行,重启应用即自动升级线上表结构。

## 实验材料(已配置正式材料)

`materials.py` 已装入正式材料:受试者始终阅读正方文章(Topic 1: AGI Achieved),agent 始终阅读反方文章(Topic 2: AGI is Impossible to Achieve),辩论总议题为 "AGI has already been achieved",三个阶段分别聚焦各自的 Learning Goal(AGI 定义与测量 / AI 训练方式 / 人类智能的产生与评估)。

流程细节:受试者读完点击按钮后,agent 先围绕 Learning Goal 引导其做简短 recall;若 recall 过于空泛,agent 会追问一轮(模型通过 `advance` 字段判定),recall 充分后 agent 才分享自己材料的核心观点并过渡进入辩论。

`CONFLICTS_REQUIRED = 3` 可调整所需认知冲突次数。

## 数据导出

- 数据库:MySQL 库 `learning_partner`(表 `users`、`sessions`、`messages`)
- 受试者背景问卷存于 `users` 表:年龄、学历、专业、AI 整体熟悉度(0-10)、AI 原理了解度(0-10)、使用频率、主要用途(JSON 多选)、是否曾用 AI 辅助学习
- 单个会话导出:`GET /api/session/{session_id}/history`
  每条消息含:阶段、环节、角色、内容、`conflict`(是否被判定为触发认知冲突)、`meta.reason`(模型的判定理由)、时间戳。
- 冲突计数与判定理由仅存后端,**受试者界面不显示**,避免干扰实验。

## 认知冲突判定说明

采用"模型结构化自评"方案:agent 每轮以 JSON 输出 `{reply, conflict_triggered, reason}`,系统提示词中给出了严格的判定标准(必须是针对受试者已表达立场的、此前未提出过的新论点/证据/质疑;重复论点、澄清性追问、受试者已认同的点均不计)。如需更严格,可在 `agent.py` 中改为独立"裁判"模型二次判定。

## 结构

```
app.py         FastAPI 后端、注册/登录接口与阶段状态机
agent.py       提示词构建 + GPT 调用(密钥只从环境变量读取)
.env.example   环境变量模板(复制为 .env 填写;.env 已被 git 忽略)
materials.py   三阶段实验材料与辩题配置
database.py    MySQL 存储:SCHEMA 声明 + 启动时自动建库/建表/补列
static/        受试者网页界面(登录、注册、阅读、对话;支持中英文切换)
```
