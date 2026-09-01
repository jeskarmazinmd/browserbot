# C3 market-gate experiment and conservative pruning

## Prospective market gates

Forward collection begins at `2026-09-02T13:30:00Z`. The unchanged
`C3N25S10` strategy remains the control. Each child is paper-only, clones the
control's entry/target/stop/exit terms exactly, and uses market data ending one
full clock minute before entry.

| Strategy | Admission rule |
| --- | --- |
| `C3MG_IWM5` | IWM five-minute return >= -0.25% |
| `C3MG_SPY5` | SPY five-minute return >= -0.20% |
| `C3MG_BRD35` | >= 35% of measured non-index symbols green over five minutes |
| `C3MG_MED10` | Median non-index five-minute return >= -0.10% |
| `C3MG_P10` | Tenth-percentile non-index five-minute return >= -0.75% |
| `C3MG_3OF4` | At least three of IWM, SPY, breadth, and median gates pass |

Breadth features require at least 50 measured non-index symbols. Missing data
fails closed for the affected arm. Every failed decision produces a
`REFRAINED` event with its causal cutoff, observed value, threshold, and reason.

These round thresholds are pre-registered hypotheses, not values optimized on
the September 1 outcome. No arm can place a broker order.

## Conservative pruning

Historical rows and outcome files are retained. Only future evaluation or
derivation is disabled. Parent strategies `A`, `B`, `D`, and `H` remain because
profitable descendants depend on their signal generation.

Newly disabled independent leaves had at least 14 active sessions and a
cumulative return of -6% or worse through September 1:

- `GT1`, `SH1`, `ET29`, `PT325`, `HT5`, `LT65`

Newly disabled derived leaves had at least 14 active sessions and a cumulative
return of -10% or worse:

- `E`, `I`, `J3`, `J4`, `J5`, `N`, `P`, `Q`

Previously disabled failed leaves remain disabled, including `K1`-`K9` and
`M`. Successful or still-informative controls remain active.
