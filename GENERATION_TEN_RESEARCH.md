# Generation 10 — G3MPR150BA research population

## Status and evidence boundary

Implemented from the uploaded source archive, with exactly 200 frozen, semantically distinct long-only challengers. Production was not accessed: `fly` is unavailable in this environment, the connected GitHub searches returned no repository, and the uploaded archive has no Git remote or production ledgers. No production data, broker orders, or existing strategy configurations were changed by this session. A local baseline commit supports a reviewable patch; it is not the user's upstream revision. Deployment and prospective results remain unverified.

The +1.743% five-day sum is user-provided, not independently reproduced. No historical variant backtest, walk-forward return, confidence interval, significance result, or optimization claim is made. No synthetic result in the tests is performance evidence.

## Parent mechanics, traced through code

`strategies/generation_three.py` defines G3MPR150 as MIDDAY/PMID with pre-crash return >=1.50%, pretrend R² >=0.50, original flash decline >=1% and <=12%, 12:00 inclusive to 14:00 exclusive New York entry, 0.1% running-trough rebound, and 600-second pending timeout. The scanner uses 30 pre-crash minutes and a three-minute flash window. Shared upstream gates additionally require positive log-price slope >=0.50%/hour, pre-return >=0.25%, and frozen flash three-minute dollar volume >=$100,000. Maximum scan freshness, market hours, scanner universe, and held-symbol skip logic remain upstream dependencies.

The raw scanner's target is the flash-end price plus **60% of the flash-start-to-flash-end gap** (`RECOVERY_TARGET_FRACTION=0.60`). At confirmed execution the G3 tracker anchors a 5% stop to the actual ASK and targets that original recovery price, requiring at least 0.20% remaining executable upside. This is not a target of full return to the pre-flash high. Existing G3 has no shorting, trailing stop, progress checkpoint or module-specific maximum hold for this ID; the established target/stop/EOD state machine exits via observed BID, with EOD at 15:55 ET. Missing displayed quantity can leave a residual position rather than guarantee a stop fill.

The G3 account is a daily equal-start $5,000 portfolio with roughly $1,000 per ordinary admitted signal. G3MPR150 itself has no extra spread gate, no nominal risk-fraction override, no symbol stacking restriction, and no cooldown. G1/G2 execution infrastructure enforces timestamped side liquidity, whole shares, cash consumption and partial exits. The raw scanner universe is not the EQUITIES tuple used by G3's separate minute architectures. Exact production symbols and configuration overrides require production evidence.

The economic hypothesis is temporary liquidity dislocation after antecedent momentum: buy a confirmed rebound while recovery room remains. The code explains the hypothesis, not why observed historical profits arose. Single-stock dominance, unusual-day dependence, survivor selection, realized spread costs, symbol turnover, and actual stop overshoots require the ledger audit below. Siblings with nearby pretrend thresholds can take substantially overlapping opportunities; 200 variants are correlated tests, not 200 independent discoveries.

## Common execution control and deliberate differences

`G10ENTRY01` preserves the parent's entry thresholds under **common G10 execution**, which deliberately differs from legacy G3 accounting. It is a fairer within-generation comparison than treating the unchanged legacy parent as cost-equivalent.

Each challenger owns cumulative $5,000 cash, never reset at midnight, $1,000 maximum order allocation, <=20% equity **aggregate per symbol**, <=1% nominal stop risk per order, and <=3% aggregate nominal stop risk. Some experiments lower these caps. The default does not prohibit repeated positions but cumulative symbol exposure is capped. Sizing uses the lower of cost equity and contemporaneously marked liquidation equity; stale residual marks reject additional entries. Realized losses reduce later capital; whole-share rounding can prevent trading high-priced stocks in the smallest risk cohorts. Those are explicit rejections, not zero-sized fills.

The shared `executable_paper_engine` classifies fills. Both book sides must be realtime and <=2,000 ms old at entry; future timestamps fail closed. Timestamped side liquidity is consumed independently per strategy. Default participation is 25% of displayed shares, with 5%, 10%, 50% research contrasts. Partial exits consume quantity and keep the original exit request latched through restart. Entries use ASK plus adverse 2 bps, exits BID minus adverse 2 bps. Assumed commission is $0.005/share/side, minimum $0.01, plus modeled $0.0002/share on sells. These are conservative research assumptions, not a verified broker tariff or a full market-impact model. Borrow is irrelevant: all G10 modules are long-only.

Targets and stops are recomputed from the cost-adjusted actual entry. Adaptive stops use frozen preflash volatility, bounded between 0.5% and 5%. Trailing stops use observed liquidation BID highs; breakeven includes entry and estimated exit commission. Time/progress clocks begin at actual fill. Stops and targets are trigger conditions, not guaranteed execution prices. Maximum hold is normally three hours, with unconditional 15:55 ET exit requests. Missing quotes or quantity defer fills; overnight residuals block new entries in that account, and missing daily opening valuation remains unknown.

## Research design

Ten families contain exactly twenty variants each: entry strength, recovery targets, protective exits, holding/progress clocks, volatility normalization, causal market/time regimes, executable liquidity/cost quality, rebound confirmation, risk allocation and deliberate interactions. Each has a hypothesis and exact configuration hash. `GENERATION_TEN_CATALOG.json` includes every field and changes relative to G10ENTRY01. The durable runtime manifest adds the actual birth map and source/execution hashes. Births must agree on restart; orphan, corrupt or changed provenance fails closed.

Regime filters use the existing contemporaneous market-confirmation series: the runner chooses SPY or QQQ by stronger available five-minute return. They are not labeled SPY-only filters. G10 records the selected feature timestamp and rejects future or >120-second-old features. Volume/volatility filters require successful frozen flash snapshots and reject missing/future evidence. Partial minute volume is causal at detection, but is not interchangeable with completed-minute turnover.

## Validation and prospective evaluation

Only source and deterministic engineering evidence are available locally. The production read-only parent audit calculates recorded trade arithmetic, timestamps, holding periods, symbol/day P&L, removing the best day, same-symbol/minute sibling overlap, and fixed-path extra cost stress at 1/3/5/10 bps per side plus commissions. It emits individual trades and missing-evidence counts. Extra-cost stress does not re-simulate position size or exit timing and cannot establish executable historical profitability.

All periods used to choose G3MPR150BA are discovery data. The audit labels chronological 60/20/20 evidence partitions for inspection, but does not misrepresent the last historical partition as untouched after parent selection. No code claims a walk-forward evaluation without causal quote paths. Obtain timestamped raw candidates, contemporaneous bid/ask and sizes, scanner universe membership and complete quote paths before meaningful chronological replay. Parent filled trades alone cannot test looser entries, alternate rebound confirmation or different exits.

Precommit the 200 rules and do not tune them during the first 20 full trading sessions after activation. Use sessions 1–20 as prospective discovery, 21–40 as validation, then 41–60 as untouched confirmation; keep this schedule conditional on adequate comparable coverage rather than automatically promoting at day 60. Seek at least 50–100 completed trades per serious candidate, distributed across multiple symbols and days. Sparse variants may require months. Analyze families and paired excess returns versus G10ENTRY01 first. Require stable net performance, acceptable drawdown and concentration, no single-day dependency, robustness to extra cost, and evidence across adverse regimes. Use day-block resampling and family-level/multiple-testing correction only when there are enough observations; the current code does not invent significance from tiny samples. No automatic promotion or retirement is implemented.

## Reporting and production verification

All-engine reporting appends G10 actual-account observations with BA suffixes. The permanent terminal table uses `strategies.output_switches.output_enabled` and `strategies.pruning.output_is_pruned`, joins durable births with the live inventory and retained IDs, and shows last reported weekdays, sum, known-day count and trade count. `--` is unknown/missing, `NT` scanner observed valid price windows with no trades, and `Z` an actual zero. G10 rows never fill earlier days with zero and never use today's quote to backfill past marks. Sampled marked drawdown is incomplete when quote gaps occur. G10 runtime faults latch an explicit durable error and fail production verification; they do not interrupt unrelated generation workers. Corrupt G10 reporting stays unknown with a diagnostic error while other generation reports continue. Reports state that accounts cannot be combined.

The G10 audit gives per-module cash performance, net completed-trade P&L, win rate/payoff/profit factor, observed drawdown, symbol notional, rejection reasons, scanner observation and paired daily excess/correlation with both benchmarks. Correlation is unavailable for fewer than three paired days or constant series. Same-symbol/minute overlap is a diagnostic, not a proof of identical execution.

Snapshot frames are capped at once per minute unless a fill requires immediate accounting visibility; the runner continues polling stops more frequently. Consequently reported drawdown samples do not capture all five-second equity extrema. Snapshot storage in the local synthetic benchmark is approximately 37 MiB per 390-minute session, before other scanner/event logs and unusual fill traffic. Monitor disk headroom in production; the preflight blocks below 200 MiB rather than pruning or deleting historical records.

## Commands on the Mac

Apply the patch only after `git apply --check` succeeds against the current branch. Do not discard existing edits to force it through. The patch includes no tokens or broker credentials.

```bash
cd ~/Desktop/browserbot
git switch modular-bot
git apply --check ~/Downloads/g10-modules.patch
git apply ~/Downloads/g10-modules.patch
python3 -m research_tools.g10.run_checks
python3 -m benchmarks.benchmark_generation_ten
git add strategies/generation_ten.py generation_ten_paper_tracker.py reporting/generation_ten_performance.py research_tools/g10 tests/test_generation_ten.py benchmarks/benchmark_generation_ten.py strategies/registry.py strategies/manifest.py live_strategy_runner.py reporting/all_engine_performance.py fly.toml Dockerfile GENERATION_TEN_CATALOG.json GENERATION_TEN_RUNTIME_HASHES.json GENERATION_TEN_RESEARCH.md GENERATION_SIX_RUNTIME_HASHES.json GENERATION_SEVEN_RUNTIME_HASHES.json GENERATION_EIGHT_RUNTIME_HASHES.json GENERATION_NINE_RUNTIME_HASHES.json
git commit -m 'Add 200 prospective G10 paper challengers of G3MPR150BA'
git push origin modular-bot
bash research_tools/g10/deploy.sh
```

The deployment script first performs read-only SSH preflight and copies parent/report evidence to the Mac, runs relevant tests and provenance checks, deploys with revision build arguments, then verifies actual births, source hashes, runner process settings, heartbeat, paper-only state, expected revision and existing collector/reporting/statarb worker presence. The deploy script also runs the existing G9 verifier. It does not call broker order APIs or claim to prove broker-side order state. The initial verifier allows report warmup; run again without `--allow-warmup` after the next reporting refresh. Fly secrets override TOML; if `ENABLE_G10_PAPER` is already set to 0 as a secret, reconcile it explicitly rather than interpreting a successful image upload as activation.

After SSH:

```bash
fly ssh console -a schwab
python -m research_tools.g10.performance_table --days 5
python -m research_tools.g10.performance_table --days 5 --g10
python -m research_tools.g10.audit --parent
python -m research_tools.g10.audit
python -m research_tools.g10.verify_production --expected-revision YOUR_COMMIT_SHA
```

## Engineering validation

The focused relevant-production command runs 279 tests, including 40 G10 tests. The G10 tests cover all 200 admissions and exits under valid synthetic evidence, independent cash, whole-share affordability, fees/slippage, partial fills, timestamped book reuse, restart recovery, no midnight reset, prebirth signals/setups, missing/future features, time/progress/trailing/breakeven exits, daily loss gates, disabled-entry drain, manifest corruption, single-writer locking, snapshot storage throttling, unknown/zero/no-trade distinctions, all-engine publication and G10 fault isolation. Synthetic fills are not profitability evidence.

Full discovery runs 776 tests with G10 versus 736 in the untouched upload. Both have the same 15 failures and 22 errors (37 failing test IDs); no new failure IDs are introduced. These pre-existing failures span older pruned-inventory expectations, C3 live fixtures, missing executor/support dependencies and the absent full-system installer. They are documented in `research_tools/g10/LOCAL_VALIDATION.json`; this delivery does not claim the entire legacy suite passes or change existing strategy/broker behavior to force those tests green. The relevant G1–G9, execution, accounting, reporting and pruning suites pass independently.

Local benchmark: 200 raw predicates per batch in roughly 0.12 ms; approximately 41 ms median update with 190 simultaneously active synthetic accounts and traced peak memory around 1.9 MiB. These are local synthetic measurements, not Fly capacity guarantees. Build-file packaging, Python compilation, shell syntax, whitespace and patch application are checked separately; no remote Docker build or production deployment is claimed.

## Inventory — all 200 frozen hypotheses

Exact common defaults are in the catalog. The change column is relative to G10ENTRY01, not a claim that execution matches the legacy parent. Birth timestamps are assigned only on actual activation.

| # | ID | Family | Hypothesis | Changed parameters |
|---:|---|---|---|---|
| 1 | G10ENTRY01 | ENTRY | Parent entry under common G10 cost/accounting model | Common execution control |
| 2 | G10ENTRY02 | ENTRY | Pretrend at least 1.0% selects stronger antecedent momentum | min_pre_return=1.0 |
| 3 | G10ENTRY03 | ENTRY | Pretrend at least 1.25% selects stronger antecedent momentum | min_pre_return=1.25 |
| 4 | G10ENTRY04 | ENTRY | Pretrend at least 1.75% selects stronger antecedent momentum | min_pre_return=1.75 |
| 5 | G10ENTRY05 | ENTRY | Pretrend at least 2.0% selects stronger antecedent momentum | min_pre_return=2.0 |
| 6 | G10ENTRY06 | ENTRY | Pretrend at least 2.25% selects stronger antecedent momentum | min_pre_return=2.25 |
| 7 | G10ENTRY07 | ENTRY | Pretrend at least 2.5% selects stronger antecedent momentum | min_pre_return=2.5 |
| 8 | G10ENTRY08 | ENTRY | Pretrend at least 3.0% selects stronger antecedent momentum | min_pre_return=3.0 |
| 9 | G10ENTRY09 | ENTRY | Pretrend R2 at least 0.55 excludes erratic ramps | min_pre_r2=0.55 |
| 10 | G10ENTRY10 | ENTRY | Pretrend R2 at least 0.6 excludes erratic ramps | min_pre_r2=0.6 |
| 11 | G10ENTRY11 | ENTRY | Pretrend R2 at least 0.65 excludes erratic ramps | min_pre_r2=0.65 |
| 12 | G10ENTRY12 | ENTRY | Pretrend R2 at least 0.7 excludes erratic ramps | min_pre_r2=0.7 |
| 13 | G10ENTRY13 | ENTRY | Pretrend R2 at least 0.75 excludes erratic ramps | min_pre_r2=0.75 |
| 14 | G10ENTRY14 | ENTRY | Pretrend R2 at least 0.8 excludes erratic ramps | min_pre_r2=0.8 |
| 15 | G10ENTRY15 | ENTRY | Pretrend R2 at least 0.85 excludes erratic ramps | min_pre_r2=0.85 |
| 16 | G10ENTRY16 | ENTRY | Minimum flash decline 1.25% tests dislocation magnitude | min_flash_drop=1.25 |
| 17 | G10ENTRY17 | ENTRY | Minimum flash decline 1.5% tests dislocation magnitude | min_flash_drop=1.5 |
| 18 | G10ENTRY18 | ENTRY | Minimum flash decline 1.75% tests dislocation magnitude | min_flash_drop=1.75 |
| 19 | G10ENTRY19 | ENTRY | Minimum flash decline 2.0% tests dislocation magnitude | min_flash_drop=2.0 |
| 20 | G10ENTRY20 | ENTRY | Minimum flash decline 2.5% tests dislocation magnitude | min_flash_drop=2.5 |
| 21 | G10TARGET01 | TARGET | Recover 30% of executable remaining gap, reducing reversal exposure | target_scale=0.3 |
| 22 | G10TARGET02 | TARGET | Recover 35% of executable remaining gap, reducing reversal exposure | target_scale=0.35 |
| 23 | G10TARGET03 | TARGET | Recover 40% of executable remaining gap, reducing reversal exposure | target_scale=0.4 |
| 24 | G10TARGET04 | TARGET | Recover 45% of executable remaining gap, reducing reversal exposure | target_scale=0.45 |
| 25 | G10TARGET05 | TARGET | Recover 50% of executable remaining gap, reducing reversal exposure | target_scale=0.5 |
| 26 | G10TARGET06 | TARGET | Recover 55% of executable remaining gap, reducing reversal exposure | target_scale=0.55 |
| 27 | G10TARGET07 | TARGET | Recover 60% of executable remaining gap, reducing reversal exposure | target_scale=0.6 |
| 28 | G10TARGET08 | TARGET | Recover 65% of executable remaining gap, reducing reversal exposure | target_scale=0.65 |
| 29 | G10TARGET09 | TARGET | Recover 70% of executable remaining gap, reducing reversal exposure | target_scale=0.7 |
| 30 | G10TARGET10 | TARGET | Recover 75% of executable remaining gap, reducing reversal exposure | target_scale=0.75 |
| 31 | G10TARGET11 | TARGET | Recover 80% of executable remaining gap, reducing reversal exposure | target_scale=0.8 |
| 32 | G10TARGET12 | TARGET | Recover 85% of executable remaining gap, reducing reversal exposure | target_scale=0.85 |
| 33 | G10TARGET13 | TARGET | Recover 90% of executable remaining gap, reducing reversal exposure | target_scale=0.9 |
| 34 | G10TARGET14 | TARGET | Recover 95% of executable remaining gap, reducing reversal exposure | target_scale=0.95 |
| 35 | G10TARGET15 | TARGET | Cap recovery target at 0.3% above cost-adjusted ask | fixed_target_pct=0.3 |
| 36 | G10TARGET16 | TARGET | Cap recovery target at 0.4% above cost-adjusted ask | fixed_target_pct=0.4 |
| 37 | G10TARGET17 | TARGET | Cap recovery target at 0.5% above cost-adjusted ask | fixed_target_pct=0.5 |
| 38 | G10TARGET18 | TARGET | Cap recovery target at 0.6% above cost-adjusted ask | fixed_target_pct=0.6 |
| 39 | G10TARGET19 | TARGET | Cap recovery target at 0.75% above cost-adjusted ask | fixed_target_pct=0.75 |
| 40 | G10TARGET20 | TARGET | Cap recovery target at 1.0% above cost-adjusted ask | fixed_target_pct=1.0 |
| 41 | G10STOP01 | STOP | Tighten ask-anchored stop to 0.5% | stop=0.005 |
| 42 | G10STOP02 | STOP | Tighten ask-anchored stop to 0.8% | stop=0.0075 |
| 43 | G10STOP03 | STOP | Tighten ask-anchored stop to 1.0% | stop=0.01 |
| 44 | G10STOP04 | STOP | Tighten ask-anchored stop to 1.2% | stop=0.0125 |
| 45 | G10STOP05 | STOP | Tighten ask-anchored stop to 1.5% | stop=0.015 |
| 46 | G10STOP06 | STOP | Tighten ask-anchored stop to 2.0% | stop=0.02 |
| 47 | G10STOP07 | STOP | Tighten ask-anchored stop to 2.5% | stop=0.025 |
| 48 | G10STOP08 | STOP | Tighten ask-anchored stop to 3.0% | stop=0.03 |
| 49 | G10STOP09 | STOP | Tighten ask-anchored stop to 3.5% | stop=0.035 |
| 50 | G10STOP10 | STOP | Tighten ask-anchored stop to 4.0% | stop=0.04 |
| 51 | G10STOP11 | STOP | After 0.5% progress trail observed bid high by 0.2% | trailing_pct=0.2 |
| 52 | G10STOP12 | STOP | After 0.5% progress trail observed bid high by 0.3% | trailing_pct=0.3 |
| 53 | G10STOP13 | STOP | After 0.5% progress trail observed bid high by 0.4% | trailing_pct=0.4 |
| 54 | G10STOP14 | STOP | After 0.5% progress trail observed bid high by 0.5% | trailing_pct=0.5 |
| 55 | G10STOP15 | STOP | After 0.5% progress trail observed bid high by 0.75% | trailing_pct=0.75 |
| 56 | G10STOP16 | STOP | After 0.5% progress trail observed bid high by 1.0% | trailing_pct=1.0 |
| 57 | G10STOP17 | STOP | Arm cost-aware breakeven after 0.25% progress | breakeven_arm_pct=0.25 |
| 58 | G10STOP18 | STOP | Arm cost-aware breakeven after 0.5% progress | breakeven_arm_pct=0.5 |
| 59 | G10STOP19 | STOP | Arm cost-aware breakeven after 0.75% progress | breakeven_arm_pct=0.75 |
| 60 | G10STOP20 | STOP | Arm cost-aware breakeven after 1.0% progress | breakeven_arm_pct=1.0 |
| 61 | G10HOLD01 | HOLD | Cap observed holding duration at 3 minutes | max_hold_seconds=180 |
| 62 | G10HOLD02 | HOLD | Cap observed holding duration at 5 minutes | max_hold_seconds=300 |
| 63 | G10HOLD03 | HOLD | Cap observed holding duration at 8 minutes | max_hold_seconds=480 |
| 64 | G10HOLD04 | HOLD | Cap observed holding duration at 10 minutes | max_hold_seconds=600 |
| 65 | G10HOLD05 | HOLD | Cap observed holding duration at 15 minutes | max_hold_seconds=900 |
| 66 | G10HOLD06 | HOLD | Cap observed holding duration at 20 minutes | max_hold_seconds=1200 |
| 67 | G10HOLD07 | HOLD | Cap observed holding duration at 30 minutes | max_hold_seconds=1800 |
| 68 | G10HOLD08 | HOLD | Cap observed holding duration at 45 minutes | max_hold_seconds=2700 |
| 69 | G10HOLD09 | HOLD | Cap observed holding duration at 60 minutes | max_hold_seconds=3600 |
| 70 | G10HOLD10 | HOLD | Cap observed holding duration at 90 minutes | max_hold_seconds=5400 |
| 71 | G10HOLD11 | HOLD | At 3 minutes exit unless observed bid gain exceeds 0.0% | checkpoint_seconds=180 |
| 72 | G10HOLD12 | HOLD | At 3 minutes exit unless observed bid gain exceeds 0.25% | checkpoint_seconds=180, checkpoint_gain_pct=0.25 |
| 73 | G10HOLD13 | HOLD | At 5 minutes exit unless observed bid gain exceeds 0.0% | checkpoint_seconds=300 |
| 74 | G10HOLD14 | HOLD | At 5 minutes exit unless observed bid gain exceeds 0.25% | checkpoint_seconds=300, checkpoint_gain_pct=0.25 |
| 75 | G10HOLD15 | HOLD | At 10 minutes exit unless observed bid gain exceeds 0.0% | checkpoint_seconds=600 |
| 76 | G10HOLD16 | HOLD | At 10 minutes exit unless observed bid gain exceeds 0.25% | checkpoint_seconds=600, checkpoint_gain_pct=0.25 |
| 77 | G10HOLD17 | HOLD | At 15 minutes exit unless observed bid gain exceeds 0.0% | checkpoint_seconds=900 |
| 78 | G10HOLD18 | HOLD | At 15 minutes exit unless observed bid gain exceeds 0.25% | checkpoint_seconds=900, checkpoint_gain_pct=0.25 |
| 79 | G10HOLD19 | HOLD | At 30 minutes exit unless observed bid gain exceeds 0.0% | checkpoint_seconds=1800 |
| 80 | G10HOLD20 | HOLD | At 30 minutes exit unless observed bid gain exceeds 0.25% | checkpoint_seconds=1800, checkpoint_gain_pct=0.25 |
| 81 | G10VOL01 | VOL | Preflash minute volatility in [0.0,0.1]% | max_vol_pct=0.1 |
| 82 | G10VOL02 | VOL | Preflash minute volatility in [0.0,0.2]% | max_vol_pct=0.2 |
| 83 | G10VOL03 | VOL | Preflash minute volatility in [0.0,0.3]% | max_vol_pct=0.3 |
| 84 | G10VOL04 | VOL | Preflash minute volatility in [0.1,0.3]% | min_vol_pct=0.1, max_vol_pct=0.3 |
| 85 | G10VOL05 | VOL | Preflash minute volatility in [0.1,0.5]% | min_vol_pct=0.1, max_vol_pct=0.5 |
| 86 | G10VOL06 | VOL | Preflash minute volatility in [0.2,0.5]% | min_vol_pct=0.2, max_vol_pct=0.5 |
| 87 | G10VOL07 | VOL | Preflash minute volatility in [0.2,1.0]% | min_vol_pct=0.2, max_vol_pct=1.0 |
| 88 | G10VOL08 | VOL | Preflash minute volatility in [0.3,1.0]% | min_vol_pct=0.3, max_vol_pct=1.0 |
| 89 | G10VOL09 | VOL | Flash shock in [3.0,6.0] preflash standard deviations | min_shock_units=3.0, max_shock_units=6.0 |
| 90 | G10VOL10 | VOL | Flash shock in [4.0,8.0] preflash standard deviations | min_shock_units=4.0, max_shock_units=8.0 |
| 91 | G10VOL11 | VOL | Flash shock in [5.0,10.0] preflash standard deviations | min_shock_units=5.0, max_shock_units=10.0 |
| 92 | G10VOL12 | VOL | Flash shock in [6.0,12.0] preflash standard deviations | min_shock_units=6.0, max_shock_units=12.0 |
| 93 | G10VOL13 | VOL | Flash shock in [4.0,12.0] preflash standard deviations | min_shock_units=4.0, max_shock_units=12.0 |
| 94 | G10VOL14 | VOL | Flash shock in [8.0,20.0] preflash standard deviations | min_shock_units=8.0, max_shock_units=20.0 |
| 95 | G10VOL15 | VOL | Stop distance 2.0 times preflash volatility, bounded 0.5%-5% | adaptive_stop_multiple=2.0 |
| 96 | G10VOL16 | VOL | Stop distance 3.0 times preflash volatility, bounded 0.5%-5% | adaptive_stop_multiple=3.0 |
| 97 | G10VOL17 | VOL | Stop distance 4.0 times preflash volatility, bounded 0.5%-5% | adaptive_stop_multiple=4.0 |
| 98 | G10VOL18 | VOL | Stop distance 5.0 times preflash volatility, bounded 0.5%-5% | adaptive_stop_multiple=5.0 |
| 99 | G10VOL19 | VOL | Stop distance 6.0 times preflash volatility, bounded 0.5%-5% | adaptive_stop_multiple=6.0 |
| 100 | G10VOL20 | VOL | Stop distance 8.0 times preflash volatility, bounded 0.5%-5% | adaptive_stop_multiple=8.0 |
| 101 | G10REGIME01 | REGIME | Require contemporaneous market 5m return >= -0.5% | market5_floor=-0.5 |
| 102 | G10REGIME02 | REGIME | Require contemporaneous market 5m return >= -0.25% | market5_floor=-0.25 |
| 103 | G10REGIME03 | REGIME | Require contemporaneous market 5m return >= -0.1% | market5_floor=-0.1 |
| 104 | G10REGIME04 | REGIME | Require contemporaneous market 5m return >= 0.0% | market5_floor=0.0 |
| 105 | G10REGIME05 | REGIME | Require contemporaneous market 5m return >= 0.1% | market5_floor=0.1 |
| 106 | G10REGIME06 | REGIME | Require contemporaneous market 5m return >= 0.25% | market5_floor=0.25 |
| 107 | G10REGIME07 | REGIME | Adjacent predeclared ET entry window 11:30-13:30 | start_minute=690, end_minute=810 |
| 108 | G10REGIME08 | REGIME | Adjacent predeclared ET entry window 12:30-14:30 | start_minute=750, end_minute=870 |
| 109 | G10REGIME09 | REGIME | Adjacent predeclared ET entry window 12:00-12:30 | end_minute=750 |
| 110 | G10REGIME10 | REGIME | Adjacent predeclared ET entry window 12:30-13:00 | start_minute=750, end_minute=780 |
| 111 | G10REGIME11 | REGIME | Adjacent predeclared ET entry window 13:00-13:30 | start_minute=780, end_minute=810 |
| 112 | G10REGIME12 | REGIME | Adjacent predeclared ET entry window 13:30-14:00 | start_minute=810 |
| 113 | G10REGIME13 | REGIME | Adjacent predeclared ET entry window 12:00-13:00 | end_minute=780 |
| 114 | G10REGIME14 | REGIME | Adjacent predeclared ET entry window 13:00-14:00 | start_minute=780 |
| 115 | G10REGIME15 | REGIME | Require contemporaneous market 1m return >= -0.2% | market1_floor=-0.2 |
| 116 | G10REGIME16 | REGIME | Require contemporaneous market 1m return >= -0.1% | market1_floor=-0.1 |
| 117 | G10REGIME17 | REGIME | Require contemporaneous market 1m return >= -0.05% | market1_floor=-0.05 |
| 118 | G10REGIME18 | REGIME | Require contemporaneous market 1m return >= 0.0% | market1_floor=0.0 |
| 119 | G10REGIME19 | REGIME | Require contemporaneous market 1m return >= 0.05% | market1_floor=0.05 |
| 120 | G10REGIME20 | REGIME | Require contemporaneous market 1m return >= 0.1% | market1_floor=0.1 |
| 121 | G10LIQ01 | LIQ | Executable spread <= 0.02% avoids costly recovery | max_spread_pct=0.02 |
| 122 | G10LIQ02 | LIQ | Executable spread <= 0.03% avoids costly recovery | max_spread_pct=0.03 |
| 123 | G10LIQ03 | LIQ | Executable spread <= 0.05% avoids costly recovery | max_spread_pct=0.05 |
| 124 | G10LIQ04 | LIQ | Executable spread <= 0.075% avoids costly recovery | max_spread_pct=0.075 |
| 125 | G10LIQ05 | LIQ | Executable spread <= 0.1% avoids costly recovery | max_spread_pct=0.1 |
| 126 | G10LIQ06 | LIQ | Executable spread <= 0.15% avoids costly recovery | max_spread_pct=0.15 |
| 127 | G10LIQ07 | LIQ | Flash dollar volume >= $250000, frozen at detection | min_dollar_volume=250000.0 |
| 128 | G10LIQ08 | LIQ | Flash dollar volume >= $500000, frozen at detection | min_dollar_volume=500000.0 |
| 129 | G10LIQ09 | LIQ | Flash dollar volume >= $1e+06, frozen at detection | min_dollar_volume=1000000.0 |
| 130 | G10LIQ10 | LIQ | Flash dollar volume >= $5e+06, frozen at detection | min_dollar_volume=5000000.0 |
| 131 | G10LIQ11 | LIQ | Executable price >= $2, price cohort without named-stock selection | min_price=2.0 |
| 132 | G10LIQ12 | LIQ | Executable price >= $5, price cohort without named-stock selection | min_price=5.0 |
| 133 | G10LIQ13 | LIQ | Executable price >= $10, price cohort without named-stock selection | min_price=10.0 |
| 134 | G10LIQ14 | LIQ | Executable price >= $20, price cohort without named-stock selection | min_price=20.0 |
| 135 | G10LIQ15 | LIQ | Consume at most 5% of displayed book per quote identity | participation=0.05 |
| 136 | G10LIQ16 | LIQ | Consume at most 10% of displayed book per quote identity | participation=0.1 |
| 137 | G10LIQ17 | LIQ | Consume at most 50% of displayed book per quote identity | participation=0.5 |
| 138 | G10LIQ18 | LIQ | Require target gap >= 4.0 times spread | min_edge_spreads=4.0 |
| 139 | G10LIQ19 | LIQ | Require target gap >= 8.0 times spread | min_edge_spreads=8.0 |
| 140 | G10LIQ20 | LIQ | Require target gap >= 12.0 times spread | min_edge_spreads=12.0 |
| 141 | G10CONFIRM01 | CONFIRM | Wait for 0.05% observed rebound from running trough | rebound_fraction=0.0005 |
| 142 | G10CONFIRM02 | CONFIRM | Wait for 0.075% observed rebound from running trough | rebound_fraction=0.00075 |
| 143 | G10CONFIRM03 | CONFIRM | Wait for 0.125% observed rebound from running trough | rebound_fraction=0.00125 |
| 144 | G10CONFIRM04 | CONFIRM | Wait for 0.15% observed rebound from running trough | rebound_fraction=0.0015 |
| 145 | G10CONFIRM05 | CONFIRM | Wait for 0.175% observed rebound from running trough | rebound_fraction=0.00175 |
| 146 | G10CONFIRM06 | CONFIRM | Wait for 0.2% observed rebound from running trough | rebound_fraction=0.002 |
| 147 | G10CONFIRM07 | CONFIRM | Wait for 0.25% observed rebound from running trough | rebound_fraction=0.0025 |
| 148 | G10CONFIRM08 | CONFIRM | Wait for 0.3% observed rebound from running trough | rebound_fraction=0.003 |
| 149 | G10CONFIRM09 | CONFIRM | Wait for 0.4% observed rebound from running trough | rebound_fraction=0.004 |
| 150 | G10CONFIRM10 | CONFIRM | Wait for 0.5% observed rebound from running trough | rebound_fraction=0.005 |
| 151 | G10CONFIRM11 | CONFIRM | Require at least 10s of pending observation before rebound admission | min_wait_seconds=10 |
| 152 | G10CONFIRM12 | CONFIRM | Require at least 20s of pending observation before rebound admission | min_wait_seconds=20 |
| 153 | G10CONFIRM13 | CONFIRM | Require at least 30s of pending observation before rebound admission | min_wait_seconds=30 |
| 154 | G10CONFIRM14 | CONFIRM | Require at least 60s of pending observation before rebound admission | min_wait_seconds=60 |
| 155 | G10CONFIRM15 | CONFIRM | Require at least 120s of pending observation before rebound admission | min_wait_seconds=120 |
| 156 | G10CONFIRM16 | CONFIRM | Reject if more than 25% of flash gap already recovered | max_recovery_fraction=0.25 |
| 157 | G10CONFIRM17 | CONFIRM | Reject if more than 35% of flash gap already recovered | max_recovery_fraction=0.35 |
| 158 | G10CONFIRM18 | CONFIRM | Reject if more than 50% of flash gap already recovered | max_recovery_fraction=0.5 |
| 159 | G10CONFIRM19 | CONFIRM | Reject if more than 65% of flash gap already recovered | max_recovery_fraction=0.65 |
| 160 | G10CONFIRM20 | CONFIRM | Reject if more than 80% of flash gap already recovered | max_recovery_fraction=0.8 |
| 161 | G10RISK01 | RISK | Nominal stop risk 0.10% equity limits loss size | risk_fraction=0.001 |
| 162 | G10RISK02 | RISK | Nominal stop risk 0.20% equity limits loss size | risk_fraction=0.002 |
| 163 | G10RISK03 | RISK | Nominal stop risk 0.25% equity limits loss size | risk_fraction=0.0025 |
| 164 | G10RISK04 | RISK | Nominal stop risk 0.30% equity limits loss size | risk_fraction=0.003 |
| 165 | G10RISK05 | RISK | Nominal stop risk 0.40% equity limits loss size | risk_fraction=0.004 |
| 166 | G10RISK06 | RISK | Nominal stop risk 0.50% equity limits loss size | risk_fraction=0.005 |
| 167 | G10RISK07 | RISK | Nominal stop risk 0.60% equity limits loss size | risk_fraction=0.006 |
| 168 | G10RISK08 | RISK | Nominal stop risk 0.75% equity limits loss size | risk_fraction=0.0075 |
| 169 | G10RISK09 | RISK | Per-order cap 5% equity reduces concentration | max_position_fraction=0.05 |
| 170 | G10RISK10 | RISK | Per-order cap 10% equity reduces concentration | max_position_fraction=0.1 |
| 171 | G10RISK11 | RISK | Per-order cap 12% equity reduces concentration | max_position_fraction=0.125 |
| 172 | G10RISK12 | RISK | Per-order cap 15% equity reduces concentration | max_position_fraction=0.15 |
| 173 | G10RISK13 | RISK | Cooldown 5 minutes after any fill suppresses clustering | cooldown_seconds=300 |
| 174 | G10RISK14 | RISK | Cooldown 10 minutes after any fill suppresses clustering | cooldown_seconds=600 |
| 175 | G10RISK15 | RISK | Cooldown 20 minutes after any fill suppresses clustering | cooldown_seconds=1200 |
| 176 | G10RISK16 | RISK | Cooldown 30 minutes after any fill suppresses clustering | cooldown_seconds=1800 |
| 177 | G10RISK17 | RISK | Stop new entries after marked daily loss 0.5%; drain residuals | daily_loss_fraction=0.005 |
| 178 | G10RISK18 | RISK | Stop new entries after marked daily loss 1.0%; drain residuals | daily_loss_fraction=0.01 |
| 179 | G10RISK19 | RISK | Stop new entries after marked daily loss 1.5%; drain residuals | daily_loss_fraction=0.015 |
| 180 | G10RISK20 | RISK | Stop new entries after marked daily loss 2.0%; drain residuals | daily_loss_fraction=0.02 |
| 181 | G10COMBO01 | COMBO | Cheap spread and half-gap recovery | target_scale=0.5, max_spread_pct=0.05 |
| 182 | G10COMBO02 | COMBO | High R2 and stronger rebound | min_pre_r2=0.75, rebound_fraction=0.002 |
| 183 | G10COMBO03 | COMBO | Stronger pretrend and modest stop | min_pre_return=2.0, stop=0.02 |
| 184 | G10COMBO04 | COMBO | One symbol at a time and ten-minute cooldown | cooldown_seconds=600, one_position_per_symbol=True |
| 185 | G10COMBO05 | COMBO | Fifteen-minute hold and partial recovery | target_scale=0.65, max_hold_seconds=900 |
| 186 | G10COMBO06 | COMBO | Tight spread and smaller risk | max_spread_pct=0.05, risk_fraction=0.0025 |
| 187 | G10COMBO07 | COMBO | Avoid falling market and demand stronger trend | min_pre_return=2.0, market5_floor=0.0 |
| 188 | G10COMBO08 | COMBO | Large shock with shallow observed recovery | min_flash_drop=2.0, max_recovery_fraction=0.5 |
| 189 | G10COMBO09 | COMBO | Three-volatility stop and twenty-minute hold | max_hold_seconds=1200, adaptive_stop_multiple=3.0 |
| 190 | G10COMBO10 | COMBO | Five-minute progress check and quarter-percent trailing stop | trailing_pct=0.25, checkpoint_seconds=300 |
| 191 | G10COMBO11 | COMBO | Breakeven protection and 75% recovery target | target_scale=0.75, breakeven_arm_pct=0.5 |
| 192 | G10COMBO12 | COMBO | High flash turnover and narrow spread | min_dollar_volume=1000000.0, max_spread_pct=0.05 |
| 193 | G10COMBO13 | COMBO | No stacking and 1% aggregate nominal stop risk | portfolio_risk_fraction=0.01, one_position_per_symbol=True |
| 194 | G10COMBO14 | COMBO | Two-times flash volume and smooth pretrend | min_pre_r2=0.7, min_volume_ratio=2.0 |
| 195 | G10COMBO15 | COMBO | Late midday, tighter stop | start_minute=780, stop=0.02 |
| 196 | G10COMBO16 | COMBO | Early midday, half-gap recovery | end_minute=780, target_scale=0.5 |
| 197 | G10COMBO17 | COMBO | Stabilization and stronger rebound | rebound_fraction=0.002, min_wait_seconds=30 |
| 198 | G10COMBO18 | COMBO | Cost-adjusted target room and quarter book participation | min_upside_pct=0.75, min_edge_spreads=8.0 |
| 199 | G10COMBO19 | COMBO | 1% daily loss gate and ten-minute timeout | max_hold_seconds=600, daily_loss_fraction=0.01 |
| 200 | G10COMBO20 | COMBO | Narrow spread, bounded volatility, no stacking | max_vol_pct=0.3, max_spread_pct=0.05, one_position_per_symbol=True |
