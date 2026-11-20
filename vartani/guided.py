"""Plan a fair model comparison and measure the effect of native-script conversion."""
from collections import defaultdict, deque
from fractions import Fraction
import hashlib
from statistics import mean

from .perturb import build_conditions, count_calls

GROQ_URL = "https://api.groq.com/openai/v1"
GROQ_MODELS = {"openai/gpt-oss-20b": "GPT-OSS 20B (Groq)", "openai/gpt-oss-120b": "GPT-OSS 120B (Groq)"}
CONFIG = {"native": True, "variants": 2, "variant_mode": "habit", "typo": False,
          "bridge": True, "bridge_variants": True, "scan": False, "seed": 42}
LETTERS = ("A", "B", "C", "D")


def sample_items(items, limit):
    if type(limit) is not int or not 6 <= limit <= 100:
        raise ValueError("Choose a question limit between 6 and 100.")
    if not isinstance(items, list) or any(not isinstance(i, dict) for i in items):
        raise ValueError("Upload a valid question set.")
    groups = defaultdict(list)
    ids = set()
    for item in items:
        if item.get("gold") not in LETTERS:
            continue
        qid = item.get("id")
        lang = item.get("lang")
        if type(qid) not in (str, int) or qid in ids or lang not in ("hi", "bn", "ta"):
            raise ValueError("Scored questions need unique IDs and a supported language.")
        ids.add(qid)
        groups[lang].append(item)
    if len(ids) < 2:
        raise ValueError("Add at least two questions with answer keys to rank models.")
    queues = [deque(sorted(group, key=lambda x: hashlib.sha256(
        f"42|{lang}|{x['id']}".encode()).digest())) for lang, group in sorted(groups.items())]
    selected = []
    while len(selected) < min(limit, len(ids)):
        for queue in queues:
            if queue and len(selected) < limit:
                selected.append(queue.popleft())
    return selected


def prepare(items, limit):
    selected = sample_items(items, limit)
    prepared = [build_conditions(i, CONFIG) for i in selected]
    return selected, {
        "questions": len(selected), "available": sum(i.get("gold") in LETTERS for i in items),
        "calls_per_model": count_calls(prepared),
        "with_changed_spelling": sum(any(k.startswith("bridge_var") for k in r["conditions"]) for r in prepared),
        "generated_roman": sum(r["meta"]["roman_source"] == "itrans" for r in prepared),
    }


def evaluate(prepared, rows):
    """Use the same baseline and distinct spelling cases before and after conversion."""
    by_id = {row["qid"]: row for row in rows}
    if len(rows) != len(prepared) or len(by_id) != len(rows):
        return None
    before, after, original, changed = [], [], [], []
    examples = {True: [], False: []}
    fixed = harmed = cases = 0
    for item in prepared:
        row = by_id.get(item["qid"])
        pairs = [("roman", "bridge")]
        pairs.extend((k.removeprefix("bridge_"), k) for k in item["conditions"] if k.startswith("bridge_var"))
        if not row or row.get("gold") != item["gold"] or any(
                field not in row["answers"] for pair in pairs for field in pair):
            return None
        answers, gold = row["answers"], item["gold"]
        raw = [answers[a] == gold for a, _ in pairs]
        normalized = [answers[b] == gold for _, b in pairs]
        before.append(Fraction(sum(raw), len(raw)))
        after.append(Fraction(sum(normalized), len(normalized)))
        original.append(raw[0])
        if len(pairs) > 1:
            changed.append(Fraction(sum(raw[1:]), len(raw) - 1))
        for (a, b), was_right, is_right in zip(pairs, raw, normalized):
            cases += 1
            if was_right == is_right:
                continue
            fixed += is_right
            harmed += was_right
            if len(examples[is_right]) < 3:
                examples[is_right].append({
                    "lang": item["lang"], "before": item["conditions"][a], "after": item["conditions"][b],
                    "before_answer": answers[a], "after_answer": answers[b], "gold": gold, "helped": is_right,
                })
    if not before:
        return None
    raw_score, converted = mean(before), mean(after)
    return {
        "raw_score": round(float(raw_score) * 100, 2), "converted_score": round(float(converted) * 100, 2),
        "raw_rank": str(raw_score), "converted_rank": str(converted),
        "gain": round(float(converted - raw_score) * 100, 2), "improved": converted > raw_score,
        "roman_accuracy": round(mean(original) * 100, 2),
        "respelling_accuracy": round(float(mean(changed)) * 100, 2) if changed else None,
        "questions": len(before), "cases": cases, "fixed": fixed, "harmed": harmed,
        "question_wins": sum(y > x for x, y in zip(before, after)),
        "question_losses": sum(y < x for x, y in zip(before, after)),
        "examples": examples[True] + examples[False],
    }
