"""Small, dependency-free statistics used by swapcheck.

Everything here is deliberately plain: a paired t interval on per-case means
(optionally cluster-robust), an exact sign-flip (permutation) test on per-case
integer counts, and Holm's adjustment. The tests check the sign-flip test and
Holm against brute force and hand values everywhere; with SciPy and errorbars
installed they also check the t distribution, the paired t and the
cluster-robust SE against those libraries.
"""

from __future__ import annotations

import math
from statistics import NormalDist

__all__ = [
    "t_ppf",
    "t_sf",
    "paired_mean_diff",
    "sign_flip_pvalue",
    "holm",
    "same",
    "percentile",
]


# --- Student t ---------------------------------------------------------------

def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the regularized incomplete beta (Lentz)."""
    tiny = 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-15:
            return h
    raise ArithmeticError("incomplete beta did not converge")


def _betai(a: float, b: float, x: float) -> float:
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def t_sf(t: float, df: int) -> float:
    """P(T > t) for Student t with ``df`` degrees of freedom."""
    if df < 1:
        raise ValueError("df must be >= 1")
    x = df / (df + t * t)
    tail = 0.5 * _betai(df / 2.0, 0.5, x)
    return tail if t >= 0 else 1.0 - tail


def t_ppf(q: float, df: int) -> float:
    """Inverse CDF of Student t (bisection; accurate to ~1e-12)."""
    if not 0.0 < q < 1.0:
        raise ValueError("q must be in (0, 1)")
    if q == 0.5:
        return 0.0
    if q < 0.5:
        return -t_ppf(1.0 - q, df)
    lo, hi = 0.0, 1.0
    while t_sf(hi, df) > 1.0 - q:
        hi *= 2.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if t_sf(mid, df) > 1.0 - q:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-13:
            break
    return (lo + hi) / 2.0


# --- paired mean difference ----------------------------------------------------

def paired_mean_diff(a: list[float], b: list[float], alpha: float = 0.05,
                     power: float = 0.8, clusters: list | None = None) -> dict:
    """Paired t on per-case values (b - a).

    ``a`` and ``b`` are per-case means, aligned by position. Returns the mean
    difference, its standard error, a two-sided (1 - alpha) interval, the
    two-sided p-value, and a rough minimum detectable effect (MDE) at
    ``power``: (t_{1-alpha/2, df} + z_{power}) * SE, using this sample's SE.

    With ``clusters`` (one label per case), the SE is cluster-robust (CR1:
    residuals summed within each cluster, scaled by G/(G-1)) and the t
    reference has G - 1 degrees of freedom for G clusters.

    The MDE is None when the differences do not vary (SE = 0): no spread was
    observed, so nothing can be said about what this sample could detect.
    """
    if len(a) != len(b):
        raise ValueError("a and b must be aligned per case")
    if clusters is not None and len(clusters) != len(a):
        raise ValueError("clusters must have one label per case")
    n = len(a)
    scale = max((abs(v) for v in list(a) + list(b)), default=0.0)
    d = [0.0 if same(x, y, scale) else y - x for x, y in zip(a, b)]
    out = {"n_cases": n, "mean_a": _mean(a), "mean_b": _mean(b),
           "n_clusters": len(set(clusters)) if clusters is not None else None}
    empty = {"se": None, "ci": None, "p": None, "mde": None, "df": None}
    if n == 0:
        return {**out, "diff": None, **empty}
    diff = _mean(d)
    out["diff"] = diff
    if clusters is None:
        if n < 2:
            return {**out, **empty}
        df = n - 1
        se = math.sqrt(sum((x - diff) ** 2 for x in d) / (n - 1) / n)
    else:
        g = len(set(clusters))
        if g < 2:
            return {**out, **empty}
        df = g - 1
        sums: dict = {}
        for lab, x in zip(clusters, d):
            sums[lab] = sums.get(lab, 0.0) + (x - diff)
        se = math.sqrt(g / (g - 1) * sum(v * v for v in sums.values())) / n
    tcrit = t_ppf(1.0 - alpha / 2.0, df)
    zpow = NormalDist().inv_cdf(power)
    if se == 0.0:
        p = 1.0 if diff == 0.0 else 0.0
        mde = None
    else:
        p = min(1.0, 2.0 * t_sf(abs(diff) / se, df))
        mde = (tcrit + zpow) * se
    return {**out, "se": se, "df": df, "ci": (diff - tcrit * se, diff + tcrit * se),
            "p": p, "mde": mde}


# --- tests on per-case counts -----------------------------------------------

def sign_flip_pvalue(diffs: list[int], alternative: str = "two-sided") -> float:
    """Exact sign-flip permutation test on integer per-case differences.

    Under the null that the two configurations are exchangeable within a case,
    each non-zero per-case difference is equally likely to have either sign.
    Two-sided: P(|S| >= |s_obs|); ``alternative="greater"``: P(S >= s_obs),
    over all 2^k sign assignments, computed exactly with a dynamic program
    over the attainable sums.
    """
    if alternative not in ("two-sided", "greater"):
        raise ValueError("alternative must be 'two-sided' or 'greater'")
    if any(float(x) != int(x) for x in diffs):
        raise ValueError("sign_flip_pvalue needs integer differences")
    nz = [abs(int(x)) for x in diffs if int(x) != 0]
    if not nz:
        return 1.0
    s_obs = sum(int(x) for x in diffs)
    obs = abs(s_obs)
    dist = {0: 1}
    for v in nz:
        nxt: dict[int, int] = {}
        for s, c in dist.items():
            nxt[s + v] = nxt.get(s + v, 0) + c
            nxt[s - v] = nxt.get(s - v, 0) + c
        dist = nxt
    total = 2 ** len(nz)
    if alternative == "greater":
        extreme = sum(c for s, c in dist.items() if s >= s_obs)
    else:
        extreme = sum(c for s, c in dist.items() if abs(s) >= obs)
    return min(1.0, extreme / total)


def holm(pvalues: list[float]) -> list[float]:
    """Holm step-down adjusted p-values, in the input order."""
    m = len(pvalues)
    order = sorted(range(m), key=lambda i: pvalues[i])
    adj = [0.0] * m
    running = 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (m - rank) * pvalues[i]))
        adj[i] = running
    return adj


# --- descriptive -------------------------------------------------------------

def percentile(values: list[float], q: float) -> float | None:
    """Linear-interpolation percentile (same as numpy's default), q in [0, 100]."""
    if not values:
        return None
    xs = sorted(values)
    if len(xs) == 1:
        return xs[0]
    pos = (len(xs) - 1) * q / 100.0
    lo = math.floor(pos)
    hi = math.ceil(pos)
    return xs[lo] + (xs[hi] - xs[lo]) * (pos - lo)


def _mean(xs: list[float]) -> float | None:
    return math.fsum(xs) / len(xs) if xs else None


def same(x: float, y: float, scale: float = 0.0) -> bool:
    """Equal up to floating-point noise: within 1e-12 of the larger of |x|, |y|
    and ``scale`` (pass the largest magnitude in the data being compared).

    Two runs with the same per-case values in a different order must compare
    as equal; a difference this small relative to the data is never a finding.
    """
    return abs(x - y) <= 1e-12 * max(abs(x), abs(y), abs(scale))
