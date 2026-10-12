# -*- coding: utf-8 -*-
"""知识图谱流水线(传统 NLP,不使用 LLM)。用法见 kg/README.md。

对外接口:
    from kg.extract import build_graph                 # 文本 → 图(纯计算)
    from kg.pipeline import build_for_session, NotReady # 会话阶段 → Neo4j
"""
