# G8 approved paper research and deployment

Approved October 13, 2026 at 20:34:29 UTC. Baseline: `fc22309f399dfb089e135022dc96b0c5abd2e3ee` on `modular-bot`.

## Changes

120 prospective paper accounts: thirty causal sampled-price state/relationship mechanisms across four fixed economic routes. They are 120 experiments, not 120 independent discoveries. `GENERATION_EIGHT_CATALOG.json` records every ID, universe, leader set, admission hypothesis and nearest existing comparator. Numeric execution settings are shared rather than swept for historical returns.

The approved output-only plan permanently retires 24 outputs and reversibly pauses G2PGU100BA/G2PGU200BA. All definitions, generation catalogs, historical outcomes and producer dependencies remain intact. PMID and M2 producers remain evaluated while their BA outputs are suppressed. Existing residual exits continue. The gate refuses an overlap with a configured live strategy.

G8 uses independently owned cash, inventory, risk, episode state, setup IDs, births and displayed-book accounting. There is no broker route. Entry quotes must be realtime, nonfuture and <=1 second old; exit quotes <=5 seconds. Each account consumes at most 10% of displayed side shares per quote identity, including partial exits and restart. Per-order notional <=$1,000; baseline $5,000; nominal per-trade risk <=1%, aggregate nominal risk <=2%, aggregate symbol cap <=20%, one residual position per symbol. Stops and a 2% daily loss brake are triggers, not guaranteed fill/loss prices. Symbol cooldowns and two-stop lockout persist through the journal. Unknown portfolio marks or carry accounting stop new entries.

The thirty feature predicates are based on contiguous completed sampled-price observations. No volume, OHLC, intraminute highs/lows, order flow or borrow is invented. Lag fits/graphs use a training segment ending ten observations before the decision. Features share bounded read-only computation; evaluators own their episode/cooldown state. First signal availability is the next minute boundary. Missing symbols/session gaps/out-of-order observations fail closed or reset state. Ninety-six contiguous sampled minutes are required before feature readiness.

Collector quote requests include the fixed 36 required G8 symbols when opted in, and retain those quotes for exit-only rollback after births exist. This does not change broker eligibility. Worst-case quote universe is 487+36=523, with existing 500-symbol batch/concurrency handling. Network latency and real quote freshness remain production verification items.

## Reporting and preservation

Main BA reports now supply explicit admitted open/closed counts and label risk-sized resimulation. G6 marks receive rich timestamped books. Live books are frozen before ledger scanning; historical residuals cannot use a later live book. Missing generation-account marks are explicit unknowns, not zero. G8 reports actual quantities and partial proceeds; unverified carry is unknown. Existing finalized history records are retained; invalid existing history fails closed rather than resetting the file. No G8 births or historical outcomes are created by reporting.

The approval audit preserves the four malformed historical main-ledger lines and prebirth provenance inconsistencies. Old numeric snapshots are not overwritten with newly corrected calculations. The predeployment preservation script copies outcomes/report/provenance evidence to a new ZIP, records ledger prefix hashes and canonical hashes of each existing finalized day, and downloads that ZIP to the Mac before deployment. Verification permits normal journal appends but detects truncation/rewrite and changes to old finalized snapshots.

## Validation

The guarded `research_tools.g8.run_checks` command runs the relevant G1–G8, execution, capital, reporting and worker-shard regression suites. Tests cover reachable separate accounts, every mechanism's evidence contrast, computed causal feature readiness/gaps, paper-only routing, strict births/manifests, quote/future/realtime rejection, symbol/cash/risk constraints, durable loss brakes, partial liquidity and recovery, preserved retired exits, checkpoint bytes and collector quote coverage during rollback.

Computed synthetic price paths activate all thirty mechanisms and produce thirty distinct behavior fingerprints. This is reachability/engineering evidence, not historical performance or proof of statistical independence. Full historical G8 P&L is deliberately absent.

Capacity gates: combined evaluation p95 <1 second and max <5 seconds. Tests include the actual eight-process IPC pool, a worst-case 523-symbol universe, 120 fsynced synthetic admissions and recovery. A read-only scan of the supplied production export completed in about 17.4 seconds versus the reporter's 600-second poll interval, and created no G8 births. Network fetch, production disk performance and market-session readiness still require verification. Docker is unavailable in this workspace; the authenticated Fly remote build is performed by the delivery script.

Two old minute-cadence assertions were already documented as failing on the G7 baseline; the focused delivery suite does not pretend the entire repository suite passes. Existing reporting tests were updated only for the intentional explicit-unknown contract and timestamped quote fixture, retaining their arithmetic/disabled-output checks.

## Delivery and rollback

The delivery contains a Git bundle and readable patch based on the exact baseline. The Mac script starts with a read-only SSH inspection, refuses unexpected source/live controls or a dirty/diverged repository, tests an isolated worktree, fast-forwards the reviewed commit, pushes `modular-bot`, repeats preflight, preserves/downloads evidence, deploys and runs structural verification. It never modifies broker secrets. A replay or disabled-G8 signal cannot fall through to a different tracker or broker.

After-hours deployment can pass structural checks with pending market warmup, quote coverage or reporter refresh clearly listed. A strict verification must be run during the next market session after warmup. No filled/profitable strategy claim follows from structural verification.

Rollback sets only the new G8 paper/retirement flags to zero, retains the compatible image and services all residual exits. Births and journals are never reset. Do not deploy an older binary without G8 exit support while G8 inventory remains. Removal of those two rollback flag overrides restores the committed Fly opt-ins only after review of the incident.

Production has not been changed by this implementation workspace. The final deployed commit/image/flags/observations must be reported from the Mac workflow outputs.
