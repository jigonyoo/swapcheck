# Review before release

swapcheck was written with AI assistance. Before release it went through two rounds of review and a re-check of the fixes. Each reviewer was a separate agent that had not written the code, got only the packaged files, and worked in its own directory. Each was told that "nothing found" was an acceptable answer. Every finding below was fixed. Each code fix got a regression test, and each test was checked by putting the bug back and watching it fail.

## Round 1: direction (before the README was written)

Three reviewers looked at what swapcheck should be, not at bugs.

- **Is this already built?** The paired statistics are not new. [errorbars](https://pypi.org/project/errorbars/) computes the same paired t, and on the bundled model switch it reproduced swapcheck's interval and p to the reported digits. What no tool the reviewer checked did was read promptfoo results with repeats grouped by test, count a named failure apart from the average with a blocking rule, and accept a stated tolerance for loss (`--max-drop`). That narrowed the scope to those three.
- **Who reads it?** People deciding a switch talk about what broke and what it costs. The draft report opened with a p-value and showed money as cents inside a table. The report now leads with the failures and the money; the statistics come after.
- **Which design premise was weakest?** "Block on any rise of a guard." Two reviewers measured it separately. The bundled data compared with itself blocked 11 times in 24. Simulations blocked about 40% of the time when nothing had changed. A guard now blocks when the rise is unlikely to be chance (one-sided exact p ≤ 0.10, Holm across guards), and is REVIEW otherwise. `--zero-tolerance` keeps the old rule for one failure at a time. The same reviewer found that unequal repeat counts biased the draft's guard test, that two promptfoo tests sharing a description were merged, and that the smallest detectable change printed 0.000 when it could not be estimated.

## Round 2: defects (on the release candidate)

Four reviewers: one compared every claim and number in the docs with the output of commands (L0); one recomputed the statistics independently (L14); one installed and ran the package on a clean environment (L15); one audited the AI-written code and text (L16).

| # | Found by | Severity | What was wrong | Fixed |
|---|---|---|---|---|
| 1 | L0, L14, L16 | medium | promptfoo writes the reason a failed assertion failed into its `error` field. swapcheck read any non-empty `error` as "the call failed", so `--guard 'error>0'` counted assertion failures. | `error` is now `failureReason == 2`. A row that really errored counts as failing every assertion, so a crash cannot read as "no failures". |
| 2 | L14 | medium | Per-case means were plain sums, which depend on order. The same values in a different order gave per-case differences in the last binary digit, all with the same sign. That made the standard error 0, p = 0, and **BLOCK** on data that had not changed. | Means and totals use `math.fsum`; differences within 1e-12 of the largest value being compared count as zero. (The two defences overlap, so the test fails only when the tolerance is removed.) |
| 3 | L15 | medium | CI installed the package in editable mode, so a broken package-data entry would ship a wheel without the demo data while CI stayed green. | A CI job builds the wheel, installs it in a fresh venv and runs the demo outside the checkout. |
| 4 | L15 | medium | Printing the report to a non-UTF-8 stdout (Windows cp1252) crashed with exit 1. | The report is written as UTF-8 bytes. |
| 5 | L16 | medium | The README used "0 of 24" on the bundled self-comparison as evidence for the new rule. Only 4 of those 24 comparisons could reach p ≤ 0.10 at all. | The README now says so and uses the simulation for the rates. The bench script prints how many could. |
| 6 | L16 | medium | "Larger than the difference between two runs of the same setup" and "ordinary noise" described the guard test as if it measured run-to-run noise. It tests whether the before and after runs are interchangeable. A large p means "cannot tell", not "nothing changed". | README, report and verdict lines reworded. A limit on drift between runs was added. |
| 7 | L16 | medium | "Two independent reviews" and similar claims had no source in the repository. | This file. |
| 8 | L0, L16 | info | The README test count (51) only held with the cross-check extras installed. | Both counts are given. |
| 9 | L0, L15 | info | The quoted Quick start output was cut without saying so, and was missing its inner code fence. | Quoted verbatim, with the cut marked. |
| 10 | L16 | info | "Understates the real figure, sometimes by half or more": the size was never measured. | Size removed; the direction stays. |
| 11 | L16 | info | Changing "first *k* runs" to "last *k*" on the after side, or `<=` to `<` at the guard limit, passed every test. | Tests for both. |
| 12 | L14 | info | `--cluster` with one cluster said "too few cases" for 30 cases. Impact totals with unequal repeats flagged a rise from the repeat count alone. Values near 1e300 crashed with a traceback. | Each fixed and tested. |
| 13 | L0, L16 | info | Dead code (`sign_test_pvalue`, `_OPS`), a stale "0.1.0 default" label in the bench script, and run times that disagreed. The demo passed tool calls as `--cost`, so a "cost" column showed tool calls. | Removed or corrected; the demo no longer reports cost. |
| — | L16 (not run) | — | A promptfoo config with two prompts would have its prompts averaged together as repeats. | Each side must now be one provider and one prompt, or swapcheck stops with an input error. |

## Re-check of the fixes

A fifth reviewer, new to the code, reproduced each row above on the old version, confirmed it on the fixed one, and put each bug back to see its test fail. Every row was fixed. It found that two fixes were incomplete, plus three smaller gaps. Rows 14 to 18 were fixed after the re-check. Each was reproduced first, fixed, re-run, and its test checked by putting the bug back. They were not re-reviewed by another reviewer.

| # | What was still wrong | Fixed |
|---|---|---|
| 14 | Row 2 was fixed for averages but not for impact totals: the same values in a different order still read "rose: $7.20 -> $7.20". | Totals use `math.fsum`, and a rise must be more than rounding. |
| 15 | Row 12 was fixed for one direction only. When some cases ran more often before and others more often after, the per-run impact and the guard could both "rise" with every case behaving the same. | A guard's rise is judged on the same first-*k* runs as its test. Impacts are compared per run within each case, then averaged over cases. |
| 16 | The tolerance in row 2 was absolute below 1 (`max(1, abs(x), abs(y))`), so a metric living around 1e-13 could double unseen. | Relative to the largest value in the data. |
| 17 | A row that errored but still carried passing grades counted as no failure. | Every errored row counts as failing every assertion, as documented. |
| 18 | "Repeat noise" survived in `--help`, the demo title and one README table cell. Mixing providers, and the check on each side separately, had no test. | Reworded; tests added. |

## After publication

One more reviewer compared everything published under this name with the release (GitHub files, README links, the repository description, the dev.to article that links here). The remote files matched the release byte for byte, and every number in the README matched its command. It found four places that still said something untrue, all fixed:

| # | What was wrong | Fixed |
|---|---|---|
| 19 | The package summary (`pip show`) and the first paragraph of `swapcheck --help` still described the draft rule: block whenever a failure goes up. | Both now say a rise blocks when it is more than chance. A test checks the help text. |
| 20 | The README called `unauthorized_cents` "money paid twice or over the cap". In the source data it is the whole order total once an order goes over the $50 cap without a human; a duplicate under $50 adds nothing to it. | Renamed "Paid over the $50 per-order cap without approval". |
| 21 | The CHANGELOG said "unreleased" after release. | Dated. |
| 22 | This file said macOS was never checked. | It now says macOS was checked on GitHub Actions only. |

## What the reviewers confirmed

- In the re-check, every number in the README matched the output of the command that produces it.
- The demo reports in `examples/` are byte-identical to what `swapcheck demo` writes.
- The bundled data matches the source repository's file by SHA-256 (`tests/test_demo_data.py` checks the hash).
- The statistics matched SciPy, errorbars 0.2.4, and brute-force enumeration. One reviewer's own fuzzing, 3,000 random inputs whose scripts are not in this repository, found 0 disagreements on guard p, Holm and the block decision.
- An independent simulation reproduced the false-alarm and detection rates in the README to within Monte Carlo error.
- The package installs and runs on Python 3.10 and 3.13. It runs offline, with an empty environment, and from any directory.
- The promptfoo field names and the `--filter-pattern` flag exist in promptfoo 0.123.1, checked against its published source.

## What was not checked

- A physical Mac and a real Windows machine. macOS was checked only on GitHub Actions after publication (`macos-latest`, Python 3.10 and 3.13, all green in the first CI run). Windows was imitated with `PYTHONIOENCODING=cp1252`.
- Regenerating the promptfoo fixture by running promptfoo again.
- promptfoo versions other than 0.123.1.
- The arXiv paper cited in the README, which was read only through a summarizing fetch tool.
