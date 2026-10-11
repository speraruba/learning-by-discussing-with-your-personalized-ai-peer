# -*- coding: utf-8 -*-
"""
命令行入口:
  python -m kg text "AI reduces memory."      # 任意文本 → 打印抽取结果(JSON),不碰任何数据库
  python -m kg text --file transcript.txt --topic 2   # 同上,并对照主题 2 的专家图打分
  python -m kg build <session_id> <stage>     # stage: recall | phase1 | phase2 | phase3
  python -m kg build <session_id> <stage> --dry-run   # 读 MySQL、抽取,但不写 Neo4j
  python -m kg build-all <session_id>         # 构建该会话所有已就绪的阶段
  python -m kg report <session_id>            # 该会话各阶段的覆盖率、命题、新增概念
  python -m kg candidates [--topic 2]         # 跨受试者的词表外概念,供研究者审定
  python -m kg rebuild                        # 改了 ontology.yaml / 专家图后,重建库里所有图
"""
import argparse
import json
import sys

STAGE_ORDER = ("recall", "phase1", "phase2", "phase3")


def _print(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m kg", description="Knowledge-graph pipeline (traditional NLP)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("text", help="extract a graph from text and print JSON (no databases)")
    t.add_argument("text", nargs="?")
    t.add_argument("--file")
    t.add_argument("--topic", type=int, help="also score against this topic's expert map")

    b = sub.add_parser("build", help="build one stage of a session into Neo4j")
    b.add_argument("session_id")
    b.add_argument("stage", choices=STAGE_ORDER)
    b.add_argument("--dry-run", action="store_true", help="extract only; do not write to Neo4j")

    a = sub.add_parser("build-all", help="build every ready stage of a session")
    a.add_argument("session_id")
    a.add_argument("--dry-run", action="store_true")

    r = sub.add_parser("report", help="coverage and new concepts per stage for one session")
    r.add_argument("session_id")

    c = sub.add_parser("candidates", help="emergent concepts across participants, for ontology review")
    c.add_argument("--topic", type=int)
    c.add_argument("--min-participants", type=int, default=1)

    sub.add_parser("rebuild", help="rebuild every graph in Neo4j (after editing the ontology)")

    args = ap.parse_args(argv)

    if args.cmd == "text":
        from . import expert
        from .extract import build_graph, get_ontology
        if args.file:
            with open(args.file, encoding="utf-8") as f:
                text = f.read()
        elif args.text:
            text = args.text
        else:
            text = sys.stdin.read()
        graph = build_graph(text)
        out = graph.to_dict()
        if args.topic:
            emap = expert.load(args.topic, get_ontology())
            out["score"] = expert.score(graph, emap) if emap else f"no expert map for topic {args.topic}"
        _print(out)
        return 0

    if args.cmd in ("report", "candidates"):
        from . import neo4j_store
        if args.cmd == "candidates":
            _print(neo4j_store.emergent_candidates(args.topic, args.min_participants))
            return 0
        rows = sorted(neo4j_store.session_report(args.session_id),
                      key=lambda x: STAGE_ORDER.index(x["stage"]) if x["stage"] in STAGE_ORDER else 9)
        if not rows:
            print(f"no graphs for session {args.session_id}", file=sys.stderr)
            return 2
        # 新增概念 = 该阶段覆盖到、而回忆阶段没覆盖到的必学概念(对应研究问题里的 newly acquired concepts)
        base = set(next((x["concepts_covered"] or [] for x in rows if x["stage"] == "recall"), []))
        for x in rows:
            if x["concepts_covered"] is not None and x["stage"] != "recall":
                x["new_since_recall"] = [k for k in x["concepts_covered"] if k not in base]
        _print(rows)
        return 0

    from . import pipeline
    try:
        if args.cmd == "build":
            out = pipeline.build_for_session(args.session_id, args.stage, write=not args.dry_run)
        elif args.cmd == "build-all":
            out = pipeline.build_all(args.session_id, write=not args.dry_run)
        else:
            out = pipeline.rebuild_existing()
    except pipeline.NotReady as e:
        print(f"not ready: {e}", file=sys.stderr)
        return 2
    _print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
