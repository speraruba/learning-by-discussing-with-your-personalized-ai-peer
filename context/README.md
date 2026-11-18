# context/ 文件索引

AI Study Peer 研究（Learning by Discussing with Your Personalized AI Peer）的设计文档与学习材料。

```
context/
├── README.md                          本索引
├── ai_study_peer_protocol.md          完整 study protocol（v0.1）
├── design/
│   ├── research_design_RQs_measures_2026-09-15_zh.pdf
│   └── study_protocol_template.md
├── materials_AGI/                     T-AGI：What counts as AGI / how do we measure intelligence
│   ├── AGI_statements_concept_map.docx
│   ├── AGI_readings_user_peer.docx
│   └── AGI_discussion_design.xlsx
└── materials_COG/                     T-COG：AI and the division of cognitive work
    ├── COG_statements_concept_map.docx
    └── COG_reading_combined.docx
```

## 从哪里开始读

讨论驱动流程的最新补充（2026-11-18）见下列文件。每个阶段经过多轮交互；controller 每轮读取完整累积对话，只判断当前任务是否完成，程序在完成后按固定顺序注入下一阶段描述，再由 peer 回复。本次为提示词与设计更新，尚未接入运行代码。

- [Stage 描述](../讨论核心/01_Stage_描述.docx)
- [Stage Controller Prompt](../讨论核心/02_Stage_Controller_Prompt.docx)
- [Peer Prompt](../讨论核心/03_Peer_Prompt.docx)
- [讨论驱动系统设计](../讨论核心/04_讨论驱动系统设计.docx)
- [网站页面流程](../网站页面设计/页面流程.md)
- 可比较的文本源：[stages.json](../讨论核心/制作与校验/stages.json)、[stage_controller.txt](../讨论核心/制作与校验/stage_controller.txt)、[peer.txt](../讨论核心/制作与校验/peer.txt)。

1. `ai_study_peer_protocol.md`：整合了下面所有文件的研究设计，包括 RQ、DG、实验条件、流程、数据采集、待决策事项（§10）、材料不一致（附录 D）。
2. 需要核对原始设计时，再看 `design/` 和对应 topic 的 `materials_*`。

## design/

| 文件 | 原文件名 | 内容 |
| --- | --- | --- |
| `research_design_RQs_measures_2026-09-15_zh.pdf` | 研究设计｜研究问题与测量方法（2026年9月15日，中文译本）.pdf | RQ1 学习效果、RQ2 诊断效度、RQ3 作用机制、RQ4 用户体验；每个 RQ 的指标、测量方法、测量时间 |
| `study_protocol_template.md` | study_protocol_template.md | 通用 study protocol 模板（RQ → DG → 研究设计 → 采集清单 → 原句库 → 伦理 → 变更日志 → 检查清单） |

## materials_AGI/（正式实验建议使用）

三个 Round：R1 What Counts as AGI?、R2 Where Do AI Capabilities Come From?、R3 How Do We Measure Intelligence?。8 个概念 + 终点节点 AGI Assessment，共 27 条 statements。

| 文件 | 原文件名 | 内容 |
| --- | --- | --- |
| `AGI_statements_concept_map.docx` | Hugo Research Project 2026_ Learning Materials (2).docx | 每个概念的 core question、statements、propositions、补充解释，按 User / Peer Contribution 划分；附 Core framework 与 expert concept map 图 |
| `AGI_readings_user_peer.docx` | Hugo Research Project 2026_ Learning Materials (3).docx | 成文阅读材料：R1 User Reading、R1–R3 Peer Readings |
| `AGI_discussion_design.xlsx` | Three-Round_Discussion_Design_EN.xlsx | 3 个 sheet：Anchor Questions & Connections（每 Round 的 anchor question、case questions、目标联系句）；Three-Phase Procedure（Sharing → Connecting → Joint Explanation 的流程与 peer 原句）；Statement Tracking（每位被试一份的人工编码表，27 条 statements 带 ID） |

## materials_COG/（建议用于 pilot）

三个 Round：R1 认知分工、R2 AI 接管任务的哪一部分、R3 长期技能保持。8 个概念 + 终点节点 Independent Capability，共 25 条 statements。

| 文件 | 原文件名 | 内容 |
| --- | --- | --- |
| `COG_statements_concept_map.docx` | Hugo Research Project 2026_ Learning Materials (1).docx | 每个概念的 core question、statements、propositions、examples，按 User / Peer Contribution 划分；附 expert concept map 图 |
| `COG_reading_combined.docx` | Hugo Research Project 2026_ Learning Materials.docx | 成文阅读材料，User 与 Peer 部分合在一起，没有拆分 |

与 T-AGI 相比，T-COG 还缺 discussion design（anchor questions、connections）和按 User / Peer 拆分的成文阅读。

## 相关但不在本文件夹

- `../PAST/`：旧版辩论式系统（FastAPI + MySQL），可复用其中的问卷、search agent、断线容错和 consent（`../PAST/consent.txt`）。详见 `../PAST/README_CN.md`。
