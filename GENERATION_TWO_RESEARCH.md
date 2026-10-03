# Generation two: 64 prospective flash experiments

Built from modular-bot commit e69344d8cb2705002e718699ab6c4f3ae877f274 on 2026-10-03.

G2 contains 32 frozen P-gain and 32 frozen Q-quality variants. Each owns an independent $5000 paper cash portfolio; portfolios are counterfactual alternatives and must not be added together. Controls use fixed $1000 orders. These are hypotheses for prospective observation, not strategies selected from unseen recent returns.

| Axis | Variants per family | IDs after G2PG or G2QV | Comparator |
| --- | ---: | --- | --- |
| Control | 1 | CTL | Frozen P gain or Q quality |
| Maximum spread | 4 | S5, S10, S20, S30 | CTL; 0.05%, 0.10%, 0.20%, 0.30% |
| Target distance / spread | 4 | E2, E3, E5, E8 | CTL; target minus ASK >= multiple times ASK minus BID |
| Executable target upside | 4 | PG: U50, U100, U150, U200; QV: U125, U150, U200, U300 | CTL; percentages encoded in hundredths |
| Gain checkpoint | 4 | K5, K10, K20, K30 | CTL; 0.25% observed BID gain required by 5/10/20/30 minutes |
| Disaster stop | 3 | D2, D3, D4 | CTL; 2%, 3%, 4% below confirmation reference |
| Recovery target fraction | 3 | T50, T65, T75 | CTL; 50%, 65%, 75% of original recovery distance |
| Nominal stop risk per order | 3 | R10, R20, R50 | CTL; 0.10%, 0.20%, 0.50% cost equity, 20% order cap |
| Fixed order / initial cash | 3 | C5, C10, C15 | CTL; $250, $500, $750 orders |
| Total open nominal stop risk | 2 | B1, B2 | R50; 1% or 2% of cost equity across residual positions |
| Symbol stacking | 1 | ONE | CTL; at most one active position per symbol per portfolio |

Existing Q admission retains its original 0.50% spread ceiling and 1% original-target upside gate. Additional gates use the final target and executable ASK. Nominal stop risk limits size orders; gaps or delayed/partial exits can exceed nominal risk. Entry stops/targets remain tied to the confirmation reference as in G1, and risk sizing uses the actual ASK-to-stop distance. Target distance relative to spread is an opportunity filter, not expected profit.

## Runtime and execution

- G2 independently evaluates frozen raw flash conditions and owns pending rebound state. It does not copy G1 entries or depend on source strategy switches/results.
- Both BID and ASK must be contemporaneous real-time quotes, at most five seconds old. Whole shares buy at ASK and sell at observed BID, consuming side-specific displayed liquidity with timestamps. Partial fills and residual exits retain actual quantities.
- Cash, filled quantities, deduplication and book consumption are recovered from an fsynced authoritative G2 ledger. Entry checkpoints are deferred; dynamic exit state is force-checkpointed during each quote update. Missing state/book diagnostics do not grant fresh cash or re-use consumed book liquidity.
- Entries use a durable first-activation timestamp, enforce a 120-second signal window, and are routed only in LIVE data mode. Replay earns no prospective credit. G2 does not place broker orders.
- `paper_generation_two_bidask_independent_*` files isolate births, outcomes, active state, status and book diagnostics. Existing G1 births and ledgers are preserved.
- All-engine reports include 64 `G2...BA` rows after activation. Returns use actual fill sizes and the existing entry-day attribution convention; missing open-position BID marks omit incomplete returns. No-trade modules are labeled `no_entries`.
- G2 uses flash volume measurements already fetched for the candidate and the local collector L1 cache. Its rules do not need rebound-volume fields, so G2 skips the additional Schwab candle-history request at rebound confirmation. Existing strategies retain their current fetch path. Other current bot paths can still call Schwab; this patch does not claim that the whole bot makes only one call per cycle.

## Local workload evidence

Repository fly.toml specifies 8 shared CPUs and 8 GB RAM; current deployed allocation and utilization were not inspected. The local synthetic benchmark tests G2 rule admission across 1000 qualifying candidates, 320 prospective fill attempts across all 64 variants, and quote updates with 312 active fills. It measures only the added G2 work, not full runner latency or live API conditions.

- Raw rule admission: 0.048s median.
- Durable admission batch: 0.062s without memory instrumentation; 312 of 320 attempts admitted after risk/symbol gates.
- Active quote update: 0.049s median.
- Peak traced tracker allocations: 1.69 MiB; not whole-process RSS.
- Example ledger plus state files: 1.63 MiB. This is a short synthetic sample, not a projection of long-run disk growth.

These measurements support trying 64 G2 modules. Live CPU, memory, cycle latency and disk growth still need checking after deployment. No Fly deployment was performed here.

## Validation

102 unittest tests passed, including 23 focused G2 tests and the existing G1, actual-fill reporting and execution regressions. Checks cover registration, unique parameter sets, source independence, executable gates, both-side freshness, forward births, replay routing, cash/book recovery without checkpoints, partial exits, symbol guard, aggregate stop-risk limits, exit policies, output switches and all-engine rows. Python compilation and git whitespace checks also passed. `GENERATION_TWO_BENCHMARK.json` records the local measured workload; `benchmarks/benchmark_generation_two.py` reproduces it.

## Installation

The self-contained installer validates touched source-file hashes against the pinned base, stages a clean copy, applies the patch and runs the regression suite before modifying the target working tree. Unrelated local changes and untracked data are allowed. Conflicting modifications to touched files stop installation. The installer does not commit, push, deploy, set Fly secrets or change live order permissions.

Download `browserbot-generation-two-install.sh`, then run:

```bash
cd ~/Desktop/browserbot
bash ~/Downloads/browserbot-generation-two-install.sh
```

Use `G2_PYTHON=/absolute/path/to/python` if your pandas-capable Python is not `python3`. After inspecting the diff, commit/push/deploy using your normal modular-bot workflow. Prospective G2 tracking starts only when the updated LIVE runner activates the tracker.
