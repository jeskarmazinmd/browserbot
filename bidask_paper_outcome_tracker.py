"""Parallel executable bid/ask accounting for core single-leg strategies.

This is deliberately a shadow of :mod:`paper_outcome_tracker`.  It never
places broker orders and never writes to the legacy last-price ledger.
"""

from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path

from executable_paper_engine import (
    EXECUTION_MODEL,
    classify_limit_order,
    executable_mark,
)
from paper_outcome_tracker import NY, PaperOutcomeTracker, _utc


FILE_STEM = "paper_signal_v2_bidask"
INDEPENDENT_FILE_STEM = "paper_signal_v4_bidask_independent"
REPRICING_FILE_STEM = "paper_signal_v3_bidask_repricing"
MAX_PENDING_SECONDS = 20.0
MAX_REPRICING_RECOVERY_AGE_SECONDS = 60.0
MAX_REPRICING_EXIT_DELAY_SECONDS = 120.0
MAX_SYMBOLS_PER_CYCLE = 400


def _positive(value):
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) and value > 0 else None


def canonical_trade_intent(parent_entry):
    """Stable, broker-agnostic handoff for future paper/live consumers."""
    return {
        "version": "TRADE_INTENT_V1",
        "trade_id": str(parent_entry.get("setup_id") or ""),
        "source_strategy_id": parent_entry.get("strategy_id"),
        "symbol": parent_entry.get("symbol"),
        "side": "LONG",
        "signal_timestamp": parent_entry.get("signal_timestamp"),
        "entry_timestamp": parent_entry.get("entry_timestamp"),
        "entry_reference_price": parent_entry.get("entry_price"),
        "sizing": {
            "paper_notional": parent_entry.get("notional"),
            "quantity": parent_entry.get("quantity"),
        },
        "exit_policy": {
            "model": parent_entry.get("exit_model"),
            "target_price": parent_entry.get("target_price"),
            "stop_price": parent_entry.get("stop_price"),
        },
    }


def register_paired_single_leg_signal(
    signal, *, parent_tracker, repricing_tracker, ioc_tracker, quote_provider,
    now_provider=None,
):
    """Fan one accepted parent event immediately to both bid/ask twins."""
    accepted = parent_tracker.register(signal)
    if not accepted:
        return False

    signal_timestamp = _utc(signal.get("timestamp"))
    processing_time = _utc(
        now_provider() if now_provider is not None else datetime.now(timezone.utc)
    )
    setup_id = parent_tracker._setup_id(signal, signal_timestamp)
    parent_entry = parent_tracker.active.get(setup_id)
    if parent_entry is None:
        raise RuntimeError(f"accepted parent entry missing from active state: {setup_id}")

    parent_entry = dict(parent_entry)
    parent_entry["parent_recorded_at"] = datetime.now(timezone.utc).isoformat()
    symbol = str(parent_entry.get("symbol") or "").upper()

    # Resolve top-of-book once in the same processing cycle as the accepted
    # parent event.  Both execution shadows see this identical cached snapshot.
    # The pure V3 B/A twin must never recover an earlier event from a later
    # quote: if ASK is absent here, that twin is immediately unpriced.
    try:
        quotes = quote_provider([symbol]) or {}
    except Exception:
        quotes = {}

    repricing_tracker.register_parent_entry(
        parent_entry,
        quote=quotes.get(symbol),
        now=processing_time,
    )

    # IOC/L1 remains the separate execution experiment.
    ioc_tracker.register(signal)
    ioc_tracker.update_quotes(quotes, processing_time)
    return True


class BidAskPaperOutcomeTracker(PaperOutcomeTracker):
    """Track the same core signals using executable top-of-book evidence."""

    def __init__(self, data_root, **kwargs):
        kwargs.setdefault("file_stem", FILE_STEM)
        kwargs.setdefault("use_observed_exit_prices", True)
        super().__init__(data_root, **kwargs)
        self.pending = OrderedDict()
        self.entry_full = 0
        self.entry_partial = 0
        self.entry_zero = 0
        self.entry_unknown = 0
        self._symbol_cursor = 0
        self._write_status()

    def _write_status(self):
        try:
            self._atomic_json(
                self.status_path,
                {
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "active": len(self.active),
                    "pending": len(getattr(self, "pending", {})),
                    "completed": self.completed,
                    "seen_setups": len(self.seen),
                    "notional_per_signal": self.notional,
                    "execution_model": EXECUTION_MODEL,
                    "pricing": "LONG BUY@ask; mark/exit SELL@bid",
                    "quote_freshness_enforced": True,
                    "displayed_liquidity_enforced": True,
                    "broker_execution_enabled": False,
                    "entry_full": getattr(self, "entry_full", 0),
                    "entry_partial": getattr(self, "entry_partial", 0),
                    "entry_zero": getattr(self, "entry_zero", 0),
                    "entry_unknown": getattr(self, "entry_unknown", 0),
                    "max_symbols_per_cycle": MAX_SYMBOLS_PER_CYCLE,
                },
            )
        except OSError:
            pass

    def register(self, signal):
        """Queue a signal until a fresh executable quote is available."""
        try:
            timestamp = _utc(signal.get("timestamp"))
        except (TypeError, ValueError):
            return False
        timestamp_et = timestamp.astimezone(NY)
        minute_et = timestamp_et.hour * 60 + timestamp_et.minute
        if not (
            self.entry_start_minute_et
            <= minute_et
            < self.entry_cutoff_minute_et
        ):
            self.rejected_outside_entry_window += 1
            self._write_status()
            return False

        setup_id = self._setup_id(signal, timestamp)
        if setup_id in self.seen or setup_id in self.pending:
            return False
        if not str(signal.get("strategy_id") or "").strip():
            return False
        if not str(signal.get("symbol") or "").strip():
            return False
        if not all(
            _positive(signal.get(field))
            for field in ("entry_price", "target_price", "stop_price")
        ):
            return False

        queued = dict(signal)
        queued["setup_id"] = setup_id
        queued["bidask_queued_at"] = datetime.now(timezone.utc).isoformat()
        self.pending[setup_id] = queued
        self._write_status()
        return True

    def symbols(self, limit=MAX_SYMBOLS_PER_CYCLE):
        """Bound quote demand, always prioritizing signals awaiting entry."""
        pending_symbols = list(dict.fromkeys(
            str(row.get("symbol") or "").upper()
            for row in self.pending.values()
            if row.get("symbol")
        ))
        remaining = max(0, int(limit) - len(pending_symbols))
        active_symbols = list(self.by_symbol)
        selected = []
        if remaining and active_symbols:
            start = self._symbol_cursor % len(active_symbols)
            rotated = active_symbols[start:] + active_symbols[:start]
            selected = rotated[:remaining]
            self._symbol_cursor = (start + len(selected)) % len(active_symbols)
        return set((pending_symbols + selected)[: int(limit)])

    def _reject_pending(self, setup_id, signal, decision, now):
        outcome = decision.outcome
        if outcome == "ZERO":
            self.entry_zero += 1
        else:
            self.entry_unknown += 1
        self._append({
            "event_type": "PAPER_ENTRY_REJECTED",
            "recorded_at": now.isoformat(),
            "setup_id": setup_id,
            "strategy_id": signal.get("strategy_id"),
            "symbol": signal.get("symbol"),
            "signal_timestamp": signal.get("timestamp"),
            "execution": decision.as_dict(),
            "paper_only": True,
            "broker_execution_enabled": False,
        })
        self.seen.add(setup_id)
        self.pending.pop(setup_id, None)

    def update_quotes(self, quotes, now):
        """Admit pending fills and update active trades from fresh BID marks."""
        now = _utc(now)
        for setup_id, signal in list(self.pending.items()):
            symbol = str(signal.get("symbol") or "").upper()
            quote = quotes.get(symbol)
            queued_at = _utc(signal["bidask_queued_at"])
            age = (now - queued_at).total_seconds()
            if quote is None:
                if age <= MAX_PENDING_SECONDS:
                    continue
                # Create a normal UNKNOWN decision for consistent audit fields.
                decision = classify_limit_order(
                    None,
                    action="BUY",
                    limit_price=float(signal["entry_price"]),
                    requested_qty=max(1, int(self.notional / float(signal["entry_price"]))),
                    now=now,
                    max_quote_age_ms=5000.0,
                )
                self._reject_pending(setup_id, signal, decision, now)
                continue

            ask = _positive(quote.get("ask"))
            if ask is None:
                continue
            requested = max(1, int(self.notional / ask))
            # This shadow measures spread and displayed liquidity.  The signal
            # is treated as an immediate paper market entry at displayed ASK.
            decision = classify_limit_order(
                quote,
                action="BUY",
                limit_price=ask,
                requested_qty=requested,
                now=now,
                max_quote_age_ms=5000.0,
            )
            if decision.outcome not in {"FULL", "PARTIAL"}:
                if age > MAX_PENDING_SECONDS or decision.outcome == "ZERO":
                    self._reject_pending(setup_id, signal, decision, now)
                continue

            filled = dict(signal)
            filled["entry_price"] = float(decision.fill_price)
            filled["paper_notional"] = (
                float(decision.fill_price) * int(decision.filled_qty)
            )
            filled["execution_entry_timestamp"] = now.isoformat()
            filled.update({
                "execution_model": EXECUTION_MODEL,
                "entry_bid": decision.bid,
                "entry_ask": decision.ask,
                "requested_qty": decision.requested_qty,
                "filled_qty": decision.filled_qty,
                "entry_fill_outcome": decision.outcome,
                "entry_quote_age_ms": decision.quote_age_ms,
                "displayed_ask_qty": decision.displayed_qty,
            })
            accepted = super().register(filled)
            if accepted:
                if decision.outcome == "FULL":
                    self.entry_full += 1
                else:
                    self.entry_partial += 1
            self.pending.pop(setup_id, None)

        bid_prices = {}
        executable_marks = {}
        for symbol, quote in quotes.items():
            mark = executable_mark(
                quote,
                action="SELL",
                now=now,
                max_quote_age_ms=5000.0,
            )
            if mark.get("state") == "EXECUTABLE":
                bid_prices[symbol] = mark["price"]
                executable_marks[symbol] = mark
        for setup_id, record in self.active.items():
            symbol = str(record.get("symbol") or "").upper()
            mark = executable_marks.get(symbol)
            if mark is not None:
                record["exit_bid"] = mark.get("bid")
                record["exit_ask"] = mark.get("ask")
                record["exit_quote_age_ms"] = mark.get("quote_age_ms")
        closed = super().update(bid_prices, now)
        self._write_status()
        return closed


class IndependentBidAskPaperTracker(BidAskPaperOutcomeTracker):
    """Own BA entries and exits without a LAST paper-trade parent.

    Signals may use the strategy's market features, but an entry is admitted
    only from an executable same-cycle ASK. Missing or stale quotes are
    rejected immediately; a later quote cannot fill an earlier signal.
    """

    def __init__(self, data_root, **kwargs):
        kwargs.setdefault("file_stem", INDEPENDENT_FILE_STEM)
        super().__init__(data_root, **kwargs)

    def register_signal(self, signal, quote, now):
        if not self.register(signal):
            return False
        now = _utc(now)
        symbol = str(signal["symbol"]).upper()
        setup_id = self._setup_id(signal, _utc(signal["timestamp"]))
        self.update_quotes({symbol: quote} if quote else {}, now)
        pending = self.pending.get(setup_id)
        if pending is not None:
            # The ordinary IOC/L1 experiment can wait for another quote.
            # This independent ledger must use the signal-cycle quote only.
            decision = classify_limit_order(
                quote,
                action="BUY",
                limit_price=float(signal["entry_price"]),
                requested_qty=max(1, int(self.notional / float(signal["entry_price"]))),
                now=now,
                max_quote_age_ms=5000.0,
            )
            self._reject_pending(setup_id, pending, decision, now)
            self._write_status()
        return setup_id in self.active


class BidAskRepricingTracker:
    """Exact-cycle bid/ask twin of accepted LAST paper trades.

    The LAST parent is the sole authority for whether and when a trade exists.
    This tracker copies the parent's entry and exit events exactly and changes
    only executable pricing: LONG entry@ASK and LONG exit@BID.

    Pricing is event-synchronous.  A quote must be available in the same
    processing cycle as the parent event.  Missing exact-cycle top-of-book is
    quarantined immediately and is never filled later from a future quote.
    """

    def __init__(self, data_root, *, file_stem=REPRICING_FILE_STEM, **_kwargs):
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.root / f"{file_stem}_outcomes.jsonl"
        self.status_path = self.root / f"{file_stem}_status.json"
        # Keep the historical filename for compatibility, but exact-cycle V3
        # never intentionally persists pending work.
        self.state_path = self.root / f"{file_stem}_pending.json"
        self.quarantine_path = self.root / f"{file_stem}_quarantine.jsonl"
        self.active = {}
        self.pending_entries = OrderedDict()
        self.pending_exits = OrderedDict()
        self.seen_entries = set()
        self.seen_exits = set()
        self.parent_entries_seen = set()
        self.parent_exits_seen = set()
        self.completed = 0
        self.quarantined_entries = 0
        self.quarantined_exits = 0
        self._recover()
        self._write_status()

    @staticmethod
    def _positive(value):
        try:
            value = float(value)
        except (TypeError, ValueError):
            return None
        return value if math.isfinite(value) and value > 0 else None

    @staticmethod
    def _setup_id(row):
        return str(row.get("setup_id") or "").strip()

    def _append(self, row):
        with self.ledger_path.open("a") as handle:
            handle.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")

    def _atomic_json(self, path, payload):
        temporary = path.with_name(path.name + ".tmp")
        with temporary.open("w") as handle:
            json.dump(payload, handle, separators=(",", ":"), default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    def _recover(self):
        if self.quarantine_path.exists():
            try:
                with self.quarantine_path.open(errors="replace") as rows:
                    for line in rows:
                        try:
                            row = json.loads(line)
                            event = str(row.get("event_type") or "").upper()
                            setup_id = self._setup_id(row)
                        except (TypeError, ValueError):
                            continue
                        if event == "BA_REPRICE_ENTRY_UNAVAILABLE":
                            self.quarantined_entries += 1
                            if setup_id:
                                self.parent_entries_seen.add(setup_id)
                        elif event == "BA_REPRICE_EXIT_UNAVAILABLE":
                            self.quarantined_exits += 1
                            if setup_id:
                                self.parent_exits_seen.add(setup_id)
            except OSError:
                pass

        if self.ledger_path.exists():
            try:
                rows = self.ledger_path.open(errors="replace")
            except OSError:
                rows = None
            if rows is not None:
                with rows:
                    for line in rows:
                        try:
                            row = json.loads(line)
                        except (TypeError, ValueError):
                            continue
                        setup_id = self._setup_id(row)
                        if not setup_id:
                            continue
                        event = str(row.get("event_type") or "").upper()
                        if event == "BA_REPRICE_ENTRY":
                            self.parent_entries_seen.add(setup_id)
                            self.seen_entries.add(setup_id)
                            self.active[setup_id] = row
                        elif event == "BA_REPRICE_EXIT":
                            self.parent_exits_seen.add(setup_id)
                            self.seen_exits.add(setup_id)
                            self.active.pop(setup_id, None)
                            self.completed += 1

        # Old versions persisted delayed-repricing work here.  On upgrade it
        # must never be resumed with a future quote.  Quarantine it immediately.
        if self.state_path.exists():
            try:
                state = json.loads(self.state_path.read_text())
                recovered_at = datetime.now(timezone.utc)

                for row in state.get("pending_entries", []):
                    setup_id = self._setup_id(row)
                    if not setup_id or setup_id in self.seen_entries:
                        continue
                    self.parent_entries_seen.add(setup_id)
                    self._quarantine(
                        "BA_REPRICE_ENTRY_UNAVAILABLE",
                        row,
                        recovered_at,
                        reason="legacy_pending_entry_discarded_exact_cycle_required",
                    )
                    self.quarantined_entries += 1

                for row in state.get("pending_exits", []):
                    setup_id = self._setup_id(row)
                    if not setup_id or setup_id in self.seen_exits:
                        continue
                    self.parent_exits_seen.add(setup_id)
                    self._quarantine(
                        "BA_REPRICE_EXIT_UNAVAILABLE",
                        row,
                        recovered_at,
                        reason="legacy_pending_exit_discarded_exact_cycle_required",
                    )
                    # Parent exit is authoritative: this B/A twin is no longer
                    # active even though its exact-cycle exit price is missing.
                    self.active.pop(setup_id, None)
                    self.quarantined_exits += 1
            except (OSError, TypeError, ValueError):
                pass

        self.pending_entries.clear()
        self.pending_exits.clear()

    def _quarantine(
        self,
        event_type,
        row,
        recovered_at,
        *,
        reason="exact_cycle_top_of_book_unavailable",
    ):
        audit = {
            "event_type": event_type,
            "recorded_at": recovered_at.isoformat(),
            "setup_id": self._setup_id(row),
            "strategy_id": row.get("strategy_id"),
            "symbol": row.get("symbol"),
            "signal_timestamp": row.get("signal_timestamp"),
            "parent_entry_timestamp": (
                row.get("parent_entry_timestamp") or row.get("entry_timestamp")
            ),
            "parent_exit_timestamp": row.get("exit_timestamp"),
            "reason": reason,
            "paper_only": True,
            "broker_execution_enabled": False,
        }
        with self.quarantine_path.open("a") as handle:
            handle.write(json.dumps(audit, separators=(",", ":")) + "\n")

    def _write_status(self):
        self._atomic_json(self.state_path, {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "pending_entries": [],
            "pending_exits": [],
        })
        self._atomic_json(self.status_path, {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "execution_model": "BIDASK_REPRICE_V1_EXACT_CYCLE",
            "pricing": "parent trade twin; exact-cycle LONG entry@ask exit@bid",
            "parent_is_trade_authority": True,
            "exact_cycle_pricing": True,
            "future_quote_recovery_enabled": False,
            "selection_recomputed": False,
            "exit_model_recomputed": False,
            "quantity_recomputed": False,
            "active": len(self.active),
            "pending_entries": 0,
            "pending_exits": 0,
            "seen_entries": len(self.seen_entries),
            "seen_exits": len(self.seen_exits),
            "completed": self.completed,
            "parity_ok": (
                not self.quarantined_entries
                and not self.quarantined_exits
            ),
            "paired_coverage": {
                "parent_entries_seen": len(self.parent_entries_seen),
                "repriced_entries": len(self.seen_entries),
                "pending_entry_prices": 0,
                "unpriced_entries": self.quarantined_entries,
                "parent_exits_seen": len(self.parent_exits_seen),
                "repriced_exits": len(self.seen_exits),
                "pending_exit_prices": 0,
                "unpriced_exits": self.quarantined_exits,
            },
            "historical_unpriced_quarantined": {
                "entries": self.quarantined_entries,
                "exits": self.quarantined_exits,
                "path": str(self.quarantine_path),
            },
            "broker_execution_enabled": False,
            "live_promotion_ready": (
                not self.quarantined_entries
                and not self.quarantined_exits
            ),
        })

    def symbols(self):
        # Only successfully priced B/A entries remain active.  There is no
        # delayed repricing queue in exact-cycle mode.
        result = {
            str(row.get("symbol") or "").upper()
            for row in self.active.values()
        }
        result.discard("")
        return result

    def register_parent_entry(self, parent_entry, quote=None, now=None):
        """Mirror a parent entry now, using only this call's quote."""
        setup_id = self._setup_id(parent_entry)
        if (
            not setup_id
            or setup_id in self.parent_entries_seen
            or setup_id in self.seen_entries
        ):
            return False

        now = _utc(now or datetime.now(timezone.utc))
        self.parent_entries_seen.add(setup_id)

        parent = dict(parent_entry)
        parent["parent_entry_price"] = parent_entry.get("entry_price")
        parent["parent_entry_timestamp"] = parent_entry.get("entry_timestamp")
        parent["queued_at"] = now.isoformat()

        quote = quote or {}
        ask = self._positive(quote.get("ask"))

        if ask is None:
            self._quarantine(
                "BA_REPRICE_ENTRY_UNAVAILABLE",
                parent,
                now,
                reason="entry_ask_unavailable_in_parent_cycle",
            )
            self.quarantined_entries += 1
            self._write_status()
            return True

        row = {
            **parent,
            "event_type": "BA_REPRICE_ENTRY",
            "recorded_at": now.isoformat(),
            "setup_id": setup_id,
            "entry_price": ask,
            "entry_ask": ask,
            "entry_bid": self._positive(quote.get("bid")),
            "entry_ask_time_ms": self._positive(quote.get("ask_time_ms")),
            "entry_ask_age_seconds": self._positive(
                quote.get("ask_age_seconds")
            ),
            "entry_timestamp": (
                parent.get("entry_timestamp") or parent.get("signal_timestamp")
            ),
            "execution_model": "BIDASK_REPRICE_V1_EXACT_CYCLE",
            "parent_strategy_id": parent.get("strategy_id"),
            "parent_setup_id": setup_id,
            "parent_recorded_at": parent.get("parent_recorded_at"),
            "mirror_registered_at": now.isoformat(),
            "quote_resolved_at": now.isoformat(),
            "trade_intent": canonical_trade_intent(parent),
            "paper_only": True,
            "broker_execution_enabled": False,
        }
        self._append(row)
        self.active[setup_id] = row
        self.seen_entries.add(setup_id)
        self._write_status()
        return True

    def register_parent_exits(self, parent_exits, quotes, now=None):
        """Mirror parent exits now, using only quotes supplied in this call."""
        now = _utc(now or datetime.now(timezone.utc))
        completed = []

        for parent_exit in parent_exits:
            setup_id = self._setup_id(parent_exit)
            if (
                not setup_id
                or setup_id in self.parent_exits_seen
                or setup_id in self.seen_exits
            ):
                continue

            self.parent_exits_seen.add(setup_id)
            entry = self.active.get(setup_id)

            if entry is None:
                # This normally means the exact-cycle entry itself was
                # unpriced.  The parent exit is still observed and must not
                # create a later pricing opportunity.
                self._quarantine(
                    "BA_REPRICE_EXIT_UNAVAILABLE",
                    parent_exit,
                    now,
                    reason="exact_cycle_entry_unpriced_no_ba_position",
                )
                self.quarantined_exits += 1
                continue

            symbol = str(entry.get("symbol") or "").upper()
            quote = (quotes or {}).get(symbol) or {}
            bid = self._positive(quote.get("bid"))

            if bid is None:
                self._quarantine(
                    "BA_REPRICE_EXIT_UNAVAILABLE",
                    parent_exit,
                    now,
                    reason="exit_bid_unavailable_in_parent_cycle",
                )
                self.active.pop(setup_id, None)
                self.quarantined_exits += 1
                continue

            entry_price = float(entry["entry_price"])
            notional = float(entry.get("notional") or 0.0)
            bid_time_ms = self._positive(quote.get("bid_time_ms"))

            row = {
                **entry,
                "event_type": "BA_REPRICE_EXIT",
                "recorded_at": now.isoformat(),
                "exit_timestamp": parent_exit.get("exit_timestamp"),
                "exit_price": bid,
                "exit_bid": bid,
                "exit_bid_time_ms": bid_time_ms,
                "exit_bid_age_seconds": self._positive(
                    quote.get("bid_age_seconds")
                ),
                "exit_quote_resolved_at": now.isoformat(),
                "exit_resolution_delay_seconds": 0.0,
                "exit_ask": self._positive(quote.get("ask")),
                "exit_reason": parent_exit.get("exit_reason"),
                "parent_exit_price": parent_exit.get("exit_price"),
                "parent_exit_timestamp": parent_exit.get("exit_timestamp"),
                "return_pct": (bid / entry_price - 1.0) * 100.0,
                "pnl": notional * (bid / entry_price - 1.0),
            }
            self._append(row)
            self.active.pop(setup_id, None)
            self.seen_exits.add(setup_id)
            self.completed += 1
            completed.append(row)

        self._write_status()
        return completed

    def update_quotes(self, quotes, now=None):
        """Do not retroactively price parent events from later quotes.

        Kept as a compatibility no-op because the runner may still call this
        method for the separate quote-update cycle.
        """
        self._write_status()
        return []


# Explicit name for the pre-existing estimated fill/liquidity experiment.
IocL1PaperOutcomeTracker = BidAskPaperOutcomeTracker
