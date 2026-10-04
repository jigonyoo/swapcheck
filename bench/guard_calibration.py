"""How often does a guard block when nothing changed, and when something did?

Run:  python bench/guard_calibration.py          (about 40 seconds, no network)

Every number comes from swapcheck's own compare(), not a re-implementation.
Two parts:

1. A/A on the bundled data. Same model, same prompt, repeat i against repeat j
   (4 setups x 6 ordered pairs = 24 comparisons, one row per case on each
   side). Nothing changed, so every BLOCK here is a false alarm. This part
   shows what "any rise" does on real data. It cannot measure the p-based
   rule's false-alarm rate: with only a few cases changing per comparison,
   most of the 24 cannot reach p <= 0.10 at all, and the script prints how
   many could. The simulation is what measures that rate.

2. Simulation. Failures sit in a minority of cases, as in the bundled data
   (the script prints the share of cases with any duplicate per setup).
   "Susceptible" cases fail on each row with a probability drawn once per case
   from 0.05-0.6; the rest never fail. That range is an assumption, not fitted.
   null:   the after run has the same per-case probabilities.
   x2:     every susceptible case fails twice as often (capped at 1).
   new:    as null, plus 3 previously clean cases now fail on 2/3 of rows.

Rules compared:
   any rise          the pre-release draft: BLOCK whenever the count goes up
   p <= a            BLOCK when the count goes up and the one-sided exact p <= a
"""

from __future__ import annotations

import json
import random
import sys
from importlib import resources
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from swapcheck.compare import Options, compare  # noqa: E402
from swapcheck.io import Condition  # noqa: E402

GUARD = Condition.parse("bad>0")
RULES = [("any rise", None), ("p <= 0.05", 0.05), ("p <= 0.10", 0.10), ("p <= 0.20", 0.20)]
SEED = 20261004
SIMS = 2000


def guard_result(a, b):
    res = compare(a, b, Options(metric="score", guards=[GUARD]))
    g = res["guards"][0]
    return g["rose"], g["p"], res


def blocks(rose, p, alpha):
    return rose if alpha is None else (rose and p <= alpha)


# --- 1. A/A on the bundled data -------------------------------------------------

def demo_aa():
    path = resources.files("swapcheck") / "data" / "refund_desk_20260923.jsonl"
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    setups: dict = {}
    for r in rows:
        setups.setdefault((r["population"], r["model"]), {}).setdefault(r["case_id"], []).append(r)
    counts = {name: 0 for name, _ in RULES}
    verdict_block = 0
    total = 0
    reachable = 0
    shares = {}
    for key, cases in sorted(setups.items()):
        hit = sum(1 for cs in cases.values() if any(r["duplicate_effects"] > 0 for r in cs))
        shares[key] = (hit, len(cases))
        for i in range(3):
            for j in range(3):
                if i == j:
                    continue
                a = [dict(cs[i], bad=cs[i]["duplicate_effects"], score=cs[i]["reward"]) for cs in cases.values()]
                b = [dict(cs[j], bad=cs[j]["duplicate_effects"], score=cs[j]["reward"]) for cs in cases.values()]
                rose, p, res = guard_result(a, b)
                for name, alpha in RULES:
                    counts[name] += blocks(rose, p, alpha)
                reachable += res["guards"][0]["min_possible_p"] <= 0.10
                full = compare(a, b, Options(metric="reward", guards=[Condition.parse("duplicate_effects>0")]))
                verdict_block += full["verdict"] == "BLOCK"
                total += 1
    return counts, verdict_block, total, reachable, shares


# --- 2. simulation -------------------------------------------------------------

def make_run(probs, reps, rng, label):
    out = []
    for c, q in enumerate(probs):
        for k in range(reps):
            out.append({"case_id": f"c{c}", "score": 1.0, "bad": int(rng.random() < q),
                        "_src": f"{label}:{c}:{k}"})
    return out


def simulate(n, reps, share, rng):
    out = {}
    for scenario in ("null", "x2", "new"):
        counts = {name: 0 for name, _ in RULES}
        for _ in range(SIMS):
            probs = [rng.uniform(0.05, 0.6) if rng.random() < share else 0.0 for _ in range(n)]
            if scenario == "null":
                pb = probs
            elif scenario == "x2":
                pb = [min(1.0, 2 * q) for q in probs]
            else:
                clean = [i for i, q in enumerate(probs) if q == 0.0]
                hit = set(rng.sample(clean, min(3, len(clean))))
                pb = [2 / 3 if i in hit else q for i, q in enumerate(probs)]
            a = make_run(probs, reps, rng, "A")
            b = make_run(pb, reps, rng, "B")
            rose, p, _ = guard_result(a, b)
            for name, alpha in RULES:
                counts[name] += blocks(rose, p, alpha)
        out[scenario] = {k: v / SIMS for k, v in counts.items()}
    return out


def main():
    print("## 1. A/A on the bundled data (nothing changed; every BLOCK is a false alarm)\n")
    counts, vb, total, reachable, shares = demo_aa()
    print("| rule | guard BLOCKs |")
    print("|---|---|")
    for name, _ in RULES:
        print(f"| {name} | {counts[name]} of {total} |")
    print(f"\nComparisons where p <= 0.10 was reachable at all: {reachable} of {total}.")
    print(f"Whole verdict with the default settings (guard at p <= 0.10, metric `reward`): "
          f"BLOCK in {vb} of {total}.\n")
    print("Cases with any duplicate, per setup: " + "; ".join(
        f"{m.split('/')[-1]} {pop}: {h} of {n}" for (pop, m), (h, n) in sorted(shares.items())) + "\n")

    rng = random.Random(SEED)
    print(f"## 2. Simulation ({SIMS} runs per cell, seed {SEED})\n")
    print("| cases | repeats | susceptible | rule | null (false alarm) | x2 (caught) | 3 new cases (caught) |")
    print("|---|---|---|---|---|---|---|")
    for n, reps, share in ((32, 3, 0.25), (32, 1, 0.25), (100, 3, 0.10), (200, 1, 0.10)):
        res = simulate(n, reps, share, rng)
        for name, _ in RULES:
            print(f"| {n} | {reps} | {share:.0%} | {name} | {res['null'][name]:.3f} | "
                  f"{res['x2'][name]:.3f} | {res['new'][name]:.3f} |")


if __name__ == "__main__":
    main()
