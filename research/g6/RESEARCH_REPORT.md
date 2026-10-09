# G6 evidence, implementation and validation

## Decision and provenance

Freeze the supplied October 7–9 ranking of 498 historical IDs. Retire exactly ranks 99–498 (400 IDs) from new paper entries and current performance visibility; retain ranks 1–98. Preserve all existing ledgers and allow already-open positions to complete. Historical outputs do not equal configured active registry counts. ENABLE_G6_PAPER=1 activates both retirement and the new population; setting it to 0 reverses the output retirement and new G6 admissions while recovered G6 positions remain serviceable.

Production evidence was captured 2026-10-09T21:40:55.880762+00:00. All supplied archive and deployed source hashes were checked; deployed sources matched cf7b7f77da8325b1647a9d7e9c2776e8e6683a0f. Frozen ranking history SHA256: 0c2ecaff2bfebb9af1789f69f009e67317e99e5135d41563a4a629f166ea1c9a. The retirement JSON contains all 498 ranked IDs and their frozen selection. The patch is incremental to the evidence-export patch plus the missing-git hotfix already applied locally; it must not reapply those additions.

## What the existing evidence supports

The machine-readable parent_audit.json covers 92 retained single-leg modules and separately STHEDGE2. It records source hashes, completed samples, period samples, wins/losses, expectancy, profit factor, median return, realized dollar drawdown, holding times, spreads, per-symbol and per-day contribution, rejection counts, quote/fill checks, representative trades and overlap. Four malformed main-ledger lines and five exits lacking entry timestamps were excluded from applicable calculations. See the JSON for module-specific coverage rather than treating missing evidence as clean evidence.

The table uses recorded nominal completed-fill dollars, not the displayed capital simulator's selectively accepted portfolio. Single-leg period means recorded exits on October 7–9 (timestamp date); the native hedge supplement uses opening dates. Profit factor uses the full available sample. Stress deducts an extra 10 basis points of entry and exit notional on each side. It is a sensitivity exercise, not a calibrated execution model.

| Module | Full / period fills | Full / period nominal P&L ($) | Full profit factor | Full P&L after extra cost ($) |
|---|---:|---:|---:|---:|
| PMID | 124 / 14 | -148.87 / 205.20 | 0.889 | -368.17 |
| PT315PLOW | 38 / 14 | -68.31 / 141.16 | 0.826 | -141.78 |
| G3MU150 | 2 / 2 | 136.21 / 136.21 | no losses | 133.33 |
| G3MU50 | 3 / 3 | 134.71 / 134.71 | 90.807 | 129.85 |
| G3MU75 | 3 / 3 | 134.71 / 134.71 | 90.807 | 129.85 |
| G3MW1130 | 8 / 8 | 119.37 / 119.37 | 2.002 | 106.39 |
| G3MW1230 | 3 / 3 | 112.81 / 112.81 | 5.821 | 107.93 |
| G3MRB20 | 4 / 4 | 108.95 / 108.95 | 49.422 | 102.71 |
| G3MR260 | 4 / 4 | 103.60 / 103.60 | 70.067 | 97.36 |
| G3MR270 | 4 / 4 | 103.60 / 103.60 | 70.067 | 97.36 |
| RS1 | 1799 / 323 | -2469.04 / -362.83 | 0.697 | -5942.14 |
| RS2 | 1898 / 353 | -2778.79 / -416.94 | 0.678 | -6443.08 |
| ARXP3S35 | 387 / 139 | -1615.73 / -474.35 | 0.624 | -2372.63 |
| PT315T75 | 195 / 55 | -518.03 / -28.95 | 0.712 | -904.29 |
| G2PGK10 | 49 / 37 | -79.67 / 54.49 | 0.752 | -176.67 |
| G2PGK5 | 49 / 37 | -81.48 / 50.78 | 0.707 | -178.14 |
| G2PGB1 | 35 / 26 | -6.43 / 39.35 | 0.933 | -33.51 |

PMID has 124 validated completed fills, only 14 in the selected period. Full nominal expectancy is negative; its selected period is positive. BIYA contributes $245.71 across the full sample, including two October 7 winners of about $98.21 and $93.50. Several leading G3 variants earn nearly all their selected profits on the same two BIYA events: G3MU150 has only two fills, both BIYA; G3MU50 and G3MU75 add one PCG loss. They represent correlated hypotheses with fragile samples. No named-symbol exclusions or winner-specific rules were added to G6.

There are 132 pairs with at least 80% exact-event overlap under the audit definition. Multiple profitable IDs are not multiple independent discoveries. RS1 and RS2 have many nominal losing fills despite a positive selected-period displayed capital result. The historical simulator can reject losses through finite cash, overlap and risk admission. Replaying all available main-engine days gives compounded capital changes of PMID -4.04%, PT315PLOW -1.14%, RS1 -5.62%, RS2 -5.35%, ARXP3S35 -5.05% and PT315T75 -4.97%. The JSON contains daily simulator results; these should not be conflated with nominal dollar totals or with a continuously funded historical portfolio.

STHEDGE2 has 329 completed groups, 25 in the period, about $331.84 total nominal profit and $95.96 period profit, full PF 1.350 and win rate 53.5%. Recorded entry/exit sides are correct, but its approximately $5,000 gross group size differs from $1,000 signal sizing. Displayed liquidity, complete per-leg quote timestamps, borrow fees and locates are not verified. This evidence does not justify adding G6 short or multi-leg execution.

Available validated single-leg fill arithmetic and recorded side/age/size fields did not reveal the specified violations. Older records frequently omit complete executable-book evidence. That limits any claim of realism. There is no complete market tape for rigorous replay, walk-forward selection, untraded opportunities, venue latency, borrow costs or regime robustness. No such results are claimed. The October 7–9 ranking is an in-sample selection; G6 is prospective paper research, with no historical G6 fills or inferred out-of-sample edge.

## Exactly 400 prospective modules

| Family | Admission cohorts | Modules | Evidence and hypothesis |
|---|---:|---:|---|
| Midday recovery | 15 | 120 | PMID and G3 midday leaders; test trend, rebound, price and time robustness |
| Low-price recovery | 10 | 80 | PT315PLOW/T75 and G2 recovery gates; test shock, price and time cohorts |
| Relative strength | 10 | 80 | RS1/RS2; distinguish absolute, market-relative, trend-fit and horizon filters |
| Volatility reversal | 5 | 40 | Normalized shock families; test shock bands and confirmation |
| Pullback | 5 | 40 | Relative leaders with completed-minute pullback and resumption |
| Retest | 5 | 40 | Relative leaders retaking bounded prior highs after a dip |
| Total | 50 | 400 | 240 raw-flash modules and 160 completed-minute modules |

Allocation emphasizes the best-supported recurring mechanisms while reducing weight on volatility reversal and new minute extensions. Counts are a research allocation, not proportional to proven returns. Each cohort has eight prespecified contrasts: conservative control, tighter cost/liquidity, more recovery room, faster exit, patient exit, smaller target, bid-progress checkpoint and quarter risk. population.json contains every exact ID, parameter, hypothesis, comparison, lineage, universe and source hash. All 400 configurations are semantically distinct. They are 50 groups of paired experiments, not 400 statistically independent discoveries; future signal overlap must be measured.

Flash modules own raw-event acceptance and pending rebound confirmation. They do not subscribe to parent fills. Minute modules share causal bounded market features but independently evaluate signals and own portfolios. Only completed contiguous minutes count; gaps reset feature histories. Warmup bars cannot create fills or credited observations. Fixed minute equity/fund universes and raw scanner price bounds are recorded per module. All entries are long equity paper trades.

Each module starts with its own $5,000 virtual cash, $1,000 nominal ceiling, 20% position cap, default 1% stop risk budget, 2% aggregate nominal stop risk, 2% stop, one position per symbol and 10-minute cooldown. RISK contrasts use 0.25% stop risk and 0.75% aggregate risk; these constraints can reduce the actual order below $1,000. This is independent experimental paper capital, not a deployable combined $2 million portfolio. Stop budgets do not guarantee loss limits through gaps.

Entry is contemporaneous ASK, exit BID. Contracts, positive uncrossed books, timestamps, maximum quote age (3 seconds or 1 second COST), spread, target room and displayed size are enforced. Participation is at most 25%, or 10% COST. Partial exits preserve residual quantities and cash. Max hold and progress checkpoints use actual fill times; stale exit quotes cannot create fills. Quote evidence, rejections and observations are recorded. There is no broker submission path for G6. The existing live-order function remains disabled and captured LIVE_ORDER_PLACEMENT_ENABLED=0 remains unchanged.

First activation durably records all 400 births and the exact retirement population. Restart validates frozen configuration and recovers only valid prospective ledger records. No pre-birth trades are created. Existing files are retained. Births occur after the October 9 regular session; the October 9 daily report may show no G6 rows. Tracker status still verifies 400 modules. The first eligible regular-session day is Monday October 12; report visibility requires a birth eligible for that report cutoff.

## Counts and dependencies

The captured performance report has 490 visible modules: 392 selected retired outputs and 98 retained outputs. The configured baseline main registry has 496 enabled outputs in the reviewed flag configuration: 395 retired and 101 remaining. G6 makes that main-registry count 501 (101 remaining plus 400 new). Ninety-four of the 98 frozen retained IDs are main-registry outputs; the other four are native-worker outputs. Seven other main outputs were absent from the historical ranking and remain enabled.

Main plus the four inspected native worker candidate lists totals 507 after replacement, including their unranked candidates. This is a scoped configured-candidate count, not a global running-worker census. Production verification reports registry, native candidate lists, observed processes and report counts separately. Source producers required by retained routes are protected from evaluation removal even when their retired paper outputs are blocked; all paper entry points also enforce retirement, while existing exits remain available.

## Validation and production limits

The focused standard-library suite passes 197 tests, covering G1–G6, reporter integration, retirement dependencies, direct tracker bypass protection, native worker wiring, partial fills, recovery, stale/future quote rejection, prospective births and independent parent-setup handling. All 400 modules accept valid synthetic scenarios. Docker build checks enforce 240 flash and 160 minute registrations without failures. The unchanged microstructure10 definition-count test fails on the original baseline as well: it expects ten active definitions after prior pruning left one. Its assertion is preserved and documented; the focused runner excludes that known baseline failure.

The recorded local synthetic benchmark averages about 0.0394 seconds per minute snapshot, maximum 0.142 seconds, peak traced feature memory 289,302 bytes. Tracking and durably accepting 400 independent synthetic admissions took about 0.131 seconds. These measurements exclude network and worker IPC, and do not establish production capacity. benchmark.json contains exact scope and measurements.

Deployment has not been performed here. Production verification checks opt-in flag, exactly 400 births and registrations, retirement activation, source hashes, expected git build revision, paper safeguards, process presence and refreshed reporter diagnostics. Actual load, latency, fresh market observations and future fill economics require production observation. Keep G6 paper-only while collecting those results. No profitability or successful deployment is claimed.

Reproduce: python3 -m research_tools.g6.run_checks; python3 -m benchmarks.benchmark_generation_six. Evidence analysis: python3 -m research_tools.g6.analyze_evidence --help, then supplement_audit with the extracted evidence directory and generated audit JSON. See GENERATION_SIX_DEPLOY.md for patch and deployment commands.
