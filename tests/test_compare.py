import json

import pytest

from swapcheck.compare import Options, compare
from swapcheck.io import Condition, InputError, apply_where, load_rows


def rows(spec, label="x"):
    """spec: {case: [(score, bad), ...]} -> rows"""
    out = []
    for case, reps in spec.items():
        for i, (score, bad) in enumerate(reps):
            out.append({"case_id": case, "score": score, "bad": bad, "fam": case[0],
                        "_src": f"{label}:{case}:{i}"})
    return out


GUARD = [Condition.parse("bad>0")]


def test_significant_guard_rise_blocks_even_when_mean_improves():
    # 12 cases, 5 of them start failing on every repeat: one-sided p = 1/32
    spec_a = {f"c{i:02d}": [(0.5, 0)] * 3 for i in range(12)}
    spec_b = {f"c{i:02d}": [(1.0, 1 if i < 5 else 0)] * 3 for i in range(12)}
    res = compare(rows(spec_a), rows(spec_b), Options(metric="score", guards=GUARD))
    g = res["guards"][0]
    assert res["primary"]["diff"] == pytest.approx(0.5)
    assert (g["events_a"], g["events_b"]) == (0, 15)
    assert g["p"] == pytest.approx(1 / 32) and g["significant"]
    assert res["verdict"] == "BLOCK"
    assert res["reasons"][0]["level"] == "BLOCK" and "Unlikely to be chance" in res["reasons"][0]["text"]
    assert res["rerun_cases"] == []


def test_rise_within_noise_is_review_and_lists_cases_to_rerun():
    a = rows({"a1": [(0.5, 0)] * 3, "a2": [(0.5, 0)] * 3, "b1": [(0.5, 0)] * 3})
    b = rows({"a1": [(1.0, 1)] * 3, "a2": [(1.0, 0)] * 3, "b1": [(1.0, 0)] * 3})
    res = compare(a, b, Options(metric="score", guards=GUARD))
    g = res["guards"][0]
    assert g["rose"] and not g["significant"]
    assert g["p"] == 0.5 and g["min_possible_p"] == 0.5
    assert res["verdict"] == "REVIEW"
    assert res["rerun_cases"] == ["a1"]
    assert any("no p below 0.500 was possible" in r["text"] for r in res["reasons"])


def test_zero_tolerance_blocks_any_rise():
    a = rows({"a1": [(0.5, 0)] * 3, "a2": [(0.5, 0)] * 3})
    b = rows({"a1": [(0.5, 1), (0.5, 0), (0.5, 0)], "a2": [(0.5, 0)] * 3})
    res = compare(a, b, Options(metric="score", zero_tolerance=GUARD))
    assert res["guards"][0]["zero_tolerance"] and res["guards"][0]["p_adjusted"] is None
    assert res["verdict"] == "BLOCK"
    assert "zero-tolerance" in res["reasons"][0]["text"]
    # a fall never blocks, even zero-tolerance
    res = compare(b, a, Options(metric="score", zero_tolerance=GUARD))
    assert res["verdict"] != "BLOCK"


def test_holm_across_guards():
    spec_a = {f"c{i:02d}": [(1, 0)] for i in range(12)}
    a = [dict(r, bad2=0) for r in rows(spec_a)]
    b = [dict(r, bad=1 if i < 4 else 0, bad2=1 if i < 4 else 0)
         for i, r in enumerate(rows(spec_a))]
    two = [Condition.parse("bad>0"), Condition.parse("bad2>0")]
    res = compare(a, b, Options(metric="score", guards=two))
    for g in res["guards"]:
        assert g["p"] == pytest.approx(1 / 16)
        assert g["p_adjusted"] == pytest.approx(2 / 16)   # 0.125 > 0.10
        assert not g["significant"]
    assert res["verdict"] == "REVIEW"
    one = compare(a, b, Options(metric="score", guards=two[:1]))
    assert one["verdict"] == "BLOCK"                      # alone, 0.0625 <= 0.10


def test_same_count_new_cases_is_review():
    a = rows({"c1": [(1, 1), (1, 0)], "c2": [(1, 0), (1, 0)], "c3": [(1, 0), (1, 0)]})
    b = rows({"c1": [(1, 0), (1, 0)], "c2": [(1, 1), (1, 0)], "c3": [(1, 0), (1, 0)]})
    res = compare(a, b, Options(metric="score", guards=GUARD))
    g = res["guards"][0]
    assert (g["events_a"], g["events_b"]) == (1, 1)
    assert g["new_cases"] == ["c2"] and g["resolved_cases"] == ["c1"]
    assert res["verdict"] == "REVIEW"


def test_no_change_is_ok_and_says_what_it_cannot_detect():
    spec = {f"c{i}": [(0.9, 0), (1.0, 0)] for i in range(20)}
    res = compare(rows(spec), rows(spec), Options(metric="score", guards=GUARD))
    assert res["verdict"] == "OK"
    assert res["primary"]["mde"] is None              # no spread: nothing to say
    assert any("do not vary" in r["text"] for r in res["reasons"])
    spec_b = {f"c{i}": [(0.9 + 0.01 * (i % 3 - 1), 0), (1.0, 0)] for i in range(20)}
    res = compare(rows(spec), rows(spec_b), Options(metric="score"))
    assert res["verdict"] == "OK" and res["primary"]["mde"] > 0
    assert any("within noise" in r["text"] and "reliably sees" in r["text"] for r in res["reasons"])


def test_too_few_cases_is_review():
    spec = {f"c{i}": [(1.0, 0)] for i in range(9)}
    res = compare(rows(spec), rows(spec), Options(metric="score"))
    assert res["verdict"] == "REVIEW" and "too few" in res["reasons"][0]["text"]


def test_cluster_option():
    a, b = [], []
    for i in range(12):
        fam = f"f{i % 4}"
        a.append({"case_id": f"c{i}", "score": 1.0, "bad": 0, "fam": fam, "_src": "a"})
        # all new failures in one family
        b.append({"case_id": f"c{i}", "score": 0.5 if fam == "f0" else 1.0,
                  "bad": 1 if fam == "f0" else 0, "fam": fam, "_src": "b"})
    case_level = compare(a, b, Options(metric="score", guards=GUARD))
    fam_level = compare(a, b, Options(metric="score", guards=GUARD, cluster_col="fam"))
    assert case_level["guards"][0]["p"] == pytest.approx(1 / 8)
    assert fam_level["guards"][0]["p"] == pytest.approx(1 / 2)   # one cluster changed
    assert fam_level["primary"]["df"] == 3 and fam_level["primary"]["n_clusters"] == 4
    assert "per-cluster" in fam_level["guards"][0]["test"]


def test_unpaired_cases_are_listed_and_excluded():
    a = rows({**{f"c{i}": [(1, 0)] for i in range(10)}, "gone": [(0, 1)]})
    b = rows({**{f"c{i}": [(1, 0)] for i in range(10)}, "new": [(0, 1)]})
    res = compare(a, b, Options(metric="score", guards=GUARD))
    acc = res["accounting"]
    assert acc["only_a"] == ["gone"] and acc["only_b"] == ["new"]
    assert acc["cases_paired"] == 10 and acc["rows_a_paired"] == 10
    # the guard events in unpaired cases are not counted in the paired comparison
    assert res["guards"][0]["events_a"] == 0 and res["guards"][0]["events_b"] == 0
    assert res["verdict"] == "REVIEW"


def test_unequal_repeats_compare_the_first_k_runs():
    a = rows({"c1": [(1, 1)] + [(1, 0)] * 3, "c2": [(1, 0)] * 4})       # 1 of 4
    b = rows({"c1": [(1, 1), (1, 0)], "c2": [(1, 0), (1, 0)]})          # 1 of 2
    res = compare(a, b, Options(metric="score", guards=GUARD))
    g = res["guards"][0]
    assert not res["accounting"]["equal_repeats"]
    assert g["events_a"] == 1 and g["events_b"] == 1
    assert g["rate_a"] == 1 / 8 and g["rate_b"] == 1 / 4   # per-row rates differ...
    assert "first k repeats" in g["test"]
    # ...but on the first 2 runs of each case it is 1 vs 1: not a rise
    assert (g["compared_a"], g["compared_b"]) == (1, 1)
    assert not g["rose"] and g["p"] == 1.0
    guard_line = [r for r in res["reasons"] if "`bad>0`" in r["text"]][0]
    assert guard_line["level"] == "OK"     # (the verdict is REVIEW: 2 cases are too few for the average)


def test_mixed_repeat_counts_alone_are_not_a_rise():
    """Same behaviour in every case; cases c0-5 ran 3 times before and once after,
    c6-11 the other way round. Neither guard nor impact may call that a rise."""
    a, b = [], []
    for i in range(12):
        ra, rb = (3, 1) if i < 6 else (1, 3)
        ev = 1 if (i % 2 and i >= 6) else 0   # failing cases ran 1 time before, 3 after
        a += [{"case_id": f"c{i}", "score": 1, "bad": ev, "usd": 0.5 * ev, "_src": "a"}] * ra
        b += [{"case_id": f"c{i}", "score": 1, "bad": ev, "usd": 0.5 * ev, "_src": "b"}] * rb
    res = compare(a, b, Options(metric="score", guards=GUARD, impacts=["usd:usd"]))
    assert not res["guards"][0]["rose"]
    assert res["impacts"][0]["shown_per_row_a"] == res["impacts"][0]["shown_per_row_b"]
    assert res["verdict"] == "OK", res["reasons"]


def test_reordered_impact_values_are_no_change():
    a = rows({f"c{i}": [(1, 0)] * 3 for i in range(12)})
    b = rows({f"c{i}": [(1, 0)] * 3 for i in range(12)})
    for rs, order in ((a, (.3, .2, .1)), (b, (.1, .2, .3))):
        for k, r in enumerate(rs):
            r["usd"] = order[k % 3]
    res = compare(a, b, Options(metric="score", impacts=["usd:usd"]))
    assert res["verdict"] == "OK", res["reasons"]


def test_tolerance_is_relative_to_the_data():
    # a metric that lives around 1e-13 still shows a doubling
    a = [{"case_id": f"c{i}", "err": 2e-13 + 1e-15 * i, "_src": "a"} for i in range(12)]
    b = [{"case_id": f"c{i}", "err": 4e-13 + 1e-15 * i, "_src": "b"} for i in range(12)]
    res = compare(a, b, Options(metric="err", higher_is_better=False))
    assert res["primary"]["diff"] == pytest.approx(2e-13) and res["verdict"] == "BLOCK"

def test_unequal_repeats_do_not_inflate_false_alarms():
    """The pre-release draft compared per-case rates with a sign test; with 1 repeat
    before and 3 after it said "up" more often than its nominal level under no change
    (see REVIEW.md). The truncated test must stay at or below its level."""
    import random
    rng = random.Random(5)
    blocks = 0
    sims = 400
    for _ in range(sims):
        probs = [rng.uniform(0.05, 0.6) if rng.random() < 0.25 else 0.0 for _ in range(60)]
        a = [{"case_id": f"c{i}", "score": 1, "bad": int(rng.random() < q), "_src": "a"}
             for i, q in enumerate(probs)]
        b = [{"case_id": f"c{i}", "score": 1, "bad": int(rng.random() < q), "_src": "b"}
             for i, q in enumerate(probs) for _ in range(3)]
        res = compare(a, b, Options(metric="score", guards=GUARD))
        blocks += res["guards"][0]["significant"]
    assert blocks / sims <= 0.07       # nominal 0.10; measured about 0.03


def test_lower_is_better_flips_direction():
    a = rows({f"c{i}": [(1.0, 0)] * 2 for i in range(10)})
    b = rows({f"c{i}": [(2.0, 0)] * 2 for i in range(10)})
    worse = compare(a, b, Options(metric="score", higher_is_better=False))
    assert worse["verdict"] == "BLOCK"
    better = compare(b, a, Options(metric="score", higher_is_better=False))
    assert better["verdict"] == "OK"
    assert len(better["improved"]) == 10 and not better["regressed"]


def test_max_drop_noninferiority():
    import random
    rng = random.Random(1)
    spec_a, spec_b = {}, {}
    for i in range(40):
        x = rng.random()
        spec_a[f"c{i}"] = [(x, 0)]
        spec_b[f"c{i}"] = [(x + rng.gauss(0, 0.05), 0)]
    a, b = rows(spec_a), rows(spec_b)
    tight = compare(a, b, Options(metric="score", max_drop=0.2))
    assert tight["verdict"] == "OK"
    strict = compare(a, b, Options(metric="score", max_drop=0.0001))
    assert strict["verdict"] in ("REVIEW", "BLOCK")


def test_regressed_list_and_every_repeat_flag():
    a = rows({"c1": [(1, 0), (1, 0)], "c2": [(1, 0), (0.5, 0)], "c3": [(0.5, 0), (0.5, 0)]})
    b = rows({"c1": [(0.5, 0), (0.5, 0)], "c2": [(1, 0), (0.0, 0)], "c3": [(1, 0), (1, 0)]})
    res = compare(a, b, Options(metric="score"))
    reg = {d["case"]: d for d in res["regressed"]}
    assert set(reg) == {"c1", "c2"}
    assert reg["c1"]["every_repeat"] and not reg["c2"]["every_repeat"]
    assert [d["case"] for d in res["improved"]] == ["c3"]
    assert res["noise"]["unstable_a"] == ["c2"] and res["noise"]["unstable_b"] == ["c2"]


def test_slices():
    a = rows({"x1": [(1, 0)], "x2": [(1, 0)], "y1": [(1, 0)]})
    b = rows({"x1": [(0, 1)], "x2": [(1, 0)], "y1": [(1, 0)]})
    res = compare(a, b, Options(metric="score", guards=GUARD, slice_col="fam"))
    s = {x["slice"]: x for x in res["slices"]}
    assert s["x"]["n_cases"] == 2 and s["x"]["diff"] == pytest.approx(-0.5)
    assert s["x"]["guards"][0] == {"guard": "bad>0", "a": 0, "b": 1}
    assert s["y"]["guards"][0]["b"] == 0


def test_bad_values_are_errors_with_location(tmp_path):
    p = tmp_path / "r.jsonl"
    p.write_text('{"case_id": "c1", "score": 1}\n{"case_id": "c2", "score": "n/a"}\n')
    rs = load_rows(p)
    with pytest.raises(InputError, match=r"r.jsonl:2.*not a number"):
        compare(rs, rs, Options(metric="score"))
    p.write_text('{"case_id": "c1", "score": NaN}\n')
    with pytest.raises(InputError, match="not finite"):
        compare(load_rows(p), load_rows(p), Options(metric="score"))
    p.write_text('{"case_id": "c1"}\n')
    with pytest.raises(InputError, match="no column 'score'"):
        compare(load_rows(p), load_rows(p), Options(metric="score"))
    p.write_text('{"case_id": "c1", "score": null}\n')
    with pytest.raises(InputError, match="empty"):
        compare(load_rows(p), load_rows(p), Options(metric="score"))
    p.write_text('{"case": "c1", "score": 1}\n')
    with pytest.raises(InputError, match="no case id"):
        compare(load_rows(p), load_rows(p), Options(metric="score"))
    p.write_text('{"case_id": "c1", "score": 1}\nnot json\n')
    with pytest.raises(InputError, match=r"r.jsonl:2"):
        load_rows(p)


def test_guard_on_missing_column_is_an_error():
    a = rows({"c1": [(1, 0)]})
    with pytest.raises(InputError, match="nope"):
        compare(a, a, Options(metric="score", guards=[Condition.parse("nope>0")]))


def test_conditions():
    r = {"m": "openai/gpt-4.1-mini", "x": 3, "ok": True, "s": "true"}
    assert Condition.parse("m=openai/gpt-4.1-mini").test(r)
    assert Condition.parse("m != other").test(r)
    assert Condition.parse("x>=3").test(r) and not Condition.parse("x>3").test(r)
    assert Condition.parse("ok==true").test(r) and Condition.parse("s=true").test(r)
    with pytest.raises(InputError):
        Condition.parse("no operator")
    with pytest.raises(InputError):
        Condition.parse("m>abc").test(r)
    with pytest.raises(InputError):
        Condition.parse("x>").test(r)


def test_csv_loader_and_where(tmp_path):
    p = tmp_path / "r.csv"
    p.write_text("case_id,model,score\nc1,a,1\nc1,b,0.5\nc2,a,1\nc2,b,1\n")
    rs = load_rows(p)
    a = apply_where(rs, [Condition.parse("model=a")], "A")
    b = apply_where(rs, [Condition.parse("model=b")], "B")
    res = compare(a, b, Options(metric="score"))
    assert res["primary"]["diff"] == pytest.approx(-0.25)


def test_empty_after_filter_is_an_error():
    a = rows({"c1": [(1, 0)]})
    with pytest.raises(InputError, match="no rows"):
        compare(a, [], Options(metric="score", label_b="B"))


def test_json_report_is_valid_json():
    from swapcheck.report import to_json, to_markdown
    a = rows({"c1": [(1, 0), (0.5, 1)], "c2": [(1, 0), (1, 0)]})
    b = rows({"c1": [(0.5, 1), (0.5, 1)], "c2": [(1, 0), (1, 0)]})
    res = compare(a, b, Options(metric="score", zero_tolerance=GUARD, slice_col="fam",
                                latency_col="score", impacts=["score:cents"]))
    back = json.loads(to_json(res))
    assert back["verdict"] == "BLOCK"
    md = to_markdown(res)
    assert "## Verdict: BLOCK" in md and "bad&gt;0" in md
    assert "$0.03" in md                        # 3 cents shown as dollars
    pa = [dict(r, case_id="x|y") for r in a]
    pb = [dict(r, case_id="x|y", score=0) for r in a]
    md = to_markdown(compare(pa, pb, Options(metric="score")))
    assert "x\\|y" in md                         # a pipe in a case id cannot break a table


def test_unequal_repeats_truncate_the_longer_side_too():
    # A ran 3 times and failed once per case (on the 3rd row); B ran once and failed.
    # Per-row rate 1/3 -> 1. Compared on the first row of each side: 0 -> 1 in 6 cases.
    a = rows({f"c{i}": [(1, 0), (1, 0), (1, 1)] for i in range(6)})
    b = rows({f"c{i}": [(1, 1)] for i in range(6)})
    res = compare(a, b, Options(metric="score", guards=GUARD))
    g = res["guards"][0]
    assert g["rose"] and g["p"] == pytest.approx(1 / 64) and res["verdict"] == "BLOCK"


def test_first_k_rows_in_file_order():
    a = rows({f"c{i}": [(1, 0)] for i in range(6)})
    first = rows({f"c{i}": [(1, 1), (1, 0), (1, 0)] for i in range(6)})
    last = rows({f"c{i}": [(1, 0), (1, 0), (1, 1)] for i in range(6)})
    r1 = compare(a, first, Options(metric="score", guards=GUARD))
    r2 = compare(a, last, Options(metric="score", guards=GUARD))
    assert r1["guards"][0]["p"] == pytest.approx(1 / 64) and r1["verdict"] == "BLOCK"
    assert r2["guards"][0]["p"] == 1.0 and r2["verdict"] == "REVIEW"


def test_guard_alpha_is_inclusive():
    spec_a = {f"c{i:02d}": [(1, 0)] for i in range(12)}
    spec_b = {f"c{i:02d}": [(1, 1 if i < 4 else 0)] for i in range(12)}
    res = compare(rows(spec_a), rows(spec_b), Options(metric="score", guards=GUARD, guard_alpha=1 / 16))
    assert res["guards"][0]["p"] == pytest.approx(1 / 16) and res["verdict"] == "BLOCK"


def test_same_values_in_a_different_order_are_no_change():
    a = rows({f"c{i}": [(.1, 0), (.2, 0), (.3, 0)] for i in range(12)})
    b = rows({f"c{i}": [(.3, 0), (.2, 0), (.1, 0)] for i in range(12)})
    res = compare(a, b, Options(metric="score"))
    assert res["verdict"] == "OK"
    assert res["primary"]["diff"] == 0.0 and not res["regressed"] and not res["improved"]


def test_one_cluster_says_so():
    a = [{"case_id": f"c{i}", "score": 1.0, "fam": "x", "_src": "a"} for i in range(30)]
    b = [{"case_id": f"c{i}", "score": 0.0 if i < 20 else 1.0, "fam": "x", "_src": "b"} for i in range(30)]
    res = compare(a, b, Options(metric="score", cluster_col="fam"))
    assert res["verdict"] == "REVIEW"
    assert "Only 1 cluster(s)" in res["reasons"][0]["text"]


def test_impact_with_unequal_repeats_is_per_run():
    a = [{"case_id": f"c{i}", "score": 1, "usd": 1.0, "_src": "a"} for i in range(12)]
    b = [{"case_id": f"c{i}", "score": 1, "usd": 1.0, "_src": "b"} for i in range(12) for _ in range(3)]
    res = compare(a, b, Options(metric="score", impacts=["usd:usd"]))
    im = res["impacts"][0]
    assert (im["shown_a"], im["shown_b"]) == ("$12.00", "$36.00")
    assert im["shown_per_row_a"] == im["shown_per_row_b"] == "$1.00"
    assert res["verdict"] == "OK"


def test_rounding_noise_is_no_change():
    vals = [0.1, 0.2, 0.4, 0.9, 0.35]
    a = rows({f"c{i}": [(vals[i % 5], 0), (vals[(i + 1) % 5], 0)] for i in range(12)})
    b = rows({f"c{i}": [((vals[i % 5] + 0.7) - 0.7, 0), ((vals[(i + 1) % 5] + 0.7) - 0.7, 0)]
              for i in range(12)})
    res = compare(a, b, Options(metric="score"))
    assert res["primary"]["diff"] == 0.0 and res["primary"]["mde"] is None
    assert not res["regressed"] and not res["improved"] and res["verdict"] == "OK"
