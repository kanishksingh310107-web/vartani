"""Plan a fair model comparison and measure the effect of native-script conversion."""
from collections import defaultdict, deque
from fractions import Fraction
import hashlib
from statistics import mean
from unicodedata import normalize

from .perturb import build_conditions, count_calls, map_fields
from .scripts import LANG_INFO, bridge, script_of

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
    languages = defaultdict(lambda: {"questions": 0, "raw": 0, "converted": 0,
                                     "native_total": 0, "native_correct": 0, "matched_raw": 0})
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
        language = languages[item["lang"]]
        language["questions"] += 1
        language["raw"] += raw[0]
        language["converted"] += normalized[0]
        if "native" in answers:
            language["native_total"] += 1
            language["native_correct"] += answers["native"] == gold
            language["matched_raw"] += raw[0]
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
        "examples": examples[True] + examples[False], "languages": dict(languages),
    }


def _check_text(text):
    if (not isinstance(text, dict) or not isinstance(text.get("passage"), str)
            or not isinstance(text.get("question"), str) or not text["question"].strip()
            or not isinstance(text.get("options"), list) or len(text["options"]) != 4
            or not all(isinstance(option, str) and option.strip() for option in text["options"])):
        raise ValueError("Each row needs a question and four nonempty text options.")
    return {key: text[key] for key in ("passage", "question", "options")}


def _export_row(item, main, roman=None, converted=False):
    row = {"id": item["id"], "lang": item["lang"], **main}
    if item.get("gold") in LETTERS:
        row["answer"] = item["gold"]
    if roman is not None:
        row.update({key + "_roman": value for key, value in roman.items()})
    if converted:
        row["native_source"] = "vartani_conversion"
    return row


def conversion_preview(items):
    if not isinstance(items, list) or not 1 <= len(items) <= 1000:
        raise ValueError("Load between 1 and 1,000 questions for a conversion review.")
    result = []
    ids = set()
    for item in items:
        if (not isinstance(item, dict) or type(item.get("id")) not in (int, str)
                or item["id"] in ids or not isinstance(item.get("lang"), str) or item["lang"] not in LANG_INFO
                or item.get("gold") not in (None, *LETTERS)):
            raise ValueError("Rows need unique IDs, a supported language, and a valid answer key if provided.")
        ids.add(item["id"])
        native = _check_text(item["native"]) if item.get("native") is not None else None
        roman = _check_text(item["roman"]) if item.get("roman") is not None else None
        if not (native or roman):
            raise ValueError("Each row needs native or Roman input.")
        original = _export_row(item, native or roman, roman if native else None)
        draft = None
        reason = "This row already uses native text." if not roman else ""
        if roman:
            converted = map_fields(roman, lambda text, _: bridge(text, item["lang"]))
            if converted == roman or script_of(converted["question"]) != "native":
                reason = "The converter could not produce a usable native-script question."
            elif len({" ".join(normalize("NFKC", option).casefold().split())
                      for option in converted["options"]}) < 4:
                reason = "Conversion made two or more answer options look the same."
            else:
                draft = _export_row(item, converted, roman, converted=True)
        result.append({"original": original, "draft": draft, "reason": reason})
    return result
