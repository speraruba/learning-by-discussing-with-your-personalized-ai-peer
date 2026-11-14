# AI Study Peer — Study Protocol

**项目**：Learning by Discussing with Your Personalized AI Peer（帮助学习者提出自己需要问的问题）
**PI**：Jessie Chin（School of Information Sciences, UIUC）
**版本**：v0.1 draft · 2026-11-13
**状态**：研究设计整理稿。标 **【建议】** 的是本稿根据现有材料提出的方案；标 **【D-xx】** 的是需要 PI / 团队拍板的决策，汇总在 §10。

---

## 0. 本稿依据与术语

### 0.1 资料来源

| 文件 | 内容 | 本稿用在哪 |
| --- | --- | --- |
| `design/research_design_RQs_measures_2026-09-15_zh.pdf` | RQ1–RQ4 及每个 RQ 的测量指标、方法、时间点 | §1、§3、§4 |
| `materials_AGI/AGI_discussion_design.xlsx` | T-AGI 的 anchor questions、connections、三阶段讨论流程、statement tracking 编码表 | §2、§3.4、§5、§6、附录 B |
| `materials_AGI/AGI_statements_concept_map.docx` | T-AGI 的 statements / propositions / 补充解释 + expert concept map | 附录 A、C |
| `materials_AGI/AGI_readings_user_peer.docx` | T-AGI 的 User Reading（R1）与 Peer Readings（R1–R3）成文版 | §3.4、附录 A |
| `materials_COG/COG_statements_concept_map.docx` | T-COG 的 statements / propositions / examples（含 User / Peer 分工）+ expert concept map | 附录 A、C |
| `materials_COG/COG_reading_combined.docx` | T-COG 的成文阅读材料（未按 User / Peer 拆分） | 附录 A |
| `../PAST/`（旧版系统） | 辩论式学习伙伴：双主题 × 三轮（讨论 → 搜索）、认知冲突计数、CID agent、search agent、人口学 + AILS + LLM 使用问卷、断线容错、consent | §4.1、§5、§7 |

路径相对于 `context/`。下文的「Excel」指 `AGI_discussion_design.xlsx`，「PDF」指 `research_design_RQs_measures_2026-09-15_zh.pdf`。

### 0.2 新旧设计的关系

旧版（`../PAST/`）是**辩论式**：agent 持相反立场，以「认知冲突」次数推进。新版是**拼图式共建（jigsaw-style co-construction）**：学习者和 AI peer 各持一部分材料，通过「复述 → 建立联系 → 共同回答 anchor question」三步把知识拼成完整的概念图。认知冲突计数在新版中不再使用。

旧版可直接复用的基础设施：断线恢复与幂等接口、MySQL `SCHEMA` 自动迁移、人口学 / AILS / LLM 使用问卷、search agent（OpenAI `web_search`）、CID agent（从对话推断学习者心智模型，即新版 DG2 的前身）。

### 0.3 统一术语

现有文件对层级的叫法不一致（`AGI_statements_concept_map.docx` 把三轮叫 Phase 1–3，Excel 把三轮叫 Round、轮内步骤叫 Phase，PDF 叫「阶段」）。本稿统一为：

| 术语 | 含义 | 对应旧叫法 |
| --- | --- | --- |
| **Topic** | 一套学习材料。**T-AGI**：What counts as AGI / how do we measure intelligence；**T-COG**：AI and the division of cognitive work | — |
| **Round (R1–R3)** | 一个内容单元，有自己的 anchor question 和新概念 | `AGI_statements_concept_map.docx` 的 Phase；PDF 的「阶段」 |
| **Phase (P1–P3)** | Round 内的讨论步骤：P1 Sharing、P2 Connecting、P3 Joint Explanation | Excel 的 stage / Phase |
| **Search** | Round 讨论结束后的自主检索环节 | 旧版「搜索」、PDF「检索阶段」 |
| **Concept** | 概念图的节点（如 Generalization） | — |
| **Statement** | 一条可复述的知识陈述，带稳定 ID（`U1-A1`、`P2-B3`） | — |
| **Proposition / Edge** | 概念图上的一条带标签连线：Concept → relation → Concept | — |
| **Gap** | 学习者在某个 statement / edge 上未掌握或理解错误的状态 | PDF「推理缺口」「知识缺口」 |
| **LKS** | Learner Knowledge State，系统内部唯一的学习者知识状态表示（见 DG2） | 旧版 CID diagram |

PDF 中「每个阶段结束后」本稿解读为**每个 Round 结束后**。

---

## 1. Research Questions

**Overall RQ**：一个能从讨论中诊断学习者知识缺口的 AI study peer，能否让学习者学得更好，并帮助他们提出针对自身缺口的问题？

- **RQ1 (Learning Outcome)**：与阅读完整材料、可自由检索信息的自学方式相比，AI study peer 辅助的学习能否让学习者学得更好？
  - 数据：U-11 / U-20 自由回忆（概念数、覆盖率、新掌握概念数）、U-21 最终概念图（与 expert map 相似度）、U-22 理解测验正确率。
- **RQ2 (Diagnostic Validity)**：AI peer 能在多大程度上根据讨论，准确识别学习者尚未明确表达的推理缺口？
  - 数据：S3 AI 预测的概念图 vs. U-12 学习者每轮自画概念图；S3 LKS vs. U-22 测验逐题对错；S3 LKS vs. U-13 检索提问内容；S3 LKS vs. 人工 Statement Tracking 编码（附录 B.3）。
- **RQ3 (Mechanism)**：当 AI 根据学习者的知识缺口提供支持时，这种支持如何影响讨论的焦点与深度？学习者为弥补重要缺口而提出的问题如何变化？
  - 数据：U-12 各轮新掌握概念数；S2 讨论记录的内容编码（概念覆盖、缺口聚焦、IAM 深度）；U-13 检索提问的类型编码（Chin & Brown）与缺口指向编码。
- **RQ4 (Experience，次要结果)**：学习者对不同条件下学习体验的评价。
  - 数据：U-23 自评学习收获、SUS、NASA-TLX。

PDF 将 RQ3 中的「讨论的概念覆盖情况」与「讨论对知识缺口的聚焦程度」标为「可删」。两者都是对 S2 的事后编码，不占用被试时间，删与留只影响编码工作量【D-13】。

---

## 2. Design Goals

### RQ2 对应的 DG

- **DG1 (Elicitation)**：系统通过结构化讨论让学习者**用自己的话**说出每条 statement 和 statement 之间的联系，使推理缺口在对话中显形。具体约束（来自 Excel）：
  - P1 Sharing：学习者先讲自己读的 statements（仅 R1），再逐条复述 peer 的 statements；peer 每条消息只呈现一条 statement；复述不完整时**追问缺失部分而不是直接纠正**。
  - P2 Connecting：peer 用 case question 引出联系，**从不先说出联系本身**；学习者自己读过的 statement 交还给学习者解释（Lead = User）。
  - P3 Joint Explanation：学习者先起草 2–3 句答案，peer 只补充、修订，不重写。
  - 输入模态：文字聊天。负担约束见 §3.4 时间预算。

- **DG2 (Inference)**：系统把讨论转成**唯一的内部状态表示 LKS**：对当前 topic 的每条 statement，记录其状态（见 §5 S3 的枚举）、追问次数、证据所在的对话轮次。LKS 每个学习者回合后更新。所有下游行为（选下一条追问、选 case question、检索前呈现什么、Round 末的预测概念图）都从 LKS 派生。
  - 每条 expert edge 对应一条 statement（附录 C），因此「AI 预测的概念图」是 LKS 在 expert edge 集上的投影，与学习者自画概念图在同一套 edge 上比较。
  - 旧版 CID agent 直接从 transcript 生成图，与 peer 的对话逻辑是两条并行的状态来源；新版把预测图改为 LKS 的派生物，保证 RQ2 测的就是驱动 peer 行为的那个状态。

### RQ3 对应的 DG

- **DG3 (Gap-adaptive Moves)**：peer 根据 LKS 中的 gap 选择下一步对话动作。动作集合（每轮自标，记入 S3）：
  `PRESENT_STATEMENT`、`ASK_RESTATE`、`PROBE_MISSING`（追问缺失部分）、`HAND_BACK`（把 User 拥有的 statement 交回学习者解释）、`ASK_CASE`、`ASK_LINK_STATEMENT`（“Which of the statements we covered does this relate to?”）、`ASK_CONNECTION_SENTENCE`、`ASK_DRAFT`、`ADD_TO_DRAFT`、`MARK_OPEN`（标记 open question）、`REVISIT_GAP`（在后续 Round 中回到前一轮的 gap）。
  - 自适应体现在三处：P1 中对 gap statement 的追问次数与方式；P2 中优先选择涉及 gap statement 的 connection（附录 B.2 的 C-x-x）；R2–R3 中通过 `REVISIT_GAP` 回到上一轮未解决的 gap。
  - 理论依据：学习者自己生成解释与联系属于 ICAP 框架中的 constructive / interactive 层级（Chi & Wylie, 2014）。

- **DG4 (Gap Surfacing before Search)**：Round 讨论结束、进入 Search 之前，系统把讨论的产出交还给学习者：已确认的 connection list、joint explanation、标记为 “not yet resolved” 的 open questions。Search 中由中立 search agent 回答学习者的问题并附来源。
  - gap 以何种显式程度呈现是本研究最关键的设计决策之一【D-04】：如果系统直接列出「你的薄弱点是 X」，RQ3 的「针对已识别缺口的提问比例」会被呈现方式机械抬高。**【建议】** 只呈现讨论自然产出的 open questions 和 connection list，不呈现 gap 清单；S4 记录实际呈现内容。

---

## 3. 研究设计

### 3.1 形态

- **设计类型**：between-subjects，两组（AI Peer vs. Self-study）【D-02、D-03】
- **研究场景**：线上远程，Zoom，研究员在场静默观察（沿用旧版 consent）
- **时长结构**：单次 session；预计 105–110 分钟（§3.4），超过旧版 consent 的 60 分钟【D-08】
- **交付形态**：桌面 web（沿用旧版 FastAPI + 单页前端）
- **材料**：**【建议】** 正式实验只用 T-AGI（唯一具备完整 anchor question、connection、statement tracking 设计的 topic）；T-COG 用于 pilot 和系统调试【D-01】

### 3.2 条件与对照

| 条件 | 系统配置 | 对应 DG |
| --- | --- | --- |
| **C1 Self-study** | 按 Round 分块阅读该 Round 的**完整**材料（User + Peer Readings），时间与 C2 对齐（见下），之后进入同样的 Search 与概念图 | 无 DG1–DG4；RQ1 的对照 |
| **C2 AI Peer（完整系统）** | 拼图式三阶段讨论 + LKS + gap-adaptive moves + 检索前产出呈现 | DG1–DG4 |
| C3 Generic Peer（可选） | 同样的三阶段脚本，但 peer 不读 LKS：按固定顺序呈现 statements 和 connections，不做 `PROBE_MISSING` / `REVISIT_GAP` 自适应 | 消融 DG2 + DG3【D-03】 |

**两组设计能回答什么**：C1 vs. C2 回答 RQ1（整个系统 vs. 自学）。RQ2 只在 C2 内回答。RQ3 的「讨论焦点与深度」只在 C2 内以 Round 间变化和 gap 相关性来回答；「检索提问」可以跨 C1、C2 比较（见下文 gap 的统一定义）。要把学习收益归因到「个性化 / 根据缺口提供支持」本身，需要 C3。

**C1 的结构【建议】**：C1 与 C2 共享同一时间骨架，只替换讨论环节：
`R1 User Reading → Free recall #1 → [R_r 完整阅读（自学）→ 概念图 → Search] × 3 → Post`。
这样两组在首次回忆前读的是同一份材料（R1 User Reading），RQ1 的「新掌握概念数」有可比基线；两组每轮都产生概念图和检索提问，RQ3 的提问分析可跨组比较。自学时长与 C2 讨论时长对齐的方式【D-02】：固定时长（取 pilot 中 C2 各 Round 讨论时长中位数）或可提前结束并记录实际时长。

**跨组统一的 gap 定义【建议】**：以学习者**自画的 Round 概念图**为准，expert edge 缺失或连错即为 gap。C2 中额外有 LKS 给出的「AI 识别的 gap」，用于 RQ2 准确率。这样 C1 也有 gap 定义，「针对知识缺口的提问比例」可跨组比较。

- **分配方式**：按到场顺序区组随机（block size 4）。**【建议】** 以 AILS 总分中位数分层【D-15】。
- **盲化**：被试无法对条件盲化。自由回忆、概念图、测验、检索提问的编码者对条件盲（导出时去掉 condition 字段）；讨论记录的编码天然只来自 C2，无法盲。

### 3.3 被试与样本量

- **目标人群**：UIUC 学生，18 岁以上，英语流利（材料与讨论为英文）。**【建议】** 排除修过 AI / 机器学习 / 心理测量课程者，因为 T-AGI 的内容会产生天花板效应【D-16】。
- **目标 N**：两组 between-subjects 独立样本比较，α = .05、power = .80：d = 0.5 需每组 64 人；d = 0.8 需每组 26 人。效应量来源待定（同类 AI tutoring / peer learning 研究）【D-17】。加入 C3 则总 N 按 1.5 倍计。
- **招募渠道**：沿用旧版（Zoom 预约）。具体渠道待定。
- **分析时的排除标准（收数据前定稿）**：
  - session 未完成 R3 讨论 / 自学 → 排除出 RQ1；已完成的 Round 保留在 RQ2、RQ3 中；
  - 某 Round 的概念图缺失 → 该 Round 排除出 RQ2；
  - S6 记录到讨论 / 回忆 / 测验阶段长时间离开页面（阈值待定）或研究员观察到使用外部 AI 工具 → 排除；
  - 系统故障导致某 Round 讨论中断且无法恢复 → 该被试排除出 RQ1，记录在 §8。

### 3.4 任务与流程

**C2 AI Peer（T-AGI）**

| 阶段 | 做什么 | 时长（估） | 数据 |
| --- | --- | --- | --- |
| Consent | 阅读并同意知情同意书 | 3 | — |
| Pre 问卷 | 人口学、学业背景、AILS、LLM 使用 | 7 | U-01–U-03 |
| 概念图练习 | 用无关小主题练习概念图工具，不计分 | 3 | U-05 |
| 首次阅读 | R1 User Reading（AGI Definition、Target Capabilities） | 5 | S1 |
| Free recall #1 | 不看材料，写下记得的内容 | 3 | U-11 |
| R1 讨论 | P1 Sharing（14 statements：先讲 7 条自己的，再复述 7 条 peer 的）→ P2 Connecting（2–3 条 connection）→ P3 Joint Explanation | 20 | U-10、U-14、S1–S5 |
| R1 概念图 | 在 R1 概念库上画连线并标注关系；**此前**系统已生成并封存 AI 预测图 | 4 | U-12、S3 |
| R1 Search | 看到 connection list + open questions，向 search agent 提问 | 5 | U-13、S2、S4 |
| R2 讨论 | P1（6 statements）→ P2 → P3 | 12 | 同 R1 |
| R2 概念图 | 在 R1+R2 概念库上继续画 | 3 | U-12、S3 |
| R2 Search | 同 R1 | 5 | U-13 |
| R3 讨论 | P1（7 statements）→ P2 → P3 | 13 | 同 R1 |
| R3 概念图 | 在全部概念库上继续画；**兼作最终概念图**【D-11】 | 4 | U-12 / U-21、S3 |
| R3 Search | 可选【D-10】 | (5) | U-13 |
| Free recall #2 | 不看材料，写下记得的全部内容 | 4 | U-20 |
| 理解测验 | 判断题 / 选择题 | 10 | U-22 |
| Post 问卷 | 自评学习收获、SUS、NASA-TLX | 5 | U-23 |
| **合计** | | **约 106（含 R3 Search 约 111）** | |

**C1 Self-study**：Consent、Pre 问卷、概念图练习、首次阅读、Free recall #1 与 C2 相同；每个 Round 的「讨论」替换为阅读该 Round 的完整材料（R1 为 Peer Reading R1，因 User Reading 已读过；R2、R3 为对应 Peer Reading），可随时回看本 Round 及之前的材料；其余阶段相同。

**重复测量**：概念图与 Search 每 Round 一次，共 3 次；顺序固定为 讨论/自学 → 概念图 → Search，保证概念图反映检索前的状态，与 AI 预测图（同样基于检索前的讨论）对齐。

**Phase 推进与超时**：每个 Phase 有结束条件（Excel）：P1 全部 statements 复述完；P2 学习者确认 2–3 条 connection；P3 双方同意最终答案。**【建议】** 每个 Phase 设软上限（P1 12 分钟、P2 8 分钟、P3 5 分钟），到时 peer 收尾进入下一 Phase，结束方式记入 S5【D-12】。

**负担预算**：旧版 consent 承诺 60 分钟 / $15。当前流程约 106–111 分钟。压缩选项按对数据的损失从小到大排列：
1. 最终概念图与 R3 概念图合并（已在上表采用）；
2. 取消 R3 Search（R3 之后没有下一个 Round 来检验检索效果）；
3. 测验按 statement 每条 1 题（27 题），只对核心 statement 出 2–3 题；
4. 将 Round 概念图改为在上一轮图上增量修改（已采用「继续画」），并只在 R1、R3 采集（会削弱 RQ2）。

### 3.5 分析计划（概要）

| RQ | 指标 | 单位 | 分析 |
| --- | --- | --- | --- |
| RQ1 | 回忆概念数 / 覆盖率（#2）；新掌握概念数（#2 − #1）；最终概念图与 expert map 的 edge-level F1；测验正确率 | 被试 | C1 vs. C2 独立样本比较；以 #1 回忆、AILS 为协变量的 ANCOVA |
| RQ2 | AI 预测图 vs. 学习者图在 expert edge 集上的一致性（逐 edge 的 accuracy、Cohen's κ，gap 检出的 sensitivity / specificity）；LKS vs. 测验逐题；LKS vs. 人工 Statement Tracking | 被试 × Round × edge | 描述统计 + 按 Round 的混合效应模型（被试随机效应） |
| RQ3 | 各 Round 新掌握 edge 数；讨论概念覆盖 / 缺口聚焦 / IAM III–V 占比；提问类型（Chin & Brown）；缺口指向提问比例 | 被试 × Round（讨论单元 / 提问） | C2 内 Round 间变化；提问相关指标 C1 vs. C2 |
| RQ4 | 自评收获、SUS、NASA-TLX | 被试 | C1 vs. C2 |

**计分单位【建议】**：概念级（T-AGI 共 9 个节点，含终点 AGI Assessment）太粗，回忆与「新掌握」按 **statement 级**（27 条）计分，同时报告概念级；概念图按 **edge 级**（9 条）计分。

**RQ2 中 PDF 未写完的一行**：「搜索环节是否问了薄弱知识点相关的问题 — 下一个 phase 被重新问起这个知识点的时候，condition 是否推进」。本稿解读为：对 Round r 的 gap statement，若学习者在 Search r 中就它提问，则在 Round r+1 的 `REVISIT_GAP` 或下一张概念图中，该 statement 的状态是否前进。需 PI 确认【D-14】。

---

## 4. 用户主动提供的数据（Participant-provided）

### 4.1 Baseline / Pre

| ID | 采集项 | 形式 | 用途 |
| --- | --- | --- | --- |
| U-01 | 人口学：出生日期、年龄、性别、受教育年限档位、英语母语、第一语言、英语习得年龄、Hispanic/Latino、种族；主修 / 第二主修 / 辅修 | 表单（沿用旧版） | 样本描述 |
| U-02 | AI Literacy Scale（Wang et al., 2023）12 题，7 点 Likert；AW_8 / US_3 / ET_2 反向计分 | Likert | 协变量 / 分层变量 |
| U-03 | LLM 使用：总体频率、用途（多选）、是否用于学习、学习频率、学习方式（多选） | 表单（沿用旧版） | 协变量 |
| U-05 | 概念图工具练习（无关小主题，如「早餐 → 提供 → 能量」） | 概念图工具 | 熟悉工具；**不计入任何分析** |

U-01 中出生日期与 consent「不收集可识别信息」的承诺冲突，见 §7。

### 4.2 任务中 / 重复测量

| ID | 采集项 | 阶段 | 形式 | 条件 |
| --- | --- | --- | --- | --- |
| U-10 | 讨论发言 | R1–R3 讨论 | 文字聊天 | C2 |
| U-11 | Free recall #1 | 首次阅读后 | 自由文本 | C1、C2 |
| U-12 | Round 概念图 | 每 Round 讨论 / 自学后 | 概念图工具：节点来自已学 Round 的概念库，学习者画连线并写关系标签 | C1、C2 |
| U-13 | 检索提问 | 每个 Search | 向 search agent 输入的问题 | C1、C2 |
| U-14 | Connection list 确认 + Joint explanation 定稿 | 每 Round P2 / P3 末 | 对话中确认 | C2 |

**概念图节点库**：只给出截至当前 Round 已学过的概念（R1：AGI Definition、Target Capabilities、AI Ability Tests、Generalization、AGI Assessment；R2 加 AI Training、Pattern Learning；R3 加 Human Intelligence、Human Intelligence Tests）。给定节点让计分集中在 edge 上，同时避免提前泄露后续 Round 的概念名。

### 4.3 Post

| ID | 采集项 | 形式 |
| --- | --- | --- |
| U-20 | Free recall #2 | 自由文本，不看材料 |
| U-21 | 最终概念图（= R3 概念图，见【D-11】） | 概念图工具 |
| U-22 | 理解测验：每条核心 statement 2–3 道判断 / 选择题 | 选择 |
| U-23 | 自评学习收获（题目待定）、SUS（Brooke, 1996）10 题、NASA-TLX（Hart & Staveland, 1988）6 个子量表 | Likert / 滑条 |

SUS 在两组评的是不同的界面（C2：讨论 + 检索系统；C1：阅读 + 检索界面），跨组比较时解释为「整体学习环境的可用性」。

半结构式访谈不在当前 consent 范围内，本版不安排。

---

## 5. 系统自动记录的数据（System-logged）

本节为 dev spec。旧版表 `participants`、`sessions`、`messages`、`search_queries`、`exam_answers` 保留并扩展；新增字段在 `../PAST/database.py` 的 `SCHEMA` 中追加即可。

### S1 · Session 元数据

- [ ] participant ID、session ID、**condition**、**topic**、开始 / 结束时间戳
- [ ] 当前 Round、Phase、state（reading / recall / discussion / map / search / quiz / post）
- [ ] 每次 Round / Phase / state 切换的时间戳（用于计算各段时长、对齐 C1 自学时长）
- [ ] 每次模型调用的 **prompt 版本号、模型 ID**

### S2 · 交互存档

- [ ] 讨论全部消息：Round、Phase、role、原文、时间戳
- [ ] Search：学习者问题原文、search agent 回答原文、引用来源 URL、时间戳
- [ ] 只存文字。Zoom 是否录屏【D-09】

### S3 · 模型侧输出

- [ ] **LKS 快照**：每个学习者回合后，对每条 statement 存
  `{status, prompts_needed, evidence_turn_ids}`，
  `status ∈ {not_introduced, introduced, restated_partial, restated_adequate, misconception, used_in_connection}`
  （与人工 Statement Tracking 表的 Covered / Restated / Prompting needed / Used in connection 一一对应，便于做 RQ2 的人机一致性）
- [ ] **AI 预测概念图**：每 Round 讨论结束时由 LKS 投影到 expert edge 集，每条 edge 标 `present / absent / misconceived`。**在学习者开始画该 Round 概念图之前生成并封存，永不向学习者展示**
- [ ] 每条 peer 消息的 **move 标签**（DG3 动作集合）、目标 statement ID、目标 connection ID（如 `C1-3`）
- [ ] 每条 peer 消息的 restatement 判定（adequate / partial + 理由），对应 Excel「moves on only when the restatement is adequate」
- [ ] prompt 版本号、模型 ID

两条硬约束，需写测试覆盖：
1. AI 预测图只使用截至该 Round 讨论结束的对话，**不读取学习者自画的任何概念图**【D-05】；
2. 预测图的生成时间戳早于学习者该 Round 概念图的首次操作时间戳。

### S4 · 呈现状态

- [ ] 每个 Search 开始时实际呈现给学习者的 connection list、joint explanation、open questions 原文
- [ ] C1 每个 Round 呈现的阅读材料版本
- [ ] 若采用任何 gap 提示（【D-04】），记录提示原文与对应 statement ID

RQ3 的「针对已识别缺口的提问」必须能对上学习者当时看到了什么。

### S5 · 交互质量指标

- [ ] 每 Phase 学习者发言轮数、每轮字数、Phase 时长
- [ ] 每条 statement 在被判 adequate 之前的追问次数
- [ ] 每 Phase 结束方式：结束条件达成 / 超时收尾
- [ ] 概念图操作日志：节点移动、连线增删、标签修改，含时间戳
- [ ] Search：提问数、时长、点击的来源
- [ ] 回忆与测验：首次输入延迟、提交时长；Likert 控件初始为未作答态，区分「未作答」与「中点」

### S6 · Engagement / 异常事件

- [ ] 页面失焦 / 切换标签页（`visibilitychange`）的起止时间，按阶段记录（用于检测外部检索或使用其他 AI 工具）
- [ ] 断线、恢复、`retry-turn`（沿用旧版容错机制）
- [ ] 模型调用失败、超时及当时的回退行为
- [ ] 中途退出：最后到达的阶段

---

## 6. 原句库（Verbatim Copy Deck）

讨论相关的句子取自 Excel，**原样使用**。标 `[DRAFT]` 的句子是本稿草拟，pilot 后定稿。

### 6.1 Onboarding

沿用 `../PAST/static/index.html` 的 Demographic Information 与 Background Information 页面。

**AI Literacy Scale（7 点，1 = Strongly disagree … 7 = Strongly agree）**
1. AW_1 _"I can distinguish between smart devices and non-smart devices."_
2. AW_8 (R) _"I do not know how AI technology can help me."_
3. AW_9 _"I can identify the AI technology employed in the applications and products I use."_
4. US_1 _"I can skilfully use AI applications or products to help me with my daily work."_
5. US_3 (R) _"It is usually hard for me to learn to use a new AI application or product."_
6. US_5 _"I can use AI applications or products to improve my work efficiency."_
7. EV_2 _"I can evaluate the capabilities and limitations of an AI application or product after using it for a while."_
8. EV_3 _"I can choose a proper solution from various solutions provided by a smart agent."_
9. EV_6 _"I can choose the most appropriate AI application or product from a variety for a particular task."_
10. ET_1 _"I always comply with ethical principles when using AI applications or products."_
11. ET_2 (R) _"I am never alert to privacy and information security issues when using AI applications or products."_
12. ET_5 _"I am always alert to the abuse of AI technology."_

**LLM Use and Learning**：沿用旧版题目与选项（频率四档：Never / Several times a month / Several times a week / Almost every day；用途 9 项多选；学习方式 8 项多选）。

### 6.2 回忆与概念图｜User input：自由文本 / 概念图工具

- Free recall `[DRAFT]`：_"Without looking back at the reading, write down everything you remember about what you have learned so far. Full sentences or short notes are both fine."_
- Round 概念图 `[DRAFT]`：_"Below are the concepts you have learned so far. Draw a link between any two concepts you think are related, and label each link with a short phrase that describes how they are related."_

### 6.3 讨论流程（C2）｜User input：文字聊天

**Anchor questions**（P2 开始时由 peer 提出）
- R1：_"An AI got 9 out of 10 reasoning questions right. To judge how far it is from AGI, what else would we need to know?"_
- R2：_"A spam classifier gets almost every training email right. How could we tell whether it has really learned to recognize spam?"_
- R3：_"When designing AI ability tests, what can we borrow from human intelligence tests, and what should we watch out for if we copy them directly?"_

**P1 Sharing**
- R1 开场：_"Let's start with your reading. What does the AGI definition emphasize?"_
- 复述请求：_"Could you put that in your own words?"_
- R2–R3 呈现 peer statement：_"Here's the first idea: … How would you say that in your own words?"_

**P2 Connecting**（每条 connection 四步：case question → 学习者回答 → 关联 statement → 一句话联系）
- _"Which of the statements we covered does this relate to?"_
- _"Can you say in one sentence how those two fit together?"_
- 各 Round 的 case question 原句见附录 B.2 的 Step 1 列。

**P3 Joint Explanation**
- _"Could you try answering the question in two or three sentences?"_
- _"I'd add one thing here: …"_

**措辞约束**：peer 补充学习者草稿时保留「我可能不确定」的空间（参照 Excel O2-1：_"I'm not sure."_），open question 明确标为 “not yet resolved”。

### 6.4 Search｜User input：文字提问

- 进入 Search `[DRAFT]`：_"Here is what we put together in this round, including the questions we left open. You can now look up anything you want to know more about. Type a question to the search assistant."_
- 呈现内容：connection list + joint explanation + open questions（见【D-04】）。
- search agent 系统提示沿用旧版 `SEARCH_RULES`（中立、跟随学习者、只引用权威来源），把 topic / learning goal 替换为本 Round 的 anchor question。检索范围是开放网络还是限定语料【D-06】。

### 6.5 Post-Study Questionnaire

- **自评学习收获**：题目待定（PDF 标注「待定中」）。
- **SUS**：10 题，5 点 Likert，标准原句（Brooke, 1996），“system” 在 C1 / C2 中分别指学习页面整体。
- **NASA-TLX**：Mental Demand、Physical Demand、Temporal Demand、Performance、Effort、Frustration 6 个子量表，标准原句（Hart & Staveland, 1988）。

### 6.6 理解测验

每条核心 statement 2–3 道判断题或选择题，题目待编写。每题标注对应的 statement ID，使测验逐题结果可以作为 RQ2 的第二个 ground truth。

---

## 7. 伦理与数据管理

旧版 consent（`../PAST/consent.txt`）的标题为 *Facilitate Belief Updating with Human-AI Teaming: Knowledge Acquisition with Information Exchange and Seeking*。新设计需要 IRB amendment，涉及以下几处：

- **IRB 编号与状态**：待补。
- **流程描述**：consent 中写的 “reading an assigned article on a target concept and drawing an initial concept map” 需改为本稿流程（首次阅读后自由回忆、每 Round 概念图、理解测验）。
- **时长与补偿**：consent 为 60 分钟 / $15；新流程约 105–110 分钟【D-08】。补偿按完成整个 session 发放还是按时长发放需写明。
- **可识别信息**：consent 写明 “We will not collect any identifiable information”，而旧版系统收集姓名（登录核对用）和出生日期。**【建议】** 新版登录只用研究者分配的 Participant ID，删去姓名与出生日期字段（保留年龄）；Participant ID 与真实身份的映射只存在研究员的预约表中，与研究数据分开存放。
- **原始媒体**：只存文字；Zoom 是否录制【D-09】，若录制需加入 consent。
- **存储**：UIUC Box（consent 已写明）；MySQL 运行库导出后存 Box，运行库在研究结束后清除。保留期待定。
- **第三方服务**：讨论与检索内容经 OpenAI API（旧版默认模型见 `../PAST/agent.py`）及其 web search 工具传输，需在 consent 中说明。
- **风险**：最小风险。主要风险为保密性丧失。
- **撤回**：被试可随时退出；退出后已收集的数据是否删除需写明。

---

## 8. 变更日志

| 日期 | 改了什么 | 影响哪些数据 | 版本号 |
| --- | --- | --- | --- |
| 2026-11-13 | 根据 context 资料整理研究设计初稿 | — | v0.1 |

---

## 9. 发布前检查清单

**协议完整性**
- [ ] §10 所有决策项已定稿
- [ ] 每个 RQ 至少有两个数据来源（RQ2：预测图 vs. 自画图、LKS vs. 测验、LKS vs. 人工编码）
- [ ] 每个 DG 在 §5 有对应记录项（DG1 → S2 / S5；DG2 → S3 LKS 与预测图；DG3 → S3 move 标签；DG4 → S4）
- [ ] 排除标准（§3.3）在收数据前定稿
- [ ] 测验每题有 statement ID
- [ ] 负担预算与 IRB 时长、补偿一致

**实现正确性**
- [ ] AI 预测图在学习者画图前生成、封存、不展示，且不读取学习者图（有测试）
- [ ] Likert 控件未作答态与中点可区分
- [ ] 所有模型输出带 prompt 版本号与模型 ID
- [ ] 条件分配、Phase 超时收尾、中途退出、模型调用失败各跑通一次
- [ ] C1 自学时长对齐机制按【D-02】实现

**端到端**
- [ ] 研究员完整走一遍两个条件
- [ ] 用 T-COG 做 2–3 人 pilot，再用 T-AGI 做 2–3 人 pilot，之后锁定 §6 措辞
- [ ] 导出 pilot 数据，用导出字段实际算一遍 §3.5 的每个指标

---

## 10. 待决策事项

| ID | 问题 | 选项 | 本稿建议 |
| --- | --- | --- | --- |
| D-01 | 用哪个 topic | (a) 只用 T-AGI；(b) T-AGI + T-COG 两个 topic，within-subjects 条件 × topic 计数平衡（旧版就是双主题） | (a)。T-COG 缺 anchor questions、connections、User / Peer 分拆的成文阅读；双主题使时长翻倍 |
| D-02 | C1 自学的结构与时长 | 按 Round 分块 + 固定时长 / 可提前结束；或一次性读完全部材料 | 按 Round 分块，固定时长取 pilot 中位数 |
| D-03 | 是否加 C3 Generic Peer | 加：可以检验「个性化」本身；不加：RQ3 只能做 C2 内的相关分析 | 视样本量预算决定；若项目标题强调 “personalized”，C3 是支撑这一主张的条件 |
| D-04 | Search 前 gap 呈现的显式程度 | 只呈现讨论产出（connections + open questions）；或显式列出 gap | 只呈现讨论产出 |
| D-05 | AI 是否读取学习者自画的概念图 | 读：个性化更强，但 RQ2 不再是「从讨论推断」；不读 | 不读 |
| D-06 | 检索范围 | 开放网络（旧版）；限定语料（只含材料及扩展文献） | 两组相同即可；开放网络更贴近 RQ1 的「自由检索」 |
| D-07 | 概念图节点是否给定 | 给定节点只画连线；完全自由 | 给定截至当前 Round 的节点 |
| D-08 | 总时长与补偿 | 压缩到 60–75 分钟；或延长并提高补偿 | 选项 1–3 只能压到约 95–100 分钟，压到 60 分钟必须砍掉 Round 概念图（削弱 RQ2）。建议保留流程、按约 105 分钟申请 amendment 并提高补偿 |
| D-09 | Zoom 是否录制 | 录 / 不录 | 不录，研究员只做现场笔记 |
| D-10 | R3 之后是否有 Search | 有 / 无 | 无 |
| D-11 | 最终概念图是否与 R3 概念图合并 | 合并 / 单独再画 | 合并 |
| D-12 | Phase 软上限 | 有 / 无；具体分钟数 | 有，P1 12 / P2 8 / P3 5 分钟 |
| D-13 | RQ3 中两项「可删」指标 | 保留 / 删除 | 保留为探索性分析（只增加编码工作量） |
| D-14 | RQ2 第二行指标的含义 | 见 §3.5 解读 | 由 PI 确认 |
| D-15 | 分层随机的变量 | AILS / LLM 学习使用频率 / 不分层 | AILS 中位数 |
| D-16 | 纳入排除标准中的先验知识 | 是否排除 AI / ML / 心理测量背景 | 排除 |
| D-17 | 目标效应量与 N | d = 0.5（每组 64）/ d = 0.8（每组 26） | 依据同类研究定 |
| D-18 | 「Personalized」的范围 | 只指 LKS 驱动的 gap 自适应；或也包括按学习者专业 / 背景定制例子 | 只指 LKS 驱动（材料与 Excel 中没有背景定制的设计） |
| D-19 | 附录 D 的材料不一致 | 逐条确认 | 见附录 D |

---

## 附录 A · 材料结构

### A.1 T-AGI（正式实验建议用）

| Round | Anchor question 主题 | 概念（Source） | Statements |
| --- | --- | --- | --- |
| R1 What Counts as AGI? | 9/10 推理题正确的 AI 离 AGI 多远 | AGI Definition、Target Capabilities（User）；AI Ability Tests、Generalization（Peer） | 14（User 7 + Peer 7） |
| R2 Where Do AI Capabilities Come From? | 训练集上近乎完美的 spam classifier | AI Training、Pattern Learning（Peer） | 6 |
| R3 How Do We Measure Intelligence? | 借用人类智力测验设计 AI 测验 | Human Intelligence、Human Intelligence Tests（Peer） | 7 |
| 合计 | | 8 个概念 + 终点节点 AGI Assessment | 27 |

成文阅读：R1 User Reading、R1–R3 Peer Readings（`AGI_readings_user_peer.docx`）。C2 中学习者只读 R1 User Reading，Peer Readings 只注入 peer 的系统提示；C1 读全部。

### A.2 T-COG（建议用于 pilot）

| Round | 主题 | 概念（Source） | Statements |
| --- | --- | --- | --- |
| R1 | AI 如何改变人脑与外部工具之间的认知分工 | Cognitive Offloading、Extended Mind（User）；Cognitive Resources、Cognitive Labor（Peer） | 13（User 7 + Peer 6） |
| R2 | AI 接管任务的哪一部分重要吗 | Core Delegation、Peripheral Delegation（Peer） | 6 |
| R3 | 反复使用 AI 与长期保持的技能 | Performance Reliance、Skill Reallocation（Peer） | 6 |
| 合计 | | 8 个概念 + 终点节点 Independent Capability | 25 |

T-COG 尚缺：anchor questions、case questions 与 connections 表、按 User / Peer 拆分的成文阅读（现有成文版 `COG_reading_combined.docx` 是合并版）。

---

## 附录 B · T-AGI 讨论设计（来自 Excel）

### B.1 三阶段流程（每 Round 相同）

| Phase | 目标 | 学习者 | Peer | 结束条件 | 产出 |
| --- | --- | --- | --- | --- | --- |
| P1 Sharing | 覆盖本 Round 每条 statement，学习者用自己的话复述 | R1：先讲自己的 statements，再复述 peer 的；R2–R3：逐条复述 peer 的 | 每条消息只呈现一条；复述不完整时追问缺失部分，不代为纠正；学习者跳过或讲错时用问题引回 | 本 Round 全部 statements 复述完（R1 14、R2 6、R3 7） | — |
| P2 Connecting | 借 anchor question 中的案例把 statements 连起来 | 回答 case question，指出相关 statement，一句话说出联系 | 提出 anchor question；每条联系走四步；从不先说出联系；Lead = User 的交还给学习者 | 学习者确认 2–3 条 connection | Connection list（2–3 条）+ 至少 1 个双方都不确定的 open question |
| P3 Joint Explanation | 共同回答 anchor question | 起草 2–3 句答案，使用 P2 的联系 | 补充、修订，不重写；检查至少用到 2 条 connection（R2–R3 至少用到 1 个 R1 概念）；open question 标为 “not yet resolved” | 双方同意最终答案 | 2–3 句的 joint explanation |

### B.2 Connections 与 open questions（仅供 peer，不向学习者展示）

| Round | ID | 联系 | 涉及 statements | Lead | Step 1 case question | Step 4 目标联系句 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | C1-1 | 9/10 是 evidence，不是 criterion | P1-A3, P1-A4 | Peer | Does 9 out of 10 by itself tell us whether it has reached AGI? | A test score is evidence; we still need criteria to decide what counts as AGI. |
| 1 | C1-2 | 题目只覆盖一种 target capability | U1-B1, U1-B2 | User | Of the abilities an AGI should have, how many do these reasoning questions test? | AGI requires several target capabilities, so a reasoning test covers only one of them. |
| 1 | C1-3 | 正确率 ≠ 「90% 推理能力」（ability vs. task） | U1-B3, U1-B4, P1-A2 | User | Is getting 9 questions right the same as having strong reasoning ability? | Task performance is only indirect evidence about an ability. |
| 1 | C1-4 | 题目对 AI 是否是新的（generalization） | P1-B1, P1-B3 | Peer | If the AI had seen these questions before, would 9/10 mean the same thing? | We need to know whether the questions were new to it, because generalization means handling new situations. |
| 1 | C1-5 | 一组推理题是一种任务类型（generality vs. generalization） | U1-A2, P1-B2 | User | If it does well on this kind of question, does that show it can do other kinds of tasks? | Doing well on one task type does not show generality across different types of tasks. |
| 1 | O1-1 | Open question | — | — | 待研究员填写 | — |
| 2 | C2-1 | 训练数据上的好表现可能只是熟悉 | P2-A2, P1-A2 | Peer | The classifier was adjusted using these exact emails. What does scoring well on them really show? | Good performance on training data may reflect familiarity rather than real ability. |
| 2 | C2-2 | 只在熟悉样例上有效的模式无法泛化 | P2-B3, P1-B1 | Peer | What might happen when it meets a spam email it has never seen? | Patterns that work only on familiar examples do not generalize, so we must test on new emails. |
| 2 | C2-3 | 新情境测试必须说明是哪种新情境 | P2-B2, P1-B3 | Peer | If you tested it on new emails, what kinds of new emails would you choose? | A generalization test should state what kind of new emails it uses and how different they are. |
| 2 | O2-1 | AI training 与 target capabilities 中的 “learning” 是一回事吗 | P2-A1, U1-B1 | User | You talked about learning ability last round. Is that the same as what training does here? I'm not sure. | （保持开放） |
| 3 | C3-1 | 人与 AI 的能力都从表现推断 | P3-A3, P1-A2 | Peer | We can't see human intelligence directly. How do we judge it? | Both human intelligence and AI ability are inferred from observable performance. |
| 3 | C3-2 | 标准化对应固定的测试条件与计分规则 | P3-B3, P1-A3 | Peer | Would an AI test also need fixed instructions and scoring rules? | Standardization in human tests corresponds to fixing conditions and scoring rules in AI tests. |
| 3 | C3-3 | AI 训练中可能见过相似题目 | P3-B1, P2-B3 | Peer | What if the AI saw many similar puzzles during training? | Copied test items may measure familiar patterns rather than ability, so items need to be new to the AI. |
| 3 | C3-4 | 人类表现可作参照水平 | P3-B4, P1-A3 | Peer | How could human scores on these tests help us evaluate an AI? | Human performance can provide a reference level for AI ability tests. |
| 3 | C3-5 | 认知任务对应 target capabilities | P3-B2, U1-B1, U1-B4 | User | A pattern-completion puzzle: which target capability does it relate to? | Cognitive tasks must be linked to the target capabilities they provide evidence about. |
| 3 | O3-1 | Open question | — | — | 待研究员填写 | — |

R1 有 5 条候选 connection，P2 只需确认 2–3 条：**DG3 的自适应就体现在从候选中优先选涉及 LKS gap statement 的那几条**。O1-1、O3-1 需在定稿前填写。

### B.3 Statement Tracking（人工编码表，每位被试一份）

逐条 statement 编码：Covered in Phase 1 / Restated by user / Prompting needed / Used in a Phase 2 connection / Notes；按 Round 汇总 coverage、restatement rate、used in connection。用途：(1) 系统忠实度检查（peer 是否覆盖了全部 statements）；(2) 与 S3 LKS 的人机一致性，作为 RQ2 的验证来源之一。

---

## 附录 C · Expert Concept Maps（edge 列表）

### C.1 T-AGI

| # | Edge | 对应 statement | 引入 Round |
| --- | --- | --- | --- |
| E1 | AGI Definition → specifies → Target Capabilities | U1-A3 | R1 |
| E2 | Target Capabilities → guide → AI Ability Tests | U1-B2 | R1 |
| E3 | AI Ability Tests → define criteria for → AGI Assessment（源节点见附录 D-1） | P1-A3 | R1 |
| E4 | AI Ability Tests → provide evidence for → AGI Assessment | P1-A4 | R1 |
| E5 | Generalization → provides evidence for → AGI Assessment | P1-B3 | R1 |
| E6 | AI Training → enables → Pattern Learning | P2-A3 | R2 |
| E7 | Pattern Learning → must support → Generalization | P2-B3 | R2 |
| E8 | Human Intelligence Tests → assess → Human Intelligence | P3-B1 | R3 |
| E9 | Human Intelligence Tests → inform the design of → AI Ability Tests | P3-B4 | R3 |

Round 概念图按累计 edge 集计分：R1 = E1–E5，R2 = E1–E7，R3 = E1–E9。

### C.2 T-COG

| # | Edge | 引入 Round |
| --- | --- | --- |
| E1 | Cognitive Resources → encourage → Cognitive Offloading | R1 |
| E2 | Cognitive Offloading → can integrate into → Extended Mind | R1 |
| E3 | Cognitive Offloading → redistributes → Cognitive Labor | R1 |
| E4 | Cognitive Labor → can concentrate in → Core Delegation | R1 / R2 |
| E5 | Extended Mind → can support → Peripheral Delegation | R1 / R2 |
| E6 | Core Delegation → can lead to → Performance Reliance | R2 / R3 |
| E7 | Peripheral Delegation → can lead to → Skill Reallocation | R2 / R3 |
| E8 | Performance Reliance → feeds into → Independent Capability（方向见附录 D-2） | R3 |
| E9 | Skill Reallocation → feeds into → Independent Capability | R3 |

T-COG 中 E4–E7 的 statement 在前一 Round 出现，但目标概念在下一 Round 才讲（例如 R1 的 Cognitive Labor 指向 R2 的 Core Delegation）。这类「跨 Round 桥接 edge」的计分归属需在使用 T-COG 前确定。

---

## 附录 D · 材料中的不一致（需在定稿前修正）

1. **T-AGI「define criteria for」的源节点**：`AGI_statements_concept_map.docx` 的 concept map 图从 **Target Capabilities** 连到 AGI Assessment；该文件的 statement、Core framework 文字与 Excel 的 P1-A3 都写作 **AI Ability Tests** → define criteria for → AGI Assessment。expert map 需统一为一种。
2. **T-COG Performance Reliance 与 Independent Capability 的方向**：`COG_statements_concept_map.docx` 与其 concept map 图为 Performance Reliance → feeds into → Independent Capability；成文阅读 `COG_reading_combined.docx` 写的是 “Independent Capability can reveal Performance Reliance”（方向相反、关系不同）。
3. **终点节点无概念卡**：T-AGI 的 AGI Assessment、T-COG 的 Independent Capability 都出现在 expert map 上，但没有自己的 statements。需确定它们是否计入回忆的「概念数」。
4. **层级术语**：Phase / Round / 阶段混用，按 §0.3 统一。
5. **Consent 与新流程**：时长、补偿、流程描述（initial concept map）、可识别信息，见 §7。
6. **PDF RQ2 第二行**未写完，见 §3.5 与【D-14】。

---

## 参考文献

- Brooke, J. (1996). SUS: A "quick and dirty" usability scale. In *Usability Evaluation in Industry*. Taylor & Francis.
- Chi, M. T. H., & Wylie, R. (2014). The ICAP framework: Linking cognitive engagement to active learning outcomes. *Educational Psychologist, 49*(4), 219–243.
- Chin, C., & Brown, D. E. (2002). Student-generated questions: A meaningful aspect of learning in science. *International Journal of Science Education, 24*(5), 521–549.
- Gunawardena, C. N., Lowe, C. A., & Anderson, T. (1997). Analysis of a global online debate and the development of an interaction analysis model for examining social construction of knowledge in computer conferencing. *Journal of Educational Computing Research, 17*(4), 397–431.
- Hart, S. G., & Staveland, L. E. (1988). Development of NASA-TLX (Task Load Index): Results of empirical and theoretical research. *Advances in Psychology, 52*, 139–183.
- Wang, B., Rau, P.-L. P., & Yuan, T. (2023). Measuring user competence in using artificial intelligence: Validity and reliability of artificial intelligence literacy scale. *Behaviour & Information Technology, 42*(9), 1324–1337.
