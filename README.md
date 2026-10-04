# swapcheck

Switching models or rewriting a prompt? See what broke, not just the average.

`swapcheck` compares two recorded eval runs, before and after, case by case. It counts the failures you name (a refund paid twice, an email address leaked) separately from the average score, says whether each rise is larger than chance would produce if the two setups behaved the same, and puts the cost next to it.

It does not call any model. You give it results you already have: a promptfoo `-o results.json`, JSONL or CSV. Pure Python, no dependencies, no API key, no network.

## What it found in the bundled example

The bundled data is 32 refund-desk cases (an agent handling refund tickets with timeouts, retries and repeat purchases), each run 3 times per model. It comes from [duplicate-side-effect-desk](https://github.com/jigonyoo/duplicate-side-effect-desk) (`reports/model_eval_20260923.jsonl`, MIT, same author), copied unchanged.

Switching from `claude-haiku-4.5` to `gpt-4.1-mini`:

| | claude-haiku-4.5 | gpt-4.1-mini |
|---|---|---|
| Average reward | 0.984 | 0.959 |
| Runs with a duplicate payment | 3 | 14 |
| Cases where that happened | 3 of 32 | 8 of 32 |
| Money paid twice or over the cap, total | $150.00 | $708.40 |

**Verdict: BLOCK.** The average alone would not have stopped this switch. It fell by 0.025, and the 95% interval runs from −0.052 to +0.002, so 32 cases cannot tell that drop from noise. The duplicate payments can: five cases started paying twice and none stopped. If the two models behaved the same, a rise that large would come up with a one-sided p of 0.016.

The second bundled comparison keeps the model (`claude-sonnet-4.5`) and changes what it is given: the source data's `hints-enabled` runs against its `hints-disabled` runs. Duplicates went from 3 to 5 runs, but from 3 to 2 cases: one case started paying twice, two stopped, and one did it more often. A rise that size could easily be chance (p = 0.438), which is not the same as nothing having changed: one case went from 0 of 3 runs to 3 of 3. So the verdict is **REVIEW**, with the four cases worth rerunning listed by name.

Full reports: [`examples/model-switch/report.md`](examples/model-switch/report.md) and [`examples/hints-on/report.md`](examples/hints-on/report.md). To reproduce:

```bash
pip install "swapcheck @ git+https://github.com/jigonyoo/swapcheck"
swapcheck demo            # writes ./swapcheck-demo/{model-switch,hints-on}/report.md
```

These are three models on one small agent task. They say nothing about which model is better in general.

## Quick start with promptfoo

Run your eval with both providers and repeats, then compare them:

```bash
promptfoo eval -c promptfooconfig.yaml --repeat 3 -o results.json

swapcheck compare results.json results.json --metric score \
  --where-a provider=before --where-b provider=after \
  --guard 'fail:correct>0' --zero-tolerance 'fail:no-pii>0' \
  --latency latency_ms --cost cost
```

`provider` is the provider's `label` in your config (its `id` if it has no label). Each side must be one provider and one prompt; if a side mixes them, swapcheck stops and asks for a `--where` filter instead of averaging them together. Two separate files, each from one provider, work too: `swapcheck compare before.json after.json --metric score`.

On the small promptfoo run in [`tests/`](tests/) (three tests, a local provider that leaks an email address on one of them), that command prints (first 14 lines of 79):

~~~
# swapcheck: before → after

## Verdict: BLOCK

- **BLOCK** — `fail:no-pii>0` happened 0 -> 3 times (in 0 -> 1 of 3 cases). Marked zero-tolerance: any rise blocks.
- **REVIEW** — `fail:correct>0` happened 0 -> 1 times (in 0 -> 1 of 3 cases). Only 1 case(s) changed, too few to tell this from chance (no p below 0.500 was possible). That is not evidence that nothing changed. Rerun the 1 case(s) that changed with more repeats: weather.
- **REVIEW** — Average `score`: 1.000 -> 0.778 (-0.222). Only 3 paired case(s): too few to judge the average (swapcheck needs at least 10).

**Cases to rerun with more repeats:** weather

```
promptfoo eval --repeat 10 --filter-pattern '^(weather)$'
```

~~~

and exits with code 4. Each promptfoo result row becomes these columns:

| column | from |
|---|---|
| `case_id` | the test's `description`; a hash of its `vars` if it has none |
| `provider`, `prompt` | provider label (else id), prompt label (else id) |
| `score`, `success` | promptfoo's score; 1/0 for pass |
| `error` | 1 when the provider call failed (`failureReason` 2). Not set by a failed assertion, though promptfoo also writes that reason into its own `error` field |
| `latency_ms`, `cost` | as recorded |
| `named:<metric>` | each named score |
| `fail:<metric>` | failed assertions with that `metric` (else assertion `type`); a row that errored counts as 1 for every assertion |

Repeats of the same test are grouped into one case. promptfoo gives every repeat its own `testIdx`, so grouping by that index would count three repeats as three independent cases.

## Your own results (JSONL or CSV)

One row per run of one case. The only required columns are a case id and a number:

```bash
swapcheck compare before.jsonl after.jsonl --metric reward \
  --guard 'duplicate_effects>0' --impact unauthorized_cents:cents --slice family
```

Conditions are `column OP value` with `=`, `!=`, `<`, `<=`, `>`, `>=`. `--where-a` and `--where-b` select rows when both runs are in one file. `--impact COL[:raw|cents|usd]` totals a column for both runs; higher is worse.

## How the verdict is made

Each line of the verdict is OK, REVIEW or BLOCK, and the verdict is the worst line.

| What | BLOCK | REVIEW |
|---|---|---|
| a `--guard` failure | it rose, and the one-sided exact p is at most `--guard-alpha` (0.10; Holm-adjusted when there are several guards) | it rose but the rise could be chance (the cases to rerun are listed), or it did not rise in total but appeared in new cases |
| a `--zero-tolerance` failure | any rise | appeared in new cases without rising in total |
| the average `--metric` | the whole interval is on the worse side | `--max-drop` is set and the interval allows a larger drop; or fewer than 10 paired cases |
| an `--impact` total | — | it rose (totals are not tested) |
| case coverage | — | some cases are in only one run |

Exit codes: 0 below the `--fail-on` level, 3 REVIEW, 4 BLOCK, 2 input error. `--fail-on` is `block` by default, so REVIEW does not fail a CI job unless you pass `--fail-on review`.

The guard test: each case's repeats are summed, and the before and after counts are compared case by case. If nothing changed, each case's difference is as likely to point up as down. p is the share of those up/down assignments that rise at least as much as what was observed, computed exactly.

## Why a rise is not enough to block

Failures you care about are usually rare, so their counts move between runs even when nothing changed. Before release, swapcheck blocked on any rise. Independent reviews ([REVIEW.md](REVIEW.md)) measured what that costs. `bench/guard_calibration.py` reproduces it with swapcheck's own `compare()`.

On the bundled data, each model against itself (repeat *i* against repeat *j*, both orders, 24 comparisons), any rise blocked 11 of 24: 11 of the 12 pairs of repeats differed, and one direction of each counts as a rise. That shows the problem; it cannot measure the fix, because only a few cases change per comparison and only 4 of the 24 could reach p ≤ 0.10 at all. The simulation measures the rates:

| | any rise blocks | p ≤ 0.10 blocks (the default) |
|---|---|---|
| simulation, 32 cases × 3 repeats, nothing changed | 43.2% blocked | 4.4% |
| same, failures twice as frequent | 97.3% caught | 66.9% |
| same, 3 clean cases start failing on 2 of 3 runs | 95.1% caught | 36.6% |
| simulation, 100 cases × 3 repeats, nothing changed | 43.5% blocked | 5.6% |
| same, failures twice as frequent | 98.4% caught | 75.8% |

The simulation's failures sit in a minority of cases (25% and 10% of cases), as in the bundled data, where 2 to 8 of the 32 cases had any duplicate. The per-run rate of a failing case, drawn between 0.05 and 0.6, is an assumption, not fitted to anything. Rows with 1 repeat and 200 cases are in the script's output. The rises that the default does not block are not dropped: they become REVIEW with the cases to rerun. For a failure that must never ship, use `--zero-tolerance`. The third row shows why: a few new failing cases are hard to tell from noise.

These rates depend on how your failures are spread across cases. Compare a setup against itself to see yours: run the same config twice and `swapcheck compare` the two runs.

## What it cannot tell you

- **Whether your cases look like production.** swapcheck compares the runs you give it.
- **Small changes in the average.** The report gives a rough smallest detectable change, the drop this sample would catch 80% of the time, computed from the sample's own spread (0.038 for the bundled model switch). With few cases or scores bunched near the top it understates the real figure. Under 10 paired cases the average is shown but not judged.
- **Cases that are not independent.** Cases are treated as independent. If yours come from a few templates or conversations that you consider a sample, pass `--cluster COL`. In the bundled example `--cluster family` turns the model-switch BLOCK into REVIEW: the new duplicates sit in 3 of 8 families, and with 3 clusters no p below 0.125 is possible. Whether the families are a sample or the whole population of interest is your call.
- **Unequal repeats.** When a case ran a different number of times before and after, a guard is compared, and tested, on the first *k* runs of that case on each side (*k* = the smaller count), in file order. Impact columns are then compared per run, case by case. The tables still show every run.
- **Slices.** The per-slice table is a description; it is not tested and not corrected for multiple comparisons.
- **promptfoo files other than `promptfoo eval -o *.json`** from version 0.123.1, the version the test fixture was written with. Two tests with the same description and the same vars are merged into one case.
- **Drift between runs.** The guard test assumes that, if nothing changed, each case's before and after runs are interchangeable. Runs on different days or API versions can differ for reasons that are not your change; compare a setup against itself to see how much.

## Related

The statistics are standard. Averaging repeats within a question and comparing models question by question is the approach of [Miller (2024), "Adding Error Bars to Evals"](https://arxiv.org/abs/2411.00640). [errorbars](https://pypi.org/project/errorbars/) implements it as a library, and swapcheck's paired and cluster-robust standard errors match errorbars 0.2.4 in the cross-check tests. What swapcheck adds is the reading of promptfoo results with repeats, the separate failure counts with a blocking rule, and a report written for the person who decides the switch.

[eval-harness](https://github.com/jigonyoo/eval-harness), by the same author, scores one pipeline against a golden set and fails CI when accuracy drops. swapcheck compares two runs you already have and counts named failures on their own.

## Development

```bash
pip install -e ".[test]"
pytest -q                            # 63 pass; the SciPy and errorbars cross-checks are skipped
pip install -e ".[crosscheck]"       # adds SciPy and errorbars: 67 pass
python bench/guard_calibration.py    # the table above, about 40 seconds
```

## License

MIT. See [LICENSE](LICENSE).

Built with AI assistance and reviewed by separate reviewers before release; what they found and what changed is in [REVIEW.md](REVIEW.md).

---

Want this run on your own prompts and cases before you switch? Model & Prompt Switch Check, fixed scope, from $500: [jigonyoo.com](https://jigonyoo.com)
