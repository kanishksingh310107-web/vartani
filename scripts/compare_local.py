"""Compare two pinned, local Transformers snapshots using identical Vartani inputs."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from importlib.metadata import version
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from vartani.analysis import report
from vartani.backends import HFLocal
from vartani.datasets import load_starter, starter_sets
from vartani.export import report_html, rows_csv, rows_jsonl
from vartani.perturb import build_conditions, default_config


def sha(data):
    return hashlib.sha256(data).hexdigest()


def reviewed_records(obj):
    """Read a reviewed manifest and use the exact approved condition texts."""
    if not obj.get("version") or not obj.get("items"):
        raise ValueError("A reviewed manifest must include a version and items.")
    out, ids = [], set()
    for item in obj["items"]:
        qid, lang, gold = item["id"], item["lang"], item["gold"]
        if not isinstance(qid, str) or not qid or qid in ids or lang not in ("hi", "bn", "ta") or gold not in list("ABCD"):
            raise ValueError(f"Missing or invalid item ID, language, or answer: {qid!r}")
        if not item.get("source") or not item.get("license") or item.get("review_status") != "approved":
            raise ValueError(f"{qid}: missing provenance or recorded approval")
        conditions = item["conditions"]
        if not {"native", "roman"} <= conditions.keys() or not any(re.fullmatch(r"var[1-9][0-9]*", c) for c in conditions):
            raise ValueError(f"{qid}: native, Roman, and reviewed spelling variants are required")
        ids.add(qid)
        names = ["native", "roman", *sorted(set(conditions) - {"native", "roman"})]
        seen, canon = {}, {}
        for name in names:
            if not (re.fullmatch(r"var[1-9][0-9]*", name) or name in ("native", "roman", "typo", "bridge")):
                raise ValueError(f"{qid}: unexpected condition name {name!r}")
            text = conditions[name]
            if (set(text) != {"question", "passage", "options"} or not isinstance(text["passage"], str)
                    or not isinstance(text["question"], str) or not text["question"].strip()
                    or not isinstance(text["options"], list) or len(text["options"]) != 4
                    or not all(isinstance(t, str) and t.strip() for t in text["options"])):
                raise ValueError(f"{qid}: malformed condition {name!r}")
            canon[name] = seen.setdefault(json.dumps(text, sort_keys=True, ensure_ascii=False), name)
        if not any(n.startswith("var") and canon[n] != "roman" for n in names):
            raise ValueError(f"{qid}: the approved spelling variants match the Roman baseline")
        meta = {"canon": canon, "identical_to_roman": [n for n in names if n != "roman" and canon[n] == "roman"]}
        out.append({"qid": qid, "lang": lang, "gold": gold,
                    "conditions": {n: conditions[n] for n in names}, "meta": meta})
    if {x["lang"] for x in out} != {"hi", "bn", "ta"}:
        raise ValueError("The reviewed comparison must include Hindi, Bengali, and Tamil.")
    return out


def inputs(dataset):
    if dataset is not None:
        raw = dataset.read_bytes()
        obj = json.loads(raw.decode("utf-8-sig"))
        return reviewed_records(obj), {"status": "reviewed-manifest", "version": obj["version"], "sha256": sha(raw),
                                       "settings": {"conditions": "exact approved texts supplied by dataset"}}
    cfg = default_config()
    records = []
    for sample in starter_sets():
        for item in load_starter(sample["id"])["items"]:
            records.append(build_conditions({**item, "id": f"{sample['id']}-{item['id']}"}, cfg))
    text = json.dumps(records, ensure_ascii=False, sort_keys=True).encode()
    return records, {"status": "exploratory-starter-set", "version": "bundled-starter-sets",
                     "sha256": sha(text), "settings": cfg}


def score(model, records):
    backend = HFLocal(str(model), "cpu")
    rows, errors = [], []
    for x in records:
        answers, margins = {}, {}
        for name, value in x["conditions"].items():
            canon = x["meta"]["canon"][name]
            if canon != name:
                answers[name], margins[name] = answers[canon], margins[canon]
                continue
            try:
                a = backend.answer(value)
                answers[name], margins[name] = a.letter, a.margin
            except Exception as exc:
                errors.append({"qid": x["qid"], "condition": name, "error": str(exc)})
                answers[name], margins[name] = None, None
                if len(errors) == 3 and not any(a for row in rows for a in row["answers"].values()) and not any(answers.values()):
                    return rows, errors
        rows.append({"qid": x["qid"], "lang": x["lang"], "gold": x["gold"],
                     "answers": answers, "margins": margins,
                     "meta": {k: x["meta"][k] for k in ("identical_to_roman", "bridge_converged", "persona") if k in x["meta"]}})
    return rows, errors


def examples(records, rows):
    by_qid = {x["qid"]: x for x in records}
    groups = {"stable": [], "changed": []}
    for row in rows:
        answers = row["answers"]
        roman = answers.get("roman")
        if roman is None:
            continue
        for variant, value in answers.items():
            if not variant.startswith("var") or value is None or variant in row["meta"]["identical_to_roman"]:
                continue
            group = groups["stable" if value == roman else "changed"]
            if len(group) < 4 and all(e["qid"] != row["qid"] for e in group):
                conds = by_qid[row["qid"]]["conditions"]
                group.append({"qid": row["qid"], "lang": row["lang"], "gold": row["gold"],
                              "roman_answer": roman, "variant_answer": value, "variant": variant,
                              "roman_question": conds["roman"]["question"], "variant_question": conds[variant]["question"],
                              "roman_input": conds["roman"], "variant_input": conds[variant]})
    return groups


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dataset", type=Path, help="Reviewed condition manifest")
    mode.add_argument("--starter-smoke", action="store_true", help="Exploratory run only; never a reviewed result")
    p.add_argument("--model", nargs=3, action="append", metavar=("MODEL_ID", "COMMIT", "SNAPSHOT_DIR"), required=True)
    p.add_argument("--output", type=Path, required=True, help="New directory for the comparison artifacts")
    p.add_argument("--threads", type=int, default=4)
    args = p.parse_args()
    if len(args.model) != 2 or len({m[0] for m in args.model}) != 2 or args.threads < 1:
        p.error("Supply exactly two different models and a positive thread count.")
    for name, commit, path in args.model:
        folder = Path(path)
        if (not re.fullmatch(r"[0-9a-f]{40}", commit) or folder.name != commit
                or not (folder / "config.json").is_file() or not list(folder.glob("*.safetensors"))
                or folder.parent.parent.name != "models--" + name.replace("/", "--")
                or folder.parent.name != "snapshots"):
            p.error(f"{name}: supply the pinned Hugging Face cache snapshot directory containing its weights.")
    records, info = inputs(args.dataset)
    args.output.mkdir(parents=True, exist_ok=False)
    prepared = json.dumps(records, ensure_ascii=False, sort_keys=True).encode()
    try:
        source = subprocess.check_output(["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        source = None
    settings = {"device": "cpu", "weights_dtype": "float32", "torch_threads": args.threads,
                "scoring": "deterministic next-token logits over A/B/C/D (no sampling)",
                "python": sys.version.split()[0], "torch": version("torch"), "transformers": version("transformers"),
                "vartani_commit": source, "comparison_script_sha256": sha(Path(__file__).read_bytes())}
    manifest = {"dataset": {**info, "prepared_sha256": sha(prepared), "n_questions": len(records),
                            "per_language": dict(Counter(r["lang"] for r in records))}, "settings": settings, "models": []}
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    import torch
    torch.set_num_threads(args.threads)
    for i, (name, commit, path) in enumerate(args.model, 1):
        print(f"Scoring {name} ({len(records)} questions)", flush=True)
        started = time.monotonic()
        rows, errors = score(Path(path).resolve(), records)
        metrics = report(rows)
        label = f"model-{i}"
        details = {"model": name, "revision": commit, "errors": errors,
                   "complete": len(rows) == len(records) and not errors, "elapsed_seconds": round(time.monotonic() - started, 2),
                   "summary": {key: metrics.get(key) for key in ("n_items", "accuracy", "script_gap", "stability", "invalid_answers")},
                   "examples": examples(records, rows)}
        manifest["models"].append(details)
        dump(args.output / f"{label}.json", {"details": details, "report": metrics})
        (args.output / f"{label}.csv").write_text(rows_csv(rows), encoding="utf-8")
        (args.output / f"{label}.jsonl").write_text(rows_jsonl(rows), encoding="utf-8")
        title = "Exploratory starter-set comparison" if args.starter_smoke else f"Reviewed benchmark {info['version']}"
        meta = {"id": label, "name": title, "model_label": name, "n_items": len(records),
                "config": info["settings"], "kind": "run", "status": "done" if details["complete"] else "failed"}
        (args.output / f"{label}.html").write_text(report_html(meta, metrics), encoding="utf-8")
        print(f"Finished {name}: {len(rows)} rows, {len(errors)} errors", flush=True)
    dump(args.output / "comparison.json", manifest)
    return 0 if all(m["complete"] for m in manifest["models"]) else 1


if __name__ == "__main__":
    raise SystemExit(main())
