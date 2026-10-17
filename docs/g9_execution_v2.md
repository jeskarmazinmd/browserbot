# G9 whole-share execution V2

## Scope and root cause

G9 only. No broker client, live configuration, live-order handling, parent
strategy, retirement rules or other generation is changed. All 400 original IDs,
signal definitions and population hash are preserved.

V1 capped paired gross at $1,000 (20% of $5,000), split that by signal weights,
and independently floored each leg. Required SPY hedges near $760 often rounded
to zero. Missing sizes and insufficient depth shared the same rejection reason.

## Effective execution configuration

V2 replaces the V1 execution cap with a $5,000 combined gross ceiling per
independent strategy. The catalog's frozen `gross_notional=1000` remains historical
V1 provenance; `generation_nine_paper_tracker.MAX_GROSS` is the explicit V2
execution override. Initial equity stays $5,000. Subsequent admission equity is
$5,000 plus that strategy's cumulative realized net P&L, including earlier days.
One open group per ID prevents concurrent reservation overlap. Profits do not
increase the gross ceiling; losses reduce feasible collateral. Daily reporting
remains daily P&L divided by the $5,000 reference, and says so explicitly.

For first-leg dollar notional A and SPY dollar notional B, intended weights w0,
w1, accept only `abs((B/A)/(w1/w0)-1) <= 0.10`. Weights include estimated beta
and the variant's hedge scale. This is a relative tolerance around the intended
weighted hedge, not an equal-dollar rule. Integer pairs are searched jointly;
maximize feasible gross, breaking ties by smaller hedge error. Both legs must
have at least one whole share. Liquidity may reduce the selected position; it
never relaxes hedge tolerance.

The paper collateral stress model reserves gross plus both modeled commissions
and planned-holding-period estimated borrowing costs against equity. Short
proceeds never finance new positions. No broker leverage is assumed. This model
is NOT a verified Schwab margin calculation or proof of broker buying power.
Actual account requirements, security-specific margin/house restrictions,
short eligibility, locates, borrow rates and recalls remain unverified.
Hypothetical admissions do not establish broker executability.

Bid/ask direction, per-variant slippage and participation, five-second freshness,
spread filters, depth consumption, paired exits, commissions and elapsed-time
borrow accrual remain enforced. Short positions can lose beyond reserved capital;
planned-hold cost reservation cannot guarantee coverage of a deferred exit.
Paired admission is an atomic research assumption, not proof of simultaneous
exchange fills. The 400 portfolios are independent and cannot be combined into
one $5,000 live account.

## Provenance and diagnostics

The original ledger, births and manifest are never rewritten by migration.
Only the exact known V1 tracker hash is accepted for migration; changed signal
rules or unknown manifests fail closed. A separate `_execution_v2.json` records
the V2 policy, source hashes and activation time. New events carry
`execution_version=G9_WHOLE_SHARE_V2`; older records are interpreted as
`G9_LEGACY_V1`. New entries cannot predate V2 activation. Legacy open groups can
still drain. Recovery validates V2 whole shares, gross, collateral, hedge error
and paper-only flags. Existing historical results are never resized or backfilled.

Entry diagnostics distinguish `insufficient_whole_share_allocation`,
`missing_quote_size`, `insufficient_displayed_liquidity`,
`hedge_ratio_mismatch`, `insufficient_collateral_or_buying_power`, and the retained
quote, spread, time, pair, contract, weight and carry conditions. The collateral
reason describes the PAPER MODEL, not a broker rejection. Status contains all-time
and per-execution-version event counts and rejection reasons; daily reports carry
execution versions and explicit broker-verification flags.

## Validation on 2026-10-17

- Relevant suite: 193 passing tests across generations 1–9, the new sizing suite,
  parent strategy, statarb worker wiring, output switches and capital reporting.
- Existing all-400 independent G9 admission regression retained, with V2 cap.
  Added all-400 unequal-weight checks, sizing and collateral boundaries, both
  execution directions, commissions, borrow, missing/depleted depth, participation,
  restart accounting, migration preservation and reporting provenance.
- Production quote fixture: October 2 GLD 384.24/384.26, SPY 770.22/770.23,
  with original timestamps and displayed sizes. At equal weights, six GLD and
  three SPY whole shares pass modeled sizing/depth in either direction. This
  historical fixture is a test input only and creates no production trades.
- A separate all-400 sizing-only sweep using that fixture and weights
  `1 : 1.3 * hedge_scale` completed in about 0.007 seconds: 396 feasible pairs,
  four correctly rejected hedge mismatches. This does not evaluate signals or
  forecast trade counts. All 400 have feasible weighted regression cases.
- Existing population benchmark passed: p95 5.137 seconds (<15), maximum 5.571,
  peak traced allocations 1.889 MiB (<128); synthetic data is not return evidence.
- Repository-wide discovery: 734 tests, 15 failures and 22 errors. Unchanged base
  `7a87217` ran 724 tests with the exact same 15 failing and 22 erroring test IDs.
  No new failures. Existing unrelated failures were not changed in this task.
- Read-only verifier checked against a temporary tracker: all checks passed;
  inspection changed no files.

## Deployment handoff

Fly CLI is unavailable in this environment; download endpoint connection timed
out. Production SSH, deployment, status and tape inspection remain blocked.
The user's supplied pre-fix counts (400 modules, 29,603 rejections, zero completed)
were not independently refreshed. No production change is claimed.

From the established local checkout, after pulling the tested commit:

```bash
cd ~/Desktop/browserbot
git switch modular-bot
git pull --ff-only
python -m unittest tests.test_generation_nine tests.test_generation_nine_sizing -q
fly deploy -a schwab
fly ssh console -a schwab -C 'python -m research_tools.verify_generation_nine'
```

The last command only reads files; it never initializes a tracker or appends
outcomes. Confirm V2, matching hashes, preserved 400 births, paper-only safeguards,
a fresh heartbeat and per-version counts. `active` counts open paired groups,
not enabled modules. Fresh OPEN events demonstrate prospective hypothetical
admissions; zero OPEN events do not prove a sizing failure. New signals need
fresh continuous warmup history and an open entry window. The weekend does not
provide regular-session candidates. Never erase provenance to bypass a mismatch.
