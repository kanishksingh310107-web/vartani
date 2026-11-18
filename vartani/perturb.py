"""Build the input conditions for one test item.

Conditions (names are stable; they are what the report and the exports use)
  native      original native-script text (only if the item has it)           = paper C0
  roman       baseline Roman text                                              = paper C1
  var1..varK  respellings of the baseline                                      = paper C2-C5
  typo        random keyboard typos                                            = paper C6
  bridge      baseline converted back to native script (the mitigation)        = paper C7
  rule:<id>   baseline with ONE spelling habit applied everywhere (deep scan)  = new

Two respelling modes
  habit  each variant is a "writer": 2-4 consistent habits applied to every word of the passage, question and
         options. This is how real people type (one person writes "aa" as "a" everywhere).
  paper  exactly the notebook's generator (40% of words, one random rule each) for replication.
"""
from __future__ import annotations
import random
from typing import Dict, List, Optional

from .scripts import bridge, romanize, LANG_INFO, native_ratio

# id -> (human label, source, replacement, scope)  scope "all" = every occurrence, "first" = first one per word
RULES: Dict[str, tuple] = {
    "aa>a": ("long a shortened (kaam → kam)", "aa", "a", "all"),
    "ee>i": ("long i shortened (keemat → kimat)", "ee", "i", "all"),
    "oo>u": ("long u shortened (poora → pura)", "oo", "u", "all"),
    "th>t": ("th written as t (thanda → tanda)", "th", "t", "all"),
    "dh>d": ("dh written as d (dhoop → doop)", "dh", "d", "all"),
    "bh>b": ("bh written as b (bhi → bi)", "bh", "b", "all"),
    "kh>k": ("kh written as k (khana → kana)", "kh", "k", "all"),
    "gh>g": ("gh written as g (ghar → gar)", "gh", "g", "all"),
    "ph>f": ("ph written as f (phir → fir)", "ph", "f", "all"),
    "sh>s": ("sh written as s (shaam → saam)", "sh", "s", "all"),
    "v>w": ("v written as w (sawal → sawal, vyakti → wyakti)", "v", "w", "all"),
    "z>j": ("z written as j (zyada → jyada)", "z", "j", "all"),
    "a>aa": ("a lengthened (kam → kaam)", "a", "aa", "first"),
    "i>ee": ("i lengthened (kitab → keetab)", "i", "ee", "first"),
    "u>oo": ("u lengthened (suraj → sooraj)", "u", "oo", "first"),
}
# Habits that contradict each other (aa>a vs a>aa) live in one group so a "writer" picks only one of them.
GROUPS = [("aa>a", "a>aa"), ("ee>i", "i>ee"), ("oo>u", "u>oo"), ("th>t",), ("dh>d",), ("bh>b",), ("kh>k",),
          ("gh>g",), ("ph>f",), ("sh>s",), ("v>w",), ("z>j",)]
PAPER_RULES = [(r[1], r[2]) for r in RULES.values()]   # same order as the notebook's SUBSTITUTION_RULES


def _words(text: str):
    import re
    return re.split(r"(\s+)", text)


def apply_rule(word: str, rule_id: str) -> str:
    _, src, dst, scope = RULES[rule_id]
    if src not in word:
        return word
    return word.replace(src, dst) if scope == "all" else word.replace(src, dst, 1)


def apply_habits(text: str, rule_ids: List[str]) -> str:
    out = []
    for tok in _words(text):
        if len(tok) > 3 and tok.isalpha():
            for rid in rule_ids:
                tok = apply_rule(tok, rid)
        out.append(tok)
    return "".join(out)


def paper_variant(text: str, seed) -> str:
    """The notebook's generator, unchanged: 40% of longer words get one random applicable rule."""
    rng = random.Random(seed)
    out = []
    for w in text.split():
        if len(w) <= 3 or not w.isalpha():
            out.append(w)
            continue
        if rng.random() < 0.40:
            for src, target in rng.sample(PAPER_RULES, len(PAPER_RULES)):
                if src in w:
                    w = w.replace(src, target, 1)
                    break
        out.append(w)
    return " ".join(out)


def inject_typos(text: str, rate: float, seed) -> str:
    """The notebook's keyboard-typo generator (substitute / insert / delete)."""
    rng = random.Random(seed)
    chars = list(text)
    alphabet = "abcdefghijklmnopqrstuvwxyz"
    for _ in range(int(len(chars) * rate)):
        idx = rng.randint(0, len(chars) - 1)
        op = rng.choice(["sub", "insert", "del"])
        if op == "sub" and chars[idx].isalpha():
            chars[idx] = rng.choice(alphabet)
        elif op == "insert":
            chars.insert(idx, rng.choice(alphabet))
        elif op == "del" and len(chars) > 10:
            chars.pop(idx)
    return "".join(chars)


# ---- text triples ------------------------------------------------------------------------------------------
def fields(t: dict) -> List[str]:
    return [t["passage"], t["question"], *t["options"]]


def from_fields(f: List[str]) -> dict:
    return {"passage": f[0], "question": f[1], "options": list(f[2:6])}


def map_fields(t: dict, fn) -> dict:
    return from_fields([fn(x, i) for i, x in enumerate(fields(t))])


def char_change_rate(a: dict, b: dict) -> float:
    import difflib
    x, y = " ".join(fields(a)), " ".join(fields(b))
    return 1 - difflib.SequenceMatcher(None, x, y, autojunk=False).ratio()


def applicable_rules(t: dict) -> List[str]:
    text = " ".join(fields(t))
    return [rid for rid in RULES if apply_habits(text, [rid]) != text]


def _persona(app: List[str], seed) -> List[str]:
    rng = random.Random(seed)
    groups = [g for g in GROUPS if any(r in app for r in g)]
    if not groups:
        return []
    picked = rng.sample(groups, min(len(groups), rng.choice([2, 3, 4])))
    return [rng.choice([r for r in g if r in app]) for g in picked]


def default_config() -> dict:
    return {"native": True, "variants": 4, "variant_mode": "habit", "typo": True, "typo_rate": 0.08,
            "bridge": True, "scan": False, "seed": 42}


def build_conditions(item: dict, cfg: Optional[dict] = None) -> dict:
    """item: {"id","lang","gold","native":triple|None,"roman":triple|None}. Returns the prepared record."""
    c = {**default_config(), **(cfg or {})}
    lang, qid = item["lang"], item["id"]
    roman_src = "provided"
    base = item.get("roman")
    if base is None:
        if not item.get("native"):
            raise ValueError("item has neither native nor Roman text")
        base = map_fields(item["native"], lambda x, i: romanize(x, lang))
        roman_src = "itrans"
    conds: Dict[str, dict] = {}
    persona: Dict[str, List[str]] = {}
    if c["native"] and item.get("native"):
        conds["native"] = item["native"]
    conds["roman"] = base
    app = applicable_rules(base)
    for k in range(1, int(c["variants"]) + 1):
        tag = f"{lang}|{qid}|{k}|{c['seed']}"
        if c["variant_mode"] == "paper":
            conds[f"var{k}"] = map_fields(base, lambda x, i, tag=tag: paper_variant(x, f"{tag}|{i}"))
        else:
            p = _persona(app, tag)
            persona[f"var{k}"] = p
            conds[f"var{k}"] = map_fields(base, lambda x, i, p=p: apply_habits(x, p))
    if c["typo"]:
        tag = f"{lang}|{qid}|typo|{c['seed']}"
        conds["typo"] = map_fields(base, lambda x, i: inject_typos(x, c["typo_rate"], f"{tag}|{i}"))
    if c["bridge"]:
        conds["bridge"] = map_fields(base, lambda x, i: bridge(x, lang))
    # Optional speech-to-text check. The supplied audio transcript replaces
    # only the question; passage and answer choices stay identical to baseline.
    spoken = str(item.get("speech_text") or "").strip()
    if spoken:
        conds["asr"] = {**base, "question": spoken}
        roman_spoken = romanize(spoken, lang) if native_ratio(spoken) > 0.3 else spoken
        conds["asr_roman"] = {**base, "question": roman_spoken}
    if c["scan"]:
        for rid in app:
            conds[f"rule:{rid}"] = map_fields(base, lambda x, i, rid=rid: apply_habits(x, [rid]))
    # Conditions whose text equals an earlier one reuse that answer (no extra model call, no fake "stability").
    canon: Dict[str, str] = {}
    seen: Dict[str, str] = {}
    for name, t in conds.items():
        key = repr(fields(t))
        canon[name] = seen.setdefault(key, name)
    meta = {"roman_source": roman_src, "canon": canon, "persona": persona,
            "identical_to_roman": [n for n in conds if n != "roman" and canon[n] == "roman"],
            "change_rate": {n: round(char_change_rate(base, t), 4) for n, t in conds.items()
                            if n.startswith("var") or n == "typo"}}
    if c["bridge"] and c["variants"]:
        ref = conds["bridge"]
        same = [map_fields(conds[f"var{k}"], lambda x, i: bridge(x, lang)) == ref
                for k in range(1, int(c["variants"]) + 1)]
        meta["bridge_converged"] = round(sum(same) / len(same), 4)
    return {"qid": qid, "lang": lang, "gold": item.get("gold"), "conditions": conds, "meta": meta}


def count_calls(prepared: List[dict]) -> int:
    return sum(len({r["meta"]["canon"][n] for n in r["conditions"]}) for r in prepared)
