"""Keep the published synthetic report reproducible and its story intact."""

import runpy
from pathlib import Path


EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_sample_report_matches_generator():
    generate = runpy.run_path(str(EXAMPLES / "generate_sample_report.py"))["sample_report"]
    report = generate()
    assert report == generate()  # The seed resets even within the same process.
    assert report == (EXAMPLES / "sample_report.md").read_text(encoding="utf-8")


def test_sample_preserves_failures_with_nonconstant_scores(monkeypatch):
    generate = runpy.run_path(str(EXAMPLES / "generate_sample_report.py"))["sample_report"]
    compare = generate.__globals__["compare"]
    results = []

    def capture(*args, **kwargs):
        result = compare(*args, **kwargs)
        results.append(result)
        return result

    monkeypatch.setitem(generate.__globals__, "compare", capture)
    report = generate()
    result = results[0]
    assert result["verdict"] == "BLOCK"
    guard = result["guards"][0]
    assert (guard["events_a"], guard["events_b"], len(guard["new_cases"])) == (0, 15, 5)
    assert result["primary"]["ci"][0] < result["primary"]["ci"][1]
    assert 0.001 < result["primary"]["p"] < 1
    assert "five newly failing tickets" in report
    assert "duplicate payments" in report
