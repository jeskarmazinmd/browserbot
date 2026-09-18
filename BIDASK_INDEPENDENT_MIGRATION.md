# Independent bid/ask paper modules

This change separates the active paper modules from LAST paper accounting.
Strategy calculations still consume their existing market features, including
the completed-minute price tape. Their emitted signal is passed directly to
the independent bid/ask tracker; acceptance no longer depends on a LAST
paper-trade entry or exit.

In LIVE mode:

- Single-leg signals enter only when the same runner cycle provides a fresh,
  valid displayed ASK and sufficient quote evidence. Open positions update
  their exit rules using fresh executable BID marks. The ledger is
  `paper_signal_v4_bidask_independent_outcomes.jsonl`.
- Coordinated signals enter only when all legs have simultaneous executable
  bid/ask evidence in the signal cycle. Their independent ledger is
  `multi_leg_paper_v3_bidask_independent_outcomes.jsonl`.
- Missing, stale, or incomplete entry quotes reject the opportunity without
  filling from a later quote. A request budget limits additional targeted
  symbol fetches to 50 per cycle after the bounded bulk quote request.
- No new LAST paper entries, V3 LAST twins, old IOC/L1 twins, or LAST
  coordinated entries are generated. Existing open positions in the old
  ledgers may drain, preserving their exit audit records.
- New broker entries are disarmed during the migration. Existing broker
  positions still run their exit management.

The active all-engine snapshot reads the new ledgers, omits LAST and
parent-dependent BA modules, and does not substitute the last traded price
for a missing executable book. Single-leg BA rows use the $5,000, 1% risk,
20% position-cap model, capped by observed filled shares. The BA-only daily
history is `all_engine_bidask_daily_history.{json,txt}`; prior history files
remain archived. The old LAST capital-performance worker is no longer
started. Native bid/ask worker modules continue on their own feeds.

Historical LAST and V3 ledgers remain available for offline comparison.
Do not compare a V4 return to V3 as if the two used identical trade selection.
No broker execution is enabled by this patch. Review a prospective week of
V4 entries, rejected quotes, exits, and open positions before considering a
separate live-trading implementation.
