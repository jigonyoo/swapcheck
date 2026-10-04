"""Markdown and JSON reports.

The markdown leads with what a person deciding the switch asks: what broke,
in how many cases, what it cost, and whether that is more than noise. The
statistics come after, for whoever wants to check them.
"""

from __future__ import annotations

import json
import re

__all__ = ["to_markdown", "to_json"]

MAX_LIST = 15


def _n(x, d=4):
    if x is None:
        return "—"
    if isinstance(x, float):
        return f"{x:.{d}f}"
    return str(x)


def _s(x, d=4):
    return "—" if x is None else f"{x:+.{d}f}"


def to_json(res: dict) -> str:
    return json.dumps(res, indent=2, ensure_ascii=False, default=list) + "\n"


def to_markdown(res: dict, title: str | None = None) -> str:
    la, lb = res["labels"]["a"], res["labels"]["b"]
    p = res["primary"]
    acc = res["accounting"]
    out: list[str] = []
    w = out.append
    unit = "cluster" if acc.get("cluster_col") else "case"

    w(f"# {title or f'swapcheck: {la} → {lb}'}\n")
    w(f"## Verdict: {res['verdict']}\n")
    for r in res["reasons"]:
        w(f"- **{r['level']}** — {_md(r['text'])}")
    w("")
    if res.get("rerun_cases"):
        w(f"**Cases to rerun with more repeats:** {_md(', '.join(res['rerun_cases'][:MAX_LIST]))}"
          + (" …" if len(res["rerun_cases"]) > MAX_LIST else ""))
        cmd = _promptfoo_rerun(res)
        if cmd:
            w(f"\n```\n{cmd}\n```\n")
        else:
            w("")

    if res["guards"]:
        w("## What broke\n")
        w(f"| failure | {_md(la)} | {_md(lb)} | cases {_md(la)} → {_md(lb)} | new cases | fixed cases | one-sided p | blocks on |")
        w("|---|---|---|---|---|---|---|---|")
        for g in res["guards"]:
            rule = "any rise" if g["zero_tolerance"] else f"p ≤ {res['guard_alpha']:g}"
            pv = _n(g["p"], 3)
            if g.get("p_adjusted") is not None and g["p_adjusted"] != g["p"]:
                pv += f" (Holm {_n(g['p_adjusted'], 3)})"
            w(f"| `{_md(g['guard'])}` | {g['events_a']} | {g['events_b']} | {g['cases_a']} → {g['cases_b']} | "
              f"{len(g['new_cases'])} | {len(g['resolved_cases'])} | {pv} | {rule} |")
        w("")
        for g in res["guards"]:
            if not g["per_case"]:
                continue
            w(f"<details><summary><code>{_html(g['guard'])}</code> by case</summary>\n")
            w(f"| case | {_md(la)} | {_md(lb)} |")
            w("|---|---|---|")
            for x in g["per_case"]:
                w(f"| {_md(x['case'])} | {x['a']}/{x['reps_a']} | {x['b']}/{x['reps_b']} |")
            w("\n</details>\n")

    if res["impacts"]:
        w("## Cost of the failures\n")
        w(f"| column | {_md(la)} total | {_md(lb)} total | {_md(la)} per run | {_md(lb)} per run |")
        w("|---|---|---|---|---|")
        for im in res["impacts"]:
            w(f"| `{_md(im['column'])}` | {im['shown_a']} | {im['shown_b']} | "
              f"{im['shown_per_row_a']} | {im['shown_per_row_b']} |")
        w("\nOver the paired cases, every repeat included. Higher is worse."
          + ("" if acc["equal_repeats"] else
             " The two runs have different numbers of repeats, so compare the per-run column.")
          + "\n")

    if res["perf"]:
        w("## Latency and cost per row\n")
        w(f"| | column | {_md(la)} mean | {_md(lb)} mean | {_md(la)} p50 / p95 | {_md(lb)} p50 / p95 | {_md(la)} total | {_md(lb)} total |")
        w("|---|---|---|---|---|---|---|---|")
        for kind, d in res["perf"].items():
            a, b = d["a"], d["b"]
            w(f"| {kind} | `{_md(d['column'])}` | {_n(a['mean'], 3)} | {_n(b['mean'], 3)} | "
              f"{_n(a['p50'], 3)} / {_n(a['p95'], 3)} | {_n(b['p50'], 3)} / {_n(b['p95'], 3)} | "
              f"{_n(a['total'], 3)} | {_n(b['total'], 3)} |")
        w("")

    w(f"## Cases that got worse on {_md(lb)}: {len(res['regressed'])}\n")
    if res["regressed"]:
        w(f"| case | {_md(la)} mean | {_md(lb)} mean | worse on every repeat? | {_md(la)} values | {_md(lb)} values |")
        w("|---|---|---|---|---|---|")
        for d in res["regressed"][:MAX_LIST]:
            w(f"| {_md(d['case'])} | {_n(d['a'], 3)} | {_n(d['b'], 3)} | {'yes' if d['every_repeat'] else 'no'} | "
              f"{_vals(d['values_a'])} | {_vals(d['values_b'])} |")
        if len(res["regressed"]) > MAX_LIST:
            w(f"\n…and {len(res['regressed']) - MAX_LIST} more in the JSON report.")
        w("")
    w(f"Cases that got better on {_md(lb)}: {len(res['improved'])}.\n")

    if res["slices"]:
        w("## By slice\n")
        gh = "".join(f" | `{_md(g['guard'])}` {_md(la)} → {_md(lb)}" for g in res["slices"][0]["guards"])
        w(f"| slice | cases | {_md(la)} | {_md(lb)} | change{gh} |")
        w("|---|---|---|---|---" + "|---" * len(res["slices"][0]["guards"]) + "|")
        for s in res["slices"]:
            gs = "".join(f" | {g['a']} → {g['b']}" for g in s["guards"])
            small = " ⚠" if s["n_cases"] < 10 else ""
            w(f"| {_md(s['slice'])}{small} | {s['n_cases']} | {_n(s['mean_a'], 3)} | {_n(s['mean_b'], 3)} | "
              f"{_s(s['diff'], 3)}{gs} |")
        w("\n⚠ fewer than 10 cases: a description, not a finding.\n")

    w("## The statistics\n")
    conf = round((1 - res["alpha"]) * 100)
    w(f"| | {_md(la)} | {_md(lb)} | change | {conf}% interval | p | rough smallest detectable change |")
    w("|---|---|---|---|---|---|---|")
    ci = p.get("ci")
    w(f"| `{_md(p['metric'])}` (mean over {p['n_cases']} cases) | {_n(p['mean_a'])} | {_n(p['mean_b'])} | "
      f"{_s(p['diff'])} | {('[' + _s(ci[0]) + ', ' + _s(ci[1]) + ']') if ci else '—'} | "
      f"{_n(p['p'], 3)} | {_n(p['mde'], 3)} |")
    w("")
    notes = [
        "Each case's repeats are averaged first; the two runs are then compared case by case "
        "(paired t on the per-case differences"
        + (f", cluster-robust by `{acc['cluster_col']}` with {p.get('n_clusters')} clusters"
           if acc.get("cluster_col") else "") + ").",
        "The smallest detectable change is the change this sample would catch 80% of the time, "
        "computed from this sample's own spread. It is rough: with few cases or scores bunched "
        "near the top it understates the real figure.",
    ]
    if res["guards"]:
        notes.append(
            "Guard p-values ask one question: if the two setups behaved the same, how often would "
            f"the failure go up at least this much? Exact test: under that assumption each "
            f"{unit}'s difference in event counts is equally likely to point either way, and p is "
            "the share of those sign assignments that rise at least as much as observed. A large "
            "p means the data cannot tell the setups apart, not that they are the same."
            + ("" if acc["equal_repeats"] else
               " Where repeat counts differ for a case, the test uses only the first k rows of "
               "that case on each side (k = the smaller count); the counts in the tables are the "
               "full ones.")
            + (" With several guards, p is Holm-adjusted before it is compared with the limit."
               if sum(1 for g in res["guards"] if not g["zero_tolerance"]) > 1 else ""))
    for t in notes:
        w(t + "\n")

    n = res["noise"]
    w("## Repeat noise\n")
    w(f"Cases whose score differed between repeats of the *same* setup: "
      f"{len(n['unstable_a'])} of {n['multi_repeat_cases_a']} in {_md(la)}, "
      f"{len(n['unstable_b'])} of {n['multi_repeat_cases_b']} in {_md(lb)} "
      "(counting only cases run more than once). "
      "A case that disagrees with itself cannot tell you much about a switch.\n")

    w("## What was compared\n")
    if "rows_in_file_a" in acc:
        w(f"- rows in the files: {_md(la)} {acc['rows_in_file_a']}, {_md(lb)} {acc['rows_in_file_b']}")
        for side, key in ((la, "where_a"), (lb, "where_b")):
            if acc.get(key):
                w(f"- filter for {_md(side)}: " + " and ".join(f"`{_md(c)}`" for c in acc[key]))
    w(f"- rows kept: {_md(la)} {acc['rows_a']}, {_md(lb)} {acc['rows_b']}")
    w(f"- cases: {_md(la)} {acc['cases_a']}, {_md(lb)} {acc['cases_b']}, paired {acc['cases_paired']} "
      f"(rows used: {acc['rows_a_paired']} and {acc['rows_b_paired']})")
    w(f"- repeats per case: {_md(la)} {acc['repeats_a']}, {_md(lb)} {acc['repeats_b']}")
    if acc["only_a"] or acc["only_b"]:
        w(f"- only in {_md(la)}: {_md(', '.join(acc['only_a'][:MAX_LIST])) or 'none'}")
        w(f"- only in {_md(lb)}: {_md(', '.join(acc['only_b'][:MAX_LIST])) or 'none'}")
    w("")
    w("_swapcheck compares two recorded runs. It does not run models, and it cannot tell you "
      "whether your test cases look like production traffic._\n")
    return "\n".join(out)


def _promptfoo_rerun(res: dict) -> str | None:
    """A promptfoo command that reruns only the cases worth a second look.

    Only possible when every case id is a promptfoo test description
    (``--filter-pattern`` matches the description with a regular expression).
    """
    if res.get("source_format") != "promptfoo":
        return None
    cases = res.get("rerun_cases") or []
    if not cases or any(c.startswith("vars:") or "[vars:" in c or "'" in c for c in cases):
        return None
    pat = "^(" + "|".join(re.escape(c) for c in cases) + ")$"
    return f"promptfoo eval --repeat 10 --filter-pattern '{pat}'"


def _vals(xs):
    s = ", ".join(f"{x:g}" for x in xs[:6])
    return s + ("…" if len(xs) > 6 else "")


def _md(s) -> str:
    """Text from the data, safe inside a markdown table cell."""
    return str(s).replace("|", "\\|").replace("\n", " ")


def _html(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
