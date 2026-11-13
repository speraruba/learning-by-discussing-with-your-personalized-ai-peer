# -*- coding: utf-8 -*-
"""
在标注测试集(kg/eval/topic_<n>.yaml)上比较几种做法,对应组会的分工:

预设命题(受试者有没有说出 / 否认我们希望他学到的命题):
  rules            规则 + 语义相似度(不用 LLM)
  rules+llm_check  同上,再让 LLM 核对规则没找到的命题(Hugo 提的"中间加一步 LLM")
新内容(受试者自己提出、预设里没有的命题):
  rules            规则抽到、但对不上任何预设命题的边
  llm              LLM 抽取的新命题

指标:
  预设命题  said / denied 各自的 precision、recall、F1;false credit = 没说却记为说了(或否认了却记为说了)
  新内容    命中的标注新命题占比(recall);在"本条没有新内容"的句子上多报的条数(噪声)

python -m kg evaluate --topic 2 [--llm] [--details]
"""
from pathlib import Path

import yaml

from . import analyze as an

DEFAULT_DIR = Path(__file__).parent / "eval"

SAID = {"matched", "similar", "llm_matched", "llm_said"}
DENIED = {"negated", "llm_negated", "llm_denied"}


def load_items(topic: int, directory=None) -> list[dict]:
    path = Path(directory or DEFAULT_DIR) / f"topic_{topic}.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    items = []
    for it in raw.get("items") or []:
        items.append({"text": it["text"], "said": set(map(str, it.get("said") or [])),
                      "denied": set(map(str, it.get("denied") or [])),
                      "new": it.get("new") or [], "note": it.get("note", "")})
    return items


def prepared_labels(score: dict) -> dict[str, str]:
    """打分结果 → {命题 id: said | denied | not}。"""
    out = {}
    for p in list(score["propositions"]) + list(score.get("definitions") or []):
        out[p["id"]] = "said" if p["status"] in SAID else "denied" if p["status"] in DENIED else "not"
    return out


def _prf(tp, fp, fn) -> dict:
    prec = tp / (tp + fp) if tp + fp else None
    rec = tp / (tp + fn) if tp + fn else None
    f1 = 2 * prec * rec / (prec + rec) if prec and rec else None
    return {"tp": tp, "fp": fp, "fn": fn, "precision": prec, "recall": rec, "f1": f1}


def _new_matches(gold: list, preds: list[dict]) -> int:
    hit = 0
    for src_kws, tgt_kws in gold:
        def has(label, kws):
            return any(k.lower() in label for k in kws)
        if any((has(p["src"], src_kws) and has(p["tgt"], tgt_kws)) or
               (has(p["src"], tgt_kws) and has(p["tgt"], src_kws)) for p in preds):
            hit += 1
    return hit


def _new_preds(graph, extractor: str) -> list[dict]:
    def label(k):
        c = graph.concepts.get(k)
        return f"{k} {c.label if c else ''}".lower()
    return [{"src": label(r.source), "tgt": label(r.target), "type": r.type, "evidence": r.evidence}
            for r in graph.relations if r.prepared_id is None and r.extractor == extractor]


def evaluate(topic: int, use_llm: bool = False, directory=None) -> dict:
    items = load_items(topic, directory)
    setups = ["rules"] + (["rules+llm_check"] if use_llm else [])
    prep = {s: {"said": [0, 0, 0], "denied": [0, 0, 0], "false_credit": 0, "errors": []} for s in setups}
    new_setups = ["rules"] + (["llm"] if use_llm else [])
    new = {s: {"hit": 0, "gold": 0, "noise": 0, "predicted": 0, "errors": []} for s in new_setups}
    notes = {}

    for idx, it in enumerate(items, 1):
        runs = {"rules": an.analyze(it["text"], topic)}
        if use_llm:
            runs["rules+llm_check"] = an.analyze(it["text"], topic, llm_check=True, llm_new=True)
            info = runs["rules+llm_check"]["llm_new"]
            if info and info.get("unavailable"):
                notes["llm"] = info["unavailable"]

        for setup in setups:
            pred = prepared_labels(runs[setup]["score"])
            m = prep[setup]
            for pid, p in pred.items():
                g = "said" if pid in it["said"] else "denied" if pid in it["denied"] else "not"
                for lab in ("said", "denied"):
                    if p == lab and g == lab:
                        m[lab][0] += 1
                    elif p == lab:
                        m[lab][1] += 1
                    elif g == lab:
                        m[lab][2] += 1
                if p == "said" and g != "said":
                    m["false_credit"] += 1
                if p != g:
                    m["errors"].append(f"#{idx} {pid}: expected {g}, got {p}  ({it['note']})")

        new_runs = {"rules": _new_preds(runs["rules"]["graph"], "rules")}
        if use_llm:
            new_runs["llm"] = _new_preds(runs["rules+llm_check"]["graph"], "llm")
        for setup, preds in new_runs.items():
            m = new[setup]
            hit = _new_matches(it["new"], preds)
            m["hit"] += hit
            m["gold"] += len(it["new"])
            m["predicted"] += len(preds)
            if not it["new"]:
                m["noise"] += len(preds)
            if hit < len(it["new"]):
                m["errors"].append(f"#{idx} missed new idea  ({it['note']})")
            if not it["new"] and preds:
                m["errors"].append(f"#{idx} reported {len(preds)} new statement(s) where none expected: "
                                   + "; ".join(f"{p['src'].split()[0]} -{p['type']}-> {p['tgt'].split()[0]}"
                                               for p in preds))

    return {
        "topic": topic, "items": len(items), "notes": notes,
        "prepared": {s: {"said": _prf(*m["said"]), "denied": _prf(*m["denied"]),
                         "false_credit": m["false_credit"], "errors": m["errors"]} for s, m in prep.items()},
        "new": {s: {"recall": (m["hit"] / m["gold"]) if m["gold"] else None, "hit": m["hit"], "gold": m["gold"],
                    "predicted": m["predicted"], "noise": m["noise"], "errors": m["errors"]}
                for s, m in new.items()},
    }


def format_report(r: dict, details: bool = False) -> str:
    f = lambda x: "  -  " if x is None else f"{x:.2f}"
    lines = [f"Topic {r['topic']}: {r['items']} labeled examples", ""]
    for k, v in r["notes"].items():
        lines.append(f"NOTE {k}: {v}")
    lines += ["Prepared statements (did they say / deny what we want them to learn?)",
              f"  {'setup':<17}{'said P':>8}{'said R':>8}{'said F1':>9}{'denied R':>10}{'false credit':>14}"]
    for s, m in r["prepared"].items():
        lines.append(f"  {s:<17}{f(m['said']['precision']):>8}{f(m['said']['recall']):>8}{f(m['said']['f1']):>9}"
                     f"{f(m['denied']['recall']):>10}{m['false_credit']:>14}")
    lines += ["", "New ideas (things they came up with that aren't prepared statements)",
              f"  {'setup':<17}{'found':>10}{'recall':>8}{'noise':>8}"]
    for s, m in r["new"].items():
        lines.append(f"  {s:<17}{str(m['hit']) + '/' + str(m['gold']):>10}{f(m['recall']):>8}{m['noise']:>8}")
    lines.append("  noise = new statements reported on examples that contain no new idea")
    if details:
        for part in ("prepared", "new"):
            for s, m in r[part].items():
                if m["errors"]:
                    lines += ["", f"Errors: {part} / {s}"] + [f"  {e}" for e in m["errors"]]
    return "\n".join(lines)
