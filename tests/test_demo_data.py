"""The bundled data reproduces the numbers published with it.

Source: github.com/jigonyoo/duplicate-side-effect-desk, reports/model_eval_20260923.jsonl
(MIT, same author), copied byte for byte. The expected values below are the
ones that repository's README publishes; if this test fails, either the copy
changed or swapcheck counts differently from the source.
"""

import hashlib
from importlib import resources

import pytest

from swapcheck.cli import main
from swapcheck.compare import Options, compare
from swapcheck.io import Condition, apply_where, load_rows

SHA256 = "35e0c1e5d0a44954863f4ef3993fc2bbe2e35eed7127ab9cda9f6b4ece203965"


@pytest.fixture(scope="module")
def data():
    path = resources.files("swapcheck") / "data" / "refund_desk_20260923.jsonl"
    with resources.as_file(path) as p:
        assert hashlib.sha256(p.read_bytes()).hexdigest() == SHA256
        yield load_rows(p)


def pick(rows, pop, model):
    return apply_where(rows, [Condition.parse(f"population={pop}"), Condition.parse(f"model={model}")], model)


def opts(**kw):
    return Options(metric="reward", guards=[Condition.parse("duplicate_effects>0")],
                   impacts=["unauthorized_cents:cents"], slice_col="family", **kw)


def test_row_counts(data):
    assert len(data) == 384
    assert len(pick(data, "hints-disabled", "openai/gpt-4.1-mini")) == 96
    assert len(pick(data, "hints-enabled", "anthropic/claude-sonnet-4.5")) == 96


@pytest.mark.parametrize("model, mean, dups, dollars", [
    ("openai/gpt-4.1-mini", 0.959, 14, 708.40),
    ("anthropic/claude-haiku-4.5", 0.984, 3, 150.00),
    ("anthropic/claude-sonnet-4.5", 0.985, 3, 205.00),
])
def test_published_three_model_table(data, model, mean, dups, dollars):
    base = pick(data, "hints-disabled", "anthropic/claude-haiku-4.5")
    res = compare(base, pick(data, "hints-disabled", model), opts())
    assert round(res["primary"]["mean_b"], 3) == mean
    assert res["guards"][0]["events_b"] == dups
    assert res["impacts"][0]["sum_b"] / 100 == pytest.approx(dollars)


def test_published_hints_comparison(data):
    a = pick(data, "hints-disabled", "anthropic/claude-sonnet-4.5")
    b = pick(data, "hints-enabled", "anthropic/claude-sonnet-4.5")
    res = compare(a, b, opts())
    assert res["guards"][0]["events_b"] == 5
    assert res["impacts"][0]["shown_b"] == "$467.40"
    g = res["guards"][0]
    assert g["rose"] and not g["significant"]
    assert g["p"] == pytest.approx(7 / 16)       # 4 cases changed; the rise is within noise
    assert res["verdict"] == "REVIEW"
    assert res["rerun_cases"] == g["changed_cases"] and len(g["changed_cases"]) == 4


def test_model_switch_story(data):
    a = pick(data, "hints-disabled", "anthropic/claude-haiku-4.5")
    b = pick(data, "hints-disabled", "openai/gpt-4.1-mini")
    res = compare(a, b, opts())
    p = res["primary"]
    assert p["n_cases"] == 32
    assert p["ci"][0] < 0 < p["ci"][1]           # the mean alone cannot tell them apart...
    g = res["guards"][0]
    assert (g["events_a"], g["events_b"], g["cases_a"], g["cases_b"]) == (3, 14, 3, 8)
    assert g["p"] == pytest.approx(1 / 64)       # ...the per-case duplicate counts can
    assert res["verdict"] == "BLOCK"
    assert res["impacts"][0]["shown_a"] == "$150.00" and res["impacts"][0]["shown_b"] == "$708.40"
    # cases inside a family are not independent if you treat families as sampled:
    fam = compare(pick(data, "hints-disabled", "anthropic/claude-haiku-4.5"),
                  pick(data, "hints-disabled", "openai/gpt-4.1-mini"), opts(cluster_col="family"))
    assert fam["guards"][0]["p"] > 0.10 and fam["verdict"] == "REVIEW"


def test_demo_command_writes_reports(tmp_path, capsys):
    assert main(["demo", "--out", str(tmp_path)]) == 0
    md = (tmp_path / "model-switch" / "report.md").read_text()
    assert "## Verdict: BLOCK" in md and "3 -> 14 times" in md and "$708.40" in md
    md2 = (tmp_path / "hints-on" / "report.md").read_text()
    assert "## Verdict: REVIEW" in md2 and "Cases to rerun" in md2
