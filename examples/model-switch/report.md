# swapcheck: claude-haiku-4.5 → gpt-4.1-mini

## Verdict: BLOCK

- **BLOCK** — `duplicate_effects>0` happened 3 -> 14 times (in 3 -> 8 of 32 cases). Unlikely to be chance: if the two setups behaved the same, a rise this large would come up with p = 0.016 (blocks at <= 0.1).
- **REVIEW** — `unauthorized_cents` rose: total $150.00 -> $708.40. Not tested on its own; the guards say whether the failures behind it could be chance.
- **OK** — Average `reward`: 0.984 -> 0.959 (-0.025): within noise (95% interval -0.052 to +0.002; this sample only reliably sees changes larger than about 0.038). Set --max-drop to say how much loss you accept.

## What broke

| failure | claude-haiku-4.5 | gpt-4.1-mini | cases claude-haiku-4.5 → gpt-4.1-mini | new cases | fixed cases | one-sided p | blocks on |
|---|---|---|---|---|---|---|---|
| `duplicate_effects>0` | 3 | 14 | 3 → 8 | 5 | 0 | 0.016 | p ≤ 0.1 |

<details><summary><code>duplicate_effects&gt;0</code> by case</summary>

| case | claude-haiku-4.5 | gpt-4.1-mini |
|---|---|---|
| cur-timeout-02 | 0/3 | 3/3 |
| cur-timeout-05 | 0/3 | 3/3 |
| cur-timeout-03 | 0/3 | 2/3 |
| cur-partialref-04 | 0/3 | 1/3 |
| cur-repeat-03 | 1/3 | 2/3 |
| cur-timeout-06 | 0/3 | 1/3 |
| cur-timeout-01 | 1/3 | 1/3 |
| cur-timeout-04 | 1/3 | 1/3 |

</details>

## Cost of the failures

| column | claude-haiku-4.5 total | gpt-4.1-mini total | claude-haiku-4.5 per run | gpt-4.1-mini per run |
|---|---|---|---|---|
| `unauthorized_cents` | $150.00 | $708.40 | $1.56 | $7.38 |

Over the paired cases, every repeat included. Higher is worse.

## Cases that got worse on gpt-4.1-mini: 5

| case | claude-haiku-4.5 mean | gpt-4.1-mini mean | worse on every repeat? | claude-haiku-4.5 values | gpt-4.1-mini values |
|---|---|---|---|---|---|
| cur-timeout-05 | 1.000 | 0.700 | yes | 1, 1, 1 | 0.7, 0.7, 0.7 |
| cur-timeout-02 | 1.000 | 0.800 | yes | 1, 1, 1 | 0.8, 0.8, 0.8 |
| cur-timeout-03 | 1.000 | 0.800 | no | 1, 1, 1 | 0.7, 0.7, 1 |
| cur-repeat-03 | 0.900 | 0.800 | no | 1, 1, 0.7 | 1, 0.7, 0.7 |
| cur-partialref-04 | 1.000 | 0.933 | no | 1, 1, 1 | 1, 0.8, 1 |

Cases that got better on gpt-4.1-mini: 1.

## By slice

| slice | cases | claude-haiku-4.5 | gpt-4.1-mini | change | `duplicate_effects>0` claude-haiku-4.5 → gpt-4.1-mini |
|---|---|---|---|---|---|
| clean-single ⚠ | 4 | 1.000 | 1.000 | +0.000 | 0 → 0 |
| duplicate-ticket ⚠ | 3 | 1.000 | 1.000 | +0.000 | 0 → 0 |
| legit-partial-refund ⚠ | 5 | 1.000 | 0.987 | -0.013 | 0 → 1 |
| legit-repeat-purchase ⚠ | 4 | 0.975 | 0.950 | -0.025 | 1 → 2 |
| parallel-worker ⚠ | 2 | 1.000 | 1.000 | +0.000 | 0 → 0 |
| partial-failure ⚠ | 4 | 0.983 | 0.983 | +0.000 | 0 → 0 |
| resumed-session ⚠ | 3 | 1.000 | 1.000 | +0.000 | 0 → 0 |
| timeout-then-retry ⚠ | 7 | 0.952 | 0.862 | -0.090 | 2 → 11 |

⚠ fewer than 10 cases: a description, not a finding.

## The statistics

| | claude-haiku-4.5 | gpt-4.1-mini | change | 95% interval | p | rough smallest detectable change |
|---|---|---|---|---|---|---|
| `reward` (mean over 32 cases) | 0.9844 | 0.9594 | -0.0250 | [-0.0516, +0.0016] | 0.065 | 0.038 |

Each case's repeats are averaged first; the two runs are then compared case by case (paired t on the per-case differences).

The smallest detectable change is the change this sample would catch 80% of the time, computed from this sample's own spread. It is rough: with few cases or scores bunched near the top it understates the real figure.

Guard p-values ask one question: if the two setups behaved the same, how often would the failure go up at least this much? Exact test: under that assumption each case's difference in event counts is equally likely to point either way, and p is the share of those sign assignments that rise at least as much as observed. A large p means the data cannot tell the setups apart, not that they are the same.

## Repeat noise

Cases whose score differed between repeats of the *same* setup: 5 of 32 in claude-haiku-4.5, 7 of 32 in gpt-4.1-mini (counting only cases run more than once). A case that disagrees with itself cannot tell you much about a switch.

## What was compared

- rows in the files: claude-haiku-4.5 384, gpt-4.1-mini 384
- filter for claude-haiku-4.5: `population=hints-disabled` and `model=anthropic/claude-haiku-4.5`
- filter for gpt-4.1-mini: `population=hints-disabled` and `model=openai/gpt-4.1-mini`
- rows kept: claude-haiku-4.5 96, gpt-4.1-mini 96
- cases: claude-haiku-4.5 32, gpt-4.1-mini 32, paired 32 (rows used: 96 and 96)
- repeats per case: claude-haiku-4.5 [3], gpt-4.1-mini [3]

_swapcheck compares two recorded runs. It does not run models, and it cannot tell you whether your test cases look like production traffic._
