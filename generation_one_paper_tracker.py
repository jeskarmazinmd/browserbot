"""Prospective BA portfolios for frozen generation-one experiments only.

Experiments are counterfactual portfolios, never added together. Within each
portfolio, constituents share one deduplicated order, cash and displayed book.
Both entry and exit quantities consume side-specific timestamped liquidity.
"""
from collections import defaultdict
import copy
from datetime import datetime, timezone
import json
import math

from executable_paper_engine import classify_limit_order, executable_mark
from paper_outcome_tracker import PaperOutcomeTracker, NY, _utc
from strategies import generation_one as flash, generation_one_minute as minute
from strategies.output_switches import output_enabled
from strategies.pruning import output_is_pruned

FILE_STEM = "paper_generation_one_bidask_independent"
IDS = flash.IDS | minute.IDS


def spec_for(sid):
    return flash.spec_for(sid) if sid in flash.IDS else minute.spec_for(sid)


class GenerationOneBidAskTracker(PaperOutcomeTracker):
    # Execution mechanics are shared; subclasses own catalogs and durable files.
    IDS = IDS
    FILE_STEM = FILE_STEM
    flash_catalog = flash
    minute_catalog = minute
    EXECUTION_MODEL = "GENERATION_ONE_BIDASK_V1"
    DEFER_ENTRY_CHECKPOINT = False

    def spec_for(self, sid):
        return (self.flash_catalog.spec_for(sid) if sid in self.flash_catalog.IDS
                else self.minute_catalog.spec_for(sid))

    def metadata_for(self, sid):
        return (self.flash_catalog.metadata(sid) if sid in self.flash_catalog.IDS
                else self.minute_catalog.metadata(sid))

    def entry_gate(self, signal, quote, now):
        return None

    def quantity_limit(self, sid, signal, ask, cash, requested):
        return requested

    def __init__(self, data_root, *, now_provider=None, **kwargs):
        self._cash = {}
        self._liquidity = {}
        self._clock = now_provider or (lambda: datetime.now(timezone.utc))
        kwargs.setdefault("file_stem", self.FILE_STEM)
        kwargs.setdefault("use_observed_exit_prices", True)
        super().__init__(data_root, **kwargs)
        self.birth_path = self.root / (self.FILE_STEM + "_births.json")
        self.liquidity_path = self.root / (self.FILE_STEM + "_liquidity.json")
        # Fail closed on corrupt provenance. Never silently reset birth dates.
        self.births = json.loads(self.birth_path.read_text()) if self.birth_path.exists() else {}
        now = _utc(self._clock())
        for sid in sorted(self.IDS):
            self.births.setdefault(sid, max(now, _utc(self.flash_catalog.CREATED_UTC)).isoformat())
        self._atomic_json(self.birth_path, self.births)
        # Book consumption is recovered from the authoritative fill ledger.
        # The separate file is a diagnostic checkpoint, never authoritative.
        self._write_status()

    def _write_status(self):
        self._atomic_json(self.status_path, {
            "updated_at": _utc(self._clock()).isoformat(), "active": len(self.active),
            "completed": self.completed, "seen_setups": len(self.seen),
            "pricing": "LONG BUY@ask; SELL@bid; whole shares; partial exits",
            "quote_freshness_enforced": True, "displayed_liquidity_enforced": True,
            "shared_cash_per_strategy": True, "shared_book_per_strategy": True,
            "experiments_are_separate_counterfactual_portfolios": True,
            "broker_execution_enabled": False,
        })

    def _cash_for(self, sid, now):
        key = (sid, now.astimezone(NY).date().isoformat())
        if key not in self._cash:
            # Daily cash reset cannot create free cash for overnight residuals.
            deployed = sum(row["remaining_qty"] * row["entry_price"]
                           for row in self.active.values() if row["strategy_id"] == sid)
            self._cash[key] = getattr(self.spec_for(sid), "equity", 5000.0) - deployed
        return key, self._cash[key]

    def _recover(self):
        # Ledger events carry complete residual quantities and cash movements.
        # A checkpoint only restores dynamic state newer than that ledger row.
        if self.ledger_path.exists():
            with self.ledger_path.open() as handle:
                self._recover_rows(handle)
        if self.state_path.exists():
            state = json.loads(self.state_path.read_text())
            for saved in state.get("active", []):
                record = self.active.get(saved["setup_id"])
                if (record is not None and saved["remaining_qty"] == record["remaining_qty"]
                        and saved.get("last_observed_at", "") >= record.get("last_observed_at", "")):
                    record.update(saved)
        for setup, row in self.active.items():
            self.by_symbol[row["symbol"]].add(setup)

    def _recover_rows(self, handle):
        for line in handle:
            try:
                row = json.loads(line)
            except ValueError:
                continue
            setup, sid = row.get("setup_id"), row.get("strategy_id")
            if not setup or sid not in self.IDS:
                continue
            self.seen.add(setup)
            event = row.get("event_type")
            book = row.get("book_consumption")
            if book:
                self._liquidity[book["key"]] = {"identity": book["identity"], "used": book["used"]}
            if event == "PAPER_ENTRY":
                key, _ = self._cash_for(sid, _utc(row["entry_timestamp"]))
                self._cash[key] -= row["notional"]
                self.active[setup] = row
            elif event in {"PAPER_PARTIAL_EXIT", "PAPER_EXIT"}:
                key, _ = self._cash_for(sid, _utc(row["exit_timestamp"]))
                self._cash[key] += row["exit_fill_proceeds"]
                if event == "PAPER_EXIT":
                    self.active.pop(setup, None)
                    self.completed += 1
                else:
                    self.active[setup] = row

    def symbols(self, limit=400):
        return set(sorted(self.by_symbol)[:limit])

    def _available_book(self, sid, symbol, quote, action):
        quote = dict(quote or {})
        side = "ask" if action == "BUY" else "bid"
        price = flash.num(quote.get(side))
        stamp = quote.get(side + "_time_ms", quote.get("quote_time_ms"))
        # Timestamp-less quotes may mark via supplied age, but cannot prove
        # book renewal for a shared portfolio. Fail closed for fills.
        key = f"{sid}|{symbol}|{side}"
        identity = [stamp]
        saved = self._liquidity.get(key)
        used = saved["used"] if saved and saved["identity"] == identity else 0
        raw_size = quote.get(side + "_size_raw")
        if raw_size is None:
            raw_size = quote.get(side + "_size")
        size = flash.num(raw_size, -1)
        older_book = (saved and stamp is not None and
                      flash.num(stamp) < flash.num(saved["identity"][0]))
        if stamp is None:
            quote[side + "_size_raw"] = None
            quote[side + "_size"] = None
        elif older_book:
            quote[side + "_size_raw"] = 0
        elif size >= 0:
            quote[side + "_size_raw"] = max(0, math.floor(size) - used)
        return quote, key, identity, used

    def _consume(self, key, identity, used, quantity):
        self._liquidity[key] = {"identity": identity, "used": used + quantity}
        self._atomic_json(self.liquidity_path, self._liquidity)

    def _reject(self, signal, setup, now, reason, decision=None):
        self.seen.add(setup)
        self._append({"event_type": "PAPER_ENTRY_REJECTED", "setup_id": setup,
                      "strategy_id": signal["strategy_id"], "symbol": signal.get("symbol"),
                      "signal_timestamp": signal.get("timestamp"), "recorded_at": now.isoformat(),
                      "reason": reason, "execution": decision.as_dict() if decision else None,
                      "research_metadata": signal.get("research_metadata"),
                      "prospective_start_utc": self.births[signal["strategy_id"]],
                      "paper_only": True, "broker_execution_enabled": False})
        return False

    def register_signal(self, signal, quote, now):
        now = _utc(now)
        sid = signal.get("strategy_id")
        if sid not in self.IDS or not output_enabled(sid) or output_is_pruned(sid):
            return False
        ts = flash.timestamp(signal.get("timestamp"))
        if ts is None:
            return False
        setup = self._setup_id(signal, ts)
        if setup in self.seen:
            return False
        if ts < _utc(self.births[sid]) or ts > now or (now - ts).total_seconds() > 120:
            return self._reject(signal, setup, now, "outside_prospective_signal_window")
        local = now.astimezone(NY)
        if not self.entry_start_minute_et <= local.hour * 60 + local.minute < self.entry_cutoff_minute_et:
            return self._reject(signal, setup, now, "outside_entry_window")
        spec = self.spec_for(sid)
        ask, bid = flash.num((quote or {}).get("ask")), flash.num((quote or {}).get("bid"))
        target, stop = flash.num(signal.get("target_price")), flash.num(signal.get("stop_price"))
        if ask <= 0 or bid <= 0 or target <= ask or not 0 < stop < bid or bid > ask:
            return self._reject(signal, setup, now, "invalid_executable_geometry")
        if sid in self.flash_catalog.IDS and (target / ask - 1) * 100 < .20:
            return self._reject(signal, setup, now, "insufficient_executable_remaining_upside")
        votes = (self.flash_catalog.executable_votes(sid, signal, ask, bid)
                 if sid in self.flash_catalog.IDS else tuple(signal.get("constituent_votes", ())))
        if len(votes) < spec.votes:
            return self._reject(signal, setup, now, "insufficient_executable_votes")
        reason = self.entry_gate(signal, quote, now)
        if reason:
            return self._reject(signal, setup, now, reason)
        key, cash = self._cash_for(sid, now)
        requested = math.floor(min(cash, spec.notional * (len(votes) if getattr(spec, "agreement_weighted", False) else 1)) / ask)
        risk = getattr(spec, "risk_fraction", None)
        if risk is not None:
            # Equity is cash plus deployed cost; no unobserved mark-up sizing.
            equity = cash + sum(row["remaining_qty"] * row["entry_price"]
                                for row in self.active.values() if row["strategy_id"] == sid)
            requested = min(math.floor(cash / ask), math.floor(equity * risk / (ask - stop)),
                            math.floor(equity * spec.max_position_fraction / ask))
        requested = self.quantity_limit(sid, signal, ask, cash, requested)
        if requested < 1:
            return self._reject(signal, setup, now, "insufficient_cash_or_risk_budget")
        book, book_key, identity, used = self._available_book(sid, signal["symbol"], quote, "BUY")
        decision = classify_limit_order(book, action="BUY", limit_price=ask, requested_qty=requested,
                                        now=now, max_quote_age_ms=5000)
        if decision.outcome not in {"FULL", "PARTIAL"}:
            return self._reject(signal, setup, now, decision.reason, decision)
        quantity = decision.filled_qty
        row = dict(signal)
        row.update(setup_id=setup, entry_price=ask, execution_entry_timestamp=now.isoformat(),
                   paper_notional=ask * quantity, requested_qty=requested, filled_qty=quantity,
                   entry_fill_outcome=decision.outcome, entry_bid=bid, entry_ask=ask,
                   entry_quote_age_ms=decision.quote_age_ms, displayed_ask_qty=decision.displayed_qty,
                   execution_model=self.EXECUTION_MODEL, prospective_start_utc=self.births[sid],
                   constituent_votes=list(votes), remaining_qty=quantity, realized_proceeds=0.0,
                   book_consumption={"key": book_key, "identity": identity, "used": used + quantity},
                   research_metadata=self.metadata_for(sid))
        if not super().register(row):
            return False
        self._cash[key] -= ask * quantity
        self._consume(book_key, identity, used, quantity)
        self._dirty = True
        self.checkpoint(force=not self.DEFER_ENTRY_CHECKPOINT)
        return True

    def update_quotes(self, quotes, now):
        now = _utc(now)
        closed = []
        for setup, record in sorted(list(self.active.items())):
            sid, symbol = record["strategy_id"], record["symbol"]
            quote = quotes.get(symbol)
            mark = executable_mark(quote, action="SELL", now=now, max_quote_age_ms=5000)
            if mark.get("state") != "EXECUTABLE":
                continue
            bid = mark["price"]
            if not record.get("pending_exit_reason"):
                # Run the established exit state machine without committing an
                # idealized whole-position exit. Only actual SELL fills commit.
                probe = copy.copy(self)
                updated = copy.deepcopy(record)
                probe.active = {setup: updated}
                probe.by_symbol = defaultdict(set, {symbol: {setup}})
                probe._append = lambda row: None
                probe.checkpoint = lambda **kwargs: None
                proposals = PaperOutcomeTracker.update(probe, {symbol: bid}, now)
                record.update(updated)
                self._dirty = True
                if not proposals:
                    continue
                record["pending_exit_reason"] = proposals[0]["exit_reason"]
            book, book_key, identity, used = self._available_book(sid, symbol, quote, "SELL")
            decision = classify_limit_order(book, action="SELL", limit_price=bid,
                                            requested_qty=record["remaining_qty"], now=now, max_quote_age_ms=5000)
            if decision.outcome not in {"FULL", "PARTIAL"}:
                continue
            key, _ = self._cash_for(sid, now)
            quantity = decision.filled_qty
            proceeds = quantity * bid
            record["remaining_qty"] -= quantity
            record["realized_proceeds"] += proceeds
            self._cash[key] += proceeds
            self._consume(book_key, identity, used, quantity)
            vwap = record["realized_proceeds"] / (record["filled_qty"] - record["remaining_qty"])
            final = record["remaining_qty"] == 0
            row = {**record, "event_type": "PAPER_EXIT" if final else "PAPER_PARTIAL_EXIT",
                   "book_consumption": {"key": book_key, "identity": identity, "used": used + quantity},
                   "recorded_at": now.isoformat(), "exit_timestamp": now.isoformat(),
                   "exit_fill_qty": quantity, "exit_fill_proceeds": proceeds,
                   "exit_fill_price": bid, "exit_fill_outcome": decision.outcome,
                   "exit_price": vwap, "exit_bid": bid, "exit_ask": mark.get("ask"),
                   "exit_quote_age_ms": decision.quote_age_ms,
                   "exit_reason": record["pending_exit_reason"],
                   "pnl": record["realized_proceeds"] - (record["filled_qty"] - record["remaining_qty"]) * record["entry_price"],
                   "return_pct": (vwap / record["entry_price"] - 1) * 100}
            self._append(row)
            if final:
                closed.append(row)
                del self.active[setup]
                self.by_symbol[symbol].discard(setup)
                if not self.by_symbol[symbol]:
                    del self.by_symbol[symbol]
                self.completed += 1
        self.checkpoint(force=True)
        return closed
