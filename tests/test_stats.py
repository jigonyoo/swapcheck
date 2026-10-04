"""The statistics, checked against independent implementations.

SciPy and errorbars are optional: the cross-checks skip without them, and the
brute-force checks run everywhere.
"""

import itertools
import math
import random

import pytest

from swapcheck.stats import (
    paired_mean_diff, percentile, sign_flip_pvalue, t_ppf, t_sf,
)


def brute_sign_flip(diffs):
    nz = [d for d in diffs if d != 0]
    if not nz:
        return 1.0
    obs = abs(sum(diffs))
    hits = 0
    for signs in itertools.product((1, -1), repeat=len(nz)):
        if abs(sum(s * d for s, d in zip(signs, nz))) >= obs:
            hits += 1
    return hits / 2 ** len(nz)


def test_sign_flip_matches_brute_force():
    rng = random.Random(7)
    for _ in range(300):
        n = rng.randint(0, 12)
        diffs = [rng.randint(-3, 3) for _ in range(n)]
        assert sign_flip_pvalue(diffs) == pytest.approx(brute_sign_flip(diffs), abs=1e-15)


def test_sign_flip_known_values():
    # six cases, all rose: only the all-positive and all-negative assignments are as extreme
    assert sign_flip_pvalue([3, 2, 3, 1, 1, 1, 0, 0]) == pytest.approx(2 / 64)
    assert sign_flip_pvalue([0, 0, 0]) == 1.0
    assert sign_flip_pvalue([1]) == 1.0
    with pytest.raises(ValueError):
        sign_flip_pvalue([0.5, 1])


def test_percentile_linear():
    xs = [1, 2, 3, 4, 10]
    assert percentile(xs, 50) == 3
    assert percentile(xs, 0) == 1
    assert percentile(xs, 100) == 10
    assert percentile(xs, 95) == pytest.approx(4 + 0.8 * 6)
    assert percentile([], 50) is None
    assert percentile([2.5], 95) == 2.5


def test_t_distribution_symmetry_and_known_points():
    # textbook values
    assert t_ppf(0.975, 1) == pytest.approx(12.706204736, rel=1e-8)
    assert t_ppf(0.975, 10) == pytest.approx(2.228138852, rel=1e-8)
    assert t_ppf(0.975, 31) == pytest.approx(2.039513446, rel=1e-8)
    assert t_ppf(0.025, 31) == pytest.approx(-t_ppf(0.975, 31))
    for df in (1, 2, 5, 31, 200):
        for t in (0.1, 1.0, 2.5, 10.0):
            assert t_sf(t, df) + t_sf(-t, df) == pytest.approx(1.0, abs=1e-12)


def test_paired_edge_cases():
    r = paired_mean_diff([], [])
    assert r["diff"] is None and r["ci"] is None
    r = paired_mean_diff([1.0], [0.5])
    assert r["diff"] == -0.5 and r["ci"] is None
    r = paired_mean_diff([1.0, 1.0], [1.0, 1.0])
    assert r["diff"] == 0 and r["se"] == 0 and r["p"] == 1.0
    with pytest.raises(ValueError):
        paired_mean_diff([1.0], [1.0, 2.0])


def brute_sign_flip_greater(diffs):
    nz = [d for d in diffs if d != 0]
    if not nz:
        return 1.0
    obs = sum(diffs)
    hits = sum(1 for signs in itertools.product((1, -1), repeat=len(nz))
               if sum(s * d for s, d in zip(signs, nz)) >= obs)
    return hits / 2 ** len(nz)


def test_one_sided_sign_flip_matches_brute_force():
    rng = random.Random(9)
    for _ in range(300):
        diffs = [rng.randint(-3, 3) for _ in range(rng.randint(0, 12))]
        assert sign_flip_pvalue(diffs, "greater") == pytest.approx(brute_sign_flip_greater(diffs), abs=1e-15)
    assert sign_flip_pvalue([1, 1, 1, 1, 1, 1], "greater") == pytest.approx(1 / 64)
    assert sign_flip_pvalue([-1, -1], "greater") == 1.0
    with pytest.raises(ValueError):
        sign_flip_pvalue([1], "less")


def test_holm_by_hand():
    from swapcheck.stats import holm
    assert holm([]) == []
    assert holm([0.01, 0.04, 0.03]) == pytest.approx([0.03, 0.06, 0.06])
    assert holm([0.5, 0.9]) == pytest.approx([1.0, 1.0])


def test_cluster_robust_by_hand():
    # 4 clusters of 2; CR1 SE = sqrt(G/(G-1) * sum_g e_g^2) / n
    a = [0.0] * 8
    b = [1, 0, 0, 0, 1, 1, 0, 0]
    cl = ["x", "x", "y", "y", "z", "z", "w", "w"]
    r = paired_mean_diff(a, b, clusters=cl)
    dbar = 3 / 8
    e = [1 - 2 * dbar, -2 * dbar, 2 - 2 * dbar, -2 * dbar]
    assert r["se"] == pytest.approx((4 / 3 * sum(x * x for x in e)) ** 0.5 / 8)
    assert r["df"] == 3 and r["n_clusters"] == 4
    assert paired_mean_diff([0, 0], [1, 1], clusters=["x", "x"])["se"] is None
