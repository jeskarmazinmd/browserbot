"""Runtime derivation of paper-only strategies from flash-family signals."""

from copy import deepcopy

from . import (
    strategy_c1, strategy_c2, strategy_c3, strategy_c4,
    strategy_e, strategy_f, strategy_g, strategy_i,
    strategy_j1, strategy_j2, strategy_j3, strategy_j4, strategy_j5, strategy_j6,
    strategy_k1, strategy_k2, strategy_k3, strategy_k4, strategy_k5,
    strategy_k6, strategy_k7, strategy_k8, strategy_k9,
    strategy_l, strategy_m, strategy_n, strategy_o, strategy_p, strategy_q,
    strategy_r, strategy_s,
)


J_MODULES = (strategy_j1, strategy_j2, strategy_j3, strategy_j4, strategy_j5, strategy_j6)
C_MODULES = (strategy_c1, strategy_c2, strategy_c3, strategy_c4)
# K1-K9 are failed leaf experiments. Parent A remains active for its other
# derived strategies and shared signal production.
K_MODULES = ()
DERIVED_STRATEGY_IDS = frozenset({
    "C1", "C2", "C3", "C4", "E", "F", "G", "I",
    "J1", "J2", "J3", "J4", "J5", "J6",
    "K1", "K2", "K3", "K4", "K5", "K6", "K7", "K8", "K9",
    "L", "M", "N", "O", "P", "Q", "R", "S",
})


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clone(parent, strategy_id, *, exit_model="target_stop_eod", stop_fraction=None, **extra):
    result = deepcopy(parent)
    result["source_strategy_id"] = str(parent.get("strategy_id"))
    result["source_setup_id"] = parent.get("setup_id")
    result["strategy_id"] = strategy_id
    result["setup_id"] = (
        f"{strategy_id}|{parent.get('symbol')}|{parent.get('timestamp')}"
    )
    result["exit_model"] = exit_model
    entry = float(result["entry_price"])
    if stop_fraction is not None:
        result["stop_price"] = entry * (1.0 - float(stop_fraction))
    result.update(extra)
    return result


def derive_signals(parent):
    """Return the derived paper entries admitted by one flash signal."""
    strategy_id = str(parent.get("strategy_id") or "").upper()
    derived = []

    if strategy_id == "A":
        if (
            parent.get("volume_data_status_flash") == "OK"
            and _float(parent.get("flash_dollar_volume_3m"))
            >= float(strategy_e.CONFIG["min_flash_dollar_volume_3m"])
        ):
            derived.append(_clone(parent, "E"))
        try:
            delay = _float(parent.get("confirmation_wait_seconds"), float("inf"))
        except (TypeError, ValueError):
            delay = float("inf")
        if delay <= float(strategy_i.CONFIG["max_confirmation_delay_seconds"]):
            derived.append(_clone(parent, "I"))

        for module in K_MODULES:
            derived.append(_clone(
                parent,
                module.STRATEGY_ID,
                exit_model="k_checkpoint",
                **module.CONFIG,
            ))

        flash_ratio = _float(parent.get("flash_volume_ratio"), -1.0)
        rebound_ratio = _float(parent.get("rebound_volume_ratio"), float("inf"))
        if (
            flash_ratio >= float(strategy_l.CONFIG["min_flash_volume_ratio"])
            and rebound_ratio <= flash_ratio * float(strategy_l.CONFIG["max_rebound_to_flash_ratio"])
        ):
            derived.append(_clone(parent, "L"))
        # M disabled after persistently negative forward results.
        derived.append(_clone(
            parent, "N", exit_model="adaptive_trail_target",
            **strategy_n.CONFIG,
        ))
        derived.append(_clone(
            parent, "O", exit_model="second_leg",
            entered=False, source_entry_price=float(parent["entry_price"]),
            **strategy_o.CONFIG,
        ))
        if (
            _float(parent.get("pre_return_pct"), -1.0) >= float(strategy_p.CONFIG["min_pre_return_pct"])
            and _float(parent.get("pre_r2"), -1.0) >= float(strategy_p.CONFIG["min_pre_r2"])
        ):
            derived.append(_clone(parent, "P"))
        pre_std = _float(parent.get("pre30_return_std_pct"))
        volatility_units = _float(parent.get("flash_drop_pct")) / pre_std if pre_std > 0 else 0.0
        if volatility_units >= float(strategy_q.CONFIG["min_volatility_units"]):
            derived.append(_clone(parent, "Q", flash_drop_volatility_units=volatility_units))
        try:
            from datetime import datetime
            from zoneinfo import ZoneInfo
            timestamp = datetime.fromisoformat(str(parent["timestamp"]).replace("Z", "+00:00"))
            minute_et = timestamp.astimezone(ZoneInfo("America/New_York")).hour * 60 + timestamp.astimezone(ZoneInfo("America/New_York")).minute
        except Exception:
            minute_et = 10**9
        if minute_et < int(strategy_r.CONFIG["end_minute_et"]):
            derived.append(_clone(parent, "R"))
        if (
            _float(parent.get("market_5m_return_pct"), -float("inf")) >= -float(strategy_s.CONFIG["max_market_5m_loss_pct"])
            and _float(parent.get("market_1m_return_pct"), -float("inf")) >= float(strategy_s.CONFIG["min_market_1m_return_pct"])
        ):
            derived.append(_clone(parent, "S"))

    elif strategy_id == "D":
        if (
            parent.get("volume_data_status_flash") == "OK"
            and _float(parent.get("flash_volume_ratio"))
            >= float(strategy_f.CONFIG["min_flash_volume_ratio"])
        ):
            derived.append(_clone(parent, "F"))

    elif strategy_id == "B":
        for module in C_MODULES:
            derived.append(_clone(
                parent,
                module.STRATEGY_ID,
                exit_model=module.STRATEGY_ID.lower(),
                stop_fraction=module.CONFIG["stop_loss_fraction"],
                **module.CONFIG,
            ))
        derived.append(_clone(
            parent,
            "G",
            exit_model="c4",
            stop_fraction=strategy_g.CONFIG["stop_loss_fraction"],
            **strategy_c4.CONFIG,
        ))
        for module in J_MODULES:
            derived.append(_clone(
                parent,
                module.STRATEGY_ID,
                exit_model="checkpoint_target_stop_eod",
                stop_fraction=module.CONFIG["stop_loss_fraction"],
                **module.CONFIG,
            ))
    return derived
