"""The promptfoo adapter, on a file promptfoo 0.123.1 actually wrote.

tests/promptfoo_results.json came from
    promptfoo eval -c tests/promptfooconfig.yaml --repeat 3 --no-cache -o results.json
with the local provider in tests/echo_provider.js (no network, no API key).
Three tests x two providers x three repeats = 18 rows. promptfoo numbered them
testIdx 0..8: every repeat got its own testIdx.
"""

import json
from pathlib import Path

import pytest

from swapcheck.cli import main
from swapcheck.compare import Options, compare
from swapcheck.io import Condition, InputError, apply_where, load_rows

HERE = Path(__file__).parent
FIXTURE = HERE / "promptfoo_results.json"


def test_fixture_really_has_one_testidx_per_repeat():
    raw = json.loads(FIXTURE.read_text())["results"]["results"]
    assert len(raw) == 18
    assert len({r["testIdx"] for r in raw}) == 9          # 3 tests x 3 repeats
    assert json.loads(FIXTURE.read_text())["metadata"]["promptfooVersion"] == "0.123.1"


def test_repeats_collapse_to_three_cases():
    rows = load_rows(FIXTURE)                             # format sniffed
    assert len(rows) == 18
    cases = {r["case_id"] for r in rows}
    assert len(cases) == 3
    assert {"refund-policy", "weather"} <= cases          # descriptions used as ids
    assert any(c.startswith("vars:") for c in cases)      # no description -> vars hash
    for c in cases:
        assert sum(r["case_id"] == c for r in rows) == 6  # 2 providers x 3 repeats


def test_assertion_failures_become_columns():
    rows = load_rows(FIXTURE)
    after = apply_where(rows, [Condition.parse("provider=after")], "after")
    assert sum(r["fail:no-pii"] for r in after) == 3
    assert sum(r["fail:correct"] for r in after) == 1
    before = apply_where(rows, [Condition.parse("provider=before")], "before")
    assert sum(r["fail:no-pii"] + r["fail:correct"] for r in before) == 0


def test_comparison_blocks_on_the_pii_guard():
    rows = load_rows(FIXTURE)
    a = apply_where(rows, [Condition.parse("provider=before")], "before")
    b = apply_where(rows, [Condition.parse("provider=after")], "after")
    res = compare(a, b, Options(metric="score", zero_tolerance=[Condition.parse("fail:no-pii>0")],
                                latency_col="latency_ms", cost_col="cost"))
    assert res["accounting"]["cases_paired"] == 3 and res["accounting"]["repeats_b"] == [3]
    g = res["guards"][0]
    assert (g["events_a"], g["events_b"], g["cases_b"]) == (0, 3, 1)
    assert res["verdict"] == "BLOCK"
    assert res["perf"]["latency"]["b"]["p50"] == 120
    assert res["perf"]["cost"]["a"]["total"] == pytest.approx(0.009)


def test_cli_exit_codes_on_promptfoo(tmp_path, capsys):
    base = [str(FIXTURE), str(FIXTURE), "--metric", "score",
            "--where-a", "provider=before", "--where-b", "provider=after"]
    # one test leaked an email on all 3 repeats: zero-tolerance blocks
    assert main(["compare", *base, "--zero-tolerance", "fail:no-pii>0"]) == 4
    assert main(["compare", *base, "--zero-tolerance", "fail:no-pii>0", "--fail-on", "never"]) == 0
    # as an ordinary guard: one case out of three cannot be told from noise (p >= 0.5)
    assert main(["compare", *base, "--guard", "fail:no-pii>0"]) == 0
    assert main(["compare", *base, "--guard", "fail:no-pii>0", "--fail-on", "review"]) == 3
    out = capsys.readouterr().out
    assert "--filter-pattern '^(refund\\-policy)$'" in out    # rerun command for promptfoo
    # a zero-tolerance block is not a "rerun to check" case
    main(["compare", *base, "--zero-tolerance", "fail:no-pii>0", "--guard", "fail:correct>0"])
    out = capsys.readouterr().out
    assert "--filter-pattern '^(weather)$'" in out
    # without guards: 3 cases are too few to judge the average: REVIEW
    assert main(["compare", *base]) == 0
    assert main(["compare", *base, "--fail-on", "review"]) == 3
    assert main(["compare", *base, "--metric", "named:missing"]) == 2
    out = capsys.readouterr()
    assert "input error" in out.err


def test_named_scores_absent_are_not_zero(tmp_path):
    raw = json.loads(FIXTURE.read_text())
    del raw["results"]["results"][0]["namedScores"]["correct"]
    p = tmp_path / "edited.json"
    p.write_text(json.dumps(raw))
    rows = load_rows(p)
    assert rows[0]["named:correct"] is None
    with pytest.raises(InputError, match="empty"):
        compare(rows, rows, Options(metric="named:correct"))


def test_two_tests_with_one_description_stay_two_cases(tmp_path):
    raw = json.loads(FIXTURE.read_text())
    for r in raw["results"]["results"]:
        r["testCase"]["description"] = "same"
    p = tmp_path / "same.json"
    p.write_text(json.dumps(raw))
    cases = {r["case_id"] for r in load_rows(p)}
    assert len(cases) == 3
    assert all(c.startswith("same [vars:") for c in cases)


def test_not_a_promptfoo_file(tmp_path):
    p = tmp_path / "x.json"
    p.write_text('{"results": {"nope": 1}}')
    with pytest.raises(InputError, match="results.results"):
        load_rows(p, "promptfoo")


def test_error_means_the_provider_failed_not_an_assertion():
    rows = load_rows(FIXTURE)
    # the fixture's 4 failing rows failed assertions (failureReason 1); none errored
    assert sum(r["error"] for r in rows) == 0
    assert sum(1 - r["success"] for r in rows) == 4


def test_an_errored_row_counts_as_failing_every_assertion(tmp_path):
    raw = json.loads(FIXTURE.read_text())
    r0 = raw["results"]["results"][0]
    r0.update(failureReason=2, error="API timeout", gradingResult=None, success=False, score=0)
    p = tmp_path / "errored.json"
    p.write_text(json.dumps(raw))
    row = load_rows(p)[0]
    assert row["error"] == 1
    assert row["fail:no-pii"] == 1 and row["fail:correct"] == 1


def test_two_prompts_on_one_side_are_refused(tmp_path, capsys):
    raw = json.loads(FIXTURE.read_text())
    for i, r in enumerate(raw["results"]["results"]):
        r["prompt"]["label"] = "p1" if i % 2 else "p2"
    p = tmp_path / "two_prompts.json"
    p.write_text(json.dumps(raw))
    code = main(["compare", str(p), str(p), "--metric", "score",
                 "--where-a", "provider=before", "--where-b", "provider=after"])
    assert code == 2
    assert "prompts" in capsys.readouterr().err


def test_non_utf8_stdout_does_not_crash():
    import os
    import subprocess
    import sys
    env = dict(os.environ, PYTHONIOENCODING="cp1252", PYTHONUTF8="0",
               PYTHONPATH=str(HERE.parent / "src"))
    out = subprocess.run([sys.executable, "-m", "swapcheck", "compare", str(FIXTURE), str(FIXTURE),
                          "--metric", "score", "--where-a", "provider=before",
                          "--where-b", "provider=after"], capture_output=True, env=env)
    assert out.returncode == 0, out.stderr
    assert "→".encode() in out.stdout


def test_huge_numbers_are_an_input_error(tmp_path, capsys):
    p = tmp_path / "huge.jsonl"
    p.write_text("".join(f'{{"case_id": "c{i}", "score": {1e300 * (i % 3)}}}\n' for i in range(12)))
    q = tmp_path / "huge2.jsonl"
    q.write_text("".join(f'{{"case_id": "c{i}", "score": {-1e300 * (i % 2)}}}\n' for i in range(12)))
    assert main(["compare", str(p), str(q), "--metric", "score"]) == 2
    assert "too large" in capsys.readouterr().err


def test_an_errored_row_with_passing_grades_still_counts_as_failing(tmp_path):
    raw = json.loads(FIXTURE.read_text())
    r1 = raw["results"]["results"][1]          # a passing row, keeps its gradingResult
    r1.update(failureReason=2, error="provider crashed", success=False)
    p = tmp_path / "errored_graded.json"
    p.write_text(json.dumps(raw))
    row = load_rows(p)[1]
    assert row["error"] == 1 and row["fail:no-pii"] == 1 and row["fail:correct"] == 1


def _relabel(tmp_path, name, fn):
    raw = json.loads(FIXTURE.read_text())
    for i, r in enumerate(raw["results"]["results"]):
        fn(i, r)
    p = tmp_path / name
    p.write_text(json.dumps(raw))
    return str(p)


@pytest.mark.parametrize("side", ["before", "after"])
def test_either_side_mixing_prompts_is_refused(tmp_path, capsys, side):
    def fn(i, r):
        if r["provider"]["label"] == side:
            r["prompt"]["label"] = "p1" if i % 2 else "p2"
    p = _relabel(tmp_path, f"mix_{side}.json", fn)
    assert main(["compare", p, p, "--metric", "score",
                 "--where-a", "provider=before", "--where-b", "provider=after"]) == 2
    assert "2 prompts" in capsys.readouterr().err


def test_mixing_providers_is_refused(capsys):
    # no --where: each side holds both providers
    assert main(["compare", str(FIXTURE), str(FIXTURE), "--metric", "score"]) == 2
    assert "2 providers" in capsys.readouterr().err
