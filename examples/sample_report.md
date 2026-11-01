# Synthetic customer sample

All tickets, scores, failures, and dollar amounts below are invented. This is an illustration, not a customer result or a model benchmark.

Decision: hold this candidate switch and investigate the five newly failing tickets. The higher average score does not offset the duplicate payments. Fix the candidate, then rerun these cases with more repeats before deciding. These synthetic cases cannot establish production safety.

# swapcheck: Synthetic current → Synthetic candidate

## Verdict: BLOCK

- **BLOCK** — `duplicate_payment>0` happened 0 -> 15 times (in 0 -> 5 of 12 cases). Unlikely to be chance: if the two setups behaved the same, a rise this large would come up with p = 0.031 (blocks at <= 0.1).
- **REVIEW** — `unauthorized_cents` rose: total $0.00 -> $375.00. Not tested on its own; the guards say whether the failures behind it could be chance.
- **OK** — Average `score`: 0.900 -> 0.920 (+0.020): better on Synthetic candidate (95% interval +0.020 to +0.020, p = 0.000).

## What broke

| failure | Synthetic current | Synthetic candidate | cases Synthetic current → Synthetic candidate | new cases | fixed cases | one-sided p | blocks on |
|---|---|---|---|---|---|---|---|
| `duplicate_payment>0` | 0 | 15 | 0 → 5 | 5 | 0 | 0.031 | p ≤ 0.1 |

<details><summary><code>duplicate_payment&gt;0</code> by case</summary>

| case | Synthetic current | Synthetic candidate |
|---|---|---|
| synthetic-ticket-01 | 0/3 | 3/3 |
| synthetic-ticket-02 | 0/3 | 3/3 |
| synthetic-ticket-03 | 0/3 | 3/3 |
| synthetic-ticket-04 | 0/3 | 3/3 |
| synthetic-ticket-05 | 0/3 | 3/3 |

</details>

## Cost of the failures

| column | Synthetic current total | Synthetic candidate total | Synthetic current per run | Synthetic candidate per run |
|---|---|---|---|---|
| `unauthorized_cents` | $0.00 | $375.00 | $0.00 | $10.42 |

Over the paired cases, every repeat included. Higher is worse.

## Cases that got worse on Synthetic candidate: 0

Cases that got better on Synthetic candidate: 12.

## The statistics

| | Synthetic current | Synthetic candidate | change | 95% interval | p | rough smallest detectable change |
|---|---|---|---|---|---|---|
| `score` (mean over 12 cases) | 0.9000 | 0.9200 | +0.0200 | [+0.0200, +0.0200] | 0.000 | — |

Each case's repeats are averaged first; the two runs are then compared case by case (paired t on the per-case differences).

The smallest detectable change is the change this sample would catch 80% of the time, computed from this sample's own spread. It is rough: with few cases or scores bunched near the top it understates the real figure.

Guard p-values ask one question: if the two setups behaved the same, how often would the failure go up at least this much? Exact test: under that assumption each case's difference in event counts is equally likely to point either way, and p is the share of those sign assignments that rise at least as much as observed. A large p means the data cannot tell the setups apart, not that they are the same.

## Repeat noise

Cases whose score differed between repeats of the *same* setup: 0 of 12 in Synthetic current, 0 of 12 in Synthetic candidate (counting only cases run more than once). A case that disagrees with itself cannot tell you much about a switch.

## What was compared

- rows kept: Synthetic current 36, Synthetic candidate 36
- cases: Synthetic current 12, Synthetic candidate 12, paired 12 (rows used: 36 and 36)
- repeats per case: Synthetic current [3], Synthetic candidate [3]

_swapcheck compares two recorded runs. It does not run models, and it cannot tell you whether your test cases look like production traffic._
