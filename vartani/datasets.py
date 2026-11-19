"""Read test sets (CSV / JSONL / pasted JSON) into one item shape, and serve the starter sets.

Item shape used everywhere:
  {"id", "lang", "gold": "A".."D"|None, "native": triple|None, "roman": triple|None}
  triple = {"passage": str, "question": str, "options": [4 strings]}

Accepted column names: passage, question, option_a..option_d (or A..D, options, choices, mc_answer1..4),
answer (A-D or 1-4), lang (hi/bn/ta or the language name). Optional *_roman columns give the Roman text explicitly.
Belebele rows (flores_passage, mc_answer1..4, correct_answer_num) work as they are.
"""
from __future__ import annotations
import csv
import io
import json
from pathlib import Path
from typing import List, Optional, Tuple

from .config import BUNDLE_DATA_DIR, LANGS
from .scripts import script_of

LANG_ALIASES = {"hi": "hi", "hin": "hi", "hindi": "hi", "hin_deva": "hi", "bn": "bn", "ben": "bn", "bengali": "bn",
                "bangla": "bn", "ben_beng": "bn", "ta": "ta", "tam": "ta", "tamil": "ta", "tam_taml": "ta"}


def _first(d: dict, *keys):
    for k in keys:
        if k in d and str(d[k]).strip() != "":
            return d[k]
    return None


def _options(d: dict, suffix: str = "") -> Optional[List[str]]:
    o = d.get("options" + suffix) or d.get("choices" + suffix)
    if isinstance(o, str):
        try:
            o = json.loads(o)
        except ValueError:
            o = None
    if isinstance(o, list) and len(o) == 4:
        return [str(x) for x in o]
    sets = [[f"option_{c}{suffix}" for c in "abcd"], [f"{c}{suffix}" for c in "ABCD"], [f"opt_{c}{suffix}" for c in "abcd"],
            [f"mc_answer{i}{suffix}" for i in range(1, 5)]]
    for keys in sets:
        if all(k in d and str(d[k]).strip() != "" for k in keys):
            return [str(d[k]) for k in keys]
    return None


def _gold(v) -> Optional[str]:
    if v is None:
        return None
    s = str(v).strip().upper()
    if s in ("A", "B", "C", "D"):
        return s
    if s in ("1", "2", "3", "4"):
        return "ABCD"[int(s) - 1]
    return None


def normalize_item(raw: dict, default_lang: Optional[str], idx: int) -> Tuple[Optional[dict], List[str]]:
    w: List[str] = []
    d = {str(k).strip(): v for k, v in raw.items()}
    lang = LANG_ALIASES.get(str(_first(d, "lang", "language") or default_lang or "").strip().lower())
    if lang not in LANGS:
        return None, [f"row {idx + 1}: language missing or not one of hi/bn/ta"]
    q = _first(d, "question")
    opts = _options(d)
    if q is None or opts is None:
        return None, [f"row {idx + 1}: needs a question and four options"]
    p = _first(d, "passage", "flores_passage", "context") or ""
    main = {"passage": str(p), "question": str(q), "options": opts}
    rq = _first(d, "question_roman")
    ropts = _options(d, "_roman")
    item = {"id": idx, "lang": lang, "gold": _gold(_first(d, "answer", "gold", "correct_answer_num", "correct")),
            "native": None, "roman": None}
    if item["gold"] is None:
        w.append(f"row {idx + 1}: no answer key (accuracy cannot be scored for this row)")
    if rq and ropts:
        item["roman"] = {"passage": str(_first(d, "passage_roman") or ""), "question": str(rq), "options": ropts}
        item["native"] = main if script_of(main["question"]) == "native" else None
    elif script_of(main["question"] + " " + " ".join(opts)) == "roman":
        item["roman"] = main
    else:
        item["native"] = main
    return item, w


def parse_dataset(text: str, filename: str = "", default_lang: Optional[str] = None) -> dict:
    text = text.lstrip("\ufeff")
    rows: List[dict] = []
    s = text.strip()
    ext = filename.lower().rsplit(".", 1)[-1]
    if ext == "csv" or (ext not in {"json", "jsonl", "ndjson"} and s and s[0] not in "[{"):
        rows = list(csv.DictReader(io.StringIO(text), strict=True))
    elif ext == "json" or (ext not in {"jsonl", "ndjson"} and s.startswith("[")):
        parsed = json.loads(s)
        rows = parsed if isinstance(parsed, list) else [parsed]
    else:
        for line_no, line in enumerate(s.splitlines(), 1):
            if line.strip():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    raise ValueError(f"line {line_no} is not valid JSON") from None
    items, warnings = [], []
    for i, r in enumerate(rows):
        if not isinstance(r, dict):
            warnings.append(f"row {i + 1}: expected an object with a question and four options")
            continue
        it, w = normalize_item(r, default_lang, i)
        warnings += w
        if it:
            items.append(it)
    return {"items": items, "warnings": warnings[:20], "skipped": len(rows) - len(items)}


def starter_sets() -> list:
    out = []
    for p in sorted((BUNDLE_DATA_DIR / "starter").glob("*.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        out.append({"id": p.stem, "lang": d["lang"], "title": d["title"], "n": len(d["items"])})
    return out


def load_starter(sid: str) -> dict:
    p = BUNDLE_DATA_DIR / "starter" / f"{Path(sid).name}.json"
    d = json.loads(p.read_text(encoding="utf-8"))
    items = []
    for i, r in enumerate(d["items"]):
        it, _ = normalize_item({**r, "lang": d["lang"]}, d["lang"], i)
        items.append(it)
    return {"id": sid, "title": d["title"], "lang": d["lang"], "items": items}
