# Changelog

## 0.1.0 — 2026-10-04

First version, published 2026-10-04. Changes made before release, after independent review (details in [REVIEW.md](REVIEW.md)):

- **A guard no longer blocks on any rise.** The first draft blocked whenever a guard's count went up. Run against itself (repeat *i* vs repeat *j* of the same model), the bundled data blocked 11 times in 24, and simulations blocked about 40% of the time with nothing changed. A rise now blocks when its one-sided exact p is at most `--guard-alpha` (0.10, Holm-adjusted across guards) and is REVIEW otherwise, with the cases to rerun listed. `--zero-tolerance` keeps the old rule for a failure that must never ship. `bench/guard_calibration.py` measures both rules.
- **Unequal repeat counts no longer bias the guard test.** The draft compared per-case rates with a sign test; with 1 repeat before and 3 after it said "up" more often than its nominal level under no change. The test now uses the first *k* runs of each case on each side.
- **Two promptfoo tests with the same description are no longer merged** into one case; the vars hash is appended.
- **The smallest detectable change is no longer reported as 0.000** when the per-case differences do not vary; it is left out, and the report says why. Under 10 paired cases the average is described but not judged.
- **The report leads with what broke and what it cost**; the statistics follow. Impact columns take a unit (`unauthorized_cents:cents` prints dollars).
- Added `--cluster` for cases that are not independent.
- **promptfoo `error` now means the provider call failed** (`failureReason` 2). promptfoo also writes the reason for a failed assertion into its `error` field; the draft counted those as errors. A row that errored counts as failing every assertion.
- **Reordered repeats no longer look like a change.** Means and totals use `math.fsum`, and differences within 1e-12 of the largest value being compared count as zero. Before, the same values in a different order could give a standard error of 0 and BLOCK, or an impact total that "rose" from $7.20 to $7.20.
- **Different repeat counts alone no longer look like a rise.** With unequal repeats, a guard's rise is judged on the same first-*k* runs as its test, and impact columns per run, case by case.
- A side of a promptfoo comparison must be one provider and one prompt; mixing them is an input error instead of being averaged as repeats.
- The report is written as UTF-8 even when stdout is not (Windows); values too large to compare are an input error (exit 2), not a traceback.
