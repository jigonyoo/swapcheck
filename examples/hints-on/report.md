# swapcheck: sonnet-4.5 hints-disabled → sonnet-4.5 hints-enabled

## Verdict: REVIEW

- **REVIEW** — `duplicate_effects>0` happened 3 -> 5 times (in 3 -> 2 of 32 cases). Could be chance: if the two setups behaved the same, a rise this large would still come up with p = 0.438. That is not evidence that nothing changed. Rerun the 4 case(s) that changed with more repeats: cur-repeat-03, cur-timeout-01, cur-timeout-05, cur-timeout-06.
- **REVIEW** — `unauthorized_cents` rose: total $205.00 -> $467.40. Not tested on its own; the guards say whether the failures behind it could be chance.
- **OK** — Average `reward`: 0.985 -> 0.984 (-0.001): within noise (95% interval -0.026 to +0.024; this sample only reliably sees changes larger than about 0.035). Set --max-drop to say how much loss you accept.

**Cases to rerun with more repeats:** cur-repeat-03, cur-timeout-01, cur-timeout-05, cur-timeout-06

## What broke

| failure | sonnet-4.5 hints-disabled | sonnet-4.5 hints-enabled | cases sonnet-4.5 hints-disabled → sonnet-4.5 hints-enabled | new cases | fixed cases | one-sided p | blocks on |
|---|---|---|---|---|---|---|---|
| `duplicate_effects>0` | 3 | 5 | 3 → 2 | 1 | 2 | 0.438 | p ≤ 0.1 |

<details><summary><code>duplicate_effects&gt;0</code> by case</summary>

| case | sonnet-4.5 hints-disabled | sonnet-4.5 hints-enabled |
|---|---|---|
| cur-timeout-05 | 0/3 | 3/3 |
| cur-timeout-01 | 1/3 | 2/3 |
| cur-repeat-03 | 1/3 | 0/3 |
| cur-timeout-06 | 1/3 | 0/3 |

</details>

## Cost of the failures

| column | sonnet-4.5 hints-disabled total | sonnet-4.5 hints-enabled total | sonnet-4.5 hints-disabled per run | sonnet-4.5 hints-enabled per run |
|---|---|---|---|---|
| `unauthorized_cents` | $205.00 | $467.40 | $2.14 | $4.87 |

Over the paired cases, every repeat included. Higher is worse.

## Cases that got worse on sonnet-4.5 hints-enabled: 2

| case | sonnet-4.5 hints-disabled mean | sonnet-4.5 hints-enabled mean | worse on every repeat? | sonnet-4.5 hints-disabled values | sonnet-4.5 hints-enabled values |
|---|---|---|---|---|---|
| cur-timeout-05 | 1.000 | 0.700 | yes | 1, 1, 1 | 0.7, 0.7, 0.7 |
| cur-timeout-01 | 0.900 | 0.800 | no | 1, 1, 0.7 | 0.7, 1, 0.7 |

Cases that got better on sonnet-4.5 hints-enabled: 3.

## By slice

| slice | cases | sonnet-4.5 hints-disabled | sonnet-4.5 hints-enabled | change | `duplicate_effects>0` sonnet-4.5 hints-disabled → sonnet-4.5 hints-enabled |
|---|---|---|---|---|---|
| clean-single ⚠ | 4 | 1.000 | 1.000 | +0.000 | 0 → 0 |
| duplicate-ticket ⚠ | 3 | 1.000 | 1.000 | +0.000 | 0 → 0 |
| legit-partial-refund ⚠ | 5 | 1.000 | 1.000 | +0.000 | 0 → 0 |
| legit-repeat-purchase ⚠ | 4 | 0.933 | 1.000 | +0.067 | 1 → 0 |
| parallel-worker ⚠ | 2 | 1.000 | 1.000 | +0.000 | 0 → 0 |
| partial-failure ⚠ | 4 | 1.000 | 1.000 | +0.000 | 0 → 0 |
| resumed-session ⚠ | 3 | 1.000 | 1.000 | +0.000 | 0 → 0 |
| timeout-then-retry ⚠ | 7 | 0.971 | 0.929 | -0.043 | 2 → 5 |

⚠ fewer than 10 cases: a description, not a finding.

## The statistics

| | sonnet-4.5 hints-disabled | sonnet-4.5 hints-enabled | change | 95% interval | p | rough smallest detectable change |
|---|---|---|---|---|---|---|
| `reward` (mean over 32 cases) | 0.9854 | 0.9844 | -0.0010 | [-0.0259, +0.0238] | 0.933 | 0.035 |

Each case's repeats are averaged first; the two runs are then compared case by case (paired t on the per-case differences).

The smallest detectable change is the change this sample would catch 80% of the time, computed from this sample's own spread. It is rough: with few cases or scores bunched near the top it understates the real figure.

Guard p-values ask one question: if the two setups behaved the same, how often would the failure go up at least this much? Exact test: under that assumption each case's difference in event counts is equally likely to point either way, and p is the share of those sign assignments that rise at least as much as observed. A large p means the data cannot tell the setups apart, not that they are the same.

## Repeat noise

Cases whose score differed between repeats of the *same* setup: 4 of 32 in sonnet-4.5 hints-disabled, 1 of 32 in sonnet-4.5 hints-enabled (counting only cases run more than once). A case that disagrees with itself cannot tell you much about a switch.

## What was compared

- rows in the files: sonnet-4.5 hints-disabled 384, sonnet-4.5 hints-enabled 384
- filter for sonnet-4.5 hints-disabled: `population=hints-disabled` and `model=anthropic/claude-sonnet-4.5`
- filter for sonnet-4.5 hints-enabled: `population=hints-enabled` and `model=anthropic/claude-sonnet-4.5`
- rows kept: sonnet-4.5 hints-disabled 96, sonnet-4.5 hints-enabled 96
- cases: sonnet-4.5 hints-disabled 32, sonnet-4.5 hints-enabled 32, paired 32 (rows used: 96 and 96)
- repeats per case: sonnet-4.5 hints-disabled [3], sonnet-4.5 hints-enabled [3]

_swapcheck compares two recorded runs. It does not run models, and it cannot tell you whether your test cases look like production traffic._
