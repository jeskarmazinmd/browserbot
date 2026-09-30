# First-generation frozen BA research implementation

Implemented on `modular-bot`, based on source commit `8698eeeb254fa2df642b367c9cf26ae10feb5c26`. No production deployment or real-money activation was performed.

## Selection and coverage

51 modules: 43 flash/rebound modules and 8 completed-minute modules. Selection uses the user-requested candidates and the recent two-day positive candidate list recovered from the prior discussion. The original live ledgers were not independently recomputed in this session. Those historical returns select hypotheses only: they are never copied into the new modules' prospective results.

The set covers the specific chat-mode proposals: PT315G1525 + QV4XU1S50V8, PT315T75 + QV4XU1S3, QV4XU1S50V8 + QV4VB608, 2-of-3 PT315G1525/QV4XU1S50V8/PMID, and 2-of-3 PT315T75/QV4XU1S3/TRENDX2. It also covers 3-of-3, 3-of-4, deduplicated unions, agreement weighting, portfolio size, stop risk, position caps, and limited parameter variants. It does not enumerate every pair or Cartesian product of all sizing settings.

Fixed-order controls at $1000 provide prospective cohort comparisons for $500/$1500/$2500 orders. A matched 3% stop control is used for the 5%/10%/15%/20%/25%/33% position-cap sweep: with a 5% stop and 1% equity risk, caps above 20% would usually be nonbinding and duplicate the control. Portfolio-equity variants span $2500/$5000/$10000/$25000; risk variants span 0.10%/0.20%/0.50%/1.00%. Q-quality risk/cap checks test transfer across source families without multiplying the whole grid.

## Complete catalog

Unless specified otherwise, each module has its own daily $5000 cash portfolio, requests one $1000 order per accepted setup, and shares available cash across all its symbols. Composite constituents contribute votes to one order; they do not each place an order. Stop and target policies are explicit and uniform within each composite. “P gain” means PT315G1525: require 0.25% bid-based MFE by 15 minutes, original target, and 5% stop unless overridden. “Q quality” means QV4XU1S50V8: >=4.25 and <=8 volatility units, >=1% executable original-target upside, <=0.50% spread, original target, and 5% stop unless overridden.

| Strategy ID | Reporting ID | Frozen sources | Exact hypothesis |
|---|---|---|---|
| `G1BB15` | `G1BB15BA` | `BRK20` | Breakout buffer 0.15% rather than 0.10%; bounded range unchanged |
| `G1BN1500` | `G1BN1500BA` | `BRK20` | Frozen breakout $1500 orders in a $5k cash portfolio |
| `G1BN500` | `G1BN500BA` | `BRK20` | Frozen breakout $500 orders in a $5k cash portfolio |
| `G1LQ` | `G1LQBA` | `PT315PLOW`, `QV4UP125` | P <=$5 confirmation plus Q >=1.25% executable upside; 5% stop/original target |
| `G1MQ` | `G1MQBA` | `PMID`, `QV4VB608` | Midday P confirmation plus Q 6-8 volatility band; 5% stop/original target |
| `G1PG10` | `G1PG10BA` | `PT315G1525` | P gain requirement assessed at 10m rather than 15m |
| `G1PG20` | `G1PG20BA` | `PT315G1525` | P gain requirement assessed at 20m rather than 15m |
| `G1PGC10` | `G1PGC10BA` | `PT315G1525`, `PT315S30` | P gain plus 3% stop, $5k portfolio, 1% equity stop risk, 10% position cap |
| `G1PGC15` | `G1PGC15BA` | `PT315G1525`, `PT315S30` | P gain plus 3% stop, $5k portfolio, 1% equity stop risk, 15% position cap |
| `G1PGC25` | `G1PGC25BA` | `PT315G1525`, `PT315S30` | P gain plus 3% stop, $5k portfolio, 1% equity stop risk, 25% position cap |
| `G1PGC33` | `G1PGC33BA` | `PT315G1525`, `PT315S30` | P gain plus 3% stop, $5k portfolio, 1% equity stop risk, 33% position cap |
| `G1PGC5` | `G1PGC5BA` | `PT315G1525`, `PT315S30` | P gain plus 3% stop, $5k portfolio, 1% equity stop risk, 5% position cap |
| `G1PGCCTL` | `G1PGCCTLBA` | `PT315G1525`, `PT315S30` | P gain plus 3% stop: $5k, 1% equity risk, 20% cap; matched cap-sweep control |
| `G1PGE10000` | `G1PGE10000BA` | `PT315G1525` | P gain portfolio $10000; 1% stop risk and 20% cap unchanged |
| `G1PGE2500` | `G1PGE2500BA` | `PT315G1525` | P gain portfolio $2500; 1% stop risk and 20% cap unchanged |
| `G1PGE25000` | `G1PGE25000BA` | `PT315G1525` | P gain portfolio $25000; 1% stop risk and 20% cap unchanged |
| `G1PGN1000` | `G1PGN1000BA` | `PT315G1525` | PT315G1525 fixed $1000 order; capacity and $5k cash competition |
| `G1PGN1500` | `G1PGN1500BA` | `PT315G1525` | PT315G1525 fixed $1500 order; capacity and $5k cash competition |
| `G1PGN2500` | `G1PGN2500BA` | `PT315G1525` | PT315G1525 fixed $2500 order; capacity and $5k cash competition |
| `G1PGN500` | `G1PGN500BA` | `PT315G1525` | PT315G1525 fixed $500 order; capacity and $5k cash competition |
| `G1PGR10` | `G1PGR10BA` | `PT315G1525` | P gain $5000 portfolio with 0.10% equity stop risk and 20% cap |
| `G1PGR20` | `G1PGR20BA` | `PT315G1525` | P gain $5000 portfolio with 0.20% equity stop risk and 20% cap |
| `G1PGR50` | `G1PGR50BA` | `PT315G1525` | P gain $5000 portfolio with 0.50% equity stop risk and 20% cap |
| `G1PGRCTL` | `G1PGRCTLBA` | `PT315G1525` | Frozen P gain $5k portfolio, 1% equity stop risk, 20% position cap |
| `G1PGS3` | `G1PGS3BA` | `PT315G1525`, `PT315S30` | P gain checkpoint with 3% rather than 5% disaster stop |
| `G1PGT75` | `G1PGT75BA` | `PT315G1525`, `PT315T75` | P gain checkpoint combined with 75% target distance |
| `G1PQ2` | `G1PQ2BA` | `PT315G1525`, `QV4XU1S50V8`, `PMID` | 2-of-3 P gain, Q quality, midday P admission with uniform P gain exit; time stratification |
| `G1PQ3` | `G1PQ3BA` | `PT315G1525`, `QV4XU1S50V8`, `PMID` | 3-of-3 P gain, Q quality, midday P admission with uniform P gain exit; stricter time/quality intersection |
| `G1PQ34` | `G1PQ34BA` | `PT315G1525`, `QV4XU1S50V8`, `QV4VB608`, `PMID` | 3-of-4 P gain, Q quality, Q 6-8 band, midday P; uniform P gain exit |
| `G1PQG` | `G1PQGBA` | `PT315G1525`, `QV4XU1S50V8` | P gain-checkpoint entry plus Q upside/spread/volatility quality; P 15m gain exit |
| `G1PQT` | `G1PQTBA` | `PT315T75`, `QV4XU1S3` | P reduced-target entry plus Q >=1% upside/3% stop admission; P 75% target exit |
| `G1PQT2` | `G1PQT2BA` | `PT315T75`, `QV4XU1S3`, `TRENDX2` | Flash-triggered 2-of-3 P 75% target, Q >=1% upside/3% stop admission, fresh completed-minute trend; uniform P 75% target exit |
| `G1PQT3` | `G1PQT3BA` | `PT315T75`, `QV4XU1S3`, `TRENDX2` | Flash-triggered 3-of-3 P 75% target, Q >=1% upside/3% stop admission, fresh completed-minute trend; uniform P 75% target exit |
| `G1PQU` | `G1PQUBA` | `PT315G1525`, `QV4XU1S50V8` | Deduplicated P gain OR Q quality admission with uniform P gain exit |
| `G1PQUW` | `G1PQUWBA` | `PT315G1525`, `QV4XU1S50V8` | P/Q union: $1000 for one vote, $2000 for two votes; one deduplicated order |
| `G1PQW2` | `G1PQW2BA` | `PT315G1525`, `QV4XU1S50V8` | P/Q agreement: $2000 only on two votes; compare G1PQG fixed $1000 |
| `G1QQ2` | `G1QQ2BA` | `QV4XU1S50V8`, `QV4VB608` | Within-Q quality AND 6-8 volatility band; quality exit policy |
| `G1QVC10` | `G1QVC10BA` | `QV4XU1S50V8` | Q quality $5k portfolio, 1% equity stop risk, 10% cap; cross-family cap check |
| `G1QVN1000` | `G1QVN1000BA` | `QV4XU1S50V8` | QV4XU1S50V8 fixed $1000 order; capacity and $5k cash competition |
| `G1QVN1500` | `G1QVN1500BA` | `QV4XU1S50V8` | QV4XU1S50V8 fixed $1500 order; capacity and $5k cash competition |
| `G1QVN2500` | `G1QVN2500BA` | `QV4XU1S50V8` | QV4XU1S50V8 fixed $2500 order; capacity and $5k cash competition |
| `G1QVN500` | `G1QVN500BA` | `QV4XU1S50V8` | QV4XU1S50V8 fixed $500 order; capacity and $5k cash competition |
| `G1QVR20` | `G1QVR20BA` | `QV4XU1S50V8` | Q quality $5k portfolio, 0.20% equity stop risk, 20% cap; cross-family risk check |
| `G1QVRCTL` | `G1QVRCTLBA` | `QV4XU1S50V8` | Frozen Q quality $5k portfolio, 1% equity stop risk, 20% position cap |
| `G1QVS3` | `G1QVS3BA` | `QV4XU1S50V8`, `QV4XU1S3` | Q quality entry with 3% rather than 5% stop |
| `G1QVU125` | `G1QVU125BA` | `QV4XU1S50V8` | Q quality entry with 1.25% rather than 1% executable upside |
| `G1TB150` | `G1TB150BA` | `TRENDX2` | Trend 30m return >=1.5% rather than 1.2%; other parameters frozen |
| `G1TB2` | `G1TB2BA` | `TRENDX2`, `BRK20` | Same-symbol trend AND bounded 20m breakout; trend 0.9% target/0.65% stop |
| `G1TBU` | `G1TBUBA` | `TRENDX2`, `BRK20` | Deduplicated trend OR bounded breakout; uniform trend exit policy |
| `G1TN1500` | `G1TN1500BA` | `TRENDX2` | Frozen trend $1500 orders in a $5k cash portfolio |
| `G1TN500` | `G1TN500BA` | `TRENDX2` | Frozen trend $500 orders in a $5k cash portfolio |

## Signal semantics and independence

All source predicates, thresholds, exit policies, and universes are literal frozen definitions in the new generation's implementation. There are no imports, callbacks, registry lookups, positions, or signal streams from source strategies. Source IDs and source commit are lineage/audit labels. The new modules share stateless frozen generation code and established market-data/execution infrastructure; they do not require any source strategy to execute.

Flash modules each receive their own scanner configuration, flash signature, pending rebound, and confirmation state. Baseline confirmation is 0.1% rebound, a 600-second pending timeout, and >=0.20% remaining final-target upside, including an executable-ask check. Each composite counts votes again at the same-cycle ask/bid. A union admits any qualifying constituent; it does not accidentally require every constituent's spread or upside gate. Entry price/stop/target geometry must also be executable for the module's uniform policy.

The two hybrid PT/Q/trend modules are **flash-triggered**. Trend votes are calculated from 31 contiguous completed-minute observations ending immediately before confirmation, for the same symbol in the frozen 32-symbol universe. Missing minutes or stale trend evidence give no trend vote. These modules do not listen to TRENDX2 outputs, and they do not independently enter trend-only setups.

Minute modules own bounded 66-observation histories. Predicates use frozen TRENDX2 and BRK20 thresholds. Gaps reset history; repeated or regressed observations are ignored. Consensus compares per-symbol predicates, rather than whether the parents happened to select the same global top candidate. Each module emits at most one highest-score symbol per minute. The trend/breakout union uses one deduplicated candidate stream and one uniform trend exit policy.

PMID overlaps the P family; both Q-quality and Q-band overlap each other. The 2-of-3/3-of-3/3-of-4 flash votes are correlated filters and time stratification tests, **not independent pieces of statistical evidence**. No extra credibility is awarded merely because there are three votes.

Source deletion tests actually copy the strategy package, delete PT/Q/PMID/TRENDX2/BRK20 source files and both old research-family files, then load the new registry/manifest in a fresh process. Source mutation and source pruning/output-disable tests also prove unchanged new signals. Optional source loading allows removed source files to disappear without preventing frozen leaves from registering; present existing modules retain their previous code and behavior.

## Prospective start and accounting

No module has an official prospective return yet because this implementation has not been deployed. `LIVE` here describes the existing runner using live market data; all new modules remain paper-only. The runner never routes a new module to historical LAST replay accounting, and it does not initialize research births during replay.

On the first LIVE paper-tracker activation, each new ID receives a durable timestamp in `paper_generation_one_bidask_independent_births.json`, at least as late as creation. Restart retains those timestamps. Signals before birth, after processing time, or more than 120 seconds old are rejected. Corrupt birth provenance fails closed. No backfill or copying of source trade records occurs.

Entries buy at fresh executable asks and are limited to displayed ask quantities. Exits sell at fresh executable bids and are limited to displayed bid quantities. Partial exits retain remaining shares, credit only actual proceeds, keep the exit decision sticky, and finish on later supported book observations. Final exit prices are the quantity-weighted average of actual bid fills. Entries, partial exits, final exits, cash movements, dynamic exit state, and book consumption survive restart; the fill ledger remains authoritative.

Within a module, displayed book consumption is keyed by symbol, side, and quote timestamp, so neither several constituents nor several positions reuse the same observed liquidity. Older books cannot replenish it. Timestamp-less books cannot support a shared-portfolio fill. Risk sizing uses actual ask-minus-stop distance, available cash, and the specified position cap; fixed sizing and agreement weighting are cash limited. Equity for sizing is cash plus deployed cost, without using an unobserved profitable mark to increase size. Daily cash resets reserve the cost of any unliquidated overnight residual.

New records use their own `paper_generation_one_bidask_independent_*` ledger/state files. Existing ledgers and prospective histories are not rewritten. The all-engine report gives every activated new strategy its independent `BA` ID and uses actual quantities and proceeds, without retroactively resizing the trades. It includes lineage and activation metadata. No-trade modules have `no_entries` status; an unmarked open portfolio is omitted and audited rather than presented as a falsely complete return. Reports retain the existing entry-day attribution convention and do not claim cross-day compounding.

Every experiment is a separate counterfactual portfolio. Their returns or fills must not be added together as if they were sleeves of one account; reporting explicitly sets `portfolio_combinable=false`. Within any one union/consensus experiment, shared capital and displayed liquidity are enforced.

## Validation

Focused command:

```bash
PYTHONPATH=tests python -m unittest test_generation_one test_independent_bidask_tracker test_independent_multi_leg_bidask test_output_switches test_performance_pruning_dependencies test_live_l1_cache test_pt325315_research test_qv425_a_research test_bidask_paper_outcome_tracker test_bidask_multi_leg_paper_tracker test_paper_outcome_tracker test_nh015_bidask_engine_integration
```

65 tests passed, including 30 new generation tests. Coverage includes literal source-rule boundary/exit-policy parity, actual source-file deletion, source mutation/pruning/disable independence, registration and manifest metadata, persistent worker-shard construction, hybrid freshness/gaps, voting at the ask, strict JSON metadata, prospective birth/restart/replay guards, cash/risk sizing, entry and exit partials, stale/unknown books, shared liquidity across positions, authoritative-ledger recovery, and reporting quantities/denominators/output switches.

Broader command:

```bash
python -m unittest discover -s tests
```

The untouched baseline ran 535 tests with 15 failures and 23 errors. The completed implementation ran 565 tests with the same 15 failures and 23 errors: 527 tests passed, and no additional failing test names appeared. Existing failures include old registry-count/pruning assumptions, C3 execution fixtures, unavailable executor/installer components, Schwab transport fixtures, and legacy reporting/options expectations. Existing tests were not modified or weakened, and source behaviors were not changed to repair unrelated baseline failures.

Offline signal-cost check: 43 flash modules across 1000 raw candidates took 0.073 seconds; 8 minute modules across 1000 snapshots of the full 32-symbol universe took 0.987 seconds in this workspace. This is a local signal-evaluation benchmark, not a production load guarantee; it excludes network, disk persistence, actual active-position volumes, and broker latency.

`py_compile` and `git diff --check` passed. The resulting diff was reviewed for source-module edits, source-output dependence, changes to existing execution behavior, retroactive credit, production deployment, and real-money enablement. None were introduced.

## Execution and research limitations

Top-of-book evidence supports a conservative displayed-size paper model, not guaranteed broker fills. There is no L2 depth, queue priority, hidden liquidity, routing latency, adverse-selection model, or market-impact model. A new quote timestamp is treated as fresh displayed evidence; it does not prove a real venue replenished exactly that many shares. Entries and exits therefore remain experiments requiring prospective observation and, later, a separately approved execution study.

Fees, taxes, dividends, corporate actions, and multi-day financing are not modeled by this new tracker. Open marks follow the existing all-engine quote loader and are hypothetical bid closes; they are not fills and cannot establish liquidation of an entire residual position. Stops can gap, and a lack of supported bid liquidity can leave a partial position open through EOD. The smaller equity/risk configurations can generate zero-share rejections, which are counted.

The two-day winner list is a short discovery window; no significance or durable profitability is claimed. Overlapping voting filters remain correlated. Fix the cohort and evaluate prospective sample size, turnover, drawdown, rejection/partial rates, and per-symbol concentration before expanding or pruning based on results. No old modules were trimmed in this change.

## Files changed

- `strategies/generation_one.py`: immutable flash catalog, frozen raw/confirmation/executable predicates and exits, provenance.
- `strategies/generation_one_minute.py`: frozen trend/breakout catalog, owned history and worker-importable classes.
- `strategies/generation_one_market.py`: fresh raw-market trend observation for hybrid confirmation.
- `strategies/optional_source.py`: safe loading when an explicitly referenced source file is absent.
- `strategies/registry.py`: new flash and minute registration; source-file removal tolerance.
- `strategies/manifest.py`: independent discovery/metadata for new IDs.
- `strategies/independent_flash_filters.py`: allow absent old source families without blocking the new registry.
- `generation_one_paper_tracker.py`: scoped prospective BA portfolios, fills, shared book, cash, risk, persistence.
- `paper_outcome_tracker.py`: preserve additional new-generation optional audit/state fields.
- `live_strategy_runner.py`: new paper routing, quote updates, hybrid raw features; replay exclusion.
- `reporting/generation_one_performance.py`: actual-fill prospective reporting.
- `reporting/all_engine_performance.py`: independent research module integration.
- `Dockerfile`: package the new paper tracker; no deployment performed.
- `tests/test_generation_one.py`: 30 new focused regression/independence tests.
- `GENERATION_ONE_CATALOG.json`: machine-readable full frozen catalog.
- `GENERATION_ONE_RESEARCH.md`: this implementation and validation report.
