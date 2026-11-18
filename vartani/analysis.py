"""Turn raw answers into a report.

Why these statistics (the paper reported plain percentages; a product has to say how sure it is):
  * Wilson 95% interval on every accuracy      - with 200 questions a single number can be off by +/-7 points.
  * Exact binomial test against 25% guessing   - "is the model better than a coin flip on four options?"
  * Exact McNemar test for paired comparisons   - same questions, two conditions (e.g. native vs Roman).
  * Flip rate per single respelling             - fair to compare with the one-typo flip rate (the paper compared
                                                  "any of 4 variants" with "1 typo", which is not like for like).
"""
from __future__ import annotations
import math
from collections import Counter
from typing import Dict, List, Optional

from .config import CHANCE
from .perturb import RULES

L = ["A", "B", "C", "D"]
COND_LABEL = {"native": "Native script", "roman": "Roman (baseline)", "typo": "Keyboard typos",
              "bridge": "Bridged to native", "asr": "Speech transcript", "asr_roman": "ASR → Romanized"}
# Colab JSONL keys -> Vartani condition names
COLAB_KEYS = {"c0_native": "native", "c1_modal": "roman", "c2_var1": "var1", "c3_var2": "var2",
              "c4_var3": "var3", "c5_var4": "var4", "c6_typo": "typo", "c7_norm": "bridge"}


# ---- statistics ---------------------------------------------------------------------------------------------
def wilson(k: int, n: int, z: float = 1.96):
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def _log_binom(n: int, k: int, p: float) -> float:
    return math.lgamma(n + 1) - math.lgamma(k + 1) - math.lgamma(n - k + 1) + k * math.log(p) + (n - k) * math.log(1 - p)


def binom_sf(k: int, n: int, p: float) -> float:
    """P(X >= k) for X ~ Binomial(n, p), exact."""
    if k <= 0:
        return 1.0
    if k > n:
        return 0.0
    return min(1.0, sum(math.exp(_log_binom(n, i, p)) for i in range(k, n + 1)))


def mcnemar(b: int, c: int) -> float:
    """Two-sided exact McNemar p-value from the discordant pair counts."""
    n = b + c
    if n == 0:
        return 1.0
    lo = min(b, c)
    tail = sum(math.exp(_log_binom(n, i, 0.5)) for i in range(0, lo + 1))
    return min(1.0, 2 * tail)


def fp(p: float) -> str:
    return "p < 0.001" if p < 0.001 else f"p = {p:.3f}".rstrip("0").rstrip(".") if p < 0.1 else f"p = {p:.2f}"


def pct(x: Optional[float]) -> Optional[float]:
    return None if x is None else round(100 * x, 1)


# ---- helpers ------------------------------------------------------------------------------------------------
def _acc(rows: List[dict], cond: str) -> Optional[dict]:
    rs = [r for r in rows if cond in r["answers"] and r.get("gold")]
    if not rs:
        return None
    k = sum(r["answers"][cond] == r["gold"] for r in rs)
    lo, hi = wilson(k, len(rs))
    return {"k": k, "n": len(rs), "acc": pct(k / len(rs)), "lo": pct(lo), "hi": pct(hi),
            "p_vs_chance": round(binom_sf(k, len(rs), CHANCE), 5)}


def _paired(rows: List[dict], a: str, b: str) -> Optional[dict]:
    """Compare condition a with condition b on the same items: effect = acc(a) - acc(b)."""
    rs = [r for r in rows if a in r["answers"] and b in r["answers"] and r.get("gold")]
    if len(rs) < 2:
        return None
    only_a = sum(r["answers"][a] == r["gold"] and r["answers"][b] != r["gold"] for r in rs)
    only_b = sum(r["answers"][b] == r["gold"] and r["answers"][a] != r["gold"] for r in rs)
    return {"n": len(rs), "effect": pct((only_a - only_b) / len(rs)), "only_a": only_a, "only_b": only_b,
            "p": round(mcnemar(only_a, only_b), 5)}


def _variants(rows: List[dict]) -> List[str]:
    names = {c for r in rows for c in r["answers"] if c.startswith("var")}
    return sorted(names, key=lambda x: int(x[3:]))


def _bins(rows: List[dict]) -> Optional[list]:
    rs = [r for r in rows if r.get("gold") and r["answers"].get("roman") and (r.get("margins") or {}).get("roman") is not None]
    if len(rs) < 30:
        return None
    q = 4 if len(rs) >= 80 else 3
    rs.sort(key=lambda r: r["margins"]["roman"])
    out = []
    for i in range(q):
        chunk = rs[i * len(rs) // q:(i + 1) * len(rs) // q]
        k = sum(r["answers"]["roman"] == r["gold"] for r in chunk)
        lo, hi = wilson(k, len(chunk))
        out.append({"label": ["lowest", "low", "high", "highest"][i] if q == 4 else ["low", "medium", "high"][i],
                    "n": len(chunk), "acc": pct(k / len(chunk)), "lo": pct(lo), "hi": pct(hi),
                    "margin_from": chunk[0]["margins"]["roman"], "margin_to": chunk[-1]["margins"]["roman"]})
    return out


def _spelling_fingerprint(rows: List[dict]) -> dict:
    """Summarize which consistent writer-style habit combinations change answers.

    This uses the generated persona attached to each respelling. It describes an
    association in this test set; it does not claim one spelling rule caused a flip.
    """
    from .perturb import RULES
    groups: Dict[tuple, dict] = {}
    for row in rows:
        answers = row.get("answers", {})
        baseline = answers.get("roman")
        if baseline is None:
            continue
        for variant, habits in (row.get("meta") or {}).get("persona", {}).items():
            if not habits or variant not in answers:
                continue
            key = (row.get("lang", "?"), tuple(sorted(set(habits))))
            item = groups.setdefault(key, {"n": 0, "scored": 0, "flips": 0, "harmful": 0, "helpful": 0, "correct": 0})
            item["n"] += 1
            item["flips"] += answers[variant] != baseline
            if row.get("gold"):
                item["scored"] += 1
                base_ok = baseline == row["gold"]
                variant_ok = answers[variant] == row["gold"]
                item["correct"] += variant_ok
                item["harmful"] += base_ok and not variant_ok
                item["helpful"] += not base_ok and variant_ok
    profiles = []
    for (lang, habits), values in groups.items():
        n = values["n"]
        profiles.append({"lang": lang, "habits": list(habits), "label": " + ".join(RULES[h][0] for h in habits),
                         "n": n, "flip_rate": pct(values["flips"] / n),
                         "accuracy": pct(values["correct"] / values["scored"]) if values["scored"] else None,
                         "harmful": values["harmful"], "helpful": values["helpful"]})
    profiles.sort(key=lambda p: (-p["flip_rate"], -p["n"], p["lang"], p["label"]))
    return {"profiles": profiles, "n_profiles": len(profiles),
            "description": "Observed answer changes for consistent writer-style spelling profiles."}


# ---- the report ---------------------------------------------------------------------------------------------
def report(rows: List[dict]) -> dict:
    rows = [r for r in rows if r.get("answers")]
    n = len(rows)
    if not n:
        return {"n_items": 0, "findings": [], "verdict": None}
    conds = []
    for c in ["native", "roman", *_variants(rows), "typo", "bridge", "asr", "asr_roman"]:
        if any(c in r["answers"] for r in rows):
            conds.append(c)
    vars_ = _variants(rows)
    langs = sorted({r["lang"] for r in rows})
    out: dict = {"n_items": n, "langs": langs, "conditions": conds, "chance": pct(CHANCE)}

    out["accuracy"] = {c: _acc(rows, c) for c in conds}
    out["by_lang"] = {lg: {c: _acc([r for r in rows if r["lang"] == lg], c) for c in conds} for lg in langs}
    if vars_:   # all variants pooled as one bar
        ks = [(sum(r["answers"][v] == r["gold"] for r in rows if v in r["answers"] and r.get("gold")),
               sum(1 for r in rows if v in r["answers"] and r.get("gold"))) for v in vars_]
        k, m = sum(a for a, _ in ks), sum(b for _, b in ks)
        lo, hi = wilson(k, m)
        out["accuracy"]["variants"] = {"k": k, "n": m, "acc": pct(k / m) if m else None, "lo": pct(lo), "hi": pct(hi),
                                       "p_vs_chance": round(binom_sf(k, m, CHANCE), 5)}
    golds = Counter(r["gold"] for r in rows if r.get("gold"))
    out["gold_dist"] = {l: pct(golds[l] / max(1, sum(golds.values()))) for l in L}
    out["majority_baseline"] = pct(max(golds.values()) / sum(golds.values())) if golds else None
    preds = Counter(r["answers"].get("roman") for r in rows if "roman" in r["answers"])
    out["pred_dist"] = {l: pct(preds[l] / max(1, sum(preds.values()))) for l in L}
    out["invalid_answers"] = sum(1 for r in rows for v in r["answers"].values() if v is None)

    out["script_gap"] = _paired(rows, "native", "roman")        # effect = native - roman
    out["bridge_gain"] = _paired(rows, "bridge", "roman")       # effect = bridge - roman
    out["typo_effect"] = _paired(rows, "typo", "roman")

    # stability across respellings
    st = None
    if vars_:
        pr = []
        for r in rows:
            if "roman" not in r["answers"]:
                continue
            ident = set((r.get("meta") or {}).get("identical_to_roman", []))
            vs = [v for v in vars_ if v in r["answers"] and v not in ident]
            if vs:
                pr.append((r, vs))
        n_p = len(pr)
        if n_p:
            any_flip = sum(any(r["answers"][v] != r["answers"]["roman"] for v in vs) for r, vs in pr)
            single = [r["answers"][v] != r["answers"]["roman"] for r, vs in pr for v in vs]
            c2i = i2c = 0
            for r, vs in pr:
                if any(r["answers"][v] != r["answers"]["roman"] for v in vs):
                    if r["answers"]["roman"] == r["gold"]:
                        c2i += 1
                    elif any(r["answers"][v] == r["gold"] for v in vs):
                        i2c += 1
            forms = [[r["answers"]["roman"]] + [r["answers"][v] for v in vs] for r, vs in pr]
            all_agree = sum(len(set(f)) == 1 for f in forms)
            pairs = same = 0
            for f in forms:
                for i in range(len(f)):
                    for j in range(i + 1, len(f)):
                        pairs += 1
                        same += f[i] == f[j]
            st = {"n": n_p, "n_unchanged_text": n - n_p, "any_flip_rate": pct(any_flip / n_p),
                  "single_flip_rate": pct(sum(single) / len(single)), "all_agree_rate": pct(all_agree / n_p),
                  "pairwise_agreement": pct(same / pairs) if pairs else None,
                  "correct_to_incorrect": pct(c2i / n_p), "incorrect_to_correct": pct(i2c / n_p)}
            # does agreement predict correctness?
            ag = [(len(set(f)) == 1, r["answers"]["roman"] == r["gold"]) for f, (r, _) in zip(forms, pr) if r.get("gold")]
            a1 = [c for a, c in ag if a]
            a0 = [c for a, c in ag if not a]
            st["signal"] = {"agree_n": len(a1), "agree_acc": pct(sum(a1) / len(a1)) if a1 else None,
                            "split_n": len(a0), "split_acc": pct(sum(a0) / len(a0)) if a0 else None}
            # does majority vote across spellings help?
            votes = []
            for f, (r, _) in zip(forms, pr):
                if r.get("gold"):
                    cnt = Counter(f)
                    top = max(cnt.values())
                    pick = f[0] if cnt[f[0]] == top else next(x for x in f if cnt[x] == top)
                    votes.append(pick == r["gold"])
            if votes:
                st["vote_acc"] = pct(sum(votes) / len(votes))
                st["single_acc"] = out["accuracy"]["roman"]["acc"] if out["accuracy"].get("roman") else None
    if "typo" in conds:
        rs = [r for r in rows if "roman" in r["answers"] and "typo" in r["answers"]]
        if rs:
            out.setdefault("typo_flip_rate", pct(sum(r["answers"]["typo"] != r["answers"]["roman"] for r in rs) / len(rs)))
    out["stability"] = st
    out["spelling_fingerprint"] = _spelling_fingerprint(rows)

    # fragility by spelling habit (deep scan)
    frag = []
    for rid, (label, *_rest) in RULES.items():
        c = f"rule:{rid}"
        rs = [r for r in rows if c in r["answers"] and "roman" in r["answers"]]
        if rs:
            fl = [r for r in rs if r["answers"][c] != r["answers"]["roman"]]
            frag.append({"rule": rid, "label": label, "n": len(rs), "flips": len(fl),
                         "flip_rate": pct(len(fl) / len(rs)),
                         "to_wrong": sum(r["answers"]["roman"] == r.get("gold") for r in fl),
                         "to_right": sum(r["answers"][c] == r.get("gold") for r in fl)})
    frag.sort(key=lambda x: (-x["flip_rate"], -x["n"]))
    out["fragility"] = frag
    bc = [r["meta"]["bridge_converged"] for r in rows if (r.get("meta") or {}).get("bridge_converged") is not None]
    out["bridge_converged"] = pct(sum(bc) / len(bc)) if bc else None
    out["margin_bins"] = _bins(rows)
    out["findings"], out["verdict"] = _findings(out)
    return out


# ---- plain-language findings ---------------------------------------------------------------------------------
def _f(level, title, text):
    return {"level": level, "title": title, "text": text}


def _findings(o: dict):
    F: List[dict] = []
    acc = o["accuracy"]
    rom = acc.get("roman")
    st = o.get("stability")
    gap = o.get("script_gap")
    if o["n_items"] < 30:
        F.append(_f("info", "Small sample", f"Only {o['n_items']} items were tested, so every interval below is wide. "
                    "Treat the numbers as a first look, not a measurement."))
    if rom:
        if rom["p_vs_chance"] > 0.05:
            F.append(_f("bad", "Roman answers are no better than guessing",
                        f"On Roman text the model scored {rom['acc']}% (95% CI {rom['lo']}–{rom['hi']}%). With four options, "
                        f"guessing gives 25%, so this result is statistically indistinguishable from a coin flip."))
        else:
            F.append(_f("info", "Roman accuracy", f"On Roman text the model scored {rom['acc']}% (95% CI {rom['lo']}–{rom['hi']}%), "
                        f"above the 25% guessing level ({fp(rom['p_vs_chance'])})."))
        mb = o.get("majority_baseline")
        if mb and rom["acc"] is not None and rom["acc"] <= mb + 2:
            F.append(_f("warn", "A constant guess scores about the same",
                        f"Always answering the most common letter would score {mb}% on this set — close to the model's "
                        f"{rom['acc']}% on Roman text."))
    if gap:
        e = gap["effect"]
        lvl = "bad" if e >= 15 and gap["p"] < .05 else "warn" if e >= 5 and gap["p"] < .05 else "good"
        txt = (f"The same questions in native script score {e:+.1f} points ({'higher' if e >= 0 else 'lower'}) than in Roman script "
               f"(paired exact test, {fp(gap['p'])}, n = {gap['n']}).")
        F.append(_f(lvl, "Script gap", txt))
    if st:
        lvl = "bad" if st["any_flip_rate"] >= 40 else "warn" if st["any_flip_rate"] >= 20 else "good"
        extra = f" One typo-laden copy changed it in {o['typo_flip_rate']}% of questions." if o.get("typo_flip_rate") is not None else ""
        F.append(_f(lvl, "Answers change with spelling",
                    f"In {st['any_flip_rate']}% of questions at least one respelling changed the answer; an average single "
                    f"respelling changed it in {st['single_flip_rate']}%.{extra}"))
        va = acc.get("variants")
        if va and rom and abs(va["acc"] - rom["acc"]) <= 3 and st["any_flip_rate"] >= 20:
            F.append(_f("warn", "Accuracy hides the churn",
                        f"Respellings scored {va['acc']}% against {rom['acc']}% for the baseline — nearly identical — yet "
                        f"{st['correct_to_incorrect']}% of questions went from right to wrong and {st['incorrect_to_correct']}% "
                        f"from wrong to right. A single accuracy number would have looked fine."))
        sg = st.get("signal") or {}
        if sg.get("agree_acc") is not None and sg.get("split_acc") is not None and min(sg["agree_n"], sg["split_n"]) >= 10:
            d = sg["agree_acc"] - sg["split_acc"]
            F.append(_f("info", "Agreement as a warning light",
                        f"When every spelling gave the same answer the model was right {sg['agree_acc']}% of the time "
                        f"(n = {sg['agree_n']}); when they disagreed, {sg['split_acc']}% (n = {sg['split_n']}). "
                        + ("Disagreement is a useful flag." if d >= 10 else "The difference is small, so disagreement is only a weak flag.")))
        if st.get("vote_acc") is not None and st.get("single_acc") is not None:
            d = st["vote_acc"] - st["single_acc"]
            F.append(_f("info", "Majority vote across spellings",
                        f"Voting over all spellings scored {st['vote_acc']}% vs {st['single_acc']}% for one query "
                        + ("— a real gain." if d >= 3 else "— it does not fix the problem." if d < 1 else "— a marginal gain.")))
    bg = o.get("bridge_gain")
    if bg:
        e = bg["effect"]
        conv = o.get("bridge_converged")
        rec = f", recovering about {round(100 * e / gap['effect'])}% of the native-script gap" if gap and gap["effect"] > 0 and e > 0 else ""
        cv = f" Only {conv}% of respellings convert to the same native text as the baseline." if conv is not None else ""
        if e > 0 and bg["p"] < .05:
            F.append(_f("good", "Bridging to native script helps", f"Converting Roman input to native script before asking "
                        f"improved accuracy by {e:+.1f} points ({fp(bg['p'])}){rec}.{cv}"))
        elif e > 0:
            F.append(_f("info", "Bridging may help", f"Bridged input scored {e:+.1f} points vs Roman, but the difference is not "
                        f"statistically solid ({fp(bg['p'])}).{cv}"))
        else:
            F.append(_f("warn", "Bridging did not help here", f"Bridged input scored {e:+.1f} points vs Roman ({fp(bg['p'])}). "
                        f"The built-in converter is rule-based and approximate, so its mistakes can cancel the benefit.{cv}"))
    if o.get("fragility"):
        top = [f for f in o["fragility"] if f["n"] >= 5][:2]
        if top:
            F.append(_f("info", "Most fragile spelling habits", "; ".join(f"{t['label']}: {t['flip_rate']}% of {t['n']} questions flipped" for t in top) + "."))
    pd_ = o.get("pred_dist") or {}
    if pd_ and max(pd_.values()) >= 40:
        l = max(pd_, key=pd_.get)
        F.append(_f("warn", "Position bias", f"The model chose option {l} for {pd_[l]}% of Roman questions (25% would be even)."))
    if o["invalid_answers"]:
        F.append(_f("warn", "Unreadable replies", f"{o['invalid_answers']} replies did not contain an answer letter and were counted as wrong."))

    # verdict
    flip = st["any_flip_rate"] if st else None
    g = gap["effect"] if gap and gap["p"] < .05 else 0
    if rom and (rom["p_vs_chance"] > .05):
        v = ("bad", "Not reliable on Roman text", "Accuracy on Roman input is statistically no better than guessing.")
    elif flip is not None and flip >= 40:
        v = ("bad", "Fragile", f"Answers change under respelling in {flip}% of questions.")
    elif (flip is not None and flip >= 25) or g >= 20:
        v = ("warn", "Shaky", "Roman input costs noticeable accuracy or changes answers often.")
    elif (flip is None or flip < 15) and g < 8:
        v = ("good", "Mostly robust", "Few answers change and the script gap is small.")
    else:
        v = ("warn", "Some sensitivity", "Moderate answer changes under respelling.")
    return F, {"level": v[0], "label": v[1], "summary": v[2]}
