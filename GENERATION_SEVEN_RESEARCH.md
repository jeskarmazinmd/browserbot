# G7 research and engineering report

**Status: two paper experiments implemented and validated; deployment and production activation are pending.**

Source branch: `jeskarmazinmd/browserbot`, `modular-bot`. Reviewed baseline: `01ad5a62cc2d026a362b490ef30d6f5a982be580`. The GitHub discovery endpoint returned an empty list; direct access and a branch-specific clone succeeded.

## Evidence and methods

The daily history has 17 weekday sessions from September 18 through the October 12 intraday snapshot. The full weekday report union is 1107 module names. The latest report has 449 modules at 2026-10-12T16:19:07.548927+00:00; neither is an active-registry count. October 10–11 were excluded from trading-session comparisons.

Seven independent long-paper ledgers were streamed in full, not restricted to the recent five days. Separately, the complete supplied native statarb ledger was checked, including August history. The seven quote archives cover October 2, 5, 6, 7, 8, 9 and an incomplete October 12. Archive and ledger hashes accompany the research results. The legacy LAST tape had been trimmed to start at 15:47 UTC, so it cannot resolve the earlier MNDR stop events.

Daily percentages below are sums of daily equal-start returns, not compounded wealth. Nominal ledger P&L is a separate measure: main-engine reported performance resizes recorded opportunities through a finite-capital simulation; generation ledgers retain their actual filled quantities. Missing module-days are not inserted as zero. Generation reporters do not supply maximum drawdown; absent drawdowns were treated as unknown.

Four malformed lines exist inside the supplied main independent ledger (lines 6105, 101281, 119875 and 165242). They were counted and excluded from parsed evidence, never repaired or overwritten. Exported files were copied sequentially, so ledger event times and report times differ. Open positions were kept separate from completed-trade statistics.

## A. Evidence-weighted parent shortlist

Five long-paper parents warrant further research. Ranking balances depth, costs, concentration and mechanism; it differs deliberately from sorting two-trade G3 winners to the top.

| # | Parent | Daily-return sum | Completed trades | Trade sessions | Nominal P&L | Profit factor | Reason / limitation |
|---:|---|---:|---:|---:|---:|---:|---|
| 1 | CMDROT1BA | +1.8236% | 75 | 15 | $+91.15 | 1.405 | Broadest reasonably positive executable single-leg evidence; rotation leader selection is interpretable. |
| 2 | CMDGAS1BA | +0.9744% | 13 | 8 | $+48.72 | 2.404 | Highest profit factor among the deeper candidates, but only 13 trades and every win is UNG exposure. |
| 3 | CMDBRD1BA | +0.6538% | 69 | 15 | $+31.67 | 1.168 | 69 trades across 15 sessions; diversified commodity breadth mechanism, thin edge and cost sensitivity. |
| 4 | PT315H12BA | +0.8810% | 15 | 7 | $+40.73 | 1.508 | Positive exploratory afternoon-hour cohort, only 15 trades; insufficient evidence for a large flash population. |
| 5 | QV4XU1S50V8BA | +0.5602% | 42 | 11 | $+25.43 | 1.082 | 42 trades across 11 sessions, low individual-symbol winner concentration; profit factor only 1.08 and high spread sensitivity. |

An additional hypothetical 10 basis points per side changes nominal P&L to: CMDROT1 −$50.70, CMDGAS1 +$22.87, CMDBRD1 −$100.88, PT315H12 +$10.85 and QV4XU1S50V8 −$48.85. This is a cost stress, not a forecast of actual slippage. The small positive margins do not establish a robust deployable edge.

STHEDGE2 leads the report-return ranking (+3.3936% over the available daily reports), and its full ledger has 329 completed groups / $331.84 nominal P&L / profit factor 1.350. STRESMOM1 has 97 groups / $175.70 / profit factor 1.223. Both use roughly $4,500–$4,700 gross group notionals; their source does not enforce the required per-leg displayed liquidity and freshness, and does not verify borrow fees or short locate. They are research watchlist mechanisms, not qualified G7 long-paper parents.

G3MU150 has only two completed trades in one traded session, both from one symbol; G3MRB20 has four trades in two sessions and about 90% of gross wins from one symbol. G3QV425X600 has four trades. Near-identical variants sharing these opportunities are not independent confirmations. G6 is also too young; its 400 outputs are paired cohort experiments and must not be treated as 400 discoveries.

PMID remains a protected unchanged control, but its full ledger is −$148.87 nominal P&L with profit factor 0.889 and a −$162.54 worst trade. Its attractive recent days did not justify selecting it over the deeper history. The large-loss G2 candidates similarly did not qualify as promising parents.

## B. October 12 loss reconstruction

| Module | Intraday report return | Completed captured trades | Completed nominal P&L | MNDR P&L | YMAT P&L |
|---|---:|---:|---:|---:|---:|
| G2PGE2BA | -10.7022% | 17 | $-506.41 | $-269.84 | $-186.55 |
| G2PGU100BA | -10.1846% | 12 | $-482.73 | $-326.05 | $-167.72 |
| G2PGU200BA | -8.9900% | 10 | $-449.50 | $-326.14 | $-123.36 |
| PT315FD200BA | -8.7954% | 10 | $-453.96 | $-340.94 | $-127.60 |
| PT315PLOWBA | -8.7814% | 10 | $-458.92 | $-328.24 | $-79.83 |
| PT315T75BA | -1.9516% | 16 | $-99.33 | $-117.58 | $-7.20 |
| PMIDBA | -0.5424% | 0 | $+0.00 | $+0.00 | $+0.00 |

These figures intentionally do not force ledger P&L to equal an earlier report. Main reports are risk-sized resimulations; generation reports include open marks; the source files have different capture times. PMID had two open positions (HIMZ and AAOX) and no completed October 12 trades in this bundle. Its reported loss is not a completed loss.

### Verified MNDR examples

| Account | Entry UTC | Ask | Qty | Stop | Exit / final liquidation UTC | Exit bid or VWAP | P&L |
|---|---|---:|---:|---:|---|---:|---:|
| PT315PLOW | 15:29:22.711 | $4.84 | 206 | $4.693 | 15:36:00.954 | $3.89 bid | −$195.70 |
| PT315FD200 | 15:29:22.131 | $4.83 | 207 | $4.693 | 15:36:00.954 | $3.89 bid | −$194.58 |
| G2PGE2 | 15:28:36.190 | $4.81 | 207 | $4.693 | 15:36:00.958 partial / 15:44:03.911 final | $3.907923 VWAP | −$186.73 |

G2PGU100 and G2PGU200 took the same MNDR setup and also lost $186.73. This is shared symbol/signal exposure in separate counterfactual portfolios, not several independent market failures.

G2PGE2 sold 200 shares at $3.89, with 7 shares remaining. It later sold those 7 at $4.42. The aggregate proceeds ($808.94) minus the $995.67 entry notional reconcile to −$186.73; the final VWAP is not the final quote bid. Entry age was about 1.47 seconds and initial stop-fill age about 2.13 seconds. The nominal entry-to-stop risk was $24.22; realized loss was about 7.7 times that amount. A stop level is a trigger to seek executable liquidity, not a guaranteed fill price.

| Archived observation UTC | MNDR bid | Displayed bid shares | Interpretation |
|---|---:|---:|---|
| 15:34:59.854 | $4.83 | 300 | Above the $4.693 stop |
| 15:35:58.715 | $3.89 | 300 | Sharp fall below the stop; rich quote timestamp is 15:35:56.634 |
| 15:36:59.850 | $3.89 | 0 | No displayed bid fill capacity |
| 15:37–15:39 samples | $3.89 | 0 | Stale / unavailable book thereafter |

The archive supports abrupt adverse movement and subsequent liquidity deterioration. Minute samples do not prove exactly when an intermediate stop-crossing quote existed, whether a trading halt occurred, or every runner scheduling delay. These remain unresolved, not silently labeled simulation defects. Earlier MNDR losses similarly show a bid around $4.57 near 14:44 followed by $3.96 near 14:45.

Repeated entries compounded damage: G2PGE2’s completed MNDR losses total $269.84 and YMAT losses $186.55, with some profitable re-entries mixed in. Cooldowns must be assessed against those profitable opportunities as well as the losses. Banning MNDR by name after seeing today would be hindsight, not a transferable rule.

## C–D. Evolution and defensive findings

Rotation and breadth have the deepest reasonably positive long-paper evidence. Their opportunity is causal persistence / cross-horizon agreement and protection of established bid gains. Generic spread tightening is not automatically beneficial: recorded-opportunity screens turned PT315H12 from +$40.73 to −$7.03 and QV4XU1S50V8 from +$25.43 to −$5.24 while removing many trades. Those screens keep parent exits and quantities; they are not a full replay of a new strategy.

Thirteen distinct minute mechanisms were replayed across three development sessions and three retrospective validation sessions. The existing runner’s 30-minute admitted-symbol cooldown was included before final selection; omitting it materially changes the comparisons. Rotation continuation then worsened validation return, while three-minute leader persistence sacrificed too much development profit. Broad rotation filtering retained too few profitable opportunities. Gas relative/cost variants made no observable difference on this sample; gas continuation nearly eliminated trading. These were rejected rather than added to fill a quota.

## E. G7 population

| # | Module | Parent | Track | Modification | Intended improvement | Main downside |
|---:|---|---|---|---|---|---|
| 1 | G7BRDSTABLE | CMDBRD1 | A | Original 15-minute commodity breadth admission plus positive-return breadth ≥65% over five minutes | Avoid a broad older trend whose recent breadth has deteriorated | Fewer trades; gross profitable opportunities also decline; not every day improves |
| 2 | G7ROTPROTECT | CMDROT1 | B | Once executable bid reaches +0.50%, request exit on a 0.35% pullback from the highest fresh bid | Preserve established gains during momentum deterioration | Can truncate continuation; does not prevent gaps before activation |

Each experiment owns an independent instance of its parent evaluator, distinct setup identity, cash, positions, displayed-book consumption, ledgers and immutable first-activation birth. No parent signal subscription, historical G7 outcome or broker route is created. Parent files remain unchanged. Both keep $5,000 equal-start daily capital, 1% nominal per-trade sizing and a 20% per-order cap. These are experimental paper tests, not recommended live strategies.

## F. Historical comparisons

The parent strategy implementation is unchanged in each replay. All portfolios use the same executable bid/ask, displayed liquidity and finite-capital replay mechanics, session window, and admitted-symbol cooldown. Archive final-minute observations become available only at the next minute boundary; entries and exits use the stored executable book, never LAST prices or idealized stops. Parent raw target/stop geometry is retained. Source history resets and missing-symbol handling are explicit in the G7 evaluator.

Development: October 2, 5, 6. Retrospective validation: October 7, 8, 9. October 12 is diagnostic only. Because parent selection and earlier screens already consulted these dates, validation is **not an untouched independent holdout**. The independent test begins after durable production activation. Minute sampling differs from live tick-level exits, especially for trailing protection.

| Pair | Development parent → G7 | Validation parent → G7 | Completed trades, six sessions | Worst validation day, parent → G7 |
|---|---:|---:|---:|---:|
| BRD / G7BRDSTABLE | -0.0346% → +0.1676% | -0.8376% → -0.4592% | 43 → 30 | -0.5182% → -0.5402% |
| ROT / G7ROTPROTECT | +0.7882% → +0.8698% | -1.2880% → -0.9268% | 34 → 33 | -0.8010% → -0.5850% |

Rotation protection improves validation’s worst sampled intraday drawdown from 0.9290% to 0.7132%, but its worst trade remains −$16.68. Breadth confirmation improves development’s worst drawdown from 0.6793% to 0.6308%, while validation’s worst drawdown worsens from 0.7529% to 0.7820%. This is an evolution candidate, not a universally safer account. It retains roughly two-thirds of parent gross winning P&L, so the opportunity cost must be checked prospectively.

On October 12, rotation protection and its replay control both return −0.3150% over two completed trades. Both breadth portfolios have three residual positions and one unavailable mark at archive cutoff, so no complete October 12 return is claimed. No apparent success on October 12 was used to manufacture acceptance. Full per-day return, drawdown, trade counts, profit factors, expectancy, worst trades and rejections for all thirteen hypotheses are in `research_tools/g7/results/replay.json`.

## Risk / reporting findings

G2PGE2, G2PGU100 and G2PGU200 explicitly configure `risk_fraction=None`, `portfolio_risk_fraction=None` and `one_position_per_symbol=False`. They use fixed $1,000 notional admission. Their approximately 20% initial-capital orders therefore do not enforce a universal 1% risk baseline, a daily stop, or a one-symbol portfolio limit. This is a configuration distinction requiring separate review, not a reason to rewrite their control history. G7 explicitly enables the requested risk sizing.

Per-trade nominal risk, daily cumulative loss, simultaneous exposure and gap risk are different quantities. Repeated stopped trades can lose more than 1% in a day; gap executions can lose more than the nominal risk of an individual trade. G7 profit protection adds an exit trigger; it makes no guaranteed-loss claim.

A reporting limitation also exists: the original G6 open-mark wrapper requires timestamped books, but the all-engine caller supplies `equity_quote`, which returns only bid, ask and source. The captured G6 diagnostic reports 28 unmarked positions. Missing returns must not be scored as zero. G7 reporting receives the full timestamped live-L1 quote; the older G6 reporter was left unchanged and this limitation documented for a separate correction.

## G. Engineering validation and production status

G7 tests cover isolated accounts and source evaluators, ask/bid fills, partial exits, no reuse of the same displayed book after restart, trailing-high persistence, executable gap stops, stale/future quote rejection, paper-only routing, immutable births/manifests, malformed-ledger failure, mark-unavailable reporting, causal completed-minute timestamps and replay/runtime fill agreement. Historical-prefix verification permits normal appends but detects truncation or rewriting.

The G6 focused regression suite passes 197 tests. G7 has 13 passing tests. Two minute-pipeline tests fail identically on the unchanged baseline commit: an old hardcoded registry count (38 versus 48) and an obsolete expected August signal log. Their assertions were preserved, not weakened to make G7 appear successful.

Synthetic G7 benchmark: about 0.03 ms mean evaluation for both strategies; two durable admissions took about 3.4 ms in this environment. G6 benchmark still admits all 400 synthetic modules. These measurements exclude network and worker IPC and are not production performance guarantees.

With the existing G3 retirement plan and G3–G6 flags, the local registry has 503 active main outputs: the prior 501 plus two G7 outputs. No retirement manifests, parent source files or old ledger files were changed. Runtime hash manifests are refreshed for the shared integration files so the existing G6 verifier continues checking the intended deployed build.

**Push and deployment are pending.** GitHub direct reading works, but the write operation returned HTTP 403 `Resource not accessible by integration`. This environment also has no authenticated Fly CLI. The tested changes are packaged as a local Git commit/bundle for a fast-forward update to the existing branch. No durable G7 production births, live evaluation counts, production ledger files or deployed revision have yet been verified. The Fly configuration adds only `ENABLE_G7_PAPER=1`; it does not change live-order secrets or place broker orders. The G7 verifier requires live-order placement to be disabled in the actual supervisor/runner environment, checks G1–G6 verification, validates original captured ledger prefixes, and fails if G7 has not been observed evaluating a current minute.

## H. Next evidence and rejection criteria

Observe at least ten prospective traded sessions before any promotion decision, and seek at least 30 independent completed opportunities per mechanism where signal frequency permits. Compare matched unchanged controls, trade retention, concentration, worst trade/day, actual bid drawdowns and cost sensitivity. Dates with unavailable marks remain unknown. Retire neither parents nor new modules solely on early low-count results.

Reject rotation protection if it repeatedly truncates trend winners without compensating lower drawdown or retained net P&L. Reject breadth confirmation if its positive replay differences do not persist, if it removes most viable opportunities, or if concentration/drawdowns worsen. Gas variants that behaved identically are not separate discoveries. The presently unsupported raw-flash hardening population is deferred rather than backfilled or optimized specifically to exclude MNDR.

Prioritize a separate review of G2 risk configuration and the older G6 open-mark reporting interface. A high-frequency book/timing archive would be needed to distinguish exact market gaps, halts and runner scheduling effects around stop triggers. Preserve the four malformed historical lines as evidence while diagnosing their origin.
