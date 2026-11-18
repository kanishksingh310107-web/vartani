from vartani import analysis, datasets, evidence, perturb, scripts


def test_paper_numbers_reproduce():
    e = evidence.evidence()
    a = e["all"]["accuracy"]
    assert (a["native"]["acc"], a["roman"]["acc"], a["bridge"]["acc"], a["typo"]["acc"]) == (60.8, 32.9, 40.4, 30.4)
    q = e["models"]["qwen3-4b"]["report"]["stability"]
    assert (q["any_flip_rate"], q["all_agree_rate"], q["pairwise_agreement"]) == (55.3, 44.7, 69.7)


def test_stats():
    lo, hi = analysis.wilson(50, 100)
    assert 0.40 < lo < 0.41 and 0.59 < hi < 0.60
    assert analysis.binom_sf(0, 10, .25) == 1 and analysis.binom_sf(10, 10, .5) < 0.002
    assert analysis.mcnemar(10, 0) < 0.01 and analysis.mcnemar(5, 5) == 1.0


def test_conditions_deterministic_and_dedup():
    it = datasets.load_starter("hi_demo")["items"][0]
    a, b = perturb.build_conditions(it, {"scan": True}), perturb.build_conditions(it, {"scan": True})
    assert a["conditions"] == b["conditions"]
    assert {"native", "roman", "var1", "var4", "typo", "bridge"} <= set(a["conditions"])
    assert a["conditions"]["bridge"]["question"].startswith("दोपहर")
    assert perturb.count_calls([a]) <= len(a["conditions"])


def test_itrans_item_without_roman():
    it = {"id": 0, "lang": "hi", "gold": "A", "roman": None,
          "native": {"passage": "सूरज पूरब से उगता है।", "question": "सूरज कहाँ से उगता है?", "options": ["पूरब", "पश्चिम", "उत्तर", "दक्षिण"]}}
    r = perturb.build_conditions(it)
    assert r["meta"]["roman_source"] == "itrans" and scripts.script_of(r["conditions"]["roman"]["question"]) == "roman"


def test_habit_is_consistent_across_fields():
    t = {"passage": "dhoop thandi", "question": "dhoop kaisi", "options": ["thandi", "dhoop", "x", "y"]}
    out = perturb.apply_habits("dhoop thandi dhoop", ["dh>d", "th>t"])
    assert out == "doop tandi doop"
