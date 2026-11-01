"""Rebuild the synthetic sample; run from the repository root after installation."""

from pathlib import Path

from swapcheck.compare import Impact, Options, compare
from swapcheck.io import Condition
from swapcheck.report import to_markdown


def sample_report():
    before, after = [], []
    for case in range(12):
        for repeat in range(3):
            common = {"case_id": f"synthetic-ticket-{case + 1:02d}"}
            before.append({**common, "score": 0.9, "duplicate_payment": 0,
                           "unauthorized_cents": 0})
            bad = case < 5
            after.append({**common, "score": 0.92, "duplicate_payment": int(bad),
                          "unauthorized_cents": 2500 if bad else 0})
    result = compare(before, after, Options(
        metric="score", guards=[Condition.parse("duplicate_payment>0")],
        impacts=[Impact.parse("unauthorized_cents:cents")],
        label_a="Synthetic current", label_b="Synthetic candidate"))
    return (
        "# Synthetic customer sample\n\n"
        "All tickets, scores, failures, and dollar amounts below are invented. "
        "This is an illustration, not a customer result or a model benchmark.\n\n"
        "Decision: hold this candidate switch and investigate the five newly failing "
        "tickets. The higher average score does not offset the duplicate payments. "
        "Fix the candidate, then rerun these cases with more repeats before deciding. "
        "These synthetic cases cannot establish production safety.\n\n"
        + to_markdown(result)
    )


if __name__ == "__main__":
    Path(__file__).with_name("sample_report.md").write_text(sample_report(), encoding="utf-8")
