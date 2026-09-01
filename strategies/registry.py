"""Cadence-aware snapshot-native strategy registry."""

from __future__ import annotations

import importlib
import multiprocessing
from multiprocessing.connection import wait
import os
import time
from strategy_diagnostics import diagnostics

from . import strategy_a
from . import strategy_b
from . import strategy_c1f1
from . import strategy_c1f1mid, strategy_c1f1r65, strategy_c1f1pb15
from . import strategy_j2t15, strategy_j2mid, strategy_j2rb30
from . import (
    strategy_c3sc,
    strategy_c3n20, strategy_c3n25, strategy_c3n30, strategy_c3n40, strategy_c3n50,
    strategy_c3n25a05, strategy_c3n25a10, strategy_c3n25a20, strategy_c3n25a50,
    strategy_c3n25t15, strategy_c3n25t60,
    strategy_c3n25s10, strategy_c3n25s10dup, strategy_c3n25s15, strategy_c3n25s25,
    strategy_c3n25be,
    strategy_c3n25w20, strategy_c3n25w30,
    strategy_c3p25, strategy_c3l25,
    strategy_c3l25q2, strategy_c3l25q4,
    strategy_c3l25d05, strategy_c3l25d20,
)
from . import strategy_d
from . import strategy_h
from . import strategy_c2t9, strategy_c2t35, strategy_c1t9, strategy_gt9, strategy_et29, strategy_pt325, strategy_pt325315, strategy_pmid, strategy_ht5, strategy_qmid, strategy_qv425, strategy_lt65


FLASH_STRATEGY_MODULES = {
    module.STRATEGY_ID: module
    for module in (
        strategy_a, strategy_b, strategy_c1f1, strategy_d, strategy_h,
        strategy_c1f1mid, strategy_c1f1r65, strategy_c1f1pb15,
        strategy_j2t15, strategy_j2mid, strategy_j2rb30,
        strategy_c2t9, strategy_c2t35, strategy_c1t9, strategy_gt9, strategy_et29, strategy_pt325, strategy_pt325315, strategy_pmid, strategy_ht5, strategy_qmid, strategy_qv425, strategy_lt65,
        strategy_c3sc,
        strategy_c3n20, strategy_c3n25, strategy_c3n30, strategy_c3n40, strategy_c3n50,
        strategy_c3n25a05, strategy_c3n25a10, strategy_c3n25a20, strategy_c3n25a50,
        strategy_c3n25t15, strategy_c3n25t60,
        strategy_c3n25s10, strategy_c3n25s10dup, strategy_c3n25s15, strategy_c3n25s25,
    strategy_c3n25be,
    strategy_c3n25w20, strategy_c3n25w30,
        strategy_c3p25, strategy_c3l25,
    strategy_c3l25q2, strategy_c3l25q4,
    strategy_c3l25d05, strategy_c3l25d20,
    )
}


def flash_strategy_configs():
    return {
        strategy_id: dict(module.CONFIG)
        for strategy_id, module in FLASH_STRATEGY_MODULES.items()
    }


def flash_accepts(strategy_id, event, global_max_drop_pct):
    return FLASH_STRATEGY_MODULES[strategy_id].accepts_flash(
        event,
        global_max_drop_pct,
    )


def refresh_flash_entry(strategy_id, event, current_price):
    return FLASH_STRATEGY_MODULES[strategy_id].refresh_event_for_entry(
        event,
        current_price,
    )


def validate_flash_entry(
    strategy_id,
    event,
    default_min_remaining_upside_pct,
):
    module = FLASH_STRATEGY_MODULES[strategy_id]

    try:
        return module.validate_confirmed_entry(
            event,
            default_min_remaining_upside_pct,
        )
    except TypeError:
        return module.validate_confirmed_entry(event)



STRATEGY_CLASSES = [
    ("strategy_ema1", "EMA1Strategy"),
    ("strategy_ema1t50", "Strategy"),
    ("strategy_ema1v15", "Strategy"),
    ("strategy_ema1rr", "Strategy"),
    ("strategy_ema2", "EMA2Strategy"),
    ("strategy_ema3", "EMA3Strategy"),
    ("strategy_sma1", "SMA1Strategy"),
    ("strategy_vwema1", "VWEMA1Strategy"),
    ("strategy_tf1", "TF1Strategy"),
    ("strategy_rs1", "RS1Strategy"),
    ("strategy_rs2", "RS2Strategy"),
    ("strategy_rs3", "RS3Strategy"),
    ("strategy_m1", "M1Strategy"),
    ("strategy_m2", "M2Strategy"),
    ("strategy_m3", "M3Strategy"),
    ("strategy_mc1", "MC1Strategy"),
    ("strategy_tl1", "TL1Strategy"),
    ("strategy_av1", "AV1Strategy"),
    ("strategy_td1", "TD1Strategy"),
    ("strategy_qtd1x", "QTD1XStrategy"),
    ("strategy_ptd1x", "PTD1XStrategy"),
    ("strategy_gtmx", "GTMXStrategy"),
    ("strategy_pairmr1", "PAIRMR1Strategy"),
    ("strategy_leadbask1", "LEADBASK1Strategy"),
    ("strategy_sectorh1", "SECTORH1Strategy"),
    ("strategy_cmdmetmr1", "Strategy"),
    ("strategy_cmdmettr1", "Strategy"),
    ("strategy_cmdgdr1", "Strategy"),
    ("strategy_cmdgdu1", "Strategy"),
    ("strategy_cmdoil1", "Strategy"),
    ("strategy_cmdgas1", "Strategy"),
    ("strategy_cmdmin1", "Strategy"),
    ("strategy_cmdcop1", "Strategy"),
    ("strategy_cmdbrd1", "Strategy"),
    ("strategy_cmdrot1", "Strategy"),
    ("strategy_shockr1", "Strategy"),
    ("strategy_shockr2", "Strategy"),
    ("strategy_prevr1", "Strategy"),
    ("strategy_prevr2", "Strategy"),
    ("strategy_volr1", "Strategy"),
    ("strategy_volr2", "Strategy"),
    ("strategy_trendx1", "Strategy"),
    ("strategy_trendx2", "Strategy"),
    ("strategy_accel1", "Strategy"),
    ("strategy_accel2", "Strategy"),
    ("strategy_pullcont1", "Strategy"),
    ("strategy_pullcont2", "Strategy"),
    ("strategy_brk20", "Strategy"),
    ("strategy_brk30", "Strategy"),
    ("strategy_compx1", "Strategy"),
    ("strategy_compx2", "Strategy"),
    ("strategy_breadth1", "Strategy"),
    ("strategy_breadth2", "Strategy"),
    ("strategy_openmom1", "Strategy"),
    ("strategy_midrev1", "Strategy"),
    ("strategy_closemom1", "Strategy"),
    ("strategy_entropy1", "Strategy"),
    ("strategy_pairmr2", "Strategy"),
    ("strategy_pairtr1", "Strategy"),
    ("strategy_invpair1", "Strategy"),
    ("strategy_leadbask2", "Strategy"),
    ("strategy_peerbask1", "Strategy"),
    ("strategy_mktneut1", "Strategy"),
    ("strategy_sectorrot1", "Strategy"),
    ("strategy_xassetpair1", "Strategy"),
    ("strategy_sh1", "SH1Strategy"),
    ("strategy_cv1", "CV1Strategy"),
    ("strategy_hl1", "HL1Strategy"),
    ("strategy_vt1", "VT1Strategy"),
    ("strategy_pd1", "PD1Strategy"),
    ("strategy_bo1", "BO1Strategy"),
    ("strategy_ge1", "GE1Strategy"),
    ("strategy_gm1", "GM1Strategy"),
    ("strategy_gp1", "GP1Strategy"),
    ("strategy_gr1", "GR1Strategy"),
    ("strategy_gt1", "GT1Strategy"),
    ("strategy_or1", "OR1Strategy"),
    ("strategy_spy_or5", "SPYOR5Strategy"),
    ("strategy_spy_or15", "SPYOR15Strategy"),
    ("strategy_spy_or30", "SPYOR30Strategy"),
    ("strategy_spy_mom1", "SPYMOM1Strategy"),
    ("strategy_spy_mr1", "SPYMR1Strategy"),
    ("strategy_spy_br1", "SPYBR1Strategy"),
    ("strategy_spy_xa1", "SPYXA1Strategy"),
    ("strategy_spy_ens1", "SPYENS1Strategy"),
]


# A/B/D/H remain on the established pending-rebound engine until their
# snapshot replacements reproduce the full legacy event schema.
LEGACY_FLASH_STRATEGY_IDS = frozenset({
    "A",
    "B",
    "D",
    "H",
})


# These strategies require current-cycle prices or explicitly use raw,
# time-weighted snapshot behavior. They are not activated in the runner until
# their retained state is compacted and complete-cycle tick delivery exists.
# Every snapshot strategy now consumes completed-minute observations.
# No strategy retains duplicated raw-tick history.
TICK_STRATEGY_IDS = frozenset()

REPORTING_STRATEGY_MODULES = {}

# These reporting-era definitions are now evaluated prospectively from their
# live A/B/D parent signals by strategies.derived_runtime.  Keeping this set
# explicit makes operational diagnostics distinguish active derived modules
# from definitions that remain reporting-only.
DERIVED_RUNTIME_STRATEGY_IDS = frozenset({
    "C1", "C2", "C3", "C4", "F", "G",
    "J1", "J2", "J6", "L", "O", "R", "S",
})

for _strategy_id in (
    "C1", "C2", "C3", "C4", "E", "F", "G", "I",
    "J1", "J2", "J3", "J4", "J5", "J6",
    "K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8", "K9",
    "L", "M", "N", "O", "P", "Q", "R", "S",
):
    REPORTING_STRATEGY_MODULES[_strategy_id] = importlib.import_module(
        f".strategy_{_strategy_id.lower()}",
        __package__,
    )


FAILED_STRATEGIES = []


def _strategy_id(strategy) -> str:
    return str(
        getattr(
            strategy,
            "name",
            getattr(strategy, "STRATEGY_ID", type(strategy).__name__),
        )
    )


def _load_strategies():
    loaded = []

    for module_name, class_name in STRATEGY_CLASSES:
        try:
            module = importlib.import_module(
                f".{module_name}",
                __package__,
            )

            cls = getattr(module, class_name)
            loaded.append(cls())

        except Exception as exc:
            FAILED_STRATEGIES.append(
                {
                    "strategy": module_name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    return loaded


DISABLED_RESEARCH_STRATEGY_IDS = frozenset({
    "SPY_XA1", "SHOCKR1", "VOLR1", "VOLR2", "BREADTH2",
    "EMA1RR", "EMA1V15", "HL1", "AV1", "TL1", "PTD1X",
    # Persistently negative independent leaves through 2026-09-01.  These do
    # not feed any successful descendants; history remains in /data.
    "GT1", "SH1", "ET29", "PT325", "HT5", "LT65",
})

ENABLED_STRATEGIES = [
    strategy
    for strategy in _load_strategies()
    if _strategy_id(strategy) not in DISABLED_RESEARCH_STRATEGY_IDS
]

FLASH_STRATEGIES = list(FLASH_STRATEGY_MODULES.values())

TICK_STRATEGIES = [
    strategy
    for strategy in ENABLED_STRATEGIES
    if _strategy_id(strategy) in TICK_STRATEGY_IDS
]

MINUTE_STRATEGIES = [
    strategy
    for strategy in ENABLED_STRATEGIES
    if (
        _strategy_id(strategy) not in LEGACY_FLASH_STRATEGY_IDS
        and _strategy_id(strategy) not in TICK_STRATEGY_IDS
    )
]


for failed in FAILED_STRATEGIES:
    print(
        "STRATEGY_LOAD_WARNING",
        failed["strategy"],
        failed["error"],
        flush=True,
    )


def _evaluate(snapshot, strategies):
    signals = []
    errors = []

    for strategy in strategies:
        strategy_id = _strategy_id(strategy)
        handler = getattr(strategy, "on_snapshot", None)

        if handler is None:
            errors.append(
                (
                    strategy_id,
                    RuntimeError("strategy missing on_snapshot"),
                )
            )
            continue

        try:
            result = handler(snapshot)

            if result:
                signals.extend(result)
            diagnostics.evaluated(
                strategy_id,
                snapshot.timestamp,
                len(snapshot.quotes),
                signal_count=len(result or []),
                nearest_miss=getattr(strategy, "nearest_miss", None),
            )

        except Exception as exc:
            diagnostics.evaluated(
                strategy_id,
                snapshot.timestamp,
                len(snapshot.quotes),
                error=f"{type(exc).__name__}: {exc}",
                nearest_miss=getattr(strategy, "nearest_miss", None),
            )
            errors.append(
                (
                    strategy_id,
                    exc,
                )
            )

    return signals, errors


def on_snapshot(snapshot):
    """Evaluate every loaded strategy; intended for tests and validation."""
    return _evaluate(snapshot, ENABLED_STRATEGIES)


def on_minute_snapshot(snapshot):
    """Evaluate bounded-state completed-minute strategies."""
    return _evaluate(snapshot, MINUTE_STRATEGIES)


def on_tick_snapshot(snapshot):
    """Evaluate tick/hybrid strategies after tick routing is activated."""
    return _evaluate(snapshot, TICK_STRATEGIES)


# Approximate warmed-up CPU seconds per full-universe minute.  These values are
# used only to balance persistent worker shards; they do not alter strategy
# behavior, thresholds, symbols, or signal ordering.
_MINUTE_STRATEGY_WEIGHTS = {
    "GP1": 1.40, "GT1": 1.15, "QTD1X": 0.79, "GTMX": 0.79,
    "M3": 0.63, "VT1": 0.50, "GM1": 0.46, "GE1": 0.45,
    "PTD1X": 0.39, "TL1": 0.39, "MC1": 0.38, "AV1": 0.36,
    "CV1": 0.34, "M2": 0.28, "GR1": 0.23, "M1": 0.15,
    "SH1": 0.15, "HL1": 0.14, "SMA1": 0.13, "VWEMA1": 0.12,
    "PD1": 0.11, "EMA2": 0.07, "TF1": 0.06, "EMA3": 0.05,
    "BO1": 0.04,
}


def _minute_strategy_specs():
    # Shard only strategies that the registry successfully loaded.
    return [
        (
            _strategy_id(strategy),
            type(strategy).__module__.rsplit(".", 1)[-1],
            type(strategy).__name__,
        )
        for strategy in MINUTE_STRATEGIES
    ]


def _balanced_shards(specs, shard_count):
    shards = [[] for _ in range(shard_count)]
    totals = [0.0] * shard_count
    weighted = sorted(
        specs,
        key=lambda spec: _MINUTE_STRATEGY_WEIGHTS.get(spec[0], 0.01),
        reverse=True,
    )
    for spec in weighted:
        index = min(range(shard_count), key=totals.__getitem__)
        shards[index].append(spec)
        totals[index] += _MINUTE_STRATEGY_WEIGHTS.get(spec[0], 0.01)
    return shards


def _minute_worker(connection, specs):
    strategies = []
    for strategy_id, module_name, class_name in specs:
        module = importlib.import_module(f".{module_name}", __package__)
        strategies.append((strategy_id, getattr(module, class_name)()))

    while True:
        command = connection.recv()
        if command is None:
            break
        sequence, snapshot = command
        rows = []
        for strategy_id, strategy in strategies:
            started = time.perf_counter()
            try:
                result = strategy.on_snapshot(snapshot) or []
                error = None
            except Exception as exc:
                result = []
                error = f"{type(exc).__name__}: {exc}"
            rows.append({
                "strategy_id": strategy_id,
                "signals": result,
                "error": error,
                "nearest_miss": getattr(strategy, "nearest_miss", None),
                "elapsed_seconds": time.perf_counter() - started,
            })
        connection.send((sequence, rows))
    connection.close()


class MinuteStrategyShardError(RuntimeError):
    """Recoverable infrastructure failure affecting one strategy shard."""


class MinuteStrategyPool:
    """Persistent process shards for stateful completed-minute strategies."""

    def __init__(self, shard_count=None, timeout_seconds=None):
        requested = int(
            shard_count
            if shard_count is not None
            else os.environ.get(
                "MINUTE_STRATEGY_SHARDS",
                str(min(8, max(1, os.cpu_count() or 1))),
            )
        )
        self.timeout_seconds = float(
            timeout_seconds
            if timeout_seconds is not None
            else os.environ.get("MINUTE_STRATEGY_TIMEOUT_SECONDS", "55")
        )
        self.specs = _minute_strategy_specs()
        self.order = {spec[0]: index for index, spec in enumerate(self.specs)}
        self.sequence = 0
        self.closed = False
        self.workers = []
        self.restart_counts = {}

        shard_count = max(1, min(requested, len(self.specs)))
        if shard_count == 1:
            self.local_strategies = MINUTE_STRATEGIES
            return

        self.local_strategies = None
        self.context = multiprocessing.get_context("fork")
        for index, shard in enumerate(_balanced_shards(self.specs, shard_count)):
            self.workers.append(self._spawn_worker(index, shard))

    @property
    def shard_count(self):
        return len(self.workers) or 1

    def _spawn_worker(self, index, shard):
        parent, child = self.context.Pipe()
        process = self.context.Process(
            target=_minute_worker,
            args=(child, shard),
            name=f"minute-strategy-{index}",
            daemon=True,
        )
        process.start()
        child.close()
        return process, parent, shard

    @staticmethod
    def _stop_worker(worker):
        process, connection, _ = worker
        try:
            connection.close()
        except OSError:
            pass
        if process.is_alive():
            process.terminate()
        process.join(timeout=2.0)
        if process.is_alive():
            process.kill()
            process.join(timeout=2.0)

    def _replace_worker(self, index, reason):
        process, _, shard = self.workers[index]
        strategy_ids = [spec[0] for spec in shard]
        self._stop_worker(self.workers[index])
        self.workers[index] = self._spawn_worker(index, shard)
        restart_count = self.restart_counts.get(index, 0) + 1
        self.restart_counts[index] = restart_count
        message = (
            f"shard={index} worker={process.name} reason={reason} "
            f"strategies={','.join(strategy_ids)} restart_count={restart_count}"
        )
        print(f"MINUTE_STRATEGY_SHARD_RESTART {message}", flush=True)
        return [
            {
                "strategy_id": strategy_id,
                "signals": [],
                "error": f"MinuteStrategyShardError: {message}",
                "nearest_miss": None,
                "elapsed_seconds": 0.0,
            }
            for strategy_id in strategy_ids
        ]

    def evaluate(self, snapshot):
        if self.closed:
            raise RuntimeError("minute strategy pool is closed")
        if self.local_strategies is not None:
            return _evaluate(snapshot, self.local_strategies)

        self.sequence += 1
        sequence = self.sequence
        pending = {}
        results = []
        for index, (process, connection, _) in enumerate(list(self.workers)):
            if not process.is_alive():
                results.extend(self._replace_worker(index, "worker_exited_before_send"))
                continue
            try:
                connection.send((sequence, snapshot))
            except (BrokenPipeError, EOFError, OSError) as exc:
                results.extend(self._replace_worker(
                    index,
                    f"send_failed:{type(exc).__name__}:{exc}",
                ))
                continue
            pending[connection] = index

        deadline = time.monotonic() + self.timeout_seconds
        while pending:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            ready = wait(list(pending), timeout=remaining)
            if not ready:
                break
            for connection in ready:
                index = pending.pop(connection)
                try:
                    returned_sequence, rows = connection.recv()
                except (EOFError, OSError) as exc:
                    results.extend(self._replace_worker(
                        index,
                        f"receive_failed:{type(exc).__name__}:{exc}",
                    ))
                    continue
                if returned_sequence != sequence:
                    results.extend(self._replace_worker(
                        index,
                        "sequence_mismatch:"
                        f"expected={sequence}:received={returned_sequence}",
                    ))
                    continue
                results.extend(rows)

        for connection, index in list(pending.items()):
            results.extend(self._replace_worker(
                index,
                f"timeout_after_{self.timeout_seconds:.1f}s",
            ))

        results.sort(key=lambda row: self.order[row["strategy_id"]])
        signals = []
        errors = []
        for row in results:
            strategy_id = row["strategy_id"]
            row_signals = row["signals"]
            error = row["error"]
            diagnostics.evaluated(
                strategy_id,
                snapshot.timestamp,
                len(snapshot.quotes),
                signal_count=len(row_signals),
                error=error,
                nearest_miss=row["nearest_miss"],
            )
            signals.extend(row_signals)
            if error:
                error_type = (
                    MinuteStrategyShardError
                    if error.startswith("MinuteStrategyShardError:")
                    else RuntimeError
                )
                errors.append((strategy_id, error_type(error)))
        return signals, errors

    def close(self):
        if self.closed:
            return
        self.closed = True
        for process, connection, _ in self.workers:
            try:
                connection.send(None)
            except (BrokenPipeError, EOFError, OSError):
                pass
        for worker in self.workers:
            self._stop_worker(worker)
