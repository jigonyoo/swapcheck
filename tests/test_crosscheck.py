"""Cross-checks against SciPy and errorbars. Skipped when they are not installed."""

import math
import random

import pytest

from swapcheck.stats import paired_mean_diff, t_ppf, t_sf

scipy_stats = pytest.importorskip("scipy.stats", reason="SciPy cross-check")


def test_t_matches_scipy():
    for df in (1, 2, 3, 7, 31, 95, 500):
        for q in (0.6, 0.9, 0.95, 0.975, 0.995):
            assert t_ppf(q, df) == pytest.approx(scipy_stats.t.ppf(q, df), rel=1e-9)
        for t in (-3.0, -0.2, 0.0, 0.7, 2.0, 6.0):
            assert t_sf(t, df) == pytest.approx(scipy_stats.t.sf(t, df), rel=1e-9, abs=1e-15)


def test_paired_matches_scipy():
    rng = random.Random(3)
    for _ in range(50):
        n = rng.randint(2, 60)
        a = [rng.random() for _ in range(n)]
        b = [x + rng.gauss(0.02, 0.1) for x in a]
        r = paired_mean_diff(a, b)
        ref = scipy_stats.ttest_rel(b, a)
        assert r["p"] == pytest.approx(ref.pvalue, rel=1e-8)
        d = [y - x for x, y in zip(a, b)]
        se = scipy_stats.sem(d)
        tc = scipy_stats.t.ppf(0.975, n - 1)
        assert r["ci"][0] == pytest.approx(sum(d) / n - tc * se, rel=1e-9, abs=1e-12)
        assert r["ci"][1] == pytest.approx(sum(d) / n + tc * se, rel=1e-9, abs=1e-12)
        assert r["mde"] == pytest.approx((tc + scipy_stats.norm.ppf(0.8)) * se, rel=1e-9)


def test_paired_matches_errorbars():
    eb = pytest.importorskip("errorbars.compare", reason="errorbars cross-check")
    rng = random.Random(11)
    a = [rng.random() for _ in range(32)]
    b = [x - 0.03 + rng.gauss(0, 0.05) for x in a]
    ours = paired_mean_diff(a, b)
    theirs = eb.paired_compare(a, b)  # errorbars reports mean(A) - mean(B)
    assert -ours["diff"] == pytest.approx(theirs.mean_diff, rel=1e-12)
    assert ours["se"] == pytest.approx(theirs.se_paired, rel=1e-9)
    assert ours["p"] == pytest.approx(theirs.p_value, rel=1e-6)
    assert math.isclose(-ours["ci"][1], theirs.ci_low, rel_tol=1e-6)


def test_cluster_robust_matches_errorbars():
    eb = pytest.importorskip("errorbars.compare", reason="errorbars cross-check")
    rng = random.Random(21)
    a = [rng.random() for _ in range(40)]
    b = [x - 0.02 + rng.gauss(0, 0.05) for x in a]
    cl = [f"f{i % 7}" for i in range(40)]
    ours = paired_mean_diff(a, b, clusters=cl)
    theirs = eb.paired_compare(a, b, clusters=cl)
    assert ours["se"] == pytest.approx(theirs.se_clustered, rel=1e-9)
    assert ours["p"] == pytest.approx(theirs.p_value_clustered, rel=1e-6)
