"""Command line: ``swapcheck compare`` and ``swapcheck demo``."""

from __future__ import annotations

import argparse
import sys
from importlib import resources
from pathlib import Path

from . import __version__
from .compare import LEVELS, Impact, Options, compare
from .io import Condition, InputError, apply_where, load_rows
from .report import to_json, to_markdown

EXIT_OK, EXIT_INPUT, EXIT_REVIEW, EXIT_BLOCK = 0, 2, 3, 4


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="swapcheck",
        description="Before you switch models or ship a prompt change: compare two recorded "
                    "eval runs case by case, and block when a failure you named rises by more "
                    "than chance.")
    ap.add_argument("--version", action="version", version=f"swapcheck {__version__}")
    sub = ap.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("compare", help="compare a before run (A) with an after run (B)")
    c.add_argument("before", help="results of the current model/prompt (JSONL, CSV or promptfoo JSON)")
    c.add_argument("after", help="results of the candidate (may be the same file with different --where-b)")
    c.add_argument("--metric", required=True, help="numeric column to average, e.g. score")
    c.add_argument("--lower-is-better", action="store_true", help="the metric is an error or a cost")
    c.add_argument("--case-col", default="case_id", help="column that identifies a test case (default: case_id)")
    c.add_argument("--guard", action="append", default=[], metavar="COND",
                   help="a failure counted on its own, e.g. 'duplicate_effects>0'. BLOCK when it "
                        "rises by more than chance would explain, REVIEW when the rise could be "
                        "chance. Repeatable")
    c.add_argument("--zero-tolerance", action="append", default=[], metavar="COND",
                   help="a guard where any rise blocks, noise or not, e.g. 'fail:no-pii>0'. Repeatable")
    c.add_argument("--guard-alpha", type=float, default=0.10, metavar="P",
                   help="one-sided p at or below which a guard rise blocks, after Holm "
                        "across guards (default 0.10)")
    c.add_argument("--impact", action="append", default=[], metavar="COL[:UNIT]",
                   help="a column to total for both runs, higher is worse, e.g. "
                        "'unauthorized_cents:cents'. UNIT: raw (default), cents, usd. Repeatable")
    c.add_argument("--cluster", dest="cluster_col", metavar="COL",
                   help="cases that share this column are not independent (same template, same "
                        "conversation): test at the cluster level")
    c.add_argument("--slice", dest="slice_col", metavar="COL", help="group cases by this column")
    c.add_argument("--latency", metavar="COL", help="latency column (p50/p95/mean/total)")
    c.add_argument("--cost", metavar="COL", help="cost column (p50/p95/mean/total)")
    c.add_argument("--where-a", action="append", default=[], metavar="COND",
                   help="keep only rows of BEFORE matching, e.g. 'model=gpt-4.1-mini'. Repeatable")
    c.add_argument("--where-b", action="append", default=[], metavar="COND", help="same, for AFTER")
    c.add_argument("--label-a", help="name for the before run in the report")
    c.add_argument("--label-b", help="name for the after run in the report")
    c.add_argument("--format", default="auto", choices=["auto", "jsonl", "csv", "promptfoo"])
    c.add_argument("--alpha", type=float, default=0.05, help="for intervals and p-values (default 0.05)")
    c.add_argument("--max-drop", type=float, metavar="X",
                   help="largest drop in the metric you accept; REVIEW if the interval allows more")
    c.add_argument("--out", metavar="DIR", help="write report.md and report.json here")
    c.add_argument("--json", action="store_true", help="print the JSON report instead of markdown")
    c.add_argument("--fail-on", default="block", choices=["block", "review", "never"],
                   help="exit non-zero at this verdict or worse (default: block)")

    d = sub.add_parser("demo", help="run on the bundled refund-desk measurements")
    d.add_argument("--out", metavar="DIR", default="swapcheck-demo", help="where to write the reports")
    return ap


def _label(path: str, conds: list[Condition]) -> str:
    if conds:
        return " & ".join(f"{c.value}" for c in conds)
    return Path(path).stem


def _exit_code(verdict: str, fail_on: str) -> int:
    if fail_on == "never":
        return EXIT_OK
    threshold = LEVELS["BLOCK"] if fail_on == "block" else LEVELS["REVIEW"]
    if LEVELS[verdict] < threshold:
        return EXIT_OK
    return EXIT_BLOCK if verdict == "BLOCK" else EXIT_REVIEW


def _one_setup_per_case(rows: list[dict], label: str, flag: str) -> None:
    """promptfoo files hold every provider and prompt; one side must be one setup.

    Without this, rows from two prompts (or two providers) of the same test
    would be averaged together as if they were repeats.
    """
    if not rows or not all(r.get("_format") == "promptfoo" for r in rows):
        return
    for col in ("provider", "prompt"):
        seen: dict[str, set] = {}
        for r in rows:
            seen.setdefault(r["case_id"], set()).add(r.get(col))
        for case, vals in seen.items():
            if len(vals) > 1:
                shown = ", ".join(sorted(map(str, vals))[:4])
                raise InputError(f"{label}: case {case!r} has rows from {len(vals)} {col}s "
                                 f"({shown}); pick one with {flag} {col}=...")


def _write_stdout(text: str) -> None:
    """Write UTF-8 even when the console or redirect says otherwise (Windows cp1252)."""
    enc = (getattr(sys.stdout, "encoding", None) or "").lower().replace("-", "")
    if enc == "utf8" or not hasattr(sys.stdout, "buffer"):
        sys.stdout.write(text)
    else:
        sys.stdout.flush()
        sys.stdout.buffer.write(text.encode("utf-8"))
        sys.stdout.buffer.flush()


def run_compare(args) -> int:
    where_a = [Condition.parse(s) for s in args.where_a]
    where_b = [Condition.parse(s) for s in args.where_b]
    label_a = args.label_a or _label(args.before, where_a)
    label_b = args.label_b or _label(args.after, where_b)
    if label_a == label_b:
        label_a, label_b = f"{label_a} (A)", f"{label_b} (B)"
    all_a = load_rows(args.before, args.format)
    all_b = load_rows(args.after, args.format)
    rows_a = apply_where(all_a, where_a, label_a)
    rows_b = apply_where(all_b, where_b, label_b)
    _one_setup_per_case(rows_a, label_a, "--where-a")
    _one_setup_per_case(rows_b, label_b, "--where-b")
    if not 0 < args.alpha < 1:
        raise InputError("--alpha must be between 0 and 1")
    if args.max_drop is not None and args.max_drop < 0:
        raise InputError("--max-drop must be >= 0")
    if not 0 < args.guard_alpha < 1:
        raise InputError("--guard-alpha must be between 0 and 1")
    opt = Options(
        metric=args.metric, case_col=args.case_col, higher_is_better=not args.lower_is_better,
        guards=[Condition.parse(g) for g in args.guard],
        zero_tolerance=[Condition.parse(g) for g in args.zero_tolerance],
        guard_alpha=args.guard_alpha, impacts=[Impact.parse(x) for x in args.impact],
        slice_col=args.slice_col, cluster_col=args.cluster_col, latency_col=args.latency, cost_col=args.cost,
        alpha=args.alpha, max_drop=args.max_drop, label_a=label_a, label_b=label_b)
    res = compare(rows_a, rows_b, opt)
    if all(r.get("_format") == "promptfoo" for r in rows_a + rows_b):
        res["source_format"] = "promptfoo"
    res["accounting"]["rows_in_file_a"] = len(all_a)
    res["accounting"]["rows_in_file_b"] = len(all_b)
    res["accounting"]["where_a"] = [c.text for c in where_a]
    res["accounting"]["where_b"] = [c.text for c in where_b]
    md, js = to_markdown(res), to_json(res)
    if args.out:
        out = Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / "report.md").write_text(md, encoding="utf-8")
        (out / "report.json").write_text(js, encoding="utf-8")
        print(f"swapcheck: {res['verdict']} — {res['reasons'][0]['text']}", file=sys.stderr)
        print(f"wrote {out / 'report.md'} and {out / 'report.json'}", file=sys.stderr)
    else:
        _write_stdout(js if args.json else md)
    return _exit_code(res["verdict"], args.fail_on)


DEMOS = [
    ("model-switch", "Model switch: claude-haiku-4.5 -> gpt-4.1-mini",
     ["--where-a", "population=hints-disabled", "--where-a", "model=anthropic/claude-haiku-4.5",
      "--where-b", "population=hints-disabled", "--where-b", "model=openai/gpt-4.1-mini",
      "--label-a", "claude-haiku-4.5", "--label-b", "gpt-4.1-mini"]),
    ("hints-on", "Same model, hints off -> on: claude-sonnet-4.5 (a rise that could be chance)",
     ["--where-a", "population=hints-disabled", "--where-a", "model=anthropic/claude-sonnet-4.5",
      "--where-b", "population=hints-enabled", "--where-b", "model=anthropic/claude-sonnet-4.5",
      "--label-a", "sonnet-4.5 hints-disabled", "--label-b", "sonnet-4.5 hints-enabled"]),
]
DEMO_COMMON = ["--metric", "reward", "--guard", "duplicate_effects>0",
               "--impact", "unauthorized_cents:cents", "--slice", "family",
               "--fail-on", "never"]


def run_demo(args) -> int:
    data = resources.files("swapcheck") / "data" / "refund_desk_20260923.jsonl"
    with resources.as_file(data) as path:
        base = Path(args.out)
        for slug, title, extra in DEMOS:
            out = base / slug
            ns = _parser().parse_args(["compare", str(path), str(path), *DEMO_COMMON, *extra,
                                       "--out", str(out)])
            print(f"\n== {title}", file=sys.stderr)
            run_compare(ns)
    print(f"\nOpen {base}/model-switch/report.md first.", file=sys.stderr)
    return EXIT_OK


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.cmd == "compare":
            return run_compare(args)
        return run_demo(args)
    except InputError as e:
        print(f"swapcheck: input error: {e}", file=sys.stderr)
        return EXIT_INPUT
    except (ArithmeticError, OverflowError) as e:
        print(f"swapcheck: input error: numbers too large to compare ({e})", file=sys.stderr)
        return EXIT_INPUT


if __name__ == "__main__":
    raise SystemExit(main())
