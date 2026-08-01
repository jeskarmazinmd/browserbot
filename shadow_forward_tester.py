from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import io
import json
import math
import subprocess
import time

import numpy as np
import pandas as pd

TAPE_DIR = Path("/data/tapes")
STATE_PATH = Path("/data/shadow_state.json")
RESULTS_PATH = Path("/data/shadow_results.jsonl")
SUMMARY_PATH = Path("/data/shadow_summary.txt")

POLL_SECONDS = 30
TAIL_ROWS = 400_000

PRE_MIN = 30
FLASH_MIN = 3
MAX_DROP = 12.0
TARGET_FRAC = 0.60
STOP_FRAC = 0.05

# Exact live V14 thresholds used for the re-entry-policy comparison.
V14_DROP = 2.0
V14_PRE_RET = 0.25
V14_PRE_SLOPE = 0.50

REENTRY_POLICIES = {
    "once_daily": {"mode": "once_daily"},
    "cooldown_30m": {"mode": "cooldown", "minutes": 30},
    "cooldown_60m": {"mode": "cooldown", "minutes": 60},
    "fresh_rearm": {"mode": "fresh_rearm"},
    "unrestricted": {"mode": "unrestricted"},
}

GRID = []

# Expanded parameter sweep:
# below / at / above current v14 thresholds
DROP_VALUES = [-1.0, 0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
PRE_RET_VALUES = [-2.0, -1.0, -0.25, 0.0, 0.25, 0.5, 1.0, 2.0]
PRE_SLOPE_VALUES = [-5.0, -2.0, -0.5, 0.0, 0.25, 0.5, 1.0, 2.0, 5.0]

for drop in DROP_VALUES:
    for pre_ret in PRE_RET_VALUES:
        for pre_slope in PRE_SLOPE_VALUES:
            GRID.append({
                "name": f"D{drop}_R{pre_ret}_S{pre_slope}",
                "drop": drop,
                "pre_ret": pre_ret,
                "pre_slope": pre_slope,
            })

def now_iso():
    return datetime.now(timezone.utc).isoformat()


def parse_ts(value):
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def ny_trading_day(ts):
    return parse_ts(ts).tz_convert(ZoneInfo("America/New_York")).date().isoformat()


def blank_stats():
    return {
        "closed": 0,
        "target": 0,
        "stop": 0,
        "end": 0,
        "sum_ret": 0.0,
        "gross_profit": 0.0,
        "gross_loss": 0.0,
        "wins": 0,
        "losses": 0,
        "equity": 0.0,
        "peak_equity": 0.0,
        "max_drawdown": 0.0,
    }


def update_stats_bucket(stats_map, key, outcome, ret):
    st = stats_map.setdefault(key, blank_stats())
    st["closed"] += 1
    st[outcome] = st.get(outcome, 0) + 1
    st["sum_ret"] += ret

    if ret > 0:
        st["wins"] += 1
        st["gross_profit"] += ret
    elif ret < 0:
        st["losses"] += 1
        st["gross_loss"] += abs(ret)

    # Equal-notional additive equity curve, suitable for comparing policies.
    st["equity"] += ret
    st["peak_equity"] = max(st["peak_equity"], st["equity"])
    drawdown = st["peak_equity"] - st["equity"]
    st["max_drawdown"] = max(st["max_drawdown"], drawdown)
    return st


def policy_key(policy, symbol):
    return f"{policy}|{symbol}"


def reentry_allowed(state, policy, symbol, ts):
    pstate = state.setdefault("reentry_policy_state", {}).setdefault(
        policy_key(policy, symbol),
        {"armed": True},
    )
    mode = REENTRY_POLICIES[policy]["mode"]

    if mode == "once_daily":
        return pstate.get("last_entry_day") != ny_trading_day(ts)

    if mode == "cooldown":
        last_exit = pstate.get("last_exit_time")
        if not last_exit:
            return True
        elapsed = (parse_ts(ts) - parse_ts(last_exit)).total_seconds() / 60.0
        return elapsed >= REENTRY_POLICIES[policy]["minutes"]

    if mode == "fresh_rearm":
        return bool(pstate.get("armed", True))

    return True


def mark_reentry_entry(state, policy, symbol, ts):
    pstate = state.setdefault("reentry_policy_state", {}).setdefault(
        policy_key(policy, symbol),
        {"armed": True},
    )
    pstate["last_entry_time"] = str(ts)
    pstate["last_entry_day"] = ny_trading_day(ts)
    if REENTRY_POLICIES[policy]["mode"] == "fresh_rearm":
        pstate["armed"] = False


def mark_reentry_exit(state, policy, symbol, ts):
    pstate = state.setdefault("reentry_policy_state", {}).setdefault(
        policy_key(policy, symbol),
        {"armed": True},
    )
    pstate["last_exit_time"] = str(ts)


def update_rearm_state(state, symbol, signal_active):
    # A fresh-rearm policy becomes eligible only after the exact V14 signal
    # has fully cleared, then qualifies again on a later scan.
    pstate = state.setdefault("reentry_policy_state", {}).setdefault(
        policy_key("fresh_rearm", symbol),
        {"armed": True},
    )
    if not signal_active:
        pstate["armed"] = True


def load_state():
    state = {}
    if STATE_PATH.exists():
        try:
            state = json.loads(STATE_PATH.read_text())
        except Exception:
            state = {}

    # Preserve the existing parameter-grid state while adding independent
    # exact-V14 re-entry-policy state.
    state.setdefault("open", [])
    state.setdefault("seen_entries", {})
    state.setdefault("stats", {})
    state.setdefault("reentry_open", [])
    state.setdefault("reentry_seen_entries", {})
    state.setdefault("reentry_stats", {})
    state.setdefault("reentry_policy_state", {})
    return state

def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2, default=str))

def append_result(row):
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    with RESULTS_PATH.open("a") as f:
        f.write(json.dumps(row, default=str) + "\n")

def latest_tape():
    files = sorted(TAPE_DIR.glob("quotes_*.csv"))
    return files[-1] if files else None

def read_recent_tape():
    tape = latest_tape()
    if not tape:
        return None

    try:
        raw = subprocess.check_output(
            ["tail", "-n", str(TAIL_ROWS), str(tape)],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception as e:
        print(f"shadow tail error: {type(e).__name__}: {e}", flush=True)
        return None

    if not raw.strip():
        return None

    df = pd.read_csv(io.StringIO(raw), names=["timestamp", "symbol", "price"])
    df = df[df["timestamp"] != "timestamp"]
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce", format="ISO8601")
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna(subset=["timestamp", "symbol", "price"])
    return df

def slope_pct_per_hour(s):
    if len(s) < 3:
        return math.nan, math.nan
    y = np.log(s.values.astype(float))
    x = np.arange(len(y))
    try:
        m, b = np.polyfit(x, y, 1)
        yhat = m * x + b
        ss_res = float(np.sum((y - yhat) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r2 = 1 - ss_res / ss_tot if ss_tot > 0 else math.nan
        per_hour = (math.exp(m * 60.0) - 1) * 100
        return per_hour, r2
    except Exception:
        return math.nan, math.nan

def update_summary(state):
    lines = []
    lines.append("SHADOW FORWARD TESTER")
    lines.append(f"Parameter variants: {len(GRID)}")
    lines.append(f"V14 re-entry policies: {len(REENTRY_POLICIES)}")
    lines.append(f"Last update: {now_iso()}")
    lines.append(f"Open grid paper positions: {len(state.get('open', []))}")
    lines.append(f"Open V14 policy positions: {len(state.get('reentry_open', []))}")

    lines.append("")
    lines.append("V14 RE-ENTRY POLICY RESULTS")
    re_stats = state.get("reentry_stats", {})
    if not re_stats:
        lines.append("No closed V14 re-entry-policy trades yet.")
    else:
        ranked = []
        for policy, st in re_stats.items():
            closed = st.get("closed", 0)
            avg = st.get("sum_ret", 0.0) / closed if closed else 0.0
            win_rate = 100.0 * st.get("wins", 0) / closed if closed else 0.0
            gross_loss = st.get("gross_loss", 0.0)
            profit_factor = (
                st.get("gross_profit", 0.0) / gross_loss
                if gross_loss > 0
                else math.inf if st.get("gross_profit", 0.0) > 0 else 0.0
            )
            ranked.append((st.get("sum_ret", 0.0), policy, st, avg, win_rate, profit_factor))

        for total, policy, st, avg, win_rate, pf in sorted(ranked, reverse=True):
            pf_text = "inf" if math.isinf(pf) else f"{pf:.2f}"
            lines.append(
                f"{policy} | closed={st.get('closed', 0)} "
                f"target={st.get('target', 0)} stop={st.get('stop', 0)} end={st.get('end', 0)} "
                f"win_rate={win_rate:.1f}% avg_ret={avg:.3f}% "
                f"cum_ret={total:.3f}% profit_factor={pf_text} "
                f"max_dd={st.get('max_drawdown', 0.0):.3f}%"
            )

    lines.append("")
    lines.append("PARAMETER GRID RESULTS")
    stats = state.get("stats", {})
    if not stats:
        lines.append("No closed parameter-grid paper trades yet.")
    else:
        ranked = []
        for name, st in stats.items():
            n = st.get("closed", 0)
            avg = st.get("sum_ret", 0.0) / n if n else 0.0
            ranked.append((avg, name, st))

        for avg, name, st in sorted(ranked, reverse=True)[:15]:
            closed = st.get("closed", 0)
            wins = st.get("target", 0)
            stops = st.get("stop", 0)
            end_count = st.get("end", 0)
            lines.append(
                f"{name} | closed={closed} target={wins} stop={stops} end={end_count} "
                f"avg_ret={avg:.3f}%"
            )

    lines.append("")
    lines.append("RECENT V14 POLICY OPEN")
    for p in state.get("reentry_open", [])[-10:]:
        lines.append(
            f"{p['policy']} {p['symbol']} entry={p['entry_price']:.2f} "
            f"target={p['target']:.2f} stop={p['stop']:.2f} at={p['entry_time']}"
        )

    lines.append("")
    lines.append("RECENT GRID OPEN")
    for p in state.get("open", [])[-10:]:
        lines.append(
            f"{p['variant']} {p['symbol']} entry={p['entry_price']:.2f} "
            f"target={p['target']:.2f} stop={p['stop']:.2f} at={p['entry_time']}"
        )

    SUMMARY_PATH.write_text("\n".join(lines) + "\n")

def close_position(state, pos, price, ts, outcome):
    ret = ((price / pos["entry_price"]) - 1) * 100
    row = {
        **pos,
        "exit_time": str(ts),
        "exit_price": float(price),
        "outcome": outcome,
        "ret_pct": ret,
        "closed_at": now_iso(),
    }
    append_result(row)
    update_stats_bucket(state.setdefault("stats", {}), pos["variant"], outcome, ret)


def close_reentry_position(state, pos, price, ts, outcome):
    ret = ((price / pos["entry_price"]) - 1) * 100
    row = {
        "event": "v14_reentry_exit",
        **pos,
        "exit_time": str(ts),
        "exit_price": float(price),
        "outcome": outcome,
        "ret_pct": ret,
        "closed_at": now_iso(),
    }
    append_result(row)
    update_stats_bucket(
        state.setdefault("reentry_stats", {}),
        pos["policy"],
        outcome,
        ret,
    )
    mark_reentry_exit(state, pos["policy"], pos["symbol"], ts)

def main():
    print("shadow_forward_tester.py starting PAPER-ONLY", flush=True)

    # One-time replay of existing tape on startup.
    # This immediately evaluates today's already-collected data.
    startup_replay_done = False

    while True:
        try:
            state = load_state()
            df = read_recent_tape()

            if df is None or df.empty:
                update_summary(state)
                time.sleep(POLL_SECONDS)
                continue

            if not startup_replay_done:
                print(
                    f"Running startup replay over existing tape: rows={len(df):,}",
                    flush=True,
                )
                startup_replay_done = True
            if df is None or df.empty:
                update_summary(state)
                time.sleep(POLL_SECONDS)
                continue

            latest_prices = (
                df.sort_values("timestamp")
                .groupby("symbol")
                .tail(1)
                .set_index("symbol")
            )

            still_open = []
            for pos in state.get("open", []):
                sym = pos["symbol"]
                if sym not in latest_prices.index:
                    still_open.append(pos)
                    continue

                px = float(latest_prices.loc[sym, "price"])
                ts = latest_prices.loc[sym, "timestamp"]

                if px >= pos["target"]:
                    close_position(state, pos, pos["target"], ts, "target")
                elif px <= pos["stop"]:
                    close_position(state, pos, pos["stop"], ts, "stop")
                else:
                    still_open.append(pos)

            state["open"] = still_open

            reentry_still_open = []
            for pos in state.get("reentry_open", []):
                sym = pos["symbol"]
                if sym not in latest_prices.index:
                    reentry_still_open.append(pos)
                    continue

                px = float(latest_prices.loc[sym, "price"])
                ts = latest_prices.loc[sym, "timestamp"]

                if px >= pos["target"]:
                    close_reentry_position(state, pos, pos["target"], ts, "target")
                elif px <= pos["stop"]:
                    close_reentry_position(state, pos, pos["stop"], ts, "stop")
                else:
                    reentry_still_open.append(pos)

            state["reentry_open"] = reentry_still_open

            for sym, g in df.groupby("symbol"):
                g = g.sort_values("timestamp").set_index("timestamp")["price"]
                s = g.resample("30s").last().dropna()

                if len(s) < 10:
                    continue

                t = s.index[-1]
                flash = s[(s.index > t - pd.Timedelta(minutes=FLASH_MIN)) & (s.index <= t)]
                pre = s[
                    (s.index > t - pd.Timedelta(minutes=PRE_MIN + FLASH_MIN))
                    & (s.index <= t - pd.Timedelta(minutes=FLASH_MIN))
                ]

                if len(flash) < 2 or len(pre) < 5:
                    continue

                pre_start, pre_end = float(pre.iloc[0]), float(pre.iloc[-1])
                flash_start, flash_end = float(flash.iloc[0]), float(flash.iloc[-1])
                if min(pre_start, pre_end, flash_start, flash_end) <= 0:
                    continue

                pre_ret = ((pre_end / pre_start) - 1) * 100
                pre_slope, pre_r2 = slope_pct_per_hour(pre)
                drop = ((flash_start - flash_end) / flash_start) * 100

                exact_v14_active = (
                    drop >= V14_DROP
                    and drop <= MAX_DROP
                    and pre_ret >= V14_PRE_RET
                    and not math.isnan(pre_slope)
                    and pre_slope >= V14_PRE_SLOPE
                )

                update_rearm_state(state, sym, exact_v14_active)

                if exact_v14_active:
                    for policy in REENTRY_POLICIES:
                        already_open = any(
                            p["policy"] == policy and p["symbol"] == sym
                            for p in state.get("reentry_open", [])
                        )
                        if already_open:
                            continue

                        entry_key = f"{policy}|{sym}|{str(t)}"
                        if entry_key in state.setdefault("reentry_seen_entries", {}):
                            continue

                        if not reentry_allowed(state, policy, sym, t):
                            continue

                        entry = flash_end
                        pos = {
                            "policy": policy,
                            "symbol": sym,
                            "entry_time": str(t),
                            "entry_price": float(entry),
                            "flash_start": float(flash_start),
                            "flash_drop_pct": float(drop),
                            "pre_return_pct": float(pre_ret),
                            "pre_slope_pct_per_hour": float(pre_slope),
                            "pre_r2": float(pre_r2) if not math.isnan(pre_r2) else None,
                            "target": float(entry + TARGET_FRAC * (flash_start - entry)),
                            "stop": float(entry * (1 - STOP_FRAC)),
                            "created_at": now_iso(),
                        }

                        state["reentry_open"].append(pos)
                        state["reentry_seen_entries"][entry_key] = now_iso()
                        mark_reentry_entry(state, policy, sym, t)
                        append_result({"event": "v14_reentry_entry", **pos})
                        print(
                            f"V14_REENTRY_ENTRY {policy} {sym} drop={drop:.2f}% "
                            f"pre_ret={pre_ret:.2f}% pre_slope={pre_slope:.2f}%/hr",
                            flush=True,
                        )

                for cfg in GRID:
                    if not (
                        drop >= cfg["drop"]
                        and drop <= MAX_DROP
                        and pre_ret >= cfg["pre_ret"]
                        and not math.isnan(pre_slope)
                        and pre_slope >= cfg["pre_slope"]
                    ):
                        continue

                    key = f"{cfg['name']}|{sym}|{str(t)}"
                    if key in state.setdefault("seen_entries", {}):
                        continue

                    already_open = any(
                        p["variant"] == cfg["name"] and p["symbol"] == sym
                        for p in state.get("open", [])
                    )
                    if already_open:
                        continue

                    entry = flash_end
                    pos = {
                        "variant": cfg["name"],
                        "symbol": sym,
                        "entry_time": str(t),
                        "entry_price": float(entry),
                        "flash_start": float(flash_start),
                        "flash_drop_pct": float(drop),
                        "pre_return_pct": float(pre_ret),
                        "pre_slope_pct_per_hour": float(pre_slope),
                        "pre_r2": float(pre_r2) if not math.isnan(pre_r2) else None,
                        "target": float(entry + TARGET_FRAC * (flash_start - entry)),
                        "stop": float(entry * (1 - STOP_FRAC)),
                        "created_at": now_iso(),
                    }

                    state["open"].append(pos)
                    state["seen_entries"][key] = now_iso()
                    append_result({"event": "paper_entry", **pos})
                    print(
                        f"SHADOW_ENTRY {cfg['name']} {sym} drop={drop:.2f}% "
                        f"pre_ret={pre_ret:.2f}% pre_slope={pre_slope:.2f}%/hr",
                        flush=True,
                    )

            # trim seen cache so state does not grow forever
            if len(state.get("seen_entries", {})) > 5000:
                items = list(state["seen_entries"].items())[-3000:]
                state["seen_entries"] = dict(items)

            if len(state.get("reentry_seen_entries", {})) > 5000:
                items = list(state["reentry_seen_entries"].items())[-3000:]
                state["reentry_seen_entries"] = dict(items)

            save_state(state)
            update_summary(state)

        except Exception as e:
            print(f"shadow error: {type(e).__name__}: {e}", flush=True)

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
