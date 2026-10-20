# Generation 11: prospective paper experiments

## Frozen decision and preserved evidence

Keep the user's twelve explicitly selected parents, unchanged. Retire new paper
entries for the other 722 outputs in the archived 734-row ranking. The exact
lists, prior configurations, source evidence and daily observation cells are in
`GENERATION_ELEVEN_RETIREMENT.json`. Retirement does not delete accounts, rewrite
births, remove ledger rows, stop residual liquidations, or modify broker routes.
The prior output controls return when G11 is disabled and workers restart.

The reference is 2026-10-20 18:17:38.014199 UTC, with observations on October 13,
15, 16, 19 and 20. The reference terminal table has four-decimal rounded daily
returns, not original full-precision JSON. We preserve that archived ordering
and precision; we do not pretend to reconstruct the exact reference snapshot.
The subsequently captured 18:30:10.566116 UTC snapshot has the same 734 IDs.
Every supplied evidence member passed its recorded SHA-256. The deployed
strategy and accounting sources match the Git baseline. Build-revision files
exist only in the production image.

The archive is a set of per-file captured prefixes, not a cross-file transactional
restore image. The deployment gate re-verifies all preserved JSONL prefixes and
deployed baseline source hashes before creating a data activation marker. A
verified local download should also be retained as an off-machine copy.

## Analytical findings and limits

Detailed numerical evidence is in `research_tools/g11/PARENT_AUDIT.json`.

* G9LONG15, G9LONG16 and G9LONG17 use 140-, 145- and 150-minute equilibrium
  lookbacks. They are distinct rules but executed the same three paired trades
  at the same timestamps, prices, sides and quantities. All three recorded
  $27.9460323532 net closed P&L through the captured cutoff. Two were first-leg
  shorts and one was a first-leg long; every trade had a short leg. LONG is a
  lookback-family name, not a long-only strategy. Their identical outcomes
  provide one highly correlated exposure sample, not three independent wins.
* The five selected observations omit real October 14 activity. G7ROTPROTECT
  recorded -$19.70 closed P&L on that date, G3CGLB30 -$17.10, G6R05CTL -$5.06,
  G6R05TARGET -$4.99, G6R05ROOM -$5.06, G6R06PATIENT -$9.00 and G6R07CTL -$2.59.
  G3MPR150 and G3MT50 recorded +$4.45 and +$16.65 respectively. Missing ranking
  observations remain missing, not zero and not retroactively inserted.
* Across available closed trade records, excluding the best close day makes
  G3CGLB30 negative (-$22.59) and G6R06PATIENT negative (-$4.27). G7 remains
  +$16.43 and the G6R05 controls remain positive, but sample sizes are small.
  The closed-P&L analysis spans available ledgers, not just the five selection
  dates. Closed cash outcomes and current hypothetical-close marks are separate.
* Single-leg legacy ledger P&L establishes bid/ask fills but does not establish
  all commissions and adverse slippage. A fixed-path extra-cost sensitivity
  adds 2 bps per side and assumed commissions. It is not an executable backtest:
  quantities, entry/exit times and price paths are held fixed. G9 already
  records commissions and estimated borrow; borrow availability, fees, margin
  and broker buying power remain unverified.
* R05 siblings share admission cohorts and strongly overlapping opportunities.
  The audit includes actual entry overlap and selected-observation correlations;
  these are descriptive and are not significance tests or regime validation.
  There is no complete time-aligned intraday quote archive in this export, so
  we do not assert historical regime-conditioned variant returns or intrapoll
  maximum drawdowns. G11 records observed drawdowns and missing-mark flags.
* Compounding daily P&L divided by a fixed $5,000 reference is an observation
  ranking score. It is not automatically a continuously reinvested account
  return. Younger G9 modules have fewer observations; comparing them without
  acknowledging unequal exposure is selection-biased.

Five selected observations, or three selected paired trades, cannot establish
statistical significance. All selection data are discovery data. Prospective
sessions after durable birth are the independent evaluation period. No trade,
historical return or variant backtest is fabricated.

## Executable architecture

722 unique G11 paper candidates use the nine non-G9 parents. The three G9
parents remain unchanged controls. We do not amplify their duplicated paired
exposure or assume short borrow availability. This research decision satisfies
the one-or-more selected-parent ancestry requirement without using every
selected parent as a seed.

132 raw-flash candidates have their own scanner admission, pending rebound and
deduplication identities. A minute hub owns seven new parent evaluator instances
and evaluates raw market observations once per parent. It shares causal feature
calculations only, never parent trades or account state. The other 590 candidates
receive independently identified events from their declared raw evaluator.
Cross-parent minute candidates require the same symbol in both parent evaluations
of the same completed observation. Flash combinations require both raw predicates
and blend exit geometry. Each candidate has an executable behavioral change.

| Family | Candidates | Behavioral contrast |
|---|---:|---|
| ENTRY | 160 | Later session admission and longer fill cooldown |
| RISK | 140 | Lower nominal risk and smaller per-symbol capital cap |
| REGIME | 120 | SPY direction and observed symbol-volatility gates |
| HOLD | 110 | Holding duration and executable-price disaster stops |
| COMBO | 100 | Joint parent admission and predeclared blended exits |
| EXEC | 92 | Spread, liquidity participation, freshness and slippage |

Full hypotheses, parent mappings and configuration hashes are in
`research_tools/g11/HYPOTHESES.csv` and `GENERATION_ELEVEN_CATALOG.json`.

Each candidate starts with independent $5,000 cumulative cash, 1% nominal stop
risk and 20% symbol exposure limits, or explicitly lower experimental limits.
No midnight cash reset, leveraged buying power, short proceeds or broker access
exists in G11. Whole-share entry and partial liquidation use actual displayed
asks/bids, per-account per-book consumption, per-side timestamps, realtime quotes,
and adverse slippage. Commissions are modeled at $0.005/share/side, minimum $0.01,
plus $0.0002/share on sale; these are research assumptions, not a verified tariff.
G9's existing $5,000 gross paired sizing and 10% hedge-ratio safeguard are unchanged.

The G11 engine is a separately versioned adaptation of the tested G10 cash
engine. Its separate manifest, births, writer lock and sequenced append-only
ledger never reuse an earlier generation's files. Source hashes and catalog
hashes are frozen at first activation. Missing provenance, stale quotes and
corrupt recovery fail closed. Liquidation reasons survive restart and missing
liquidity. Daily cost equity is recorded before a new day's first entry.
Reports distinguish realized cash P&L, unrealized hypothetical-close P&L and
unknown valuation. A zero return is published only after the input path was
observed with a known flat account; births alone never invent returns.

## Deployment and verification

GitHub reads succeeded but GitHub integration writes returned HTTP 403. The
delivery therefore includes a Git bundle for a clean fast-forward into the
user's local modular-bot checkout. The Mac deployment script runs checks, pushes
Git, verifies preserved production prefixes and unchanged deployed baseline
sources, creates a durable data activation marker, then deploys through Fly.
It never patches source on the machine. Missing disk headroom or population
drift stops activation. No production success is claimed from local tests.

Run `python3 -m research_tools.g11.run_checks` before deploying. Run
`bash research_tools/g11/deploy.sh` from the committed checkout. Immediately
after deployment use `python -m research_tools.g11.verify_production --allow-warmup`
on Fly, then use the strict verifier after a report refresh and observed market
inputs. Strict success requires exact 12 + 722 = 734 reporting IDs, retired
entry controls, correct source hashes, independent durable births and events,
and unchanged historical ledger prefixes. Production entries may legitimately
remain zero until a fresh eligible setup occurs; no synthetic test ledger is
ever deployed.

Rollback prospectively with ENABLE_G11_PAPER=0 and a worker restart. Existing
G11 birth files keep the exit-servicing tracker alive, while G11 admission and
retirement gates are disabled. Historical data and all prior generations remain
recoverable. Do not delete the activation marker or any ledger to reset results.

Local benchmark (synthetic, host-dependent): initializing 722 accounts ~0.06s,
722 admissions ~0.61s, restart recovery ~0.10s, peak Python process RSS ~54 MiB
on the Linux benchmark host. Complete per-minute account frames use lossless
zlib/base64 encoding in the sequenced ledger; decoded accounts remain separately
identifiable. The measured frame budget is ~5.8 MiB per 390-minute session,
plus observations, signals, fills and rejects. This is not a full-production
load guarantee. The activation gate requires at least 512 MiB free on /data.
