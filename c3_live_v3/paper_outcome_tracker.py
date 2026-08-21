"""Lightweight, durable paper-signal outcome tracking.

This module deliberately does not read the quote tape.  The strategy runner
passes it the latest price for each symbol once per cycle, so work is
proportional to active paper trades rather than tape size.
"""

from __future__ import annotations

import json
import math
import os
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from strategies import strategy_o


NY = ZoneInfo("America/New_York")

OPTIONAL_FIELDS = (
    "exit_model", "source_strategy_id", "source_setup_id",
    "activation_gain_pct", "pullback_from_high_pct",
    "no_new_high_seconds", "lower_samples", "min_total_decline_pct",
    "slope_window_seconds", "negative_slope_pct_per_minute",
    "checkpoint_seconds", "checkpoint_max_return_pct",
    "activated", "activation_time", "highest_price", "highest_price_time",
    "recent_samples", "checkpoint_evaluated",
    "mode", "seconds", "min_return_pct", "min_mfe_pct",
    "required_gain_pct", "trail_from_high_pct",
    "pullback_from_first_high_pct", "rebound_from_pullback_low_pct",
    "stop_loss_fraction", "entered", "source_entry_price",
    "first_high", "pullback_low", "original_target_price",
    "flash_drop_volatility_units",
    "last_observed_price", "last_observed_at",
    "breakeven_after_activation",
    "capacity_filter_passed", "capacity_filter_audit",
    "capacity_filter_version",
    "exit_duration_sweep_seconds", "exit_duration_sweep_parent",
    "exit_duration_sweep_version",
    "forward_start_utc", "paper_only",
    "m2_family_variant", "m2_family_version",
)


def _utc(value):
    if isinstance(value, datetime):
        result = value
    else:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if result.tzinfo is None:
        result = result.replace(tzinfo=timezone.utc)
    return result.astimezone(timezone.utc)


def _number(value):
    try:
        result = float(value)
        return result if math.isfinite(result) and result > 0 else None
    except (TypeError, ValueError):
        return None


class PaperOutcomeTracker:
    """Record signal entries and close them from current quote snapshots."""

    def __init__(
        self, data_root, *, notional=1000.0, eod_hour=15, eod_minute=55,
        entry_start_hour=9, entry_start_minute=30,
        entry_cutoff_hour=15, entry_cutoff_minute=30,
        checkpoint_seconds=300,
    ):
        self.root = Path(data_root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.ledger_path = self.root / "paper_signal_outcomes.jsonl"
        self.state_path = self.root / "paper_signal_active.json"
        self.status_path = self.root / "paper_signal_status.json"
        self.notional = float(notional)
        self.eod_hour = int(eod_hour)
        self.eod_minute = int(eod_minute)
        self.entry_start_minute_et = int(entry_start_hour) * 60 + int(entry_start_minute)
        self.entry_cutoff_minute_et = int(entry_cutoff_hour) * 60 + int(entry_cutoff_minute)
        self.checkpoint_seconds = float(checkpoint_seconds)
        self.seen = set()
        self.active = {}
        self.by_symbol = defaultdict(set)
        self.completed = 0
        self.rejected_outside_entry_window = 0
        self._dirty = False
        self._last_checkpoint = 0.0
        self._recover()

    def _recover(self):
        # The ledger is authoritative for durable deduplication.  Streaming it
        # once at boot avoids repeatedly persisting a potentially large set.
        if self.ledger_path.exists():
            with self.ledger_path.open(errors="replace") as handle:
                for line in handle:
                    try:
                        row = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    setup_id = row.get("setup_id")
                    if not setup_id:
                        continue
                    event_type = row.get("event_type")
                    self.seen.add(setup_id)
                    if event_type == "PAPER_ENTRY":
                        record = {
                            key: row.get(key)
                            for key in (
                                "setup_id", "strategy_id", "symbol",
                                "signal_timestamp", "entry_price",
                                "target_price", "stop_price", "notional",
                            )
                        }
                        for key in OPTIONAL_FIELDS:
                            if key in row:
                                record[key] = row[key]
                        if record.get("symbol"):
                            self.active[setup_id] = record
                    elif event_type == "PAPER_EXIT":
                        self.active.pop(setup_id, None)
                        self.completed += 1
        # Overlay the latest checkpoint only onto trades the authoritative
        # ledger still considers active. This restores dynamic-exit state
        # without allowing a stale checkpoint to resurrect a completed trade.
        if self.state_path.exists():
            try:
                checkpoint = json.loads(self.state_path.read_text())
                checkpoint_records = checkpoint.get("active", [])
            except (OSError, ValueError, TypeError):
                checkpoint_records = []
            for saved in checkpoint_records:
                setup_id = saved.get("setup_id")
                if setup_id in self.active:
                    self.active[setup_id].update(saved)
        for setup_id, record in self.active.items():
            self.by_symbol[str(record["symbol"])].add(setup_id)
        self._write_status()

    def _append(self, row):
        with self.ledger_path.open("a") as handle:
            handle.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")

    def _atomic_json(self, path, value):
        temporary = path.with_name(path.name + ".tmp")
        with temporary.open("w") as handle:
            json.dump(value, handle, separators=(",", ":"), default=str)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)

    def _persist_active(self):
        self._atomic_json(
            self.state_path,
            {
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "active": list(self.active.values()),
            },
        )

    def _write_status(self):
        try:
            self._atomic_json(
                self.status_path,
                {
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                    "active": len(self.active),
                    "completed": self.completed,
                    "seen_setups": len(self.seen),
                    "notional_per_signal": self.notional,
                    "rejected_outside_entry_window": self.rejected_outside_entry_window,
                },
            )
        except OSError:
            pass

    @staticmethod
    def _setup_id(signal, timestamp):
        supplied = signal.get("setup_id")
        if supplied:
            return str(supplied)
        minute = timestamp.replace(second=0, microsecond=0).isoformat()
        return f"{signal.get('strategy_id')}|{signal.get('symbol')}|{minute}"

    def register(self, signal):
        """Durably register one signal; return False for invalid/duplicate input."""
        try:
            timestamp = _utc(signal.get("timestamp"))
        except (TypeError, ValueError):
            return False
        timestamp_et = timestamp.astimezone(NY)
        minute_et = timestamp_et.hour * 60 + timestamp_et.minute
        if not (self.entry_start_minute_et <= minute_et < self.entry_cutoff_minute_et):
            self.rejected_outside_entry_window += 1
            self._dirty = True
            return False
        strategy_id = str(signal.get("strategy_id") or "").strip()
        symbol = str(signal.get("symbol") or "").strip()
        entry = _number(signal.get("entry_price"))
        target = _number(signal.get("target_price"))
        stop = _number(signal.get("stop_price"))
        if not strategy_id or not symbol or not entry or not target or not stop:
            return False
        setup_id = self._setup_id(signal, timestamp)
        if setup_id in self.seen:
            return False

        record = {
            "setup_id": setup_id,
            "strategy_id": strategy_id,
            "symbol": symbol,
            "signal_timestamp": timestamp.isoformat(),
        "entry_timestamp": (
            timestamp.isoformat()
            if signal.get("entered", True) is not False
            else None
        ),
            "entry_price": entry,
            "target_price": target,
            "stop_price": stop,
            "notional": self.notional,
        }
        for key in OPTIONAL_FIELDS:
            if key in signal:
                record[key] = signal[key]
        record.setdefault("exit_model", "target_stop_eod")
        record.setdefault("activated", False)
        record.setdefault("highest_price", entry)
        record.setdefault("highest_price_time", timestamp.isoformat())
        record.setdefault("recent_samples", [])
        record.setdefault("checkpoint_evaluated", False)
        record.setdefault("original_target_price", target)
        record.setdefault("last_observed_price", entry)
        record.setdefault("last_observed_at", timestamp.isoformat())
        self._append({
            "event_type": "PAPER_ENTRY",
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            **record,
        })
        self.seen.add(setup_id)
        self.active[setup_id] = record
        self.by_symbol[symbol].add(setup_id)
        self._dirty = True
        return True

    def checkpoint(self, *, force=False):
        """Periodically snapshot active state without rewriting it per signal."""
        if not self._dirty:
            return
        now = time.monotonic()
        if not force and now - self._last_checkpoint < self.checkpoint_seconds:
            return
        self._persist_active()
        self._write_status()
        self._dirty = False
        self._last_checkpoint = now

    def update(self, prices, now):
        """Close target/stop/EOD outcomes using one current-price snapshot."""
        now = _utc(now)
        now_et = now.astimezone(NY)
        at_eod = (now_et.hour, now_et.minute) >= (self.eod_hour, self.eod_minute)
        closed = []
        for symbol in tuple(self.by_symbol):
            observed_now = _number(prices.get(symbol))
            for setup_id in tuple(self.by_symbol[symbol]):
                record = self.active.get(setup_id)
                if not record:
                    continue
                if observed_now is not None:
                    observed = observed_now
                    record["last_observed_price"] = observed
                    record["last_observed_at"] = now.isoformat()
                    self._dirty = True
                elif at_eod or now_et.date() > _utc(record["signal_timestamp"]).astimezone(NY).date():
                    observed = _number(record.get("last_observed_price"))
                else:
                    continue
                if observed is None:
                    continue
                signal_day = _utc(record["signal_timestamp"]).astimezone(NY).date()
                model = record.get("exit_model", "target_stop_eod")
                reason = exit_price = None
                if model == "second_leg" and not record.get("entered"):
                    if now_et.date() > signal_day or at_eod:
                        reason, exit_price = "NO_SECOND_LEG", record["entry_price"]
                    else:
                        reason, exit_price = self._update_second_leg(record, observed, now)
                    if reason is None:
                        continue
                elif observed <= record["stop_price"]:
                    reason, exit_price = "STOP", record["stop_price"]
                elif now_et.date() > signal_day or at_eod:
                    reason, exit_price = "EOD", observed
                elif model == "checkpoint_target_stop_eod":
                    if observed >= record["target_price"]:
                        reason, exit_price = "TARGET", record["target_price"]
                    else:
                        seconds = record.get("checkpoint_seconds")
                        age = (now - _utc(record["signal_timestamp"])).total_seconds()
                        if (
                            seconds is not None
                            and not record.get("checkpoint_evaluated")
                            and age >= float(seconds)
                        ):
                            record["checkpoint_evaluated"] = True
                            checkpoint_return = (observed / record["entry_price"] - 1.0) * 100.0
                            if checkpoint_return <= float(record.get("checkpoint_max_return_pct", 0.0)):
                                reason, exit_price = "NO_PROGRESS_CHECKPOINT", observed
                            self._dirty = True
                elif model in {"c1", "c2", "c3", "c4"}:
                    reason, exit_price = self._update_dynamic(record, observed, now, model)
                elif model == "adaptive_trail_target":
                    if observed >= record["target_price"]:
                        reason, exit_price = "TARGET", record["target_price"]
                    else:
                        reason, exit_price = self._update_adaptive_trail(record, observed, now)
                elif model == "k_checkpoint":
                    if observed >= record["target_price"]:
                        reason, exit_price = "TARGET", record["target_price"]
                    else:
                        reason, exit_price = self._update_k_checkpoint(record, observed, now)
                elif observed >= record["target_price"]:
                    reason, exit_price = "TARGET", record["target_price"]
                if reason is None:
                    continue
                pnl = record["notional"] * (exit_price / record["entry_price"] - 1.0)
                row = {
                    "event_type": "PAPER_EXIT",
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    **record,
                    "exit_timestamp": now.isoformat(),
                    "exit_price": exit_price,
                    "observed_price": observed,
                    "exit_reason": reason,
                    "return_pct": (exit_price / record["entry_price"] - 1.0) * 100.0,
                    "pnl": pnl,
                }
                self._append(row)
                closed.append(row)
                del self.active[setup_id]
                self.by_symbol[symbol].discard(setup_id)
                self.completed += 1
            if not self.by_symbol[symbol]:
                del self.by_symbol[symbol]
        if closed:
            self._dirty = True
        self.checkpoint()
        return closed

    def _update_k_checkpoint(self, record, price, now):
        highest = max(float(record.get("highest_price", record["entry_price"])), price)
        record["highest_price"] = highest
        self._dirty = True
        if record.get("checkpoint_evaluated"):
            return None, None
        age = (now - _utc(record["signal_timestamp"])).total_seconds()
        if age < float(record.get("seconds", 0)):
            return None, None
        record["checkpoint_evaluated"] = True
        ret = (price / record["entry_price"] - 1.0) * 100.0
        mfe = (highest / record["entry_price"] - 1.0) * 100.0
        mode = record.get("mode")
        should_exit = (
            mode == "fixed_exit"
            or (mode == "conditional_return" and ret <= float(record.get("min_return_pct", 0.0)))
            or (mode == "conditional_mfe" and mfe < float(record.get("min_mfe_pct", 0.0)))
            or (mode == "conditional_reach" and mfe < float(record.get("required_gain_pct", 0.0)))
        )
        if should_exit:
            return f"{str(mode).upper()}_{int(float(record.get('seconds', 0)))}S", price
        return None, None

    def _update_adaptive_trail(self, record, price, now):
        highest = max(float(record.get("highest_price", record["entry_price"])), price)
        record["highest_price"] = highest
        if not record.get("activated") and price >= record["entry_price"] * (1.0 + float(record.get("activation_gain_pct", 0.3)) / 100.0):
            record["activated"] = True
            record["activation_time"] = now.isoformat()
        self._dirty = True
        if record.get("activated") and price <= highest * (1.0 - float(record.get("trail_from_high_pct", 0.2)) / 100.0):
            return "ADAPTIVE_TRAIL", price
        return None, None

    def _update_second_leg(self, record, price, now):
        """Delegate O-specific delayed-entry behavior to strategy O."""
        result = strategy_o.update_second_leg(record, price, now)
        self._dirty = True
        return result

    def _update_dynamic(self, record, price, now, model):
        """Advance one C-family exit state machine from the latest quote."""
        highest = float(record.get("highest_price", record["entry_price"]))
        if price > highest:
            highest = price
            record["highest_price"] = price
            record["highest_price_time"] = now.isoformat()
        activation_price = record["entry_price"] * (
            1.0 + float(record.get("activation_gain_pct", 0.3)) / 100.0
        )
        if not record.get("activated"):
            if price < activation_price:
                return None, None
            record["activated"] = True
            record["activation_time"] = now.isoformat()
            record["recent_samples"] = [[now.isoformat(), price]]
            self._dirty = True
            return None, None

        if (
            record.get("breakeven_after_activation")
            and price <= float(record["entry_price"])
        ):
            return "BREAKEVEN_PROTECT", float(record["entry_price"])

        samples = list(record.get("recent_samples") or [])
        samples.append([now.isoformat(), price])
        if model == "c1":
            pullback = (highest - price) / highest * 100.0
            if pullback >= float(record.get("pullback_from_high_pct", 0.2)):
                return "TRAIL_PULLBACK", price
            samples = samples[-2:]
        elif model == "c2":
            high_time = _utc(record.get("highest_price_time"))
            if (now - high_time).total_seconds() >= float(record.get("no_new_high_seconds", 30.0)):
                return "NO_NEW_HIGH", price
            samples = samples[-2:]
        elif model == "c3":
            needed = int(record.get("lower_samples", 3)) + 1
            samples = samples[-needed:]
            if len(samples) >= needed:
                values = [float(sample[1]) for sample in samples]
                decline = (values[0] - values[-1]) / values[0] * 100.0
                if all(values[i] < values[i - 1] for i in range(1, len(values))) and decline >= float(record.get("min_total_decline_pct", 0.1)):
                    return "CONSECUTIVE_LOWER_QUOTES", price
        else:
            window = float(record.get("slope_window_seconds", 30.0))
            samples = [sample for sample in samples if (now - _utc(sample[0])).total_seconds() <= window]
            if len(samples) >= 2:
                elapsed = (now - _utc(samples[0][0])).total_seconds() / 60.0
                slope = ((price / float(samples[0][1]) - 1.0) * 100.0 / elapsed) if elapsed > 0 else 0.0
                if slope <= float(record.get("negative_slope_pct_per_minute", -0.2)):
                    return "NEGATIVE_SLOPE", price
        record["recent_samples"] = samples
        self._dirty = True
        return None, None
