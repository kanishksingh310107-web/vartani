"""The paper's own recorded runs (data/paper/*.jsonl, produced by the Colab notebook), analysed with the same code
the report uses. Nothing here is simulated: every number comes from 1,800 real model evaluations."""
from __future__ import annotations
import glob
import json
from collections import Counter
from functools import lru_cache

from .analysis import COLAB_KEYS, report, pct
from .config import BUNDLE_DATA_DIR

MODEL_LABEL = {"qwen2.5-3b": "Qwen2.5-3B-Instruct", "qwen3-4b": "Qwen3-4B", "gemma3-4b": "Gemma-3-4B-it"}


def load_paper_rows() -> list:
    rows = []
    for f in sorted(glob.glob(str(BUNDLE_DATA_DIR / "paper" / "*.jsonl"))):
        for line in open(f, encoding="utf-8"):
            if line.strip():
                d = json.loads(line)
                rows.append({"qid": d["qid"], "lang": d["lang"], "gold": d["gold"], "model": d["model"],
                             "answers": {v: d[k] for k, v in COLAB_KEYS.items() if k in d},
                             "margins": {"roman": d.get("modal_margin")}, "meta": {}})
    return rows


def import_colab(text: str) -> list:
    rows = []
    for line in text.splitlines():
        if line.strip():
            d = json.loads(line)
            rows.append({"qid": d["qid"], "lang": d["lang"], "gold": d["gold"],
                         "answers": {v: d[k] for k, v in COLAB_KEYS.items() if k in d},
                         "margins": {"roman": d.get("modal_margin")}, "meta": {}})
    return rows


@lru_cache(maxsize=1)
def evidence() -> dict:
    rows = load_paper_rows()
    if not rows:
        return {"available": False}
    out = {"available": True, "n_rows": len(rows), "n_evals": sum(len(r["answers"]) for r in rows), "models": {}}
    for m in sorted({r["model"] for r in rows}):
        rs = [r for r in rows if r["model"] == m]
        out["models"][m] = {"label": MODEL_LABEL.get(m, m), "report": report(rs)}
    out["all"] = report(rows)
    # per model x language accuracy grid
    grid = []
    for m, v in out["models"].items():
        for lg, accs in v["report"]["by_lang"].items():
            grid.append({"model": m, "label": v["label"], "lang": lg, **{c: (a or {}).get("acc") for c, a in accs.items()}})
    out["grid"] = grid
    # beyond the paper: answer-position bias per model
    out["position_bias"] = {}
    for m in out["models"]:
        c = Counter(r["answers"]["roman"] for r in rows if r["model"] == m)
        out["position_bias"][m] = {l: pct(c[l] / sum(c.values())) for l in "ABCD"}
    return out
