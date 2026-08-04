# August 4 capacity-filter analysis

## Outcome

August 4 contained 212,985 signal events. After deduplication and matching to
paper exits, 29 strategies had more than 500 completed setups. A prospective,
single-rule capacity filter was found for 22 strategies. Every selected rule:

- reduced the matched setup count to 500 or fewer;
- improved the simulated $10,000 account P/L in the August 4 sample; and
- used only information available when the signal was generated.

The simulation uses ten reusable $1,000 slots, no leverage, and recorded entry
and exit times. It excludes fees, spread, slippage, partial fills, and market
impact. Results are in-sample and must be validated prospectively.

## Selected rules and rounded-value replay

| Strategy | Setups before | Setups after | $10k P/L before | $10k P/L after | One selected rule |
|---|---:|---:|---:|---:|---|
| CV1 | 16,704 | 359 | +$118.69 | +$179.94 | Keep highest early R² each snapshot |
| EMA1 | 5,825 | 353 | -$40.52 | +$100.68 | Keep lowest latest-volume ratio each snapshot |
| EMA2 | 6,273 | 425 | +$47.94 | +$58.06 | Rebound 2m ≤ 0.11% |
| GE1 | 6,333 | 359 | -$39.96 | +$170.14 | Keep lowest rebound-from-low each snapshot |
| GM1 | 7,327 | 423 | +$122.97 | +$160.18 | Z-score ≥ -1.30 |
| GP1 | 6,057 | 409 | +$142.79 | +$210.38 | Up-minute fraction ≥ 0.63 |
| GT1 | 4,562 | 452 | +$123.48 | +$151.31 | Trend slope between 1.57% and 1.80%/hour |
| M1 | 1,581 | 299 | +$18.41 | +$261.08 | Keep lowest 2m rebound each snapshot |
| M2 | 967 | 147 | +$90.87 | +$264.87 | Largest one-minute decline ≤ 0.74% |
| MC1 | 3,160 | 467 | +$45.63 | +$216.51 | Require legacy eligibility |
| OR1 | 875 | 49 | +$65.04 | +$175.00 | Opening range ≥ 2.20% |
| PD1 | 1,521 | 235 | -$397.09 | +$203.14 | Rebound from low ≤ 0.53% |
| RS1 | 5,665 | 240 | -$29.11 | +$72.73 | Excess 30m return ≤ 0.76% |
| RS2 | 5,665 | 240 | -$29.11 | +$72.73 | Excess 30m return ≤ 0.76% |
| RS3 | 5,665 | 358 | +$60.35 | +$132.55 | Keep lowest 30m return each snapshot |
| SH1 | 3,372 | 352 | +$117.57 | +$226.16 | Keep highest flattening ratio each snapshot |
| TD1 | 3,350 | 163 | +$118.50 | +$126.90 | 5m return ≤ 0.045% |
| TF1 | 1,180 | 70 | +$16.98 | +$151.05 | Pullback from 10m high ≤ 0.26% |
| TL1 | 838 | 148 | -$109.73 | +$30.79 | Prior gap below trendline ≤ 0.28% |
| VE1 | 9,239 | 425 | +$59.17 | +$142.34 | Compression range ≥ 0.565% |
| VR1 | 5,839 | 499 | +$39.59 | +$186.53 | Require high-liquidity membership |
| VT1 | 3,568 | 352 | +$145.98 | +$184.07 | 45m slope ≥ 1.34%/hour |

## Strategies deliberately left unchanged

No tested one-rule filter for `AV1`, `BO1`, `EMA3`, `GR1`, `HL1`, `SMA1`, or
`VWEMA1` both reduced the strategy to 500 or fewer setups and improved the
$10,000 constrained P/L. Forcing a change would misrepresent the evidence.

## Implementation

The original strategy modules are untouched. `strategies/capacity_filters.py`
contains a reversible selection layer, and `live_strategy_runner.py` applies it
after universe metadata is attached but before cooldown, event logging, and
paper-outcome registration. Rules begin prospectively on August 5 in the code
metadata. Six focused unit tests pass, and all modified Python files compile.
