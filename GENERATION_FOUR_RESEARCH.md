# Generation Four: prospective research design

Status: implemented and locally tested; not deployed or production-verified from this workspace.
Baseline inspected: `0af3a25a7d98ee64d849c0f39f3060ac0d165b4f` (`modular-bot`).
Research date: 7 October 2026. No historical return optimization was performed.

## Existing architecture and evidence

The source review inventoried the entire strategy directory through ASTs (199 Python modules before G4) and read the generation and integration paths, including the registry, manifest, G1 flash/minute/market definitions, G2 and G3 catalogues, their tracker inheritance, common executable fill and paper exit engines, completed-minute construction, worker reconstruction, runner routing, all-engine reporting, output controls, dependency protection, image build and Fly configuration.

G1 combines frozen P/Q/midday admissions, sizing and exit interventions, plus eight owned minute experiments. G2 contains 64 flash execution/risk/exit interventions. G3 contains 150 experiments: 66 flash and 84 minute experiments around midday reversal, volatility reversal, commodity rotation/breadth/gas confirmation, trend and breakout. A shared implementation of execution mechanics does not mean shared cash: each experiment is its own counterfactual portfolio. G4 owns its hypotheses and state; it does not subscribe to G1–G3 signals.

The supplied 7 October tables give useful directional diagnostics, not a reconstructed audit of every fill. One active-set table joins unsuffixed strategy IDs to suffixed BA reporting IDs and produces 236 false missing/zero totals. The longer pasted history includes weekend zero rows and compounds daily equal-start returns; neither constitutes additional trading evidence. G3 has only one observed trading day. G2 has only a few trading days and G1 roughly a week. These generations are too young for durability conclusions.

In the longer supplied table, 136 reported G3 rows include 59 positive and 44 negative totals; G2 has 64 rows, 11 positive and 47 negative; G1 has 51 rows, nine positive and 39 negative. The horizons differ, some zero rows reflect inactivity, and these are counts from that table rather than comparable effect estimates. Strong G3 midday rows often have identical returns, consistent with overlapping trades, not independent discoveries. Older family rankings reverse across dates. This motivates mechanism diversity, observation coverage and overlap reporting rather than multiplying the best recent rule.

Production health pasted earlier that evening reports eight logical CPUs, estimated CPU pressure 22.1%, load about 1.77, daily peak CPU pressure 43.1%, peak memory 42.1% and storage 20.9%. These are historical snapshots, not a live capacity certification. The source Fly configuration specifies eight shared CPUs and 8 GB memory. The persistent volume remains much smaller than RAM; growing uncompressed research ledgers deserve separate monitoring.

Direct Fly SSH is unavailable here (private IPv6 network unreachable), the Fly CLI/credential are absent, and Docker is unavailable. Therefore current secrets, exact live source parity, raw current ledgers, machine capacity and deployed activation have not been independently verified.

## Literature and data feasibility

Primary sources were searched across intraday momentum/reversal, factor residuals, price discovery/lead-lag, liquidity provision, queue/order-flow imbalance, semivariance, variance ratios and multiple-testing bias. The following are intellectual antecedents and constraints. They do not establish profitability of the frozen G4 rules.

| Source | Finding or method relevant to the design | G4 use and limitation |
|---|---|---|
| [Avellaneda & Lee, Statistical Arbitrage in the U.S. Equities Market](https://math.nyu.edu/inmemoriam/avellaneda/AvellanedaLeeStatArb20090616.pdf) | Factor residuals and mean reversion; trading-time/volume distinctions | Lagged OLS residual signal. G4 is long-only and unhedged; neither a PCA/OU implementation nor a market-neutral replication. |
| [Heston, Korajczyk & Sadka, Intraday Patterns in the Cross-section of Stock Returns](https://doi.org/10.1111/j.1540-6261.2010.01573.x) | Same-time return continuation and short-term reversal; bid/ask bounce matters | Motivates competing persistence/reversal hypotheses and execution realism. No claim to implement their multi-day seasonality effect. |
| [Gao, Han, Li & Zhou, Market Intraday Momentum](https://doi.org/10.1016/j.jfineco.2018.05.009) | Early-session market return predicts late-session return in their sample | Directional momentum context. Exact overnight-to-open predictor is deferred because the current owned minute feed lacks durable previous-close provenance. |
| [Curme et al., statistically validated intraday lead-lag relationships](https://arxiv.org/abs/1401.0462) | Lagged relationships depend on sampling scale and multiplicity | Factor recoupling/dispersion context; G4 does not claim statistically validated links from 45 minutes of data. Generic leader-following already exists and was not added again. |
| [Nagel, Evaporating Liquidity](https://www.nber.org/papers/w17653) | Short-term reversal can reflect liquidity provision and changing market conditions | Reversal is regime-sensitive. G4 is a taker at displayed prices, not a liquidity-providing limit-order model. |
| [Barndorff-Nielsen, Kinnebrock & Shephard, Realised Semivariance](https://scholar.harvard.edu/files/downside200808.pdf) | Splitting realized variation by return sign | Semivariance regime features. The transition rule is an original hypothesis, not a published result. |
| [Lo & MacKinlay, variance-ratio specification test](https://www.nber.org/papers/w2168) | Comparing variances across sampling frequencies | A descriptive three-minute nonoverlapping ratio. The short-window threshold is not an econometric significance test; their weekly-return evidence does not validate this intraday adaptation. |
| [Cont, Kukanov & Stoikov, Price Impact of Order Book Events](https://arxiv.org/abs/1011.6402) | Event-level order-flow imbalance and depth explain short-run price changes | Deferred: no event-complete order-book feed in the completed-minute path. Sparse snapshots must not masquerade as OFI. |
| [Gould & Bonart, Queue Imbalance](https://arxiv.org/abs/1512.03492) | Top-of-book imbalance predicts the next price movement in their samples | Deferred: minute feed omits queue sizes and side timestamps; executable L1 quotes alone do not supply continuous queue history. |
| [Bailey & López de Prado, Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf) | Selection and many trials inflate reported performance | Preserve the entire frozen trial population and negative results; treat leaderboards as exploratory. The advisory age review does not claim to implement DSR. |

VWAP/volume-clock rules, continuous-time jump tests, overnight-gap models, true OHLC auction patterns, news/earnings and fundamental catalysts were considered but deferred where source fields or timestamp provenance are absent. The existing completed-minute cache supplies price and sets volume, bid and ask to `None`. G4 uses only prices for admission, and fresh side-specific L1 quotes for execution. It creates no new subscriptions or per-child candle/API calls.

## Frozen population: 12 hypotheses × three economic cohorts

Each mechanism is tested in INDEX (benchmark SPY), TECH (benchmark QQQ) and SECTOR (benchmark SPY). Universes are fixed in the source before activation; no asset was chosen from the October leaderboard. Cohorts overlap economically and are not independent trials. IDs are `G4` + mechanism + cohort, for example `G4RREVTECH`; reporting adds `BA`.

| Mechanism | Frozen causal question | Increment over existing mechanisms |
|---|---|---|
| RREV | Does a negative five-minute factor innovation recover? | Lagged alpha/beta residual, rather than raw flash or simple pair-ratio displacement. |
| RCONT | Does positive factor innovation persist? | Competing idiosyncratic continuation hypothesis against residual reversal. |
| FAIL | Does a price below an old range floor, followed by reclamation, persist upward? | Failed downside excursion rather than a high-side breakout or generic rebound. Sampled prices are not true OHLC auction data. |
| RETEST | Does an earlier ceiling escape hold through a later retest? | A two-stage path requirement rather than buying the first breakout. |
| JCONT | Does a concentrated positive three-minutes-ago shock continue? | Concentration in squared returns plus standardized shock and follow-through. Not a formal jump test. |
| JFADE | Does a concentrated negative shock partially retrace? | Concentration and incomplete recovery rather than a raw volatility-unit flash threshold. Related to reversal, not claimed orthogonal. |
| SEMIFLIP | Does downside variation dominance switch to upside dominance? | Signed realized-variation transition rather than positive-minute counts. |
| DISPCOMP | Does a recovering laggard benefit when cross-sectional dispersion compresses? | Change in dispersion, not simply buying the strongest sector or weakest pair. |
| RECOUPLE | Does a factor relationship recover after a temporary breakdown from below? | Prior, disrupted and recovery correlations must differ; not fixed correlation admission alone. |
| SERIAL | Does negative return autocorrelation switch to positive autocorrelation? | Change in serial dependence rather than entropy or raw return direction. |
| OCCUPY | Does an extended period below a starting anchor end in successful reclamation? | Time spent underwater, not just maximum drawdown or return magnitude. |
| VRSHIFT | Does anti-persistence become persistence across time aggregation? | Nonoverlapping variance-ratio transition rather than moving-average or simple trend thresholds. |

There is one parameter set per mechanism, reused across the three universes. This is a broad initial mechanism population, not an exhaustive search or proof of novelty in quantitative finance. Failure/retest/occupation and the concentrated-shock rules are original hypotheses; the source literature supplies context, not validation. Their realized signal overlap will be measured.

All scanners retain at most 66 contiguous completed minutes per symbol. A lagged 45-return factor fit ends 20 minutes before the decision window. Missing, invalid, regressed, duplicate, non-minute or overnight observations cannot bridge a continuity gap. Cross-sectional decisions require every fixed cohort member. Very small benchmark/residual variance and implausible betas fail closed. Warmup, missing data, or a degenerate fit may make a rule silent; silence is recorded as an observability issue rather than negative edge.

## Execution and prospective activation

- Default Python registry flag is off. The proposed Fly configuration explicitly enables `ENABLE_G4_PAPER=1` at deployment; it has not been deployed here.
- G4 signals route only to the isolated G4 tracker in the runner's LIVE data mode. LIVE refers to market data, not broker orders. REPLAY never earns G4 credit.
- Existing broker-entry function still returns false. No broker code or live-order setting is enabled by this change.
- Separate durable births, immutable manifest, outcomes, state, status, liquidity and observation files use `paper_generation_four_bidask_independent_*`.
- Rules carry a population hash and SHA-256 of the actual strategy source. Restart refuses changed frozen manifests. A rule revision requires new experiment identities and provenance.
- Births are the later of actual first tracker activation and creation time. No backfill. Unchanged births survive restart. Signal time must match completed-minute provenance and be no more than 120 seconds old at admission.
- Each experiment has a $5,000 daily equal-start cash account, at most $1,000 per signal, whole shares, one residual position per symbol and a ten-minute cooldown from the last admitted fill. Portfolios cannot be added together.
- Entry buys at observed ASK and exit sells at observed BID. Both book sides must be executable and no more than five seconds old. Entry spread must be at most 0.08%; target distance must exceed five spreads. Side-timestamp liquidity cannot be spent twice within a portfolio. Quotes/size may produce partial fills; only filled cash and quantities move.
- Stop is 0.4% below actual ASK; target is 0.6% above actual ASK. Neither is an expected profit estimate. A 20-minute maximum hold uses actual fill time. If no fresh executable exit exists, the position remains open until an observed exit can execute. No idealized stop fill is substituted.
- Entries run 10:30–15:45 New York time, with normal existing EOD liquidation. A full same-session warmup completes around 10:35. Overnight residuals continue to reserve cash.
- Admissions retain their numerical evidence, rule/source hash, completed minute and execution reference. The common schema was extended to preserve these fields; legacy execution behavior was not changed.
- Disabling G4 stops new admissions/evaluation but reconstructs its tracker when births exist so open positions can drain. Existing G1–G3 definitions, flags, portfolios and approved output controls are preserved. No new retirement is applied.

Displayed quantity is a conservative paper constraint, not proof a real order would fill: depth could disappear, a feed may sample stale books, and market impact/queue latency is not fully simulated. No extra commission or regulatory-fee schedule is assumed. All current reports are after spread crossing, before any unspecified costs; evaluate cost sensitivity before promotion.

## Evidence collection and age-aware review

The runner records actually processed, current, error-free evaluation opportunities separately from fills. Historical warmup is not a new observed session. Missing cohort data and worker errors reduce readiness. A day is conservatively usable for retirement review only with at least 300 ready minutes and no worker errors. Early-close and partial-activation days are not silently counted as complete. A malformed ledger blocks verified evidence in the G4 review. The as-of date excludes that date and later ledger events; missing dates are not zeros.

`python -m research_tools.g4_review.report --root /data --as-of YYYY-MM-DD` reports births, coverage, actual closed-trade returns, rejects, signal Jaccard overlap, and pairwise return correlation after at least 20 common complete dates. Open residuals exclude a session from retirement evidence. This report is advisory and does not rewrite the existing performance history.

The generic `research_tools.g4_review.evidence` interface accepts evidence for established modules from any generation. It requires a verified birth date and independently verified daily coverage. It must not infer age from first appearance in a leaderboard, silently use LAST-based histories, combine accounting models or invent coverage. Dependency-protected source/control IDs (including PMID) remain protected.

Conservative retirement-candidate floors are **90 calendar days, 60 complete observed sessions, 100 closed trades and 20 traded sessions**. The first and second sample halves must both be negative, and a descriptive five-observation-block bootstrap upper 95% mean must be below zero. This is a research review flag, not automatic retirement and not a calibrated significance result. Repeated reviews, multiple comparisons, regime change and longer serial dependence can invalidate an apparent confidence result. Check signal/PnL complementarity, market regimes, material costs and producer dependencies before a separately reviewed output/evaluation change. Sparse established rules remain insufficient evidence even when their age is large. New generations cannot pass merely because one bad day contains many trades.

Generic evidence JSON:

```json
{
  "EXISTING_MODULE_ID": {
    "birth_date": "2026-01-01",
    "sessions": [{"day": "2026-10-06", "return_pct": -0.1,
      "closed_trades": 5, "coverage_verified": true,
      "unmarked": 0, "residual_positions": 0}]
  }
}
```

Run `python -m research_tools.g4_review.evidence --evidence evidence.json --as-of YYYY-MM-DD`. No automated retirement plan is produced or applied. Keep current protected modules active while accumulating coverage. A ranked daily review can inform investigation; it cannot supply missing observation days.

For edge discovery, freeze hypotheses, retain all outcomes and predeclare subsequent changes as new trials. Review activity/cost failures first; examine broad factor exposure, regime dependence and return overlap before interpreting the winner. A later confirmatory phase should use untouched future dates with multiplicity and sequential testing designed in advance. This initial implementation does not assert a validated durable edge.

## Validation and capacity

All 94 generation tests pass, including 14 dedicated G4 tests. The dedicated tests cover all 12 predicate fixtures; lagged fit isolation; registry opt-in; actual runner routing; price gaps and invalid prices; actual ASK anchoring; partial fills/exits; cash and cooldown recovery; quote age; paper contract; durable births; disabled draining; max hold; verified coverage; unknown/young/sparse/protected evidence; and frozen-manifest mismatch.

The final full-suite comparison ran 635 tests with G4 versus 621 on the untouched baseline. Both had the identical 37 failing/error test identities (15 failures, 22 errors): no additional failing identity was introduced in that comparison. The suite is not entirely green. Existing live/executor, historical registry-count and optional-module tests remain broken on the baseline. Docker build and production SSH tests were not run because those capabilities are unavailable here.

The local synthetic benchmark measured all 36 warmed scanners at about **0.110 s median / 0.136 s p95 per completed minute**, 36 durable synthetic entries in about **0.0049 s**, and a quote update in about **0.0050 s**. These exclude full-runner IPC/network/Fly contention and growing-ledger recovery. The scanner warmup allocation trace measured about 0.56 MB peak Python allocations; tracemalloc is not RSS. Synthetic timing and signals do not measure returns or certify production headroom.

G4 uses 21 distinct symbols drawn from existing universes, 36 bounded scanner instances, no new workers and no per-child network requests. Upper-bound activity is roughly 32 admissions per module per full session given the ten-minute global module cooldown, before other gates. Repeated metadata makes ledger growth material; do not delete or rotate authoritative G4 ledgers using legacy compaction that cannot reconstruct birth, book, cash and cooldown state. Monitor data disk and report latency. Preserve a durable off-host archive before designing any compatible compaction.

After deployment verify process health, population, immutable manifests and birth timestamps, zero broker capability, collector freshness, minute lag/worker errors, memory/CPU/storage and then observation coverage at the next full session. Reduce future experimental expansion if latency/storage becomes limiting; do not silently sample away the declared universes or select new-module losers from short histories.
