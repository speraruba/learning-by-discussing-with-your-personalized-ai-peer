# -*- coding: utf-8 -*-
"""
命令行入口:
  python -m kg text "AI reduces memory."      # 任意文本 → 打印抽取结果(JSON),不碰任何数据库
  python -m kg text --file transcript.txt
  python -m kg build <session_id> <stage>     # stage: recall | phase1 | phase2 | phase3
  python -m kg build <session_id> <stage> --dry-run   # 读 MySQL、抽取,但不写 Neo4j
  python -m kg build-all <session_id>         # 构建该会话所有已就绪的阶段
"""
import argparse
import json
import sys


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m kg", description="Knowledge-graph pipeline (traditional NLP)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    t = sub.add_parser("text", help="extract a graph from text and print JSON (no databases)")
    t.add_argument("text", nargs="?")
    t.add_argument("--file")

    b = sub.add_parser("build", help="build one stage of a session into Neo4j")
    b.add_argument("session_id")
    b.add_argument("stage", choices=("recall", "phase1", "phase2", "phase3"))
    b.add_argument("--dry-run", action="store_true", help="extract only; do not write to Neo4j")

    a = sub.add_parser("build-all", help="build every ready stage of a session")
    a.add_argument("session_id")
    a.add_argument("--dry-run", action="store_true")

    args = ap.parse_args(argv)

    if args.cmd == "text":
        from .extract import build_graph
        if args.file:
            with open(args.file, encoding="utf-8") as f:
                text = f.read()
        elif args.text:
            text = args.text
        else:
            text = sys.stdin.read()
        print(json.dumps(build_graph(text).to_dict(), ensure_ascii=False, indent=2))
        return 0

    from . import pipeline
    try:
        if args.cmd == "build":
            out = pipeline.build_for_session(args.session_id, args.stage, write=not args.dry_run)
        else:
            out = pipeline.build_all(args.session_id, write=not args.dry_run)
    except pipeline.NotReady as e:
        print(f"not ready: {e}", file=sys.stderr)
        return 2
    print(json.dumps(out, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
