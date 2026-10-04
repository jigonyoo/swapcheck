"""The comparison itself: before (A) vs after (B), paired by case."""

from __future__ import annotations

from dataclasses import dataclass, field

from .io import Condition, InputError, number
import math

from .stats import holm, paired_mean_diff, percentile, same, sign_flip_pvalue

__all__ = ["Options", "Impact", "compare", "LEVELS", "MIN_CASES"]

LEVELS = {"OK": 0, "REVIEW": 1, "BLOCK": 2}
MIN_CASES = 10          # below this, the average is described but not judged

UNITS = {"raw": (1.0, ""), "cents": (100.0, "$"), "usd": (1.0, "$")}


@dataclass
class Impact:
    """A column summed for both runs (money, records, messages...). Higher is worse."""
    column: str
    unit: str = "raw"

    @classmethod
    def parse(cls, text: str) -> "Impact":
        col, _, unit = text.partition(":")
        unit = unit.strip() or "raw"
        if not col.strip():
            raise InputError(f"--impact {text!r}: no column")
        if unit not in UNITS:
            raise InputError(f"--impact {text!r}: unit must be one of {', '.join(UNITS)}")
        return cls(col.strip(), unit)

    def show(self, x: float) -> str:
        div, sym = UNITS[self.unit]
        return f"{sym}{x / div:,.2f}" if sym else f"{x:g}"


@dataclass
class Options:
    metric: str
    case_col: str = "case_id"
    higher_is_better: bool = True
    guards: list[Condition] = field(default_factory=list)
    zero_tolerance: list[Condition] = field(default_factory=list)
    guard_alpha: float = 0.10
    impacts: list = field(default_factory=list)          # Impact or "col[:unit]"
    slice_col: str | None = None
    cluster_col: str | None = None
    latency_col: str | None = None
    cost_col: str | None = None
    alpha: float = 0.05
    max_drop: float | None = None
    label_a: str = "A"
    label_b: str = "B"


def _by_case(rows: list[dict], case_col: str, label: str) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        if case_col not in r or r[case_col] in (None, ""):
            raise InputError(f"{label} {r.get('_src', '')}: no case id in column {case_col!r}")
        out.setdefault(str(r[case_col]), []).append(r)
    return out


def _num(r: dict, col: str, label: str) -> float:
    where = f"{label} {r.get('_src', '')}: "
    if col not in r:
        raise InputError(f"{where}no column {col!r}")
    return number(r[col], col, where)


def _mean(xs):
    return math.fsum(xs) / len(xs) if xs else None


def compare(rows_a: list[dict], rows_b: list[dict], opt: Options) -> dict:
    if not rows_a:
        raise InputError(f"{opt.label_a}: no rows left after filtering")
    if not rows_b:
        raise InputError(f"{opt.label_b}: no rows left after filtering")
    A = _by_case(rows_a, opt.case_col, opt.label_a)
    B = _by_case(rows_b, opt.case_col, opt.label_b)
    paired = sorted(set(A) & set(B))
    only_a = sorted(set(A) - set(B))
    only_b = sorted(set(B) - set(A))

    def metric_of(r, label):
        return _num(r, opt.metric, label)

    # read every metric value on every row, paired or not: bad data is an error
    vals_a = {c: [metric_of(r, opt.label_a) for r in rs] for c, rs in A.items()}
    vals_b = {c: [metric_of(r, opt.label_b) for r in rs] for c, rs in B.items()}

    reps_a = {c: len(A[c]) for c in paired}
    reps_b = {c: len(B[c]) for c in paired}
    equal_reps = all(reps_a[c] == reps_b[c] for c in paired)

    accounting = {
        "rows_a": len(rows_a), "rows_b": len(rows_b),
        "cases_a": len(A), "cases_b": len(B), "cases_paired": len(paired),
        "rows_a_paired": sum(reps_a.values()), "rows_b_paired": sum(reps_b.values()),
        "only_a": only_a, "only_b": only_b,
        "repeats_a": sorted(set(reps_a.values())), "repeats_b": sorted(set(reps_b.values())),
        "equal_repeats": equal_reps,
    }

    clusters = None
    if opt.cluster_col:
        clusters = [_one_value(A[c] + B[c], opt.cluster_col, c) for c in paired]
    accounting["cluster_col"] = opt.cluster_col

    ma = [_mean(vals_a[c]) for c in paired]
    mb = [_mean(vals_b[c]) for c in paired]
    primary = paired_mean_diff(ma, mb, alpha=opt.alpha, clusters=clusters)
    primary["metric"] = opt.metric
    primary["higher_is_better"] = opt.higher_is_better

    sign = 1.0 if opt.higher_is_better else -1.0

    # --- guards ---
    # A guard is a failure counted on its own. Its test is one-sided (did it go
    # UP on B?), exact, on per-case event counts. When repeat counts differ for
    # a case, the test uses only the first k rows of that case on each side
    # (k = the smaller count), so both sides have the same chance of an event
    # under "no change"; the counts shown are always the full ones.
    strict_texts = {g.text for g in opt.zero_tolerance}
    all_guards = list(opt.guards) + [g for g in opt.zero_tolerance
                                     if g.text not in {x.text for x in opt.guards}]
    guards = []
    for g in all_guards:
        flags_a = {c: [g.test(r, f"{opt.label_a} {r.get('_src', '')}: ") for r in A[c]] for c in paired}
        flags_b = {c: [g.test(r, f"{opt.label_b} {r.get('_src', '')}: ") for r in B[c]] for c in paired}
        ca = {c: sum(flags_a[c]) for c in paired}
        cb = {c: sum(flags_b[c]) for c in paired}
        ev_a, ev_b = sum(ca.values()), sum(cb.values())
        aff_a = {c for c in paired if ca[c] > 0}
        aff_b = {c for c in paired if cb[c] > 0}
        rate_a = ev_a / max(1, accounting["rows_a_paired"])
        rate_b = ev_b / max(1, accounting["rows_b_paired"])
        if equal_reps:
            ta, tb = ca, cb
            rose = ev_b > ev_a
        else:
            k = {c: min(reps_a[c], reps_b[c]) for c in paired}
            ta = {c: sum(flags_a[c][:k[c]]) for c in paired}
            tb = {c: sum(flags_b[c][:k[c]]) for c in paired}
            rose = sum(tb.values()) > sum(ta.values())
        diffs = [tb[c] - ta[c] for c in paired]
        unit_diffs = diffs
        if clusters is not None:
            agg: dict = {}
            for lab, d in zip(clusters, diffs):
                agg[lab] = agg.get(lab, 0) + d
            unit_diffs = list(agg.values())
        p = sign_flip_pvalue(unit_diffs, alternative="greater")
        changed = sum(1 for x in unit_diffs if x != 0)
        test = ("exact one-sided sign-flip test on per-"
                + ("cluster" if clusters is not None else "case") + " event counts"
                + ("" if equal_reps else ", first k repeats per case where repeat counts differ"))
        per_case = [
            {"case": c, "a": ca[c], "b": cb[c], "reps_a": reps_a[c], "reps_b": reps_b[c]}
            for c in paired if ca[c] or cb[c]
        ]
        per_case.sort(key=lambda x: (-(x["b"] - x["a"]), x["case"]))
        guards.append({
            "guard": g.text, "zero_tolerance": g.text in strict_texts,
            "events_a": ev_a, "events_b": ev_b,
            "rate_a": rate_a, "rate_b": rate_b,
            "compared_a": sum(ta.values()), "compared_b": sum(tb.values()),
            "cases_a": len(aff_a), "cases_b": len(aff_b),
            "new_cases": sorted(aff_b - aff_a), "resolved_cases": sorted(aff_a - aff_b),
            "changed_cases": sorted(c for c in paired if ca[c] != cb[c]),
            "p": p, "test": test, "rose": rose, "per_case": per_case,
            "units_changed": changed,
            "min_possible_p": 1.0 / 2 ** changed if changed else 1.0,
        })
    tested = [x for x in guards if not x["zero_tolerance"]]
    for x, padj in zip(tested, holm([x["p"] for x in tested])):
        x["p_adjusted"] = padj
    for x in guards:
        x.setdefault("p_adjusted", None)
        x["significant"] = (x["p_adjusted"] is not None and x["rose"]
                            and x["p_adjusted"] <= opt.guard_alpha)

    # --- impacts (money, records, anything you want summed) ---
    impacts = []
    for im in opt.impacts:
        im = im if isinstance(im, Impact) else Impact.parse(im)
        xa = {c: [_num(r, im.column, opt.label_a) for r in A[c]] for c in paired}
        xb = {c: [_num(r, im.column, opt.label_b) for r in B[c]] for c in paired}
        sa = math.fsum(v for c in paired for v in xa[c])
        sb = math.fsum(v for c in paired for v in xb[c])
        # per run: each case's own per-run average, averaged over cases, so a
        # different number of repeats in some cases cannot move it by itself
        pa = _mean([_mean(xa[c]) for c in paired]) if paired else None
        pb = _mean([_mean(xb[c]) for c in paired]) if paired else None
        impacts.append({"column": im.column, "unit": im.unit, "sum_a": sa, "sum_b": sb,
                        "shown_a": im.show(sa), "shown_b": im.show(sb),
                        "per_row_a": pa, "per_row_b": pb,
                        "shown_per_row_a": im.show(pa) if pa is not None else "—",
                        "shown_per_row_b": im.show(pb) if pb is not None else "—"})

    # --- per-case changes ---
    changes = []
    scale = max((abs(v) for v in ma + mb), default=0.0)
    for c, x, y in zip(paired, ma, mb):
        if not same(x, y, scale):
            worse = sign * (y - x) < 0
            if worse:
                consistent = (min(vals_a[c]) > max(vals_b[c])) if opt.higher_is_better \
                    else (max(vals_a[c]) < min(vals_b[c]))
            else:
                consistent = (max(vals_a[c]) < min(vals_b[c])) if opt.higher_is_better \
                    else (min(vals_a[c]) > max(vals_b[c]))
            changes.append({"case": c, "a": x, "b": y, "worse": worse,
                            "every_repeat": consistent,
                            "values_a": vals_a[c], "values_b": vals_b[c]})
    changes.sort(key=lambda d: (sign * (d["b"] - d["a"]), d["case"]))
    regressed = [d for d in changes if d["worse"]]
    improved = [d for d in changes if not d["worse"]]

    # --- repeat noise ---
    def unstable(vals):
        return sorted(c for c in paired if len(vals[c]) > 1 and len(set(vals[c])) > 1)

    noise = {
        "unstable_a": unstable(vals_a), "unstable_b": unstable(vals_b),
        "multi_repeat_cases_a": sum(1 for c in paired if len(vals_a[c]) > 1),
        "multi_repeat_cases_b": sum(1 for c in paired if len(vals_b[c]) > 1),
    }

    # --- slices ---
    slices = []
    if opt.slice_col:
        groups: dict[str, list[int]] = {}
        for i, c in enumerate(paired):
            groups.setdefault(_one_value(A[c] + B[c], opt.slice_col, c), []).append(i)
        for name in sorted(groups):
            idx = groups[name]
            res = paired_mean_diff([ma[i] for i in idx], [mb[i] for i in idx], alpha=opt.alpha)
            gsl = []
            for gd in guards:
                cs = {paired[i] for i in idx}
                gsl.append({"guard": gd["guard"],
                            "a": sum(x["a"] for x in gd["per_case"] if x["case"] in cs),
                            "b": sum(x["b"] for x in gd["per_case"] if x["case"] in cs)})
            slices.append({"slice": name, "n_cases": len(idx), "mean_a": res["mean_a"],
                           "mean_b": res["mean_b"], "diff": res["diff"], "ci": res["ci"],
                           "guards": gsl})

    # --- latency / cost ---
    perf = {}
    for kind, col in (("latency", opt.latency_col), ("cost", opt.cost_col)):
        if not col:
            continue
        xa = [_num(r, col, opt.label_a) for c in paired for r in A[c]]
        xb = [_num(r, col, opt.label_b) for c in paired for r in B[c]]
        perf[kind] = {
            "column": col,
            "a": {"mean": _mean(xa), "p50": percentile(xa, 50), "p95": percentile(xa, 95), "total": math.fsum(xa)},
            "b": {"mean": _mean(xb), "p50": percentile(xb, 50), "p95": percentile(xb, 95), "total": math.fsum(xb)},
        }

    verdict, reasons = _verdict(opt, accounting, primary, guards, impacts, regressed)
    rerun = sorted({c for gd in guards
                    if gd["rose"] and not gd["significant"] and not gd["zero_tolerance"]
                    for c in gd["changed_cases"]})
    return {
        "rerun_cases": rerun,
        "guard_alpha": opt.guard_alpha,
        "labels": {"a": opt.label_a, "b": opt.label_b},
        "verdict": verdict, "reasons": reasons,
        "accounting": accounting, "primary": primary, "guards": guards,
        "impacts": impacts, "regressed": regressed, "improved": improved,
        "noise": noise, "slices": slices, "perf": perf,
        "alpha": opt.alpha, "max_drop": opt.max_drop,
    }


def _one_value(rows: list[dict], col: str, case: str) -> str:
    names = {str(r.get(col)) for r in rows}
    if any(col not in r for r in rows):
        raise InputError(f"case {case!r}: some rows have no column {col!r}")
    if len(names) != 1:
        raise InputError(f"case {case!r} has more than one {col!r}: {sorted(names)}")
    return names.pop()


def _list(xs, n=5):
    return ", ".join(xs[:n]) + (f" and {len(xs) - n} more" if len(xs) > n else "")


def _verdict(opt: Options, acc: dict, primary: dict, guards: list[dict],
             impacts: list[dict], regressed: list[dict]):
    reasons: list[tuple[str, str]] = []
    la, lb = opt.label_a, opt.label_b
    n = acc["cases_paired"]
    unit = "cluster" if acc.get("cluster_col") else "case"

    for g in guards:
        head = (f"`{g['guard']}` happened {g['events_a']} -> {g['events_b']} times "
                f"(in {g['cases_a']} -> {g['cases_b']} of {n} cases)")
        if not acc["equal_repeats"]:
            head += (f"; on the first k runs of each case, where both sides have a run: "
                     f"{g['compared_a']} -> {g['compared_b']}")
        if g["rose"] and g["zero_tolerance"]:
            reasons.append(("BLOCK", f"{head}. Marked zero-tolerance: any rise blocks."))
        elif g["rose"] and g["significant"]:
            adj = "" if g["p_adjusted"] == g["p"] else f", {g['p_adjusted']:.3f} after Holm across guards"
            reasons.append(("BLOCK",
                f"{head}. Unlikely to be chance: if the two setups behaved the same, a rise "
                f"this large would come up with p = {g['p']:.3f}{adj} (blocks at <= {opt.guard_alpha:g})."))
        elif g["rose"]:
            rerun = (f" Rerun the {len(g['changed_cases'])} case(s) that changed with more "
                     f"repeats: {_list(g['changed_cases'])}.")
            if g["min_possible_p"] > opt.guard_alpha:
                reasons.append(("REVIEW",
                    f"{head}. Only {g['units_changed']} {unit}(s) changed, too few to tell this "
                    f"from chance (no p below {g['min_possible_p']:.3f} was possible). That is not "
                    "evidence that nothing changed." + rerun))
            else:
                adj = ("" if g["p_adjusted"] == g["p"]
                       else f", {g['p_adjusted']:.3f} after Holm across guards")
                reasons.append(("REVIEW",
                    f"{head}. Could be chance: if the two setups behaved the same, a rise this "
                    f"large would still come up with p = {g['p']:.3f}{adj}. That is not evidence "
                    "that nothing changed." + rerun))
        elif g["new_cases"]:
            reasons.append(("REVIEW",
                f"{head}: not up in total, but new in {len(g['new_cases'])} case(s) where {la} "
                f"had none: {_list(g['new_cases'])}."))
        else:
            reasons.append(("OK", f"{head}: not up, no new cases."))

    for im in impacts:
        if acc["equal_repeats"]:
            rose = im["sum_b"] > im["sum_a"] and not same(im["sum_a"], im["sum_b"])
            what = f"total {im['shown_a']} -> {im['shown_b']}"
        else:   # different numbers of runs: compare per run, not totals
            rose = (im["per_row_b"] > im["per_row_a"]
                    and not same(im["per_row_a"], im["per_row_b"]))
            what = (f"per run {im['shown_per_row_a']} -> {im['shown_per_row_b']} "
                    f"(totals {im['shown_a']} -> {im['shown_b']} over different numbers of runs)")
        if rose:
            reasons.append(("REVIEW",
                f"`{im['column']}` rose: {what}. Not tested on its own; the guards say whether "
                "the failures behind it could be chance."))
        else:
            reasons.append(("OK", f"`{im['column']}`: {what}."))

    if acc["only_a"] or acc["only_b"]:
        reasons.append(("REVIEW",
            f"{len(acc['only_a'])} case(s) only in {la} and {len(acc['only_b'])} only in {lb}; "
            "they are left out of every paired number. A case missing from the after run can "
            "mean it crashed."))

    m = f"`{opt.metric}`"
    avg = (f"Average {m}: {primary['mean_a']:.3f} -> {primary['mean_b']:.3f} "
           f"({_fmt(primary['diff'])})") if primary.get("diff") is not None else f"Average {m}: no paired cases"
    if n >= MIN_CASES and acc.get("cluster_col") and primary.get("ci") is None:
        reasons.append(("REVIEW", f"{avg}. Only {primary.get('n_clusters')} cluster(s) in "
                        f"`{acc['cluster_col']}`: a cluster-level interval needs at least 2."))
    elif primary.get("ci") is None or n < MIN_CASES:
        reasons.append(("REVIEW", f"{avg}. Only {n} paired case(s): too few to judge the average "
                        f"(swapcheck needs at least {MIN_CASES})."))
    else:
        s = 1.0 if opt.higher_is_better else -1.0
        lo = min(s * primary["ci"][0], s * primary["ci"][1])
        hi = max(s * primary["ci"][0], s * primary["ci"][1])
        conf = round((1 - opt.alpha) * 100)
        span = f"{conf}% interval {_fmt(primary['ci'][0])} to {_fmt(primary['ci'][1])}"
        mde = primary.get("mde")
        see = (f"; this sample only reliably sees changes larger than about {mde:.3f}"
               if mde is not None else "; the per-case differences do not vary, so the "
               "interval says little")
        worse_cases = f" {len(regressed)} case(s) got worse." if regressed else ""
        if hi < 0:
            reasons.append(("BLOCK", f"{avg}: worse on {lb} ({span}, p = {primary['p']:.3f}).{worse_cases}"))
        elif opt.max_drop is not None and lo < -opt.max_drop:
            reasons.append(("REVIEW",
                f"{avg}: cannot rule out a drop larger than the {opt.max_drop:g} you accept "
                f"({span}).{worse_cases}"))
        elif lo > 0:
            reasons.append(("OK", f"{avg}: better on {lb} ({span}, p = {primary['p']:.3f})."))
        else:
            tail = (f" Within the {opt.max_drop:g} you accept." if opt.max_drop is not None
                    else " Set --max-drop to say how much loss you accept.")
            reasons.append(("OK", f"{avg}: within noise ({span}{see}).{tail}"))

    level = max((LEVELS[lvl] for lvl, _ in reasons), default=0)
    verdict = [k for k, v in LEVELS.items() if v == level][0]
    order = {"BLOCK": 0, "REVIEW": 1, "OK": 2}
    reasons.sort(key=lambda x: order[x[0]])
    return verdict, [{"level": lvl, "text": t} for lvl, t in reasons]


def _fmt(x: float) -> str:
    return f"{x:+.3f}"
