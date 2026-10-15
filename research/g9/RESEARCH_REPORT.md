# G9: STHEDGE2 prospective population

## Decision and evidence boundary

The supplied October 15 terminal table is the authoritative ranking. The frozen JSON preserves its exact order, five reported dates and rounded values. Ranks 1–130 are retained; ranks 131–596 (466 IDs) lose new paper entries and active reporting. October 14 is absent from the supplied dates; no missing value is converted to a zero or filled from another date. Totals are preserved rather than recomputed from rounded cells. Existing histories and open-position exits survive retirement. Source producers continue evaluating where descendants may depend on them. No broker routing, credentials or live-order settings change.

This implementation was developed from branch `modular-bot`, baseline `4fe31bf`. Production access belongs to the user. No SSH, production-ledger download, deployment, activation, or production performance validation was performed by the implementing agent. The deployment helper makes a read-only SSH inspection its first production operation and downloads baseline reporting and parent-ledger evidence before deploying.

## Parent mechanics and source audit

`statarb2_strategies/strategy_sthedge2.py` collects midpoint prices into 130-observation per-symbol queues. It waits for at least 101 observations of SPY and a candidate. Percentage returns feed two covariance/variance beta estimates (30 and 100 returns). Eligibility requires long beta in [0.2, 2.5] and absolute beta drift at most 0.25. Using the current long beta, it forms 60 residual returns, estimates their population standard deviation, and sums the latest 10 residuals. The signal score divides that sum by residual standard deviation times sqrt(10). The strongest absolute score of at least 2 is selected. A positive residual score shorts the asset and buys SPY; a negative score buys the asset and shorts SPY. SPY's relative gross weight equals beta. Admission cooldown is 30 minutes; grouped target/stop/time limits are 0.45% / 0.38% / 120 minutes. Worker entry window is 09:35–15:30 New York; tracker attempts EOD exit at 15:55.

The economic hypothesis is temporary asset-specific displacement after removing stable market exposure. Positive short-run/long-run hedge agreement may select less unstable relationships, but it does not establish stationarity, cointegration, statistical independence, or a persistent tradable edge. Summed minute residuals are serially dependent; the score is a heuristic, not a calibrated normal-tail probability. Fitting beta and residual volatility using the current observation is causal at that observation, but gives no independent out-of-sample validation.

Source limitations found:

- Original per-symbol queues can misalign when different symbols miss polls. They also span session gaps. New shared features require contiguous, synchronized same-session observations; missing quotes clear the affected history, missing SPY blocks all signals, and time gaps reset all histories.
- Original parent queues only update during the worker entry window. New features warm up from regular-market open, while retaining configured entry windows. This modestly changes earliest eligibility; no old trade is backfilled.
- Original cooldown starts at signal emission rather than successful admission; G9 cooldown starts at recorded admission and survives restart.
- The original tracker sizes each group near $5,000 gross, allows concurrent groups without an independent cash ledger, lacks per-leg displayed-size checks, and stores incomplete quote-timestamp evidence. It restores groups and crosses bid/ask, but nominal trade P&L does not establish feasible independently funded portfolio returns.
- Original stop/time exits defer when a required mark is missing, and do not latch the exit trigger. G9 persists a triggered exit until both legs are fresh and have enough displayed quantity. Unfillable EOD groups remain open, never receive fabricated closing prices.
- Neither the original nor G9 can verify locates, actual borrow charges, queue position, intraminute extremes, or simultaneous execution of both exchange orders. G9 is explicitly a paired paper model.
- Selecting the best of 596 on five reported dates creates selection bias. The table alone cannot measure trade-level expectancy, concentration, drawdown, leverage, or broad regime robustness.

The repository's earlier G6 parent audit reports 329 completed STHEDGE2 groups, nominal P&L $331.84, profit factor 1.350, win rate 53.5%, and 25 groups / $95.96 in its reviewed period. It found no recorded side errors. These are OLD archived results, not a refreshed October 15 trade audit. That report itself states missing displayed liquidity and complete per-leg timestamps, approximately $5,000 gross groups, and unverified borrow/locate. They are insufficient to assert executable parent returns. `research_tools/g9/parent_audit.py` is provided for a current read-only Fly audit: hashes, recomputed leg P&L, prices/sides, duplicates, orphan closes, realized drawdown, holding times, daily and pair concentration, and exit reasons. Production evidence must be reviewed before claiming current trade-level validation.

## Population design

Exactly 400 unique executable parameter sets use IDs G9<family><01–20>. The full frozen catalog is `research/g9/catalog.json`; the same specs and source hashes are frozen into the production manifest on first activation. Each family has 20 variants, specified before any new outcomes exist:

| Family | Hypothesis |
|---|---|
| Z | Residual-score selectivity; G9Z01 retains the parent signal parameters |
| DRIFT | Hedge-estimate stability |
| SHORT | Short beta adaptation speed |
| LONG | Long beta equilibrium horizon |
| RECENT | Dislocation accumulation horizon |
| RESID | Residual volatility estimation horizon |
| COOL | Frequency versus recycled capital |
| TARGET | Profit capture versus waiting for convergence |
| STOP | Failed-convergence loss limits |
| HOLD | Convergence speed and time-based exits |
| HEDGE | Under/over hedging and market-exposure tradeoffs |
| BETA | Stable beta cohorts |
| SIDE | Long-residual versus short-residual selection |
| COHORT | Stocks, sector ETFs, macro ETFs, index ETFs |
| SESSION | Opening, middle, afternoon session regimes |
| COST | Spread admissibility |
| VOL | Noise and shock exclusions |
| REGIME | Market direction and reversal confirmation |
| CONVERGE | Exit when the original residual converges or crosses zero |
| ROBUST | Predeclared interactions plus adverse slippage and reduced book participation |

G9Z01 supplies a prospective, equally sized, cost-aware control. Its signal math matches the parent on synchronized, contiguous, same-window observations (tested numerically), but session warmup, execution checks, one-group admission, portfolio sizing and costs differ. It is not a claim of identical production trades or raw returns. The retained STHEDGE2 remains unchanged as a historical reference. Compare new variants primarily with G9Z01, using the same forward dates and funding model, rather than inferring improvement from differently sized legacy accounts.

## Paper accounting and activation

Each ID is a separate counterfactual $5,000 account, reset to equal-start equity per exchange day; accounts cannot be added together. One concurrent pair per ID. Gross entry collateral is at most $1,000 and 20% of current daily equity; short proceeds cannot fund another position. Whole-share quantities split the budget by the chosen hedge weight. Both legs need fresh, realtime, uncrossed quotes and sufficient side-specific displayed depth. Raw vendor sizes are used without a speculative lot multiplier, a conservative restriction when units are uncertain. Quote depth is consumed per portfolio/symbol/side/timestamp and restored from the ledger; siblings do not compete because they represent alternative portfolios.

Long opens at ask and closes at bid; short opens at bid and closes at ask. Stressed variants apply additional adverse slippage. Model fees are $0.005 per share per side, minimum $0.01 per leg. Borrow is estimated at 300 annual basis points on short entry notional for actual held time, including weekends. These are explicit assumptions, not a verified broker fee schedule or borrow commitment. Full paired fill requirements avoid inventing a naked partial-leg hedge; they do not prove atomic exchange execution.

Births use actual activation time. No old outcomes, historical profits or nominal zero-before-birth accounts are imported. A missing manifest, changed frozen rule, corrupt ledger, missing births, duplicate group or second writer fails closed. OPEN/PENDING/CLOSE events are flushed and fsynced, so admitted fills and pending exit triggers recover durably. Restart warmup uses new market observations rather than guessed history. Turning off G9 entries leaves restored exits running.

Marked reporting uses actual quantities, fees and estimated borrow. Missing fresh marks produce unknown returns; closed groups retain actual P&L. Overnight carry days remain unknown, and new admission is blocked for an account on the day a prior-session group closes. This avoids silently treating unrealized carry as free daily cash.

## Prospective evaluation rule

Do not promote the maximum of 400 noisy returns directly. Keep every ID and its source frozen. Use an initial 20 trading-session observation block and require at least 30 completed groups before considering a candidate supported; sparse variants continue collecting. Compare matched-day net returns with G9Z01, including all rejected opportunities and carry/unknown coverage. Inspect per-pair and per-day concentration, worst day, drawdown, holding times, costs, rejected liquidity and short exposure. Report families and correlations, because parameter neighbors are highly correlated rather than 400 independent discoveries.

Any finalists require a second untouched 20-session confirmation block, the same original IDs/rules, positive cost-stressed evidence, and no single-pair domination. Treat superiority as unproven if uncertainty spans zero, missing marks are material, or borrow/execution assumptions drive the gain. Do not retune and then credit the old observation block. There is no automatic promotion, real trading, or claim that the 400 variants will outperform.

## Validation and deployment

Tests cover all 400 reachable rules/accounts, signal parity, synchronized history and session gaps, retirement boundaries, both-leg freshness/size, actual sides and costs, unknown marks, restart/lock/provenance, cutoff causality, exit shutdown, and overnight cash. Regression evidence and benchmark results accompany this report. The synthetic benchmark measures compute/memory, never investment returns. Existing market polling serves all variants; no additional data requests or processes are introduced.

After deployment, run `python -m research_tools.g9.verify_production --allow-warmup`, then repeat without that flag after reporting refresh. Run `python -m research_tools.g9.parent_audit` for fresh parent evidence and `python -m research_tools.g9.performance_table --days 5` for the permanent numbered active-only terminal table. Structural verification does not establish forward profitability.
