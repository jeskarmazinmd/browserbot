from pathlib import Path
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from collections import deque
import json
import csv
import time
import shutil
import heapq

RUN_MODE = os.environ.get("RUN_MODE", "LIVE")
RUN_ID = os.environ.get("RUN_ID", "live")

if RUN_MODE == "REPLAY":
    OUTPUT_ROOT = Path("./replay") / RUN_ID
else:
    OUTPUT_ROOT = Path("/data")

OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

def output_path(filename):
    return OUTPUT_ROOT / filename

SUMMARY_TXT = output_path("bot_output.txt")
ELIGIBILITY_STATUS_PATH = Path("/data/eligibility_status.json")
AUTH_HEALTH_LOG = Path("/data/auth_health_log.jsonl")
SIGNAL_PAPER_OUTCOMES_JSONL = output_path("signal_paper_outcomes_rebound_v1.jsonl")
NEAR_MISS_PAPER_JSONL = output_path("near_miss_paper_outcomes_rebound_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_B_JSONL = output_path("signal_paper_outcomes_strategy_b_rebound_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_D_JSONL = output_path("signal_paper_outcomes_strategy_d_090_rebound_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_E_JSONL = output_path("signal_paper_outcomes_strategy_e_liquidity_v1.jsonl")
NEAR_MISS_PAPER_E_JSONL = output_path("near_miss_paper_outcomes_strategy_e_liquidity_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_F_JSONL = output_path("signal_paper_outcomes_strategy_f_d_volume_ratio_v1.jsonl")
NEAR_MISS_PAPER_F_JSONL = output_path("near_miss_paper_outcomes_strategy_f_d_volume_ratio_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_C1_JSONL = output_path("signal_paper_outcomes_strategy_c1_trailing_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_C2_JSONL = output_path("signal_paper_outcomes_strategy_c2_no_high_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_C3_JSONL = output_path("signal_paper_outcomes_strategy_c3_lower_quotes_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_C4_JSONL = output_path("signal_paper_outcomes_strategy_c4_negative_slope_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_G_JSONL = output_path("signal_paper_outcomes_strategy_g_c4_stop_1_5_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_H_JSONL = output_path("signal_paper_outcomes_strategy_h_filtered_broad_rebound_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_I_JSONL = output_path("signal_paper_outcomes_strategy_i_fast_confirmation_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_J1_JSONL = output_path("signal_paper_outcomes_strategy_j1_stop_1pct_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_J2_JSONL = output_path("signal_paper_outcomes_strategy_j2_stop_0_5pct_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_J3_JSONL = output_path("signal_paper_outcomes_strategy_j3_15s_no_progress_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_J4_JSONL = output_path("signal_paper_outcomes_strategy_j4_30s_no_progress_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_J5_JSONL = output_path("signal_paper_outcomes_strategy_j5_60s_no_progress_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_J6_JSONL = output_path("signal_paper_outcomes_strategy_j6_30s_no_progress_stop_0_5pct_v1.jsonl")
K_EARLY_BEHAVIOR_JSONL = output_path("strategy_k_early_behavior_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_L_JSONL = output_path("signal_paper_outcomes_strategy_l_exhaustion_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_M_JSONL = output_path("signal_paper_outcomes_strategy_m_rolling_vwap_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_N_JSONL = output_path("signal_paper_outcomes_strategy_n_adaptive_trail_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_O_JSONL = output_path("signal_paper_outcomes_strategy_o_second_leg_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_P_JSONL = output_path("signal_paper_outcomes_strategy_p_strong_stock_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_Q_JSONL = output_path("signal_paper_outcomes_strategy_q_vol_normalized_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_R_JSONL = output_path("signal_paper_outcomes_strategy_r_morning_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_S_JSONL = output_path("signal_paper_outcomes_strategy_s_market_confirmed_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_TF1_JSONL = output_path("signal_paper_outcomes_tf1_trend_pullback_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_BO1_JSONL = output_path("signal_paper_outcomes_bo1_consolidation_breakout_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_OR1_JSONL = output_path("signal_paper_outcomes_or1_opening_range_breakout_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_RS1_JSONL = output_path("signal_paper_outcomes_rs1_relative_strength_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_RS2_JSONL = output_path("signal_paper_outcomes_rs2_relative_strength_exit_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_VE1_JSONL = output_path("signal_paper_outcomes_ve1_volatility_expansion_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_VR1_JSONL = output_path("signal_paper_outcomes_vr1_rolling_mean_reclaim_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_M1_JSONL = output_path("signal_paper_outcomes_m1_15m_reversal_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_M2_JSONL = output_path("signal_paper_outcomes_m2_30m_reversal_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_M3_JSONL = output_path("signal_paper_outcomes_m3_60m_reversal_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_RS3_JSONL = output_path("signal_paper_outcomes_rs3_tighter_exit_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_MC1_JSONL = output_path("signal_paper_outcomes_mc1_momentum_continuation_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_TL1_JSONL = output_path("signal_paper_outcomes_tl1_trendline_reclaim_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_AV1_JSONL = output_path("signal_paper_outcomes_av1_volatility_adaptive_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_TD1_JSONL = output_path("signal_paper_outcomes_td1_time_of_day_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_SH1_JSONL = output_path("signal_paper_outcomes_sh1_shape_flattening_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_CV1_JSONL = output_path("signal_paper_outcomes_cv1_curvature_reversal_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_HL1_JSONL = output_path("signal_paper_outcomes_hl1_higher_low_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_VT1_JSONL = output_path("signal_paper_outcomes_vt1_trendline_mean_confluence_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_PD1_JSONL = output_path("signal_paper_outcomes_pd1_panic_drop_snapback_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_EMA1_JSONL = output_path("signal_paper_outcomes_ema1_9_21_crossover_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_EMA2_JSONL = output_path("signal_paper_outcomes_ema2_pullback_bounce_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_EMA3_JSONL = output_path("signal_paper_outcomes_ema3_alignment_breakout_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_SMA1_JSONL = output_path("signal_paper_outcomes_sma1_20_50_crossover_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_VWEMA1_JSONL = output_path("signal_paper_outcomes_vwema1_mean_ema_momentum_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_GE1_JSONL = output_path("signal_paper_outcomes_ge1_selling_exhaustion_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_GM1_JSONL = output_path("signal_paper_outcomes_gm1_mean_reversion_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_GP1_JSONL = output_path("signal_paper_outcomes_gp1_trend_pullback_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_GR1_JSONL = output_path("signal_paper_outcomes_gr1_support_rejection_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_GT1_JSONL = output_path("signal_paper_outcomes_gt1_trend_continuation_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_K1_JSONL = output_path("signal_paper_outcomes_strategy_k1_exit_30s_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_K2_JSONL = output_path("signal_paper_outcomes_strategy_k2_exit_60s_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_K3_JSONL = output_path("signal_paper_outcomes_strategy_k3_exit_120s_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_K4_JSONL = output_path("signal_paper_outcomes_strategy_k4_30s_below_entry_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_K5_JSONL = output_path("signal_paper_outcomes_strategy_k5_60s_below_entry_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_K6_JSONL = output_path("signal_paper_outcomes_strategy_k6_60s_mfe_0_10_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_K7_JSONL = output_path("signal_paper_outcomes_strategy_k7_60s_mfe_0_30_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_K8_JSONL = output_path("signal_paper_outcomes_strategy_k8_60s_reach_0_20_v1.jsonl")
SIGNAL_PAPER_OUTCOMES_K9_JSONL = output_path("signal_paper_outcomes_strategy_k9_30min_timeout_v1.jsonl")
NEAR_MISS_PAPER_H_JSONL = output_path("near_miss_paper_outcomes_strategy_h_filtered_broad_rebound_v1.jsonl")
NEAR_MISS_PAPER_C1_JSONL = output_path("near_miss_paper_outcomes_strategy_c1_trailing_v1.jsonl")
NEAR_MISS_PAPER_C2_JSONL = output_path("near_miss_paper_outcomes_strategy_c2_no_high_v1.jsonl")
NEAR_MISS_PAPER_C3_JSONL = output_path("near_miss_paper_outcomes_strategy_c3_lower_quotes_v1.jsonl")
NEAR_MISS_PAPER_C4_JSONL = output_path("near_miss_paper_outcomes_strategy_c4_negative_slope_v1.jsonl")
NEAR_MISS_PAPER_G_JSONL = output_path("near_miss_paper_outcomes_strategy_g_c4_stop_1_5_v1.jsonl")
NEAR_MISS_PAPER_B_JSONL = output_path("near_miss_paper_outcomes_strategy_b_rebound_v1.jsonl")
NEAR_MISS_PAPER_D_JSONL = output_path("near_miss_paper_outcomes_strategy_d_090_rebound_v1.jsonl")
HISTORY_JSONL = output_path("bot_history.jsonl")
EVENTS_JSONL = output_path("bot_events.jsonl")
TRIGGER_OUTCOMES_JSONL = output_path("trigger_trade_outcomes.jsonl")
DAILY_PNL_HISTORY_JSON = output_path("daily_pnl_history.json")
STRATEGY_PERFORMANCE_CSV = output_path("strategy_performance.csv")
STRATEGY_PERFORMANCE_TABLE_TXT = output_path(
    "strategy_performance_table.txt"
)
DAILY_LIVE_DEPLOYMENT_HISTORY_JSON = output_path("daily_live_deployment_history.json")
DAILY_MARKET_BEHAVIOR_HISTORY_JSON = output_path("daily_market_behavior_history.json")

POLL_SECONDS = 30
MAX_HISTORY_ROWS = 5000

# Prevent the live dashboard from becoming a research archive.
MAX_DASHBOARD_BYTES = 250000

# Keep paper entry mechanics aligned with live_strategy_runner.py.
REBOUND_CONFIRMATION_PCT = 0.001
STRATEGY_B_REBOUND_CONFIRMATION_PCT = 0.002
RECOVERY_TARGET_FRACTION = 0.60
STOP_LOSS_FRACTION_BELOW_ENTRY = 0.05
STRATEGY_B_STOP_LOSS_FRACTION_BELOW_ENTRY = 0.02
STRATEGY_D_FLASH_DROP_PCT = 0.90
STRATEGY_D_REBOUND_CONFIRMATION_PCT = STRATEGY_B_REBOUND_CONFIRMATION_PCT
STRATEGY_D_STOP_LOSS_FRACTION_BELOW_ENTRY = STRATEGY_B_STOP_LOSS_FRACTION_BELOW_ENTRY
STRATEGY_E_MIN_FLASH_DOLLAR_VOLUME_3M = 1_200_000
# Forward-only start avoids reconstructing Strategy E from a tape trimmed before deployment.
STRATEGY_E_FORWARD_START_UTC = "2026-07-30T13:30:00+00:00"
STRATEGY_F_MIN_FLASH_VOL_RATIO = 0.75
# Forward-only start keeps Strategy F as a clean prospective test.
STRATEGY_F_FORWARD_START_UTC = "2026-07-30T13:30:00+00:00"
STOP_REPLAY_LEVELS_PCT = (1.0, 1.5, 2.0, 2.5, 3.0, 5.0)

# Fixed prospective candidate definition. Lower miss_score is closer to a true signal.
# Keep unchanged while collecting a versioned forward dataset.
NEAR_MISS_SCORE_CUTOFF = 0.25

# Strategy C forward-paper variants. They share Strategy B entries and its 2% protective stop.
# Start on the next full US market session so no pre-deployment trades are backfilled.
STRATEGY_C_FORWARD_START_UTC = "2026-07-28T13:30:00+00:00"
STRATEGY_C_ACTIVATION_GAIN_PCT = 0.30
STRATEGY_C1_PULLBACK_FROM_HIGH_PCT = 0.20
STRATEGY_C2_NO_NEW_HIGH_SECONDS = 30.0
STRATEGY_C3_LOWER_SAMPLES = 3
STRATEGY_C3_MIN_TOTAL_DECLINE_PCT = 0.10
STRATEGY_C4_SLOPE_WINDOW_SECONDS = 30.0
STRATEGY_C4_NEGATIVE_SLOPE_PCT_PER_MINUTE = -0.20

# Strategy G: Strategy C4 exit logic with a tighter 1.5% protective stop.
STRATEGY_G_STOP_LOSS_FRACTION_BELOW_ENTRY = 0.015
STRATEGY_G_FORWARD_START_UTC = "2026-07-30T13:30:00+00:00"

# Strategy H: native paper signals emitted by live_strategy_runner.py.
STRATEGY_H_MIN_FLASH_DROP_PCT = 0.60
STRATEGY_H_MAX_FLASH_DROP_PCT = 2.50
STRATEGY_H_MIN_PRE_R2 = 0.40
STRATEGY_H_MAX_PRE_SLOPE_PCT_PER_HOUR = 12.0
STRATEGY_H_REBOUND_CONFIRMATION_PCT = 0.001
STRATEGY_H_STOP_LOSS_FRACTION_BELOW_ENTRY = 0.04
STRATEGY_H_MIN_REMAINING_UPSIDE_PCT = 0.10
STRATEGY_H_FORWARD_START_UTC = "2026-07-30T13:30:00+00:00"

# Strategy I: Strategy A signals whose rebound confirms quickly.
STRATEGY_I_MAX_CONFIRMATION_DELAY_SECONDS = 30.0
STRATEGY_I_FORWARD_START_UTC = "2026-07-31T13:30:00+00:00"

# Strategy J: post-entry failure-management family using identical Strategy B entries.
# These are prospective paper variants; no live orders are placed.
STRATEGY_J_FORWARD_START_UTC = "2026-07-31T13:30:00+00:00"
STRATEGY_J_CONFIGS = {
    "J1": {"stop_loss_fraction": 0.010, "checkpoint_seconds": None, "checkpoint_max_return_pct": None},
    "J2": {"stop_loss_fraction": 0.005, "checkpoint_seconds": None, "checkpoint_max_return_pct": None},
    "J3": {"stop_loss_fraction": 0.010, "checkpoint_seconds": 15.0, "checkpoint_max_return_pct": 0.0},
    "J4": {"stop_loss_fraction": 0.010, "checkpoint_seconds": 30.0, "checkpoint_max_return_pct": 0.0},
    "J5": {"stop_loss_fraction": 0.010, "checkpoint_seconds": 60.0, "checkpoint_max_return_pct": 0.0},
    "J6": {"stop_loss_fraction": 0.005, "checkpoint_seconds": 30.0, "checkpoint_max_return_pct": 0.0},
}
STRATEGY_J_OUTCOME_PATHS = {
    "J1": SIGNAL_PAPER_OUTCOMES_J1_JSONL,
    "J2": SIGNAL_PAPER_OUTCOMES_J2_JSONL,
    "J3": SIGNAL_PAPER_OUTCOMES_J3_JSONL,
    "J4": SIGNAL_PAPER_OUTCOMES_J4_JSONL,
    "J5": SIGNAL_PAPER_OUTCOMES_J5_JSONL,
    "J6": SIGNAL_PAPER_OUTCOMES_J6_JSONL,
}

# Strategy K: post-entry exit research on identical Strategy A entries.
# Forward-only; no live orders. All variants retain A's target, 5% stop and 15:55 ET exit
# unless the configured early rule exits first.
STRATEGY_K_FORWARD_START_UTC = "2026-07-31T13:30:00+00:00"
STRATEGY_K_CHECKPOINT_SECONDS = (15, 30, 60, 90, 120, 180, 300)
STRATEGY_K_CONFIGS = {
    "K1": {"mode": "fixed_exit", "seconds": 30},
    "K2": {"mode": "fixed_exit", "seconds": 60},
    "K3": {"mode": "fixed_exit", "seconds": 120},
    "K4": {"mode": "conditional_return", "seconds": 30, "min_return_pct": 0.0},
    "K5": {"mode": "conditional_return", "seconds": 60, "min_return_pct": 0.0},
    "K6": {"mode": "conditional_mfe", "seconds": 60, "min_mfe_pct": 0.10},
    "K7": {"mode": "conditional_mfe", "seconds": 60, "min_mfe_pct": 0.30},
    "K8": {"mode": "conditional_reach", "seconds": 60, "required_gain_pct": 0.20},
    "K9": {"mode": "fixed_exit", "seconds": 1800},
}
STRATEGY_K_OUTCOME_PATHS = {
    "K1": SIGNAL_PAPER_OUTCOMES_K1_JSONL,
    "K2": SIGNAL_PAPER_OUTCOMES_K2_JSONL,
    "K3": SIGNAL_PAPER_OUTCOMES_K3_JSONL,
    "K4": SIGNAL_PAPER_OUTCOMES_K4_JSONL,
    "K5": SIGNAL_PAPER_OUTCOMES_K5_JSONL,
    "K6": SIGNAL_PAPER_OUTCOMES_K6_JSONL,
    "K7": SIGNAL_PAPER_OUTCOMES_K7_JSONL,
    "K8": SIGNAL_PAPER_OUTCOMES_K8_JSONL,
    "K9": SIGNAL_PAPER_OUTCOMES_K9_JSONL,
}


# Strategies L-S: eight independent mean-reversion hypotheses, prospective only.
STRATEGY_LS_FORWARD_START_UTC = "2026-07-31T13:30:00+00:00"
STRATEGY_L_MIN_FLASH_VOL_RATIO = 1.00
STRATEGY_L_MAX_REBOUND_TO_FLASH_RATIO = 0.75
STRATEGY_M_MIN_DISTANCE_BELOW_VWAP_PCT = 0.50
STRATEGY_N_ACTIVATION_GAIN_PCT = 0.30
STRATEGY_N_TRAIL_FROM_HIGH_PCT = 0.20
STRATEGY_O_PULLBACK_FROM_FIRST_HIGH_PCT = 0.10
STRATEGY_O_REBOUND_FROM_PULLBACK_LOW_PCT = 0.10
STRATEGY_O_STOP_LOSS_FRACTION = 0.02
STRATEGY_P_MIN_PRE_RETURN_PCT = 0.75
STRATEGY_P_MIN_PRE_R2 = 0.50
STRATEGY_Q_MIN_VOLATILITY_UNITS = 3.0
STRATEGY_R_END_MINUTE_ET = 11 * 60
STRATEGY_S_MAX_MARKET_5M_LOSS_PCT = 0.15
STRATEGY_S_MIN_MARKET_1M_RETURN_PCT = 0.0
STRATEGY_LS_PATHS = {
    "L": SIGNAL_PAPER_OUTCOMES_L_JSONL,
    "M": SIGNAL_PAPER_OUTCOMES_M_JSONL,
    "N": SIGNAL_PAPER_OUTCOMES_N_JSONL,
    "O": SIGNAL_PAPER_OUTCOMES_O_JSONL,
    "P": SIGNAL_PAPER_OUTCOMES_P_JSONL,
    "Q": SIGNAL_PAPER_OUTCOMES_Q_JSONL,
    "R": SIGNAL_PAPER_OUTCOMES_R_JSONL,
    "S": SIGNAL_PAPER_OUTCOMES_S_JSONL,
}

# Native independent strategy families. These SIGNAL events are emitted directly
# by live_strategy_runner.py and do not inherit Strategy A entries.
INDEPENDENT_FORWARD_START_UTC = "2026-07-31T13:30:00+00:00"
INDEPENDENT_STRATEGY_PATHS = {
    "TF1": SIGNAL_PAPER_OUTCOMES_TF1_JSONL,
    "BO1": SIGNAL_PAPER_OUTCOMES_BO1_JSONL,
    "OR1": SIGNAL_PAPER_OUTCOMES_OR1_JSONL,
    "RS1": SIGNAL_PAPER_OUTCOMES_RS1_JSONL,
    "RS2": SIGNAL_PAPER_OUTCOMES_RS2_JSONL,
    "VE1": SIGNAL_PAPER_OUTCOMES_VE1_JSONL,
    "VR1": SIGNAL_PAPER_OUTCOMES_VR1_JSONL,
    "M1": SIGNAL_PAPER_OUTCOMES_M1_JSONL,
    "M2": SIGNAL_PAPER_OUTCOMES_M2_JSONL,
    "M3": SIGNAL_PAPER_OUTCOMES_M3_JSONL,
    "RS3": SIGNAL_PAPER_OUTCOMES_RS3_JSONL,
    "MC1": SIGNAL_PAPER_OUTCOMES_MC1_JSONL,
    "TL1": SIGNAL_PAPER_OUTCOMES_TL1_JSONL,
    "AV1": SIGNAL_PAPER_OUTCOMES_AV1_JSONL,
    "TD1": SIGNAL_PAPER_OUTCOMES_TD1_JSONL,
    "SH1": SIGNAL_PAPER_OUTCOMES_SH1_JSONL,
    "CV1": SIGNAL_PAPER_OUTCOMES_CV1_JSONL,
    "HL1": SIGNAL_PAPER_OUTCOMES_HL1_JSONL,
    "VT1": SIGNAL_PAPER_OUTCOMES_VT1_JSONL,
    "PD1": SIGNAL_PAPER_OUTCOMES_PD1_JSONL,
    "EMA1": SIGNAL_PAPER_OUTCOMES_EMA1_JSONL,
    "EMA2": SIGNAL_PAPER_OUTCOMES_EMA2_JSONL,
    "EMA3": SIGNAL_PAPER_OUTCOMES_EMA3_JSONL,
    "SMA1": SIGNAL_PAPER_OUTCOMES_SMA1_JSONL,
    "VWEMA1": SIGNAL_PAPER_OUTCOMES_VWEMA1_JSONL,
    "GE1": SIGNAL_PAPER_OUTCOMES_GE1_JSONL,
    "GM1": SIGNAL_PAPER_OUTCOMES_GM1_JSONL,
    "GP1": SIGNAL_PAPER_OUTCOMES_GP1_JSONL,
    "GR1": SIGNAL_PAPER_OUTCOMES_GR1_JSONL,
    "GT1": SIGNAL_PAPER_OUTCOMES_GT1_JSONL,
}
INDEPENDENT_STRATEGY_DESCRIPTIONS = {
    "TF1": "Trend pullback: orderly +30m trend, shallow pullback, renewed rise",
    "BO1": "Consolidation breakout: break above a narrow prior 10-minute range",
    "OR1": "Opening range breakout: break above the frozen 09:30-09:45 ET high",
    "RS1": "Relative strength: positive trend outperforming SPY over 30 minutes",
    "RS2": "RS1 entry with 50/50 exit research variant (RS1 exit + 60 minute hold)",
    "VE1": "Volatility expansion: directional break from a compressed 15-minute range",
    "VR1": "Reclaim: cross and hold above a rolling 30-minute price-mean proxy",
    "M1": "15-minute selloff exhaustion: stabilize above the low and begin rebounding",
    "M2": "30-minute selloff exhaustion: stabilize above the low and begin rebounding",
    "M3": "60-minute selloff exhaustion: stabilize above the low and begin rebounding",
    "RS3": "RS1 entry with tighter 0.60% target and 0.45% stop exit experiment",
    "MC1": "Momentum continuation: aligned 5m/15m strength near the recent high",
    "TL1": "Trendline reclaim: cross back above a rising 30-minute regression line",
    "AV1": "Volatility adaptive rebound: drop and rebound thresholds scale with recent sigma",
    "TD1": "Time-of-day relative strength: continuation signals only from 10:00-11:30 ET",
    "SH1": "Decline shape: selloff weakens materially before a positive short-term turn",
    "CV1": "Curvature reversal: late trend slope improves sharply versus early selloff slope",
    "HL1": "Higher-low reversal: second swing low is higher, then price breaks the intervening high",
    "VT1": "Trendline/mean confluence: rising trend, rolling mean proximity and renewed rebound",
    "PD1": "Panic drop snapback: sharp one-minute fall followed by a measurable recovery",
    "EMA1": "9/21 EMA bullish crossover with increasing completed-minute volume",
    "EMA2": "Pullback to a rising 20 EMA followed by a short-term bounce",
    "EMA3": "Sustained 9 > 21 > 50 EMA alignment followed by a recent-high breakout",
    "SMA1": "20 SMA crosses above 50 SMA and remains confirmed for two minutes",
    "VWEMA1": "Price above a rolling price-mean proxy and rising 20 EMA with positive momentum",
}

NY_TZ = ZoneInfo("America/New_York")

def event_strategy(event):
    """Legacy untagged events belong to Strategy A."""
    return str((event or {}).get("strategy_id") or "A").upper()


def threshold_near_miss_candidates(events, strategy_id, cutoff=NEAR_MISS_SCORE_CUTOFF):
    """Return the first qualifying near-miss observation per symbol/day.

    This creates a stable prospective population instead of selecting a daily
    top-N ranking. A candidate qualifies only when 0 < miss_score <= cutoff.
    Repeated scanner observations cannot crowd out other symbols.
    """
    strategy_id = str(strategy_id).upper()
    first_by_symbol_day = {}
    for event in events:
        if event.get("event_type") != "NEAR_MISS" or event_strategy(event) != strategy_id:
            continue
        candidate = dict(event.get("candidate", {}) or {})
        candidate["seen_at"] = event.get("timestamp")
        try:
            score = float(candidate.get("miss_score", 999))
        except (TypeError, ValueError):
            continue
        if not (0.0 < score <= float(cutoff)):
            continue
        symbol = str(candidate.get("symbol") or event.get("symbol") or "").upper()
        day = str(candidate.get("seen_at") or "")[:10]
        if not symbol or len(day) != 10:
            continue
        candidate["symbol"] = symbol
        candidate["candidate_cutoff"] = float(cutoff)
        candidate["candidate_definition"] = "0 < miss_score <= cutoff"
        key = (day, symbol)
        current = first_by_symbol_day.get(key)
        if current is None or str(candidate.get("seen_at")) < str(current.get("seen_at")):
            first_by_symbol_day[key] = candidate
    return sorted(first_by_symbol_day.values(), key=lambda c: str(c.get("seen_at", "")))


def strategy_e_eligible_signal(event):
    """True when a Strategy A signal passes Strategy E's liquidity overlay.

    Strategy E deliberately reuses Strategy A's confirmed paper entry and exit
    mechanics. Its only additional rule is at least $1.2M of dollar volume in
    the three-minute flash snapshot. Missing/error volume snapshots do not pass.
    """
    if event_strategy(event) != "A" or (event or {}).get("event_type") != "SIGNAL":
        return False
    signal = (event or {}).get("signal", {}) or {}
    if signal.get("volume_data_status_flash") != "OK":
        return False
    try:
        return float(signal.get("flash_dollar_volume_3m")) >= STRATEGY_E_MIN_FLASH_DOLLAR_VOLUME_3M
    except (TypeError, ValueError):
        return False


def strategy_e_eligible_near_miss(candidate):
    """True when an A near miss has a valid Strategy E flash-liquidity snapshot."""
    candidate = candidate or {}
    if candidate.get("volume_data_status_flash") != "OK":
        return False
    try:
        return float(candidate.get("flash_dollar_volume_3m")) >= STRATEGY_E_MIN_FLASH_DOLLAR_VOLUME_3M
    except (TypeError, ValueError):
        return False


def strategy_e_after_forward_start(value):
    """Prevent Strategy E from backfilling the incomplete pre-deployment session."""
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        start = datetime.fromisoformat(STRATEGY_E_FORWARD_START_UTC)
        return ts.astimezone(timezone.utc) >= start.astimezone(timezone.utc)
    except Exception:
        return False


def strategy_f_eligible_signal(event):
    """True when a Strategy D signal passes Strategy F's relative-volume overlay."""
    if event_strategy(event) != "D" or (event or {}).get("event_type") != "SIGNAL":
        return False
    signal = (event or {}).get("signal", {}) or {}
    if signal.get("volume_data_status_flash") != "OK":
        return False
    try:
        return float(signal.get("flash_volume_ratio")) >= STRATEGY_F_MIN_FLASH_VOL_RATIO
    except (TypeError, ValueError):
        return False


def strategy_f_eligible_near_miss(candidate):
    """True when a Strategy D near miss has a valid qualifying flash-volume ratio."""
    candidate = candidate or {}
    if candidate.get("volume_data_status_flash") != "OK":
        return False
    try:
        return float(candidate.get("flash_volume_ratio")) >= STRATEGY_F_MIN_FLASH_VOL_RATIO
    except (TypeError, ValueError):
        return False


def strategy_f_after_forward_start(value):
    """Keep Strategy F prospective and prevent historical backfill."""
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        start = datetime.fromisoformat(STRATEGY_F_FORWARD_START_UTC)
        return ts.astimezone(timezone.utc) >= start.astimezone(timezone.utc)
    except Exception:
        return False



def strategy_i_eligible_signal(event):
    """True when a Strategy A signal confirmed within the fixed delay threshold."""
    if event_strategy(event) != "A" or (event or {}).get("event_type") != "SIGNAL":
        return False
    signal = (event or {}).get("signal", {}) or {}
    try:
        delay = float(signal.get("confirmation_wait_seconds"))
        ts = datetime.fromisoformat(str(event.get("timestamp")).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        start = datetime.fromisoformat(STRATEGY_I_FORWARD_START_UTC)
        return (
            ts.astimezone(timezone.utc) >= start.astimezone(timezone.utc)
            and delay <= STRATEGY_I_MAX_CONFIRMATION_DELAY_SECONDS
        )
    except (TypeError, ValueError):
        return False


def is_rth_timestamp(value):
    """True only for Monday-Friday, 09:30 <= New York time < 16:00."""
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        et = ts.astimezone(NY_TZ)
        if et.weekday() >= 5:
            return False
        minutes = et.hour * 60 + et.minute
        return 9 * 60 + 30 <= minutes < 16 * 60
    except Exception:
        return False

def fmt_near(e):
    return (
        f"{e.get('symbol')} | score={float(e.get('miss_score', 999)):.2f} | "
        f"drop={float(e.get('flash_drop_pct', 0)):.2f}% | "
        f"gap={float(e.get('gap', 0)):.2f}% | "
        f"pre_ret={float(e.get('pre_return_pct', 0)):.2f}% | "
        f"pre_slope={float(e.get('pre_slope_pct_per_hour', 0)):.2f}%/hr | "
        f"r2={float(e.get('pre_r2', 0)):.2f} | "
        f"fails={e.get('failed', 'unknown')} | "
        f"price={float(e.get('price', 0)):.2f}"
    )

def _fmt_volume_metrics(obj):
    """Compact, readable flash/rebound volume fields for bot_output.txt."""
    obj = obj or {}
    parts = []
    if obj.get("volume_data_status_flash") == "OK":
        parts.extend([
            f"flash_vol_1m={_safe_float(obj.get('flash_volume_1m')):,.0f}",
            f"flash_vol_3m={_safe_float(obj.get('flash_volume_3m')):,.0f}",
            f"pre30_avg_1m={_safe_float(obj.get('avg_volume_1m_pre30')):,.0f}",
            f"flash_vol_ratio={_safe_float(obj.get('flash_volume_ratio')):.2f}x",
            f"flash_$vol_3m=${_safe_float(obj.get('flash_dollar_volume_3m')):,.0f}",
        ])
    elif obj.get("volume_data_status_flash"):
        parts.append(f"flash_vol_status={obj.get('volume_data_status_flash')}")

    if obj.get("volume_data_status_rebound") == "OK":
        parts.extend([
            f"rebound_vol_1m={_safe_float(obj.get('rebound_volume_1m')):,.0f}",
            f"rebound_vol_total={_safe_float(obj.get('rebound_volume_total')):,.0f}",
            f"rebound_vol_ratio={_safe_float(obj.get('rebound_volume_ratio')):.2f}x",
            f"rebound_$vol=${_safe_float(obj.get('rebound_dollar_volume_total')):,.0f}",
        ])
    elif obj.get("volume_data_status_rebound"):
        parts.append(f"rebound_vol_status={obj.get('volume_data_status_rebound')}")
    return " | ".join(parts)


def _volume_suffix(obj):
    text = _fmt_volume_metrics(obj)
    return f" | {text}" if text else ""


def load_recent_rows():
    if not HISTORY_JSONL.exists():
        return []
    rows = deque(maxlen=MAX_HISTORY_ROWS)
    with HISTORY_JSONL.open() as f:
        for raw in f:
            raw = raw.strip()
            if raw:
                try:
                    rows.append(json.loads(raw))
                except Exception:
                    pass
    return list(rows)

def load_recent_events():
    if not EVENTS_JSONL.exists():
        return []
    rows = deque(maxlen=MAX_HISTORY_ROWS)
    with EVENTS_JSONL.open() as f:
        for raw in f:
            raw = raw.strip()
            if raw:
                try:
                    rows.append(json.loads(raw))
                except Exception:
                    pass
    return list(rows)


def summarize_signal_event(e):
    sig = e.get("signal", {}) or {}
    ts = e.get("timestamp", "?")
    sym = e.get("symbol") or sig.get("symbol", "?")
    return (
        f"{ts} | {sym} | "
        f"drop={float(sig.get('flash_drop_pct', 0)):.2f}% "
        f"pre_ret={float(sig.get('pre_return_pct', 0)):.2f}% "
        f"pre_slope={float(sig.get('pre_slope_pct_per_hour', 0)):.2f}%/hr "
        f"entry={float(sig.get('entry_price', 0)):.2f} "
        f"target={float(sig.get('target_price', 0)):.2f} "
        f"stop={float(sig.get('stop_price', 0)):.2f}"
        + _volume_suffix(sig)
    )



def deep_find(obj, keys):
    if isinstance(keys, str):
        keys = {keys}
    else:
        keys = set(keys)

    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in keys:
                return v
        for v in obj.values():
            found = deep_find(v, keys)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = deep_find(v, keys)
            if found is not None:
                return found
    return None


def trigger_key(e, strategy_id="A"):
    return f"{strategy_id}|{e.get('timestamp')}|{e.get('symbol')}"


def load_trigger_outcomes(path=SIGNAL_PAPER_OUTCOMES_JSONL):
    out = {}
    if not path.exists():
        return out
    try:
        with path.open() as f:
            for line in f:
                try:
                    r = json.loads(line)
                    k = r.get("key")
                    if k:
                        out[k] = r
                except Exception:
                    pass
    except Exception:
        pass
    return out


def save_trigger_outcomes(outcomes, path=SIGNAL_PAPER_OUTCOMES_JSONL):
    try:
        tmp = path.with_suffix(".tmp")
        with tmp.open("w") as f:
            for r in outcomes.values():
                f.write(json.dumps(r) + "\n")
        tmp.replace(path)
    except Exception:
        pass


def _resolve_rs2_split_outcome(rec, trade_rows, entry_ts):
    """Resolve RS2 as 50% RS1 exit plus 50% protected 60-minute hold."""
    import pandas as pd

    entry = float(rec["entry"])
    target = float(rec["target"])
    stop = float(rec["stop"])
    deadline = entry_ts + pd.Timedelta(minutes=60)

    standard_exit = None
    standard_reason = None
    hold_exit = None
    hold_reason = None

    highest = entry
    lowest = entry
    highest_time = entry_ts
    lowest_time = entry_ts

    for _, row in trade_rows.iterrows():
        price = float(row["price"])
        timestamp = row["timestamp"]
        market_time = timestamp.tz_convert(NY_TZ)

        if price > highest:
            highest = price
            highest_time = timestamp

        if price < lowest:
            lowest = price
            lowest_time = timestamp

        if standard_exit is None:
            if price >= target:
                standard_exit = row
                standard_reason = "target"
            elif price <= stop:
                standard_exit = row
                standard_reason = "stop"
            elif (market_time.hour, market_time.minute) >= (15, 55):
                standard_exit = row
                standard_reason = "end"

        if hold_exit is None:
            if price <= stop:
                hold_exit = row
                hold_reason = "stop"
            elif timestamp >= deadline:
                hold_exit = row
                hold_reason = "60_minute_hold"
            elif (market_time.hour, market_time.minute) >= (15, 55):
                hold_exit = row
                hold_reason = "end"

        if standard_exit is not None and hold_exit is not None:
            break

    def leg_values(exit_row, reason, latest_price):
        if exit_row is None:
            exit_price = float(latest_price)
            return {
                "closed": False,
                "exit_time": None,
                "exit_price": None,
                "exit_reason": None,
                "ret_pct": (exit_price / entry - 1.0) * 100.0,
            }

        if reason == "target":
            exit_price = target
        elif reason == "stop":
            exit_price = stop
        else:
            exit_price = float(exit_row["price"])

        return {
            "closed": True,
            "exit_time": str(exit_row["timestamp"]),
            "exit_price": exit_price,
            "exit_reason": reason,
            "ret_pct": (exit_price / entry - 1.0) * 100.0,
        }

    latest = trade_rows.iloc[-1]
    standard = leg_values(
        standard_exit,
        standard_reason,
        latest["price"],
    )
    hold = leg_values(
        hold_exit,
        hold_reason,
        latest["price"],
    )

    combined_return = (
        standard["ret_pct"] * 0.50
        + hold["ret_pct"] * 0.50
    )
    combined_pnl = (
        float(rec.get("paper_notional", 1000.0))
        * combined_return
        / 100.0
    )

    rec.update({
        "exit_model": "50pct_rs1_exit_50pct_60m_hold",
        "standard_leg_fraction": 0.50,
        "standard_leg_exit_time": standard["exit_time"],
        "standard_leg_exit_price": standard["exit_price"],
        "standard_leg_exit_reason": standard["exit_reason"],
        "standard_leg_ret_pct": standard["ret_pct"],
        "hold_leg_fraction": 0.50,
        "hold_leg_stop": stop,
        "hold_leg_deadline": str(deadline),
        "hold_leg_exit_time": hold["exit_time"],
        "hold_leg_exit_price": hold["exit_price"],
        "hold_leg_exit_reason": hold["exit_reason"],
        "hold_leg_ret_pct": hold["ret_pct"],
        "highest_price": highest,
        "highest_price_time": str(highest_time),
        "lowest_price": lowest,
        "lowest_price_time": str(lowest_time),
        "mfe_pct": (highest / entry - 1.0) * 100.0,
        "mae_pct": (lowest / entry - 1.0) * 100.0,
        "last_checked": datetime.now(timezone.utc).isoformat(),
    })

    if standard["closed"] and hold["closed"]:
        completion_times = [
            pd.Timestamp(standard["exit_time"]),
            pd.Timestamp(hold["exit_time"]),
        ]
        completion_time = max(completion_times)

        rec.update({
            "status": "closed",
            "exit_time": str(completion_time),
            "exit_price": (
                float(standard["exit_price"]) * 0.50
                + float(hold["exit_price"]) * 0.50
            ),
            "exit_reason": (
                f"50pct_{standard['exit_reason']}_"
                f"50pct_{hold['exit_reason']}"
            ),
            "ret_pct": combined_return,
            "pnl_usd": combined_pnl,
            "holding_minutes": max(
                0.0,
                (completion_time - entry_ts).total_seconds() / 60.0,
            ),
            "current_price": None,
            "current_return_pct": None,
            "current_pnl_usd": None,
        })
    else:
        rec.update({
            "status": "open",
            "current_price": float(latest["price"]),
            "current_return_pct": combined_return,
            "current_pnl_usd": combined_pnl,
            "last_price_time": str(latest["timestamp"]),
        })


def signal_paper_outcome_lines(signal_events, max_items=5, strategy_id="A", outcomes_path=SIGNAL_PAPER_OUTCOMES_JSONL):
    """Paper-track every qualifying SIGNAL using its entry, target, stop and EOD exit."""
    try:
        import pandas as pd
        from zoneinfo import ZoneInfo
    except Exception as e:
        return [f"unavailable: import failed: {type(e).__name__}: {e}"]

    outcomes = load_trigger_outcomes(outcomes_path)

    # Defense in depth: ignore any historical SIGNAL outside RTH.
    signal_events = [
        e for e in signal_events
        if is_rth_timestamp(e.get("timestamp"))
    ]

    # Create one durable paper record for every qualifying signal.
    for e in signal_events:
        try:
            k = trigger_key(e, strategy_id)
            if k in outcomes:
                continue

            sig = e.get("signal", {}) or {}
            sym = e.get("symbol") or sig.get("symbol")
            entry = sig.get("entry_price")
            target = sig.get("target_price")
            stop = sig.get("stop_price")
            drop = sig.get("flash_drop_pct")

            if not sym or entry is None or target is None or stop is None:
                continue

            outcomes[k] = {
                "key": k,
                "strategy_id": strategy_id,
                "timestamp": e.get("timestamp"),
                "symbol": sym,

                "paper_entry_regime": e.get("signal_regime"),

                "entry": float(entry),
                "target": float(target),
                "stop": float(stop),

                "flash_drop_pct": float(sig.get("flash_drop_pct", 0)),
                "pre_return_pct": float(sig.get("pre_return_pct", 0)),
                "pre_slope_pct_per_hour": float(sig.get("pre_slope_pct_per_hour", 0)),
                "pre_r2": float(sig.get("pre_r2", 0)),
                "pending_created_at": sig.get("pending_created_at"),
                "confirmation_wait_seconds": sig.get("confirmation_wait_seconds"),
                "running_low_price": sig.get("running_low_price"),
                "actual_rebound_pct": sig.get("actual_rebound_pct"),
                "recovery_fraction_at_entry": sig.get("recovery_fraction_at_entry"),
                "remaining_upside_pct": sig.get("remaining_upside_pct"),
                "original_target_price": sig.get("original_target_price"),
                "original_flash_drop_pct": sig.get("original_flash_drop_pct"),
                "setup": sig.get("setup"),
                "setup_id": sig.get("setup_id"),
                "exit_model": sig.get("exit_model"),
                "primary_universe": sig.get("primary_universe", "UNKNOWN"),
                "universe_memberships": sig.get("universe_memberships", []),
                "sampling_tier": sig.get("sampling_tier", "UNKNOWN"),
                "dynamic_promoted": bool(sig.get("dynamic_promoted", False)),
                "research_metrics": {
                    key: value for key, value in sig.items()
                    if key not in {
                        "strategy_id", "symbol", "timestamp", "entry_price",
                        "target_price", "stop_price", "live_order_placement"
                    }
                },
                **{
                    key: sig.get(key)
                    for key in (
                        "volume_data_status_flash", "flash_volume_1m", "flash_volume_3m",
                        "avg_volume_1m_pre30", "flash_volume_ratio",
                        "flash_dollar_volume_1m", "flash_dollar_volume_3m",
                        "flash_price_snapshot", "rolling_vwap_45m",
                        "distance_below_rolling_vwap_pct", "pre30_return_std_pct",
                        "flash_drop_volatility_units",
                        "volume_data_status_rebound", "rebound_volume_1m",
                        "rebound_volume_total", "rebound_volume_ratio",
                        "rebound_dollar_volume_1m", "rebound_dollar_volume_total",
                    )
                    if sig.get(key) is not None
                },

                "paper_notional": 1000.0,
                "status": "open",

                # Post-entry excursion tracking.
                "highest_price": float(entry),
                "highest_price_time": e.get("timestamp"),
                "lowest_price": float(entry),
                "lowest_price_time": e.get("timestamp"),
                "mfe_pct": 0.0,
                "mae_pct": 0.0,

                "exit_time": None,
                "exit_price": None,
                "exit_reason": None,
                "ret_pct": None,
                "pnl_usd": None,
                "last_checked": None,
            }
        except Exception:
            pass

    # Read only symbols that still have open paper trades.
    wanted_by_day = {}
    for rec in outcomes.values():
        if rec.get("status") == "closed" and rec.get("mfe_pct") is not None:
            continue
        ts = str(rec.get("timestamp", ""))
        sym = rec.get("symbol")
        if len(ts) >= 10 and sym:
            wanted_by_day.setdefault(ts[:10], set()).add(str(sym))

    tape_cache = {}
    for day, wanted in wanted_by_day.items():
        tape_path = Path("/data/tapes") / f"quotes_{day.replace('-', '')}.csv"
        if not tape_path.exists():
            tape_cache[day] = None
            continue

        try:
            parts = []
            for chunk in pd.read_csv(
                tape_path,
                usecols=["timestamp_utc", "symbol", "last_price"],
                dtype={"symbol": "string"},
                chunksize=50_000,
            ):
                chunk = chunk[chunk["symbol"].astype(str).isin(wanted)]
                if not chunk.empty:
                    parts.append(chunk)

            if not parts:
                tape_cache[day] = None
                continue

            df = pd.concat(parts, ignore_index=True).rename(
                columns={"timestamp_utc": "timestamp", "last_price": "price"}
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
            df["price"] = pd.to_numeric(df["price"], errors="coerce")
            df = df.dropna(subset=["timestamp", "symbol", "price"])

            et = df["timestamp"].dt.tz_convert(NY_TZ)
            minutes = et.dt.hour * 60 + et.dt.minute
            df = df[
                (et.dt.weekday < 5)
                & (minutes >= 9 * 60 + 30)
                & (minutes < 16 * 60)
            ]
            tape_cache[day] = df
        except Exception:
            tape_cache[day] = None

    # Resolve each trade at whichever occurs first: target, stop, or 15:55 ET.
    for rec in outcomes.values():
        if rec.get("status") == "closed" and rec.get("mfe_pct") is not None:
            continue

        try:
            ts = pd.Timestamp(rec["timestamp"])
            ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
            day = ts.strftime("%Y-%m-%d")
            df = tape_cache.get(day)
            if df is None or df.empty:
                continue

            sdf = df[
                (df["symbol"].astype(str) == str(rec["symbol"]))
                & (df["timestamp"] >= ts)
            ].sort_values("timestamp")
            if sdf.empty:
                continue

            if (
                rec.get("strategy_id") == "RS2"
                and rec.get("exit_model")
                == "50pct_rs1_exit_50pct_60m_hold"
            ):
                _resolve_rs2_split_outcome(rec, sdf, ts)
                continue

            target = float(rec["target"])
            stop = float(rec["stop"])
            entry = float(rec["entry"])
            exit_row = None
            reason = None

            highest_price = float(rec.get("highest_price", entry) or entry)
            lowest_price = float(rec.get("lowest_price", entry) or entry)
            highest_price_time = rec.get("highest_price_time") or rec.get("timestamp")
            lowest_price_time = rec.get("lowest_price_time") or rec.get("timestamp")

            for _, row in sdf.iterrows():
                px = float(row["price"])
                row_time = str(row["timestamp"])
                et = row["timestamp"].tz_convert(ZoneInfo("America/New_York"))

                if px > highest_price:
                    highest_price = px
                    highest_price_time = row_time
                if px < lowest_price:
                    lowest_price = px
                    lowest_price_time = row_time

                if px >= target:
                    exit_row, reason = row, "target"
                    break
                if px <= stop:
                    exit_row, reason = row, "stop"
                    break
                if (et.hour, et.minute) >= (15, 55):
                    exit_row, reason = row, "end"
                    break

            mfe_pct = (highest_price / entry - 1.0) * 100.0
            mae_pct = (lowest_price / entry - 1.0) * 100.0
            try:
                mfe_ts = pd.Timestamp(highest_price_time)
                mfe_ts = mfe_ts.tz_localize("UTC") if mfe_ts.tzinfo is None else mfe_ts.tz_convert("UTC")
                time_to_mfe_minutes = max(0.0, (mfe_ts - ts).total_seconds() / 60.0)
            except Exception:
                time_to_mfe_minutes = None
            stop_replay = {
                f"stop_{str(level).replace('.', '_')}pct_hit": mae_pct <= -level
                for level in STOP_REPLAY_LEVELS_PCT
            }
            rec.update({
                "highest_price": highest_price,
                "highest_price_time": highest_price_time,
                "lowest_price": lowest_price,
                "lowest_price_time": lowest_price_time,
                "mfe_pct": mfe_pct,
                "mae_pct": mae_pct,
                "time_to_mfe_minutes": time_to_mfe_minutes,
                "stop_replay": stop_replay,
                "last_checked": datetime.now(timezone.utc).isoformat(),
            })

            if exit_row is None:
                latest_row = sdf.iloc[-1]
                _update_open_mark_to_market(rec, latest_row["price"], latest_row["timestamp"])
                continue

            if reason == "target":
                exit_price = target
            elif reason == "stop":
                exit_price = stop
            else:
                exit_price = float(exit_row["price"])

            ret_pct = (exit_price / float(rec["entry"]) - 1) * 100
            rec.update({
                "status": "closed",
                "exit_time": str(exit_row["timestamp"]),
                "exit_price": exit_price,
                "exit_reason": reason,
                "ret_pct": ret_pct,
                "pnl_usd": float(rec.get("paper_notional", 1000.0)) * ret_pct / 100.0,
                "holding_minutes": max(
                    0.0, (exit_row["timestamp"] - ts).total_seconds() / 60.0
                ),
                "time_to_target_minutes": (
                    max(0.0, (exit_row["timestamp"] - ts).total_seconds() / 60.0)
                    if reason == "target" else None
                ),
                "last_checked": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass

    save_trigger_outcomes(outcomes, outcomes_path)

    rows = sorted(
        outcomes.values(),
        key=lambda r: str(r.get("timestamp", "")),
        reverse=True,
    )[:max_items]

    if not rows:
        return ["None"]

    lines = []
    for row in rows:
        try:
            base = (
                f"{row.get('timestamp')} | {row.get('symbol')} | "
                f"entry={float(row.get('entry', 0)):.2f} | "
                f"drop={float(row.get('flash_drop_pct', 0)):.2f}% | "
                f"pre_ret={float(row.get('pre_return_pct', 0)):.2f}% | "
                f"pre_slope={float(row.get('pre_slope_pct_per_hour', 0)):.2f}%/hr | "
                f"r2={float(row.get('pre_r2', 0)):.2f} | "
                f"universe={row.get('primary_universe', 'UNKNOWN')} | "
                f"sampling={row.get('sampling_tier', 'UNKNOWN')} | "
                f"promoted={'Y' if row.get('dynamic_promoted') else 'N'} | "
                f"detected={row.get('pending_created_at') or 'NA'} | "
                f"confirmed={row.get('timestamp')} | "
                f"confirmation_delay={float(row.get('confirmation_wait_seconds', 0) or 0):.1f}s | "
                f"running_low={float(row.get('running_low_price', row.get('entry', 0)) or 0):.2f} | "
                f"rebound={float(row.get('actual_rebound_pct', 0) or 0):.3f}% | "
                f"target={float(row.get('target', 0)):.2f} | "
                f"stop={float(row.get('stop', 0)):.2f} | "
                f"high={float(row.get('highest_price', row.get('entry', 0))):.2f} | "
                f"MFE={float(row.get('mfe_pct', 0) or 0):+.2f}%"
                f" @ {row.get('highest_price_time')} | "
                f"low={float(row.get('lowest_price', row.get('entry', 0))):.2f} | "
                f"MAE={float(row.get('mae_pct', 0) or 0):+.2f}%"
                f" @ {row.get('lowest_price_time')} | "
                f"recovery_at_entry={float(row.get('recovery_fraction_at_entry', 0) or 0) * 100:.1f}% | "
                f"remaining_upside={float(row.get('remaining_upside_pct', 0) or 0):.2f}% | "
                f"time_to_MFE={float(row.get('time_to_mfe_minutes', 0) or 0):.1f}m | "
                f"stop_replay=" + ",".join(
                    f"{level:g}%:{'Y' if (row.get('stop_replay') or {}).get('stop_' + str(level).replace('.', '_') + 'pct_hit') else 'N'}"
                    for level in STOP_REPLAY_LEVELS_PCT
                )
                + _volume_suffix(row)
                + (f" | setup={row.get('setup')} | metrics={json.dumps(row.get('research_metrics', {}), sort_keys=True, default=str)}" if row.get("setup") else "")
                + " | "
            )

            if row.get("status") == "closed":
                lines.append(
                    base
                    + f"exit_time={row.get('exit_time')} | "
                    + f"holding={float(row.get('holding_minutes', 0) or 0):.1f}m | "
                    + f"time_to_target={float(row.get('time_to_target_minutes', 0) or 0):.1f}m | "
                    + f"exit={float(row.get('exit_price', 0)):.2f} | "
                    + f"reason={row.get('exit_reason')} | "
                    + f"return={float(row.get('ret_pct', 0)):+.2f}% | "
                    + f"P/L_on_$1000={float(row.get('pnl_usd', 0)):+.2f}"
                )
            else:
                lines.append(base + _open_mark_to_market_suffix(row))
        except Exception as e:
            lines.append(
                f"{row.get('timestamp')} | {row.get('symbol')} | "
                f"render_error={type(e).__name__}: {e}"
            )

    return lines



_STRATEGY_C_TAPE_CACHE = {}

# Cache expensive live deployment simulation results within a writer process.
# Keyed by date and refreshed only when underlying inputs change.
_LIVE_DEPLOYMENT_CACHE = {}
_LIVE_DEPLOYMENT_RESULT_CACHE = {}



def _load_strategy_c_tape_day(day, wanted, pd):
    """Read a day's filtered tape once per file modification and symbol set."""
    tape_path = Path("/data/tapes") / f"quotes_{day.replace('-', '')}.csv"
    if not tape_path.exists():
        return None

    try:
        cache_key = (day, tuple(sorted(str(symbol) for symbol in wanted)))
        modified_ns = tape_path.stat().st_mtime_ns
        cached = _STRATEGY_C_TAPE_CACHE.get(cache_key)
        if cached and cached.get("modified_ns") == modified_ns:
            return cached.get("df")

        parts = []
        for chunk in pd.read_csv(
            tape_path,
            usecols=["timestamp_utc", "symbol", "last_price"],
            dtype={"symbol": "string"},
            chunksize=50_000,
        ):
            chunk = chunk[chunk["symbol"].astype(str).isin(wanted)]
            if not chunk.empty:
                parts.append(chunk)

        if not parts:
            result = None
        else:
            result = pd.concat(parts, ignore_index=True).rename(
                columns={"timestamp_utc": "timestamp", "last_price": "price"}
            )
            result["timestamp"] = pd.to_datetime(
                result["timestamp"], errors="coerce", utc=True
            )
            result["price"] = pd.to_numeric(result["price"], errors="coerce")
            result = result.dropna(subset=["timestamp", "symbol", "price"])
            et = result["timestamp"].dt.tz_convert(NY_TZ)
            minutes = et.dt.hour * 60 + et.dt.minute
            result = result[
                (et.dt.weekday < 5)
                & (minutes >= 9 * 60 + 30)
                & (minutes < 16 * 60)
            ]

        _STRATEGY_C_TAPE_CACHE[cache_key] = {
            "modified_ns": modified_ns,
            "df": result,
        }
        # Prevent unbounded growth if symbol sets change repeatedly.
        if len(_STRATEGY_C_TAPE_CACHE) > 20:
            oldest_key = next(iter(_STRATEGY_C_TAPE_CACHE))
            if oldest_key != cache_key:
                _STRATEGY_C_TAPE_CACHE.pop(oldest_key, None)
        return result
    except Exception:
        return None

def strategy_c_signal_paper_outcome_lines(
    signal_events,
    variant,
    max_items=5,
    outcomes_path=SIGNAL_PAPER_OUTCOMES_C1_JSONL,
    stop_loss_fraction=None,
    forward_start_utc=None,
):
    """Forward-paper Strategy C exits using Strategy B entries and quote tape.

    C1: exit after a configured pullback from the post-entry high.
    C2: exit after no new post-entry high for a configured number of seconds.
    C3: exit after configured consecutive lower quote samples and a minimum decline.
    C4: exit when the trailing price slope turns sufficiently negative.
    G: same exit as C4, with a separately configured protective stop.

    C variants retain Strategy B's original 2% protective stop unless an explicit
    stop override is supplied. Every variant keeps the 15:55 ET exit.
    Dynamic exits activate only after the trade first reaches the configured gain.
    """
    try:
        import pandas as pd
    except Exception as e:
        return [f"unavailable: import failed: {type(e).__name__}: {e}"]

    variant = str(variant).upper()
    if variant not in {"C1", "C2", "C3", "C4", "G"}:
        return [f"unavailable: unknown Strategy C variant {variant}"]

    outcomes = load_trigger_outcomes(outcomes_path)
    stop_loss_fraction = (
        STRATEGY_B_STOP_LOSS_FRACTION_BELOW_ENTRY
        if stop_loss_fraction is None
        else float(stop_loss_fraction)
    )
    start_ts = pd.Timestamp(forward_start_utc or STRATEGY_C_FORWARD_START_UTC)

    eligible_events = []
    for event in signal_events:
        try:
            event_ts = pd.Timestamp(event.get("timestamp"))
            event_ts = (
                event_ts.tz_localize("UTC")
                if event_ts.tzinfo is None
                else event_ts.tz_convert("UTC")
            )
            if is_rth_timestamp(event.get("timestamp")) and event_ts >= start_ts:
                eligible_events.append(event)
        except Exception:
            continue

    # Create one durable variant record for each Strategy B signal.
    for event in eligible_events:
        try:
            source_key = event.get("source_key")
            key = f"{variant}|{source_key}" if source_key else trigger_key(event, variant)
            if key in outcomes:
                continue

            sig = event.get("signal", {}) or {}
            symbol = event.get("symbol") or sig.get("symbol")
            entry = sig.get("entry_price")
            original_stop = sig.get("stop_price")
            if not symbol or entry is None:
                continue

            entry = float(entry)
            # Use Strategy B's recorded stop by default; dedicated variants may
            # override it while keeping the same entry and dynamic exit logic.
            if stop_loss_fraction == STRATEGY_B_STOP_LOSS_FRACTION_BELOW_ENTRY and original_stop is not None:
                stop = float(original_stop)
            else:
                stop = entry * (1.0 - stop_loss_fraction)

            outcomes[key] = {
                "key": key,
                "strategy_id": variant,
                "source_strategy_id": "B",
                "source_record_type": event.get("source_record_type", "signal"),
                "source_key": source_key,
                "timestamp": event.get("timestamp"),
                "symbol": symbol,
                "entry": entry,
                "stop": stop,
                "baseline_target": float(sig.get("target_price", 0) or 0),
                "flash_drop_pct": float(sig.get("flash_drop_pct", 0) or 0),
                "pre_return_pct": float(sig.get("pre_return_pct", 0) or 0),
                "pre_slope_pct_per_hour": float(sig.get("pre_slope_pct_per_hour", 0) or 0),
                "pre_r2": float(sig.get("pre_r2", 0) or 0),
                "paper_notional": 1000.0,
                "status": "open",
                "activation_gain_pct": STRATEGY_C_ACTIVATION_GAIN_PCT,
                "dynamic_exit_activated": False,
                "activation_time": None,
                "highest_price": entry,
                "highest_price_time": event.get("timestamp"),
                "lowest_price": entry,
                "lowest_price_time": event.get("timestamp"),
                "mfe_pct": 0.0,
                "mae_pct": 0.0,
                "exit_time": None,
                "exit_price": None,
                "exit_reason": None,
                "ret_pct": None,
                "pnl_usd": None,
                "holding_minutes": None,
                "last_checked": None,
            }
        except Exception:
            pass

    wanted_by_day = {}
    for rec in outcomes.values():
        if rec.get("status") == "closed":
            continue
        ts = str(rec.get("timestamp", ""))
        symbol = rec.get("symbol")
        if len(ts) >= 10 and symbol:
            wanted_by_day.setdefault(ts[:10], set()).add(str(symbol))

    tape_cache = {
        day: _load_strategy_c_tape_day(day, wanted, pd)
        for day, wanted in wanted_by_day.items()
    }

    for rec in outcomes.values():
        if rec.get("status") == "closed":
            continue
        try:
            entry_ts = pd.Timestamp(rec["timestamp"])
            entry_ts = (
                entry_ts.tz_localize("UTC")
                if entry_ts.tzinfo is None
                else entry_ts.tz_convert("UTC")
            )
            day = entry_ts.strftime("%Y-%m-%d")
            df = tape_cache.get(day)
            if df is None or df.empty:
                continue

            trade_rows = df[
                (df["symbol"].astype(str) == str(rec["symbol"]))
                & (df["timestamp"] >= entry_ts)
            ].sort_values("timestamp")
            if trade_rows.empty:
                continue

            entry = float(rec["entry"])
            stop = float(rec["stop"])
            activation_price = entry * (1.0 + STRATEGY_C_ACTIVATION_GAIN_PCT / 100.0)
            highest_price = entry
            lowest_price = entry
            highest_price_time = entry_ts
            lowest_price_time = entry_ts
            activated = False
            activation_time = None
            exit_row = None
            reason = None
            recent_samples = []

            for _, row in trade_rows.iterrows():
                px = float(row["price"])
                row_ts = row["timestamp"]
                et = row_ts.tz_convert(NY_TZ)

                if px > highest_price:
                    highest_price = px
                    highest_price_time = row_ts

                if px < lowest_price:
                    lowest_price = px
                    lowest_price_time = row_ts

                # Protective rules always remain active.
                if px <= stop:
                    exit_row, reason = row, "stop"
                    break
                if (et.hour, et.minute) >= (15, 55):
                    exit_row, reason = row, "end"
                    break

                if not activated and px >= activation_price:
                    activated = True
                    activation_time = row_ts
                    # Reset the dynamic pattern at activation so pre-activation
                    # weakness cannot immediately force an exit.
                    recent_samples = [(row_ts, px)]
                    highest_price = max(highest_price, px)
                    highest_price_time = row_ts
                    continue

                if not activated:
                    continue

                recent_samples.append((row_ts, px))

                if variant == "C1":
                    pullback_pct = (highest_price - px) / highest_price * 100.0
                    if pullback_pct >= STRATEGY_C1_PULLBACK_FROM_HIGH_PCT:
                        exit_row, reason = row, "trail_pullback"
                        break

                elif variant == "C2":
                    seconds_without_high = (row_ts - highest_price_time).total_seconds()
                    if seconds_without_high >= STRATEGY_C2_NO_NEW_HIGH_SECONDS:
                        exit_row, reason = row, "no_new_high"
                        break

                elif variant == "C3":
                    needed = STRATEGY_C3_LOWER_SAMPLES + 1
                    if len(recent_samples) >= needed:
                        window = recent_samples[-needed:]
                        prices = [sample[1] for sample in window]
                        all_lower = all(
                            prices[i] < prices[i - 1]
                            for i in range(1, len(prices))
                        )
                        total_decline_pct = (prices[0] - prices[-1]) / prices[0] * 100.0
                        if all_lower and total_decline_pct >= STRATEGY_C3_MIN_TOTAL_DECLINE_PCT:
                            exit_row, reason = row, "consecutive_lower_quotes"
                            break

                elif variant in {"C4", "G"}:
                    cutoff = row_ts - pd.Timedelta(seconds=STRATEGY_C4_SLOPE_WINDOW_SECONDS)
                    recent_samples = [
                        sample for sample in recent_samples if sample[0] >= cutoff
                    ]
                    if len(recent_samples) >= 2:
                        first_ts, first_px = recent_samples[0]
                        elapsed_minutes = (row_ts - first_ts).total_seconds() / 60.0
                        if elapsed_minutes > 0:
                            slope_pct_per_minute = (
                                (px / first_px - 1.0) * 100.0 / elapsed_minutes
                            )
                            if slope_pct_per_minute <= STRATEGY_C4_NEGATIVE_SLOPE_PCT_PER_MINUTE:
                                exit_row, reason = row, "negative_slope"
                                rec["exit_slope_pct_per_minute"] = slope_pct_per_minute
                                break

            rec.update({
                "dynamic_exit_activated": activated,
                "activation_time": str(activation_time) if activation_time is not None else None,
                "highest_price": highest_price,
                "highest_price_time": str(highest_price_time),
                "lowest_price": lowest_price,
                "lowest_price_time": str(lowest_price_time),
                "mfe_pct": (highest_price / entry - 1.0) * 100.0,
                "mae_pct": (lowest_price / entry - 1.0) * 100.0,
                "last_checked": datetime.now(timezone.utc).isoformat(),
            })

            if exit_row is None:
                latest_row = trade_rows.iloc[-1]
                _update_open_mark_to_market(rec, latest_row["price"], latest_row["timestamp"])
                continue

            exit_price = stop if reason == "stop" else float(exit_row["price"])
            ret_pct = (exit_price / entry - 1.0) * 100.0
            rec.update({
                "status": "closed",
                "exit_time": str(exit_row["timestamp"]),
                "exit_price": exit_price,
                "exit_reason": reason,
                "ret_pct": ret_pct,
                "pnl_usd": float(rec.get("paper_notional", 1000.0)) * ret_pct / 100.0,
                "holding_minutes": max(
                    0.0, (exit_row["timestamp"] - entry_ts).total_seconds() / 60.0
                ),
            })
        except Exception:
            pass

    save_trigger_outcomes(outcomes, outcomes_path)

    rows = sorted(
        outcomes.values(),
        key=lambda row: str(row.get("timestamp", "")),
        reverse=True,
    )[:max_items]
    if not rows:
        return ["None"]

    lines = []
    for row in rows:
        try:
            base = (
                f"{row.get('timestamp')} | {row.get('symbol')} | "
                f"entry={float(row.get('entry', 0)):.2f} | "
                f"stop={float(row.get('stop', 0)):.2f} | "
                f"baseline_target={float(row.get('baseline_target', 0)):.2f} | "
                f"activated={'Y' if row.get('dynamic_exit_activated') else 'N'} | "
                f"activation_time={row.get('activation_time')} | "
                f"high={float(row.get('highest_price', row.get('entry', 0))):.2f} | "
                f"MFE={float(row.get('mfe_pct', 0) or 0):+.2f}% | "
                f"low={float(row.get('lowest_price', row.get('entry', 0))):.2f} | "
                f"MAE={float(row.get('mae_pct', 0) or 0):+.2f}% | "
            )
            if row.get("status") == "closed":
                slope_suffix = (
                    f" | exit_slope={float(row.get('exit_slope_pct_per_minute')):+.2f}%/min"
                    if row.get("exit_slope_pct_per_minute") is not None
                    else ""
                )
                lines.append(
                    base
                    + f"exit_time={row.get('exit_time')} | "
                    + f"holding={float(row.get('holding_minutes', 0) or 0):.1f}m | "
                    + f"exit={float(row.get('exit_price', 0)):.2f} | "
                    + f"reason={row.get('exit_reason')} | "
                    + f"return={float(row.get('ret_pct', 0)):+.2f}% | "
                    + f"P/L_on_$1000={float(row.get('pnl_usd', 0)):+.2f}"
                    + slope_suffix
                )
            else:
                lines.append(base + _open_mark_to_market_suffix(row))
        except Exception as e:
            lines.append(
                f"{row.get('timestamp')} | {row.get('symbol')} | "
                f"render_error={type(e).__name__}: {e}"
            )
    return lines

def strategy_c_near_miss_paper_outcome_lines(
    variant,
    max_items=5,
    outcomes_path=NEAR_MISS_PAPER_C1_JSONL,
    source_path=NEAR_MISS_PAPER_B_JSONL,
    stop_loss_fraction=None,
    forward_start_utc=None,
):
    """Apply a Strategy C exit variant to confirmed Strategy B near-miss entries.

    Strategy C changes only the exit. Entry qualification and rebound confirmation
    therefore remain owned by the Strategy B near-miss ledger. Pending candidates
    and candidates with no rebound confirmation are intentionally excluded.
    """
    source_records = load_near_miss_paper(source_path)
    pseudo_events = []

    for source_key, rec in source_records.items():
        try:
            entry = rec.get("entry")
            entry_time = rec.get("confirmation_time")
            if entry is None or not entry_time:
                continue
            if rec.get("status") in {"pending_rebound", "no_confirmation"}:
                continue
            if not is_rth_timestamp(entry_time):
                continue

            entry = float(entry)
            stop = rec.get("stop")
            if stop is None:
                stop = entry * (1.0 - STRATEGY_B_STOP_LOSS_FRACTION_BELOW_ENTRY)

            pseudo_events.append({
                "event_type": "SIGNAL",
                "strategy_id": "B",
                "timestamp": entry_time,
                "symbol": rec.get("symbol"),
                "source_key": source_key,
                "source_record_type": "strategy_b_near_miss",
                "signal": {
                    "symbol": rec.get("symbol"),
                    "entry_price": entry,
                    "stop_price": float(stop),
                    "target_price": float(rec.get("target") or 0),
                    "flash_drop_pct": float(rec.get("flash_drop_pct", 0) or 0),
                    "pre_return_pct": float(rec.get("pre_return_pct", 0) or 0),
                    "pre_slope_pct_per_hour": float(
                        rec.get("pre_slope_pct_per_hour", 0) or 0
                    ),
                    "pre_r2": float(rec.get("pre_r2", 0) or 0),
                },
            })
        except Exception:
            continue

    return strategy_c_signal_paper_outcome_lines(
        pseudo_events,
        variant=variant,
        max_items=max_items,
        outcomes_path=outcomes_path,
        stop_loss_fraction=stop_loss_fraction,
        forward_start_utc=forward_start_utc,
    )



def strategy_j_signal_paper_outcome_lines(
    signal_events,
    variant,
    max_items=5,
    outcomes_path=None,
    forward_start_utc=STRATEGY_J_FORWARD_START_UTC,
):
    """Prospectively test early-failure exits on identical Strategy B entries.

    Every J variant retains Strategy B's recorded recovery target and differs only
    in protective stop size and/or one fixed post-entry checkpoint. At the first
    quote at or after the checkpoint, a trade exits when its return is at or below
    the configured threshold. The target, protective stop, and 15:55 ET exit remain
    active throughout. This is paper-only and never submits a broker order.
    """
    try:
        import pandas as pd
    except Exception as exc:
        return [f"unavailable: import failed: {type(exc).__name__}: {exc}"]

    variant = str(variant).upper()
    config = STRATEGY_J_CONFIGS.get(variant)
    if config is None:
        return [f"unavailable: unknown Strategy J variant {variant}"]
    outcomes_path = outcomes_path or STRATEGY_J_OUTCOME_PATHS[variant]
    outcomes = load_trigger_outcomes(outcomes_path)
    start_ts = pd.Timestamp(forward_start_utc)

    eligible_events = []
    for event in signal_events:
        try:
            event_ts = pd.Timestamp(event.get("timestamp"))
            event_ts = event_ts.tz_localize("UTC") if event_ts.tzinfo is None else event_ts.tz_convert("UTC")
            if (
                event_strategy(event) == "B"
                and event.get("event_type") == "SIGNAL"
                and is_rth_timestamp(event.get("timestamp"))
                and event_ts >= start_ts
            ):
                eligible_events.append(event)
        except Exception:
            continue

    for event in eligible_events:
        try:
            sig = event.get("signal", {}) or {}
            symbol = event.get("symbol") or sig.get("symbol")
            entry = sig.get("entry_price")
            target = sig.get("target_price")
            if not symbol or entry is None or target is None:
                continue
            source_key = trigger_key(event, "B")
            key = f"{variant}|{source_key}"
            if key in outcomes:
                continue
            entry = float(entry)
            outcomes[key] = {
                "key": key,
                "strategy_id": variant,
                "source_strategy_id": "B",
                "source_key": source_key,
                "timestamp": event.get("timestamp"),
                "symbol": symbol,
                "entry": entry,
                "target": float(target),
                "stop": entry * (1.0 - float(config["stop_loss_fraction"])),
                "stop_loss_fraction": float(config["stop_loss_fraction"]),
                "checkpoint_seconds": config["checkpoint_seconds"],
                "checkpoint_max_return_pct": config["checkpoint_max_return_pct"],
                "checkpoint_time": None,
                "checkpoint_price": None,
                "checkpoint_return_pct": None,
                "checkpoint_evaluated": False,
                "paper_notional": 1000.0,
                "status": "open",
                "highest_price": entry,
                "highest_price_time": event.get("timestamp"),
                "lowest_price": entry,
                "lowest_price_time": event.get("timestamp"),
                "mfe_pct": 0.0,
                "mae_pct": 0.0,
                "exit_time": None,
                "exit_price": None,
                "exit_reason": None,
                "ret_pct": None,
                "pnl_usd": None,
                "holding_minutes": None,
                "last_checked": None,
            }
        except Exception:
            continue

    wanted_by_day = {}
    for rec in outcomes.values():
        if rec.get("status") == "closed":
            continue
        timestamp = str(rec.get("timestamp", ""))
        symbol = rec.get("symbol")
        if len(timestamp) >= 10 and symbol:
            wanted_by_day.setdefault(timestamp[:10], set()).add(str(symbol))

    tape_cache = {
        day: _load_strategy_c_tape_day(day, wanted, pd)
        for day, wanted in wanted_by_day.items()
    }

    for rec in outcomes.values():
        if rec.get("status") == "closed":
            continue
        try:
            entry_ts = pd.Timestamp(rec["timestamp"])
            entry_ts = entry_ts.tz_localize("UTC") if entry_ts.tzinfo is None else entry_ts.tz_convert("UTC")
            df = tape_cache.get(entry_ts.strftime("%Y-%m-%d"))
            if df is None or df.empty:
                continue
            rows = df[
                (df["symbol"].astype(str) == str(rec["symbol"]))
                & (df["timestamp"] >= entry_ts)
            ].sort_values("timestamp")
            if rows.empty:
                continue

            entry = float(rec["entry"])
            target = float(rec["target"])
            stop = float(rec["stop"])
            checkpoint_seconds = rec.get("checkpoint_seconds")
            checkpoint_deadline = (
                entry_ts + pd.Timedelta(seconds=float(checkpoint_seconds))
                if checkpoint_seconds is not None else None
            )
            highest_price = entry
            lowest_price = entry
            highest_price_time = entry_ts
            lowest_price_time = entry_ts
            checkpoint_evaluated = bool(rec.get("checkpoint_evaluated"))
            exit_row = None
            reason = None

            for _, row in rows.iterrows():
                px = float(row["price"])
                row_ts = row["timestamp"]
                et = row_ts.tz_convert(NY_TZ)
                if px > highest_price:
                    highest_price, highest_price_time = px, row_ts
                if px < lowest_price:
                    lowest_price, lowest_price_time = px, row_ts

                # Quote-order simulation: whichever condition appears first in tape wins.
                if px <= stop:
                    exit_row, reason = row, "stop"
                    break
                if px >= target:
                    exit_row, reason = row, "target"
                    break
                if (et.hour, et.minute) >= (15, 55):
                    exit_row, reason = row, "end"
                    break

                if (
                    checkpoint_deadline is not None
                    and not checkpoint_evaluated
                    and row_ts >= checkpoint_deadline
                ):
                    checkpoint_return = (px / entry - 1.0) * 100.0
                    rec.update({
                        "checkpoint_evaluated": True,
                        "checkpoint_time": str(row_ts),
                        "checkpoint_price": px,
                        "checkpoint_return_pct": checkpoint_return,
                    })
                    checkpoint_evaluated = True
                    if checkpoint_return <= float(rec["checkpoint_max_return_pct"]):
                        exit_row, reason = row, "no_progress_checkpoint"
                        break

            rec.update({
                "highest_price": highest_price,
                "highest_price_time": str(highest_price_time),
                "lowest_price": lowest_price,
                "lowest_price_time": str(lowest_price_time),
                "mfe_pct": (highest_price / entry - 1.0) * 100.0,
                "mae_pct": (lowest_price / entry - 1.0) * 100.0,
                "last_checked": datetime.now(timezone.utc).isoformat(),
            })
            if exit_row is None:
                latest = rows.iloc[-1]
                _update_open_mark_to_market(rec, latest["price"], latest["timestamp"])
                continue

            exit_price = stop if reason == "stop" else target if reason == "target" else float(exit_row["price"])
            ret_pct = (exit_price / entry - 1.0) * 100.0
            rec.update({
                "status": "closed",
                "exit_time": str(exit_row["timestamp"]),
                "exit_price": exit_price,
                "exit_reason": reason,
                "ret_pct": ret_pct,
                "pnl_usd": float(rec.get("paper_notional", 1000.0)) * ret_pct / 100.0,
                "holding_minutes": max(0.0, (exit_row["timestamp"] - entry_ts).total_seconds() / 60.0),
            })
        except Exception:
            continue

    save_trigger_outcomes(outcomes, outcomes_path)
    records = sorted(outcomes.values(), key=lambda row: str(row.get("timestamp", "")), reverse=True)[:max_items]
    if not records:
        return ["None"]

    lines = []
    for row in records:
        try:
            checkpoint = (
                f"checkpoint={float(row.get('checkpoint_seconds')):.0f}s | "
                f"checkpoint_return={float(row.get('checkpoint_return_pct')):+.3f}% | "
                if row.get("checkpoint_seconds") is not None and row.get("checkpoint_return_pct") is not None
                else f"checkpoint={float(row.get('checkpoint_seconds')):.0f}s | checkpoint_return=NA | "
                if row.get("checkpoint_seconds") is not None
                else "checkpoint=none | "
            )
            base = (
                f"{row.get('timestamp')} | {row.get('symbol')} | "
                f"entry={float(row.get('entry', 0)):.2f} | "
                f"target={float(row.get('target', 0)):.2f} | "
                f"stop={float(row.get('stop', 0)):.2f} | "
                + checkpoint
                + f"MFE={float(row.get('mfe_pct', 0) or 0):+.2f}% | "
                f"MAE={float(row.get('mae_pct', 0) or 0):+.2f}% | "
            )
            if row.get("status") == "closed":
                lines.append(
                    base
                    + f"exit_time={row.get('exit_time')} | "
                    + f"holding={float(row.get('holding_minutes', 0) or 0):.2f}m | "
                    + f"exit={float(row.get('exit_price', 0)):.2f} | "
                    + f"reason={row.get('exit_reason')} | "
                    + f"return={float(row.get('ret_pct', 0)):+.2f}% | "
                    + f"P/L_on_$1000={float(row.get('pnl_usd', 0)):+.2f}"
                )
            else:
                lines.append(base + _open_mark_to_market_suffix(row))
        except Exception as exc:
            lines.append(f"{row.get('timestamp')} | {row.get('symbol')} | render_error={type(exc).__name__}: {exc}")
    return lines



def strategy_k_family_lines(
    signal_events,
    max_items=5,
    forward_start_utc=STRATEGY_K_FORWARD_START_UTC,
):
    """Update shared early-behavior instrumentation and K1-K9 paper outcomes.

    K uses identical Strategy A entries. A single shared record captures quote-tape
    behavior at 15/30/60/90/120/180/300 seconds plus first-positive milestones.
    Each K variant then applies one predeclared early-exit rule while preserving
    A's recorded target, stop and 15:55 ET exit. No broker orders are submitted.
    """
    try:
        import pandas as pd
    except Exception as exc:
        return {"analysis": [f"unavailable: import failed: {type(exc).__name__}: {exc}"], "variants": {}}

    start_ts = pd.Timestamp(forward_start_utc)
    analysis = load_trigger_outcomes(K_EARLY_BEHAVIOR_JSONL)
    variant_maps = {
        variant: load_trigger_outcomes(path)
        for variant, path in STRATEGY_K_OUTCOME_PATHS.items()
    }

    eligible = []
    for event in signal_events:
        try:
            event_ts = pd.Timestamp(event.get("timestamp"))
            event_ts = event_ts.tz_localize("UTC") if event_ts.tzinfo is None else event_ts.tz_convert("UTC")
            if (
                event_strategy(event) == "A"
                and event.get("event_type") == "SIGNAL"
                and is_rth_timestamp(event.get("timestamp"))
                and event_ts >= start_ts
            ):
                eligible.append(event)
        except Exception:
            continue

    for event in eligible:
        try:
            sig = event.get("signal", {}) or {}
            symbol = event.get("symbol") or sig.get("symbol")
            entry = sig.get("entry_price")
            target = sig.get("target_price")
            stop = sig.get("stop_price")
            if not symbol or entry is None or target is None or stop is None:
                continue
            source_key = trigger_key(event, "A")
            if source_key not in analysis:
                analysis[source_key] = {
                    "key": source_key,
                    "strategy_id": "K_ANALYSIS",
                    "source_strategy_id": "A",
                    "timestamp": event.get("timestamp"),
                    "symbol": symbol,
                    "entry": float(entry),
                    "target": float(target),
                    "stop": float(stop),
                    "checkpoints": {},
                    "first_positive_time": None,
                    "first_positive_seconds": None,
                    "first_plus_0_10_time": None,
                    "first_plus_0_10_seconds": None,
                    "first_plus_0_20_time": None,
                    "first_plus_0_20_seconds": None,
                    "first_5m_mfe_pct": 0.0,
                    "first_5m_mae_pct": 0.0,
                    "baseline_exit_time": None,
                    "baseline_exit_reason": None,
                    "baseline_exit_price": None,
                    "baseline_ret_pct": None,
                    "status": "open",
                    "last_checked": None,
                }
            for variant, config in STRATEGY_K_CONFIGS.items():
                key = f"{variant}|{source_key}"
                outcomes = variant_maps[variant]
                if key in outcomes:
                    continue
                outcomes[key] = {
                    "key": key,
                    "strategy_id": variant,
                    "source_strategy_id": "A",
                    "source_key": source_key,
                    "timestamp": event.get("timestamp"),
                    "symbol": symbol,
                    "entry": float(entry),
                    "target": float(target),
                    "stop": float(stop),
                    "rule": dict(config),
                    "paper_notional": 1000.0,
                    "status": "open",
                    "highest_price": float(entry),
                    "lowest_price": float(entry),
                    "mfe_pct": 0.0,
                    "mae_pct": 0.0,
                    "checkpoint_time": None,
                    "checkpoint_price": None,
                    "checkpoint_return_pct": None,
                    "checkpoint_mfe_pct": None,
                    "checkpoint_mae_pct": None,
                    "exit_time": None,
                    "exit_price": None,
                    "exit_reason": None,
                    "ret_pct": None,
                    "pnl_usd": None,
                    "holding_minutes": None,
                    "last_checked": None,
                }
        except Exception:
            continue

    wanted_by_day = {}
    for rec in analysis.values():
        if rec.get("status") == "complete":
            continue
        ts = str(rec.get("timestamp", ""))
        sym = rec.get("symbol")
        if len(ts) >= 10 and sym:
            wanted_by_day.setdefault(ts[:10], set()).add(str(sym))
    for outcomes in variant_maps.values():
        for rec in outcomes.values():
            if rec.get("status") == "closed":
                continue
            ts = str(rec.get("timestamp", ""))
            sym = rec.get("symbol")
            if len(ts) >= 10 and sym:
                wanted_by_day.setdefault(ts[:10], set()).add(str(sym))

    tape_cache = {
        day: _load_strategy_c_tape_day(day, wanted, pd)
        for day, wanted in wanted_by_day.items()
    }

    # Shared instrumentation.
    for rec in analysis.values():
        if rec.get("status") == "complete":
            continue
        try:
            entry_ts = pd.Timestamp(rec["timestamp"])
            entry_ts = entry_ts.tz_localize("UTC") if entry_ts.tzinfo is None else entry_ts.tz_convert("UTC")
            df = tape_cache.get(entry_ts.strftime("%Y-%m-%d"))
            if df is None or df.empty:
                continue
            rows = df[(df["symbol"].astype(str) == str(rec["symbol"])) & (df["timestamp"] >= entry_ts)].sort_values("timestamp")
            if rows.empty:
                continue
            entry, target, stop = float(rec["entry"]), float(rec["target"]), float(rec["stop"])
            first5_highest = entry
            first5_lowest = entry
            checkpoints = dict(rec.get("checkpoints") or {})
            baseline_exit = None
            baseline_reason = None

            for _, row in rows.iterrows():
                px = float(row["price"])
                row_ts = row["timestamp"]
                elapsed = max(0.0, (row_ts - entry_ts).total_seconds())
                ret = (px / entry - 1.0) * 100.0
                if elapsed <= max(STRATEGY_K_CHECKPOINT_SECONDS):
                    first5_highest = max(first5_highest, px)
                    first5_lowest = min(first5_lowest, px)
                if rec.get("first_positive_time") is None and ret > 0:
                    rec["first_positive_time"] = str(row_ts)
                    rec["first_positive_seconds"] = elapsed
                if rec.get("first_plus_0_10_time") is None and ret >= 0.10:
                    rec["first_plus_0_10_time"] = str(row_ts)
                    rec["first_plus_0_10_seconds"] = elapsed
                if rec.get("first_plus_0_20_time") is None and ret >= 0.20:
                    rec["first_plus_0_20_time"] = str(row_ts)
                    rec["first_plus_0_20_seconds"] = elapsed
                for seconds in STRATEGY_K_CHECKPOINT_SECONDS:
                    key = str(seconds)
                    if key not in checkpoints and elapsed >= seconds:
                        checkpoints[key] = {
                            "time": str(row_ts),
                            "price": px,
                            "return_pct": ret,
                            "mfe_pct": (first5_highest / entry - 1.0) * 100.0,
                            "mae_pct": (first5_lowest / entry - 1.0) * 100.0,
                        }
                et = row_ts.tz_convert(NY_TZ)
                if px >= target:
                    baseline_exit, baseline_reason = row, "target"
                    break
                if px <= stop:
                    baseline_exit, baseline_reason = row, "stop"
                    break
                if (et.hour, et.minute) >= (15, 55):
                    baseline_exit, baseline_reason = row, "end"
                    break

            rec["checkpoints"] = checkpoints
            rec["first_5m_mfe_pct"] = (first5_highest / entry - 1.0) * 100.0
            rec["first_5m_mae_pct"] = (first5_lowest / entry - 1.0) * 100.0
            rec["last_checked"] = datetime.now(timezone.utc).isoformat()
            if baseline_exit is not None:
                exit_price = target if baseline_reason == "target" else stop if baseline_reason == "stop" else float(baseline_exit["price"])
                rec.update({
                    "baseline_exit_time": str(baseline_exit["timestamp"]),
                    "baseline_exit_reason": baseline_reason,
                    "baseline_exit_price": exit_price,
                    "baseline_ret_pct": (exit_price / entry - 1.0) * 100.0,
                })
            if baseline_exit is not None:
                rec["status"] = "complete"
            elif len(checkpoints) == len(STRATEGY_K_CHECKPOINT_SECONDS):
                rec["status"] = "instrumented"
        except Exception:
            continue

    # Variant simulations.
    for variant, config in STRATEGY_K_CONFIGS.items():
        outcomes = variant_maps[variant]
        for rec in outcomes.values():
            if rec.get("status") == "closed":
                continue
            try:
                entry_ts = pd.Timestamp(rec["timestamp"])
                entry_ts = entry_ts.tz_localize("UTC") if entry_ts.tzinfo is None else entry_ts.tz_convert("UTC")
                df = tape_cache.get(entry_ts.strftime("%Y-%m-%d"))
                if df is None or df.empty:
                    continue
                rows = df[(df["symbol"].astype(str) == str(rec["symbol"])) & (df["timestamp"] >= entry_ts)].sort_values("timestamp")
                if rows.empty:
                    continue
                entry, target, stop = float(rec["entry"]), float(rec["target"]), float(rec["stop"])
                deadline = entry_ts + pd.Timedelta(seconds=float(config["seconds"]))
                highest = entry
                lowest = entry
                evaluated = rec.get("checkpoint_time") is not None
                exit_row = None
                reason = None
                for _, row in rows.iterrows():
                    px = float(row["price"])
                    row_ts = row["timestamp"]
                    et = row_ts.tz_convert(NY_TZ)
                    highest = max(highest, px)
                    lowest = min(lowest, px)
                    if px >= target:
                        exit_row, reason = row, "target"
                        break
                    if px <= stop:
                        exit_row, reason = row, "stop"
                        break
                    if (et.hour, et.minute) >= (15, 55):
                        exit_row, reason = row, "end"
                        break
                    if not evaluated and row_ts >= deadline:
                        ret = (px / entry - 1.0) * 100.0
                        mfe = (highest / entry - 1.0) * 100.0
                        mae = (lowest / entry - 1.0) * 100.0
                        rec.update({
                            "checkpoint_time": str(row_ts),
                            "checkpoint_price": px,
                            "checkpoint_return_pct": ret,
                            "checkpoint_mfe_pct": mfe,
                            "checkpoint_mae_pct": mae,
                        })
                        evaluated = True
                        mode = config["mode"]
                        should_exit = (
                            mode == "fixed_exit"
                            or (mode == "conditional_return" and ret <= float(config["min_return_pct"]))
                            or (mode == "conditional_mfe" and mfe < float(config["min_mfe_pct"]))
                            or (mode == "conditional_reach" and mfe < float(config["required_gain_pct"]))
                        )
                        if should_exit:
                            exit_row, reason = row, f"{mode}_{int(config['seconds'])}s"
                            break
                rec.update({
                    "highest_price": highest,
                    "lowest_price": lowest,
                    "mfe_pct": (highest / entry - 1.0) * 100.0,
                    "mae_pct": (lowest / entry - 1.0) * 100.0,
                    "last_checked": datetime.now(timezone.utc).isoformat(),
                })
                if exit_row is None:
                    latest = rows.iloc[-1]
                    _update_open_mark_to_market(rec, latest["price"], latest["timestamp"])
                    continue
                exit_price = target if reason == "target" else stop if reason == "stop" else float(exit_row["price"])
                ret_pct = (exit_price / entry - 1.0) * 100.0
                rec.update({
                    "status": "closed",
                    "exit_time": str(exit_row["timestamp"]),
                    "exit_price": exit_price,
                    "exit_reason": reason,
                    "ret_pct": ret_pct,
                    "pnl_usd": float(rec.get("paper_notional", 1000.0)) * ret_pct / 100.0,
                    "holding_minutes": max(0.0, (exit_row["timestamp"] - entry_ts).total_seconds() / 60.0),
                })
            except Exception:
                continue

    save_trigger_outcomes(analysis, K_EARLY_BEHAVIOR_JSONL)
    for variant, outcomes in variant_maps.items():
        save_trigger_outcomes(outcomes, STRATEGY_K_OUTCOME_PATHS[variant])

    analysis_rows = sorted(analysis.values(), key=lambda r: str(r.get("timestamp", "")), reverse=True)[:max_items]
    analysis_lines = []
    if not analysis_rows:
        analysis_lines = ["None"]
    else:
        for rec in analysis_rows:
            cps = rec.get("checkpoints") or {}
            checkpoint_text = ", ".join(
                f"{sec}s={float((cps.get(str(sec)) or {}).get('return_pct')):+.3f}%"
                if (cps.get(str(sec)) or {}).get("return_pct") is not None else f"{sec}s=NA"
                for sec in STRATEGY_K_CHECKPOINT_SECONDS
            )
            analysis_lines.append(
                f"{rec.get('timestamp')} | {rec.get('symbol')} | entry={float(rec.get('entry', 0)):.2f} | "
                f"{checkpoint_text} | first_positive={rec.get('first_positive_seconds')}s | "
                f"first_+0.10={rec.get('first_plus_0_10_seconds')}s | first_+0.20={rec.get('first_plus_0_20_seconds')}s | "
                f"first5m_MFE={float(rec.get('first_5m_mfe_pct', 0) or 0):+.2f}% | "
                f"first5m_MAE={float(rec.get('first_5m_mae_pct', 0) or 0):+.2f}% | "
                f"baseline={rec.get('baseline_exit_reason') or 'OPEN'}"
            )

    variant_lines = {}
    for variant, outcomes in variant_maps.items():
        rows = sorted(outcomes.values(), key=lambda r: str(r.get("timestamp", "")), reverse=True)[:max_items]
        lines = []
        if not rows:
            lines = ["None"]
        else:
            for rec in rows:
                base = (
                    f"{rec.get('timestamp')} | {rec.get('symbol')} | entry={float(rec.get('entry', 0)):.2f} | "
                    f"checkpoint_return={float(rec.get('checkpoint_return_pct', 0) or 0):+.3f}% | "
                    f"checkpoint_MFE={float(rec.get('checkpoint_mfe_pct', 0) or 0):+.3f}% | "
                    f"checkpoint_MAE={float(rec.get('checkpoint_mae_pct', 0) or 0):+.3f}% | "
                    f"MFE={float(rec.get('mfe_pct', 0) or 0):+.2f}% | MAE={float(rec.get('mae_pct', 0) or 0):+.2f}% | "
                )
                if rec.get("status") == "closed":
                    lines.append(base + f"exit_time={rec.get('exit_time')} | holding={float(rec.get('holding_minutes', 0) or 0):.2f}m | exit={float(rec.get('exit_price', 0)):.2f} | reason={rec.get('exit_reason')} | return={float(rec.get('ret_pct', 0)):+.2f}% | P/L_on_$1000={float(rec.get('pnl_usd', 0)):+.2f}")
                else:
                    lines.append(base + _open_mark_to_market_suffix(rec))
        variant_lines[variant] = lines

    return {"analysis": analysis_lines, "variants": variant_lines}


def trigger_trade_outcome_lines(max_items=5):
    """Render completed real broker trades, including MFE and MAE."""
    if not TRIGGER_OUTCOMES_JSONL.exists():
        return ["None"]

    rows = deque(maxlen=max_items)
    try:
        with TRIGGER_OUTCOMES_JSONL.open() as f:
            for raw in f:
                try:
                    row = json.loads(raw)
                    if row.get("symbol"):
                        rows.append(row)
                except Exception:
                    pass
    except Exception as e:
        return [f"unavailable: {type(e).__name__}: {e}"]

    if not rows:
        return ["None"]

    lines = []
    for r in reversed(rows):
        try:
            lines.append(
                f"{r.get('entry_fill_time')} | {r.get('symbol')} | "
                f"entry={float(r.get('entry_fill_price', 0)):.2f} | "
                f"exit_time={r.get('exit_fill_time')} | "
                f"exit={float(r.get('exit_fill_price', 0)):.2f} | "
                f"reason={r.get('exit_reason')} | "
                f"holding={float(r.get('holding_minutes', 0) or 0):.1f}m | "
                f"high={float(r.get('highest_price', 0)):.2f} | "
                f"MFE={float(r.get('mfe_pct', 0)):+.2f}% @ {r.get('mfe_at')} | "
                f"low={float(r.get('lowest_price', 0)):.2f} | "
                f"MAE={float(r.get('mae_pct', 0)):+.2f}% @ {r.get('mae_at')} | "
                f"recovery_at_entry={float(r.get('recovery_fraction_at_entry', 0) or 0) * 100:.1f}% | "
                f"remaining_upside={float(r.get('remaining_upside_pct', 0) or 0):.2f}% | "
                f"time_to_MFE={float(r.get('time_to_mfe_minutes', 0) or 0):.1f}m | "
                f"time_to_target={float(r.get('time_to_target_minutes', 0) or 0):.1f}m | "
                f"stop_replay=" + ",".join(
                    f"{level:g}%:{'Y' if (r.get('stop_replay') or {}).get('stop_' + str(level).replace('.', '_') + 'pct_hit') else 'N'}"
                    for level in STOP_REPLAY_LEVELS_PCT
                )
                + _volume_suffix(r)
                + " | "
                f"return={float(r.get('return_pct', 0)):+.2f}% | "
                f"P/L={float(r.get('realized_pnl', 0)):+.2f}"
            )
        except Exception as e:
            lines.append(f"{r.get('symbol', '?')} | render_error={type(e).__name__}: {e}")
    return lines


def summarize_trigger_event(e):
    sig = e.get("signal", {}) or {}
    return (
        f"{e.get('timestamp')} | {e.get('symbol')} | "
        f"buy_limit={float(e.get('buy_limit_price', 0)):.2f} | "
        f"entry={float(sig.get('entry_price', 0)):.2f} | "
        f"target={float(sig.get('target_price', 0)):.2f} | "
        f"stop={float(sig.get('stop_price', 0)):.2f} | "
        f"drop={float(sig.get('flash_drop_pct', 0)):.2f}% | "
        f"pre_ret={float(sig.get('pre_return_pct', 0)):.2f}% | "
        f"pre_slope={float(sig.get('pre_slope_pct_per_hour', 0)):.2f}%/hr"
        + _volume_suffix(sig)
    )

def summarize_execution_event(e):
    et = e.get("event_type", "UNKNOWN")
    sym = e.get("symbol", "?")
    qty = e.get("qty", "?")
    ts = e.get("timestamp", "?")
    if et in ("BUY_ATTEMPT", "SELL_ATTEMPT"):
        return f"{ts} | {et} | {sym} qty={qty}"
    if et in ("BUY_RESPONSE", "SELL_RESPONSE"):
        return f"{ts} | {et} | {sym} qty={qty} response={e.get('response')}"
    if et in ("BUY_ERROR", "SELL_ERROR"):
        return f"{ts} | {et} | {sym} qty={qty} error={e.get('exception_type')}: {e.get('error')}"
    return f"{ts} | {et} | {sym} qty={qty}"


def eligibility_health_lines():
    if not ELIGIBILITY_STATUS_PATH.exists():
        return [
            "ELIGIBILITY UNIVERSE",
            "status: UNKNOWN",
            f"status_file: {ELIGIBILITY_STATUS_PATH} MISSING",
        ]

    try:
        status = json.loads(ELIGIBILITY_STATUS_PATH.read_text())
        fallback = bool(status.get("used_fallback", False))
        age_days = status.get("age_days")
        age_text = "unknown" if age_days is None else f"{age_days} day" + ("" if age_days == 1 else "s")
        return [
            "ELIGIBILITY UNIVERSE",
            f"file: {status.get('filename', 'unknown')}",
            f"cache_date: {status.get('cache_date', 'unknown')}",
            f"symbols: {status.get('symbol_count', 'unknown')}",
            f"source: {'FALLBACK' if fallback else 'TODAY'}",
            f"age: {age_text}",
            f"collector_loaded: {status.get('loaded_at', 'unknown')}",
            f"status: {status.get('status', 'UNKNOWN')}",
        ]
    except Exception as exc:
        return [
            "ELIGIBILITY UNIVERSE",
            "status: ERROR",
            f"eligibility_status_error: {type(exc).__name__}: {exc}",
        ]


def memory_health_lines():
    """Report VM/container RAM from procfs without external packages."""
    try:
        values = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            if ":" not in line:
                continue
            key, raw = line.split(":", 1)
            parts = raw.strip().split()
            if parts:
                values[key] = int(parts[0]) * 1024  # meminfo values are kB

        total = int(values.get("MemTotal", 0))
        available = int(values.get("MemAvailable", values.get("MemFree", 0)))
        used = max(0, total - available)
        pct = (used / total * 100) if total else 0.0

        def fmt(n):
            n = float(n)
            for unit in ["B", "K", "M", "G", "T"]:
                if n < 1024:
                    return f"{n:.0f}{unit}"
                n /= 1024
            return f"{n:.0f}P"

        python_rss = 0
        python_processes = 0
        for status_path in Path("/proc").glob("[0-9]*/status"):
            try:
                name = None
                rss_kb = 0
                for line in status_path.read_text().splitlines():
                    if line.startswith("Name:"):
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("VmRSS:"):
                        rss_kb = int(line.split()[1])
                if name and name.startswith("python") and rss_kb:
                    python_processes += 1
                    python_rss += rss_kb * 1024
            except (FileNotFoundError, ProcessLookupError, PermissionError, ValueError):
                continue

        return [
            "MEMORY HEALTH",
            f"ram_used_estimate: {fmt(used)} / {fmt(total)}",
            f"ram_available: {fmt(available)}",
            f"ram_use_percent_estimate: {pct:.1f}%",
            f"python_process_rss_total: {fmt(python_rss)} across {python_processes} processes",
        ]
    except Exception as exc:
        return ["MEMORY HEALTH", f"memory_error: {type(exc).__name__}: {exc}"]



def cpu_health_lines():
    """Estimate CPU pressure from Linux load average without external packages."""
    try:
        load1, load5, load15 = map(
            float, Path("/proc/loadavg").read_text().split()[:3]
        )
        cpu_count = os.cpu_count() or 1
        pressure_pct = (load1 / cpu_count) * 100.0

        if pressure_pct < 70:
            status = "OK"
        elif pressure_pct < 100:
            status = "BUSY"
        elif pressure_pct < 150:
            status = "HIGH"
        else:
            status = "OVERLOADED"

        return [
            "CPU HEALTH",
            f"cpu_count: {cpu_count}",
            f"cpu_pressure_estimate: {pressure_pct:.1f}% ({status})",
            f"load_average_1m_5m_15m: {load1:.2f} / {load5:.2f} / {load15:.2f}",
        ]
    except Exception as exc:
        return ["CPU HEALTH", f"cpu_error: {type(exc).__name__}: {exc}"]

def storage_health_lines():
    try:
        usage = shutil.disk_usage("/data")
        total = usage.total
        used = usage.used
        free = usage.free
        pct = (used / total * 100) if total else 0

        def fmt(n):
            for unit in ["B", "K", "M", "G", "T"]:
                if n < 1024:
                    return f"{n:.0f}{unit}"
                n /= 1024
            return f"{n:.0f}P"

        return [
            "STORAGE HEALTH",
            f"data_used: {fmt(used)} / {fmt(total)}",
            f"data_available: {fmt(free)}",
            f"data_use_percent: {pct:.1f}%",
        ]
    except Exception as e:
        return ["STORAGE HEALTH", f"storage_error: {e}"]

def _one_token_health_lines(label, token_path):
    token_path = Path(token_path)
    if not token_path.exists():
        return [label, f"token_file: {token_path} MISSING", "auth_status: BROKEN"]

    try:
        token_data = json.loads(token_path.read_text())
        token = token_data.get("token", {}) if isinstance(token_data.get("token"), dict) else {}

        created = float(token_data.get("creation_timestamp", 0) or 0)
        expires = float(token.get("expires_at", 0) or token_data.get("expires_at", 0) or 0)
        has_access_token = bool(token.get("access_token") or token_data.get("access_token"))
        has_refresh_token = bool(token.get("refresh_token") or token_data.get("refresh_token"))
        account_present = bool(token_data.get("account_id") or token_data.get("account_hash"))
        now = time.time()

        minutes_left = (expires - now) / 60 if expires else -999999
        access_status = "EXPIRED" if minutes_left <= 0 else ("WARNING" if minutes_left < 10 else "OK")

        if has_refresh_token:
            auth_status = "REFRESHABLE" if access_status != "EXPIRED" else "ACCESS_EXPIRED_BUT_REFRESH_TOKEN_PRESENT"
        else:
            auth_status = "ACCESS_ONLY_EXPIRED_NEEDS_MANUAL_REGEN" if access_status == "EXPIRED" else "ACCESS_ONLY_OK"

        lines = [
            label,
            f"token_file: {token_path}",
            f"token_file_modified_utc: {datetime.fromtimestamp(token_path.stat().st_mtime, timezone.utc).isoformat()}",
            f"token_created_utc: {datetime.fromtimestamp(created, timezone.utc).isoformat() if created else 'unknown'}",
            f"access_token_expires_utc: {datetime.fromtimestamp(expires, timezone.utc).isoformat() if expires else 'unknown'}",
            f"access_token_minutes_left: {minutes_left:.1f}",
            f"has_access_token: {has_access_token}",
            f"has_refresh_token: {has_refresh_token}",
            f"account_present: {account_present}",
            f"access_status: {access_status}",
            f"auth_status: {auth_status}",
            f"auto_refresh: {'YES_VIA_SCHWAB_PY' if has_refresh_token else 'NO_REFRESH_TOKEN'}",
            f"refresh_note: {'access token refreshes automatically on next authenticated SDK request' if has_refresh_token else 'manual token regeneration required when access expires'}",
        ]

        if created:
            lines += [
                f"manual_reauth_due_utc: {datetime.fromtimestamp(created + 7*24*3600, timezone.utc).isoformat()}",
                f"manual_reauth_time_left: {((created + 7*24*3600) - now)/86400:.2f} days",
            ]

        return lines

    except Exception as e:
        return [label, f"token_parse_error: {e}", "auth_status: BROKEN"]



def append_auth_health_snapshot():
    try:
        snap = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "market_minutes_left": token_minutes_left("/data/schwab_token.json"),
            "trading_minutes_left": token_minutes_left("/data/schwab_trade_token.json"),
            "storage_used_percent": storage_used_percent(),
        }

        snap["market_status"] = (
            "EXPIRED" if snap["market_minutes_left"] < 0 else
            "WARNING" if snap["market_minutes_left"] < 10 else
            "OK"
        )
        snap["trading_status"] = (
            "EXPIRED" if snap["trading_minutes_left"] < 0 else
            "WARNING" if snap["trading_minutes_left"] < 10 else
            "OK"
        )

        with AUTH_HEALTH_LOG.open("a") as f:
            f.write(json.dumps(snap) + "\n")
    except Exception:
        pass


def auth_downtime_history_lines():
    try:
        if not AUTH_HEALTH_LOG.exists():
            return ["No auth history yet."]

        today = datetime.now(timezone.utc).date().isoformat()
        rows = []
        with AUTH_HEALTH_LOG.open() as f:
            for line in f:
                try:
                    r = json.loads(line)
                    if str(r.get("timestamp", ""))[:10] == today:
                        rows.append(r)
                except Exception:
                    pass

        if not rows:
            return ["No auth history today."]

        lines = []
        for prefix, min_key, status_key in [
            ("market_data", "market_minutes_left", "market_status"),
            ("trading", "trading_minutes_left", "trading_status"),
        ]:
            vals = [float(r.get(min_key, 999999)) for r in rows]
            statuses = [r.get(status_key, "unknown") for r in rows]

            warnings = sum(1 for st in statuses if st == "WARNING")
            expired = sum(1 for st in statuses if st == "EXPIRED")
            worst = min(vals) if vals else 999999

            bad_rows = [
                r for r in rows
                if r.get(status_key) in ("WARNING", "EXPIRED")
            ]
            last_bad = bad_rows[-1].get("timestamp") if bad_rows else "none"

            lines.append(
                f"{prefix} | snapshots={len(rows)} | warnings={warnings} | "
                f"expired={expired} | worst_minutes_left={worst:.1f} | last_bad={last_bad}"
            )

        storage_vals = [float(r.get("storage_used_percent", 0)) for r in rows]
        lines.append(
            f"storage | worst_used_percent={max(storage_vals):.1f}% | "
            f"latest_used_percent={storage_vals[-1]:.1f}%"
        )

        return lines
    except Exception as e:
        return [f"auth history unavailable: {type(e).__name__}: {e}"]

def token_health_lines():
    market = _one_token_health_lines("SCHWAB MARKET DATA HEALTH", "/data/schwab_token.json")
    trading = _one_token_health_lines("SCHWAB TRADING HEALTH", "/data/schwab_trade_token.json")

    def status(lines):
        joined = "\n".join(lines)
        if "access_status: OK" in joined or "access_status: WARNING" in joined:
            return "OK"
        if "auth_status: ACCESS_EXPIRED_BUT_REFRESH_TOKEN_PRESENT" in joined:
            return "REFRESHABLE"
        return "BROKEN"

    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    tape = Path("/data/tapes") / f"quotes_{today}.csv"
    if not tape.exists() or tape.stat().st_size == 0:
        quote_status = "NO_TAPE"
    else:
        tape_age = max(0, time.time() - tape.stat().st_mtime)
        quote_status = "OK" if tape_age <= 120 else f"STALE ({tape_age:.0f}s)"

    capabilities = [
        "BOT CAPABILITIES",
        f"quote_collection: {quote_status}",
        "signal_generation: OK",
        f"order_placement: {status(trading)}",
    ]

    return market + [""] + trading + [""] + capabilities


def near_miss_paper_key(e, strategy_id="A"):
    return f"{strategy_id}|{e.get('seen_at')}|{e.get('symbol')}|{float(e.get('price', 0)):.6f}"


def load_near_miss_paper(path=NEAR_MISS_PAPER_JSONL):
    out = {}
    if not path.exists():
        return out
    try:
        with path.open() as f:
            for line in f:
                try:
                    row = json.loads(line)
                    key = row.get("key")
                    if key:
                        out[key] = row
                except Exception:
                    pass
    except Exception:
        pass
    return out


def save_near_miss_paper(outcomes, path=NEAR_MISS_PAPER_JSONL):
    try:
        tmp = path.with_suffix(".tmp")
        with tmp.open("w") as f:
            for row in outcomes.values():
                f.write(json.dumps(row) + "\n")
        tmp.replace(path)
    except Exception:
        pass


def near_miss_paper_lines(top_events, max_items=25, strategy_id="A", outcomes_path=NEAR_MISS_PAPER_JSONL, rebound_confirmation_pct=None, stop_loss_fraction=None):
    """Paper-track near misses using the live strategy's rebound entry logic.

    A near miss is first recorded as pending. Its paper entry occurs only after
    price rises REBOUND_CONFIRMATION_PCT above the running post-detection low.
    Target, stop, holding time and P/L are then calculated from that confirmed
    entry, matching the signal paper trade mechanics.
    """
    try:
        import pandas as pd
    except Exception as e:
        return [f"unavailable: import failed: {type(e).__name__}: {e}"]

    outcomes = load_near_miss_paper(outcomes_path)
    rebound_confirmation_pct = (
        REBOUND_CONFIRMATION_PCT if rebound_confirmation_pct is None else rebound_confirmation_pct
    )
    stop_loss_fraction = (
        STOP_LOSS_FRACTION_BELOW_ENTRY if stop_loss_fraction is None else stop_loss_fraction
    )

    # Defense in depth: only paper-track near misses first observed in RTH.
    top_events = [
        event for event in top_events
        if is_rth_timestamp(event.get("seen_at"))
    ]

    # Freeze each distinct dashboard event once. Repeated symbols at different
    # timestamps remain separate paper candidates.
    for event in top_events:
        try:
            key = near_miss_paper_key(event, strategy_id)
            if key in outcomes:
                rec = outcomes[key]
                rec.setdefault("pre_return_pct", float(event.get("pre_return_pct", 0) or 0))
                rec.setdefault(
                    "pre_slope_pct_per_hour",
                    float(event.get("pre_slope_pct_per_hour", 0) or 0),
                )
                rec.setdefault("pre_r2", float(event.get("pre_r2", 0) or 0))
                rec.setdefault("failed", event.get("failed", "unknown"))
                rec.setdefault("gap", float(event.get("gap", 0) or 0))
                rec.setdefault("miss_score", float(event.get("miss_score", 999) or 999))
                for volume_key in (
                    "volume_data_status_flash", "flash_volume_1m", "flash_volume_3m",
                    "avg_volume_1m_pre30", "flash_volume_ratio",
                    "flash_dollar_volume_1m", "flash_dollar_volume_3m",
                ):
                    if event.get(volume_key) is not None:
                        rec.setdefault(volume_key, event.get(volume_key))
                continue

            detection_price = float(event.get("price", 0))
            drop = float(event.get("flash_drop_pct", 0))
            if detection_price <= 0 or drop >= 100:
                continue

            flash_start = detection_price / (1 - drop / 100.0)

            outcomes[key] = {
                "key": key,
                "strategy_id": strategy_id,
                "date": str(event.get("seen_at", ""))[:10],
                "timestamp": event.get("seen_at"),
                "detection_time": event.get("seen_at"),
                "symbol": event.get("symbol"),
                "detection_price": detection_price,
                "flash_start_price": flash_start,
                "flash_drop_pct": drop,
                "pre_return_pct": float(event.get("pre_return_pct", 0) or 0),
                "pre_slope_pct_per_hour": float(
                    event.get("pre_slope_pct_per_hour", 0) or 0
                ),
                "pre_r2": float(event.get("pre_r2", 0) or 0),
                "failed": event.get("failed", "unknown"),
                "gap": float(event.get("gap", 0) or 0),
                "miss_score": float(event.get("miss_score", 999) or 999),
                **{
                    volume_key: event.get(volume_key)
                    for volume_key in (
                        "volume_data_status_flash", "flash_volume_1m", "flash_volume_3m",
                        "avg_volume_1m_pre30", "flash_volume_ratio",
                        "flash_dollar_volume_1m", "flash_dollar_volume_3m",
                    )
                    if event.get(volume_key) is not None
                },
                "required_rebound_pct": rebound_confirmation_pct * 100,
                "running_low": detection_price,
                "confirmation_time": None,
                "confirmation_delay_seconds": None,
                "actual_rebound_pct": None,
                "entry": None,
                "target": None,
                "stop": None,
                "paper_notional": 1000.0,
                "status": "pending_rebound",
                "highest_price": None,
                "highest_price_time": None,
                "lowest_price": None,
                "lowest_price_time": None,
                "mfe_pct": None,
                "mae_pct": None,
                "exit_time": None,
                "exit_price": None,
                "exit_reason": None,
                "ret_pct": None,
                "pnl_usd": None,
            }
        except Exception:
            pass

    wanted_by_day = {}
    for rec in outcomes.values():
        if rec.get("status") in ("closed", "no_confirmation"):
            continue
        ts = str(rec.get("detection_time") or rec.get("timestamp", ""))
        sym = rec.get("symbol")
        if len(ts) >= 10 and sym:
            wanted_by_day.setdefault(ts[:10], set()).add(str(sym))

    tape_cache = {}
    for day, wanted in wanted_by_day.items():
        tape_path = Path("/data/tapes") / f"quotes_{day.replace('-', '')}.csv"
        if not tape_path.exists():
            tape_cache[day] = None
            continue
        try:
            parts = []
            for chunk in pd.read_csv(
                tape_path,
                usecols=["timestamp_utc", "symbol", "last_price"],
                dtype={"symbol": "string"},
                chunksize=50_000,
            ):
                chunk = chunk[chunk["symbol"].astype(str).isin(wanted)]
                if not chunk.empty:
                    parts.append(chunk)
            if not parts:
                tape_cache[day] = None
                continue
            df = pd.concat(parts, ignore_index=True).rename(
                columns={"timestamp_utc": "timestamp", "last_price": "price"}
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
            df["price"] = pd.to_numeric(df["price"], errors="coerce")
            df = df.dropna(subset=["timestamp", "symbol", "price"])

            et = df["timestamp"].dt.tz_convert(NY_TZ)
            minutes = et.dt.hour * 60 + et.dt.minute
            df = df[
                (et.dt.weekday < 5)
                & (minutes >= 9 * 60 + 30)
                & (minutes < 16 * 60)
            ]
            tape_cache[day] = df
        except Exception:
            tape_cache[day] = None

    for rec in outcomes.values():
        if rec.get("status") in ("closed", "no_confirmation"):
            continue
        try:
            detection_ts = pd.Timestamp(
                rec.get("detection_time") or rec.get("timestamp")
            )
            detection_ts = (
                detection_ts.tz_localize("UTC")
                if detection_ts.tzinfo is None
                else detection_ts.tz_convert("UTC")
            )
            day = detection_ts.strftime("%Y-%m-%d")
            df = tape_cache.get(day)
            if df is None or df.empty:
                continue

            sdf = df[
                (df["symbol"].astype(str) == str(rec["symbol"]))
                & (df["timestamp"] >= detection_ts)
            ].sort_values("timestamp")
            if sdf.empty:
                continue

            # New records wait for the same running-low rebound as live entries.
            # Legacy open records that already have an entry are allowed to
            # continue resolving without rewriting historical paper results.
            if rec.get("entry") is None:
                running_low = float(
                    rec.get("running_low")
                    or rec.get("detection_price")
                    or sdf.iloc[0]["price"]
                )
                confirmation_row = None

                for _, row in sdf.iterrows():
                    px = float(row["price"])
                    if px < running_low:
                        running_low = px

                    rebound_fraction = (px / running_low) - 1.0
                    if rebound_fraction >= rebound_confirmation_pct:
                        confirmation_row = row
                        rec["actual_rebound_pct"] = rebound_fraction * 100
                        break

                    et = row["timestamp"].tz_convert(NY_TZ)
                    if (et.hour, et.minute) >= (15, 55):
                        rec.update({
                            "status": "no_confirmation",
                            "running_low": running_low,
                            "exit_time": str(row["timestamp"]),
                            "exit_reason": "no_rebound_confirmation",
                            "ret_pct": 0.0,
                            "pnl_usd": 0.0,
                        })
                        break

                rec["running_low"] = running_low

                if rec.get("status") == "no_confirmation":
                    continue
                if confirmation_row is None:
                    continue

                entry = float(confirmation_row["price"])
                flash_start = float(rec["flash_start_price"])
                target = entry + RECOVERY_TARGET_FRACTION * (flash_start - entry)
                stop = entry * (1 - stop_loss_fraction)
                confirmation_ts = confirmation_row["timestamp"]

                rec.update({
                    "status": "open",
                    "confirmation_time": str(confirmation_ts),
                    "highest_price": entry,
                    "highest_price_time": str(confirmation_ts),
                    "lowest_price": entry,
                    "lowest_price_time": str(confirmation_ts),
                    "mfe_pct": 0.0,
                    "mae_pct": 0.0,
                    "confirmation_delay_seconds": max(
                        0.0, (confirmation_ts - detection_ts).total_seconds()
                    ),
                    "entry": entry,
                    "target": target,
                    "stop": stop,
                    "confirmed_flash_drop_pct": (
                        (flash_start - entry) / flash_start * 100
                    ),
                })

            entry_ts = pd.Timestamp(rec.get("confirmation_time") or rec["timestamp"])
            entry_ts = (
                entry_ts.tz_localize("UTC")
                if entry_ts.tzinfo is None
                else entry_ts.tz_convert("UTC")
            )
            trade_rows = sdf[sdf["timestamp"] >= entry_ts]
            if trade_rows.empty:
                continue

            target = float(rec["target"])
            stop = float(rec["stop"])
            entry = float(rec["entry"])
            exit_row = None
            reason = None

            highest_price = float(rec.get("highest_price", entry) or entry)
            lowest_price = float(rec.get("lowest_price", entry) or entry)
            highest_price_time = rec.get("highest_price_time") or str(entry_ts)
            lowest_price_time = rec.get("lowest_price_time") or str(entry_ts)

            for _, row in trade_rows.iterrows():
                px = float(row["price"])
                row_time = str(row["timestamp"])
                et = row["timestamp"].tz_convert(NY_TZ)

                if px > highest_price:
                    highest_price = px
                    highest_price_time = row_time
                if px < lowest_price:
                    lowest_price = px
                    lowest_price_time = row_time

                if px >= target:
                    exit_row, reason = row, "target"
                    break
                if px <= stop:
                    exit_row, reason = row, "stop"
                    break
                if (et.hour, et.minute) >= (15, 55):
                    exit_row, reason = row, "end"
                    break

            rec.update({
                "highest_price": highest_price,
                "highest_price_time": highest_price_time,
                "lowest_price": lowest_price,
                "lowest_price_time": lowest_price_time,
                "mfe_pct": (highest_price / entry - 1.0) * 100.0,
                "mae_pct": (lowest_price / entry - 1.0) * 100.0,
            })

            if exit_row is None:
                latest_row = trade_rows.iloc[-1]
                _update_open_mark_to_market(rec, latest_row["price"], latest_row["timestamp"])
                continue

            exit_price = (
                target if reason == "target"
                else stop if reason == "stop"
                else float(exit_row["price"])
            )
            ret_pct = (exit_price / float(rec["entry"]) - 1) * 100
            rec.update({
                "status": "closed",
                "exit_time": str(exit_row["timestamp"]),
                "exit_price": exit_price,
                "exit_reason": reason,
                "ret_pct": ret_pct,
                "pnl_usd": float(rec.get("paper_notional", 1000.0)) * ret_pct / 100.0,
                "holding_minutes": max(
                    0.0, (exit_row["timestamp"] - entry_ts).total_seconds() / 60.0
                ),
            })
        except Exception:
            pass

    save_near_miss_paper(outcomes, outcomes_path)

    rows = sorted(
        outcomes.values(),
        key=lambda r: str(r.get("detection_time") or r.get("timestamp", "")),
        reverse=True,
    )[:max_items]
    if not rows:
        return ["None"]

    lines = []
    for row in rows:
        try:
            detection_price = float(
                row.get("detection_price")
                or row.get("entry")
                or 0
            )
            base = (
                f"{row.get('detection_time') or row.get('timestamp')} | {row.get('symbol')} | "
                f"detected={detection_price:.2f} | "
                f"drop={float(row.get('flash_drop_pct', 0)):.2f}% | "
                f"pre_ret={float(row.get('pre_return_pct', 0)):.2f}% | "
                f"pre_slope={float(row.get('pre_slope_pct_per_hour', 0)):.2f}%/hr | "
                f"r2={float(row.get('pre_r2', 0)):.2f} | "
                f"gap={float(row.get('gap', 0)):.2f}% | "
                f"fails={row.get('failed', 'unknown')} | "
                f"score={float(row.get('miss_score', 999)):.2f}"
                + _volume_suffix(row)
                + " | "
            )

            if row.get("status") == "pending_rebound":
                lines.append(
                    base
                    + f"low={float(row.get('running_low', detection_price)):.2f} | "
                    + f"required_rebound={float(row.get('required_rebound_pct', rebound_confirmation_pct * 100)):.2f}% | "
                    + "status=PENDING_REBOUND"
                )
            elif row.get("status") == "no_confirmation":
                lines.append(
                    base
                    + f"low={float(row.get('running_low', detection_price)):.2f} | "
                    + "status=NO_REBOUND_CONFIRMATION | P/L_on_$1000=+0.00"
                )
            else:
                base += (
                    f"confirmed={row.get('confirmation_time', row.get('timestamp'))} | "
                    f"delay={float(row.get('confirmation_delay_seconds', 0) or 0):.1f}s | "
                    f"low={float(row.get('running_low', 0) or 0):.2f} | "
                    f"rebound={float(row.get('actual_rebound_pct', 0) or 0):.3f}% | "
                    f"entry={float(row.get('entry', 0)):.2f} | "
                    f"target={float(row.get('target', 0)):.2f} | "
                    f"stop={float(row.get('stop', 0)):.2f} | "
                    f"high={float(row.get('highest_price', row.get('entry', 0)) or row.get('entry', 0)):.2f} | "
                    f"MFE={float(row.get('mfe_pct', 0) or 0):+.2f}%"
                    f" @ {row.get('highest_price_time')} | "
                    f"low={float(row.get('lowest_price', row.get('entry', 0)) or row.get('entry', 0)):.2f} | "
                    f"MAE={float(row.get('mae_pct', 0) or 0):+.2f}%"
                    f" @ {row.get('lowest_price_time')} | "
                )
                if row.get("status") == "closed":
                    lines.append(
                        base
                        + f"exit_time={row.get('exit_time')} | "
                        + f"holding={float(row.get('holding_minutes', 0) or 0):.1f}m | "
                        + f"exit={float(row.get('exit_price', 0)):.2f} | "
                        + f"reason={row.get('exit_reason')} | "
                        + f"return={float(row.get('ret_pct', 0)):+.2f}% | "
                        + f"P/L_on_$1000={float(row.get('pnl_usd', 0)):+.2f}"
                    )
                else:
                    lines.append(base + _open_mark_to_market_suffix(row))
        except Exception as e:
            lines.append(
                f"{row.get('timestamp')} | {row.get('symbol')} | "
                f"render_error={type(e).__name__}: {e}"
            )
    return lines


REBOUND_EVENT_TYPES = {
    "PENDING_REBOUND_CREATED",
    "PENDING_REBOUND_NEW_LOW",
    "PENDING_REBOUND_WAITING",
    "REBOUND_CONFIRMED",
    "PENDING_REBOUND_CANCELLED_NOT_QUALIFIED",
    "PENDING_REBOUND_CANCELLED_ENTRY_CUTOFF",
    "PENDING_REBOUND_TIMEOUT",
}


def load_today_rebound_events(today):
    """Load every rebound-lifecycle event for today without the 5,000-row cap."""
    if not EVENTS_JSONL.exists():
        return []
    rows = []
    try:
        with EVENTS_JSONL.open() as f:
            for raw in f:
                try:
                    event = json.loads(raw)
                except Exception:
                    continue
                if (
                    event.get("event_type") in REBOUND_EVENT_TYPES
                    and str(event.get("timestamp", "")).startswith(today)
                    and is_rth_timestamp(event.get("timestamp"))
                ):
                    rows.append(event)
    except Exception:
        return []
    return rows


def _safe_float(value, default=None):
    try:
        return float(value)
    except Exception:
        return default


def _update_open_mark_to_market(rec, price, price_time):
    """Store a lightweight mark-to-market snapshot for an open paper trade."""
    try:
        entry = float(rec.get("entry"))
        current_price = float(price)
        if entry <= 0 or current_price <= 0:
            return
        current_ret_pct = (current_price / entry - 1.0) * 100.0
        notional = float(rec.get("paper_notional", 1000.0) or 1000.0)
        rec.update({
            "current_price": current_price,
            "current_price_time": str(price_time),
            "current_ret_pct": current_ret_pct,
            "current_pnl_usd": notional * current_ret_pct / 100.0,
        })
    except Exception:
        pass


def _open_mark_to_market_suffix(row):
    """Render the latest cached quote and unrealized P/L for an open record."""
    current_price = _safe_float((row or {}).get("current_price"))
    current_ret_pct = _safe_float((row or {}).get("current_ret_pct"))
    current_pnl_usd = _safe_float((row or {}).get("current_pnl_usd"))
    if current_price is None or current_ret_pct is None or current_pnl_usd is None:
        return "current=UNAVAILABLE | status=OPEN (P/L unavailable)"
    return (
        f"current={current_price:.2f} | "
        f"current_return={current_ret_pct:+.2f}% | "
        f"current_P/L_on_$1000={current_pnl_usd:+.2f} | "
        f"current_at={row.get('current_price_time')} | status=OPEN ({current_pnl_usd:+.2f})"
    )


def _outcome_summary_lines(outcomes, date_utc=None):
    """Summarize realized plus cached mark-to-market P/L for one outcome table."""
    date_utc = date_utc or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    records = []
    for row in (outcomes or {}).values():
        timestamp = str(row.get("timestamp") or row.get("detection_time") or "")
        row_date = str(row.get("date") or timestamp[:10])
        if row_date == date_utc:
            records.append(row)

    closed = [r for r in records if r.get("status") == "closed"]
    open_rows = [r for r in records if r.get("status") == "open"]
    pending = [r for r in records if r.get("status") == "pending_rebound"]
    no_confirmation = [r for r in records if r.get("status") == "no_confirmation"]

    realized = sum(float(r.get("pnl_usd", 0) or 0) for r in closed)
    open_values = [
        _safe_float(r.get("current_pnl_usd"))
        for r in open_rows
        if _safe_float(r.get("current_pnl_usd")) is not None
    ]
    open_mtm = sum(open_values)
    unavailable = len(open_rows) - len(open_values)
    total = realized + open_mtm
    suffix = f" | open_P/L_unavailable={unavailable}" if unavailable else ""
    as_of = datetime.now(timezone.utc).isoformat()
    return [
        f"SUMMARY_DATE_UTC: {date_utc} | as_of_utc: {as_of}",
        f"trades={len(closed) + len(open_rows)} | closed={len(closed)} | open={len(open_rows)} | pending_rebound={len(pending)} | no_confirmation={len(no_confirmation)}",
        f"realized_P/L_on_$1000_each={realized:+.2f} | open_mark_to_market_P/L={open_mtm:+.2f} | current_total_P/L={total:+.2f}{suffix}",
    ]


def _with_outcome_summary(lines, outcomes):
    return _outcome_summary_lines(outcomes) + list(lines or ["None"])


def rebound_lifecycle(rebound_events):
    """Return active candidates, completed outcomes, and summary statistics."""
    active = {}
    outcomes = []

    for event in sorted(rebound_events, key=lambda e: str(e.get("timestamp", ""))):
        event_type = event.get("event_type")
        symbol = event.get("symbol")
        if not symbol:
            continue

        if event_type == "PENDING_REBOUND_CREATED":
            active[symbol] = {
                "symbol": symbol,
                "created_at": event.get("timestamp"),
                "last_update": event.get("timestamp"),
                "current_price": event.get("current_price"),
                "lowest_price": event.get("current_price"),
                "rebound_pct": 0.0,
                "highest_rebound_pct": 0.0,
                "required_rebound_pct": event.get("required_rebound_pct"),
                "waiting_seconds": 0.0,
                "signal": event.get("signal", {}) or {},
            }
            continue

        candidate = active.get(symbol)

        if event_type in ("PENDING_REBOUND_NEW_LOW", "PENDING_REBOUND_WAITING"):
            if candidate is None:
                candidate = {
                    "symbol": symbol,
                    "created_at": event.get("pending_created_at") or event.get("timestamp"),
                    "signal": event.get("signal", {}) or {},
                }
                active[symbol] = candidate
            candidate["last_update"] = event.get("timestamp")
            candidate["current_price"] = event.get("current_price", event.get("new_low"))
            candidate["lowest_price"] = event.get(
                "lowest_price", event.get("new_low", candidate.get("lowest_price"))
            )
            candidate["rebound_pct"] = event.get("rebound_pct", candidate.get("rebound_pct"))
            candidate["highest_rebound_pct"] = event.get(
                "highest_rebound_pct", candidate.get("highest_rebound_pct", 0.0)
            )
            candidate["required_rebound_pct"] = event.get(
                "required_rebound_pct", candidate.get("required_rebound_pct")
            )
            candidate["waiting_seconds"] = event.get(
                "waiting_seconds", candidate.get("waiting_seconds")
            )
            if event.get("signal"):
                candidate["signal"] = event.get("signal")
            continue

        if event_type in (
            "REBOUND_CONFIRMED",
            "PENDING_REBOUND_CANCELLED_NOT_QUALIFIED",
            "PENDING_REBOUND_CANCELLED_ENTRY_CUTOFF",
            "PENDING_REBOUND_TIMEOUT",
        ):
            base = candidate or {
                "symbol": symbol,
                "created_at": event.get("pending_created_at"),
                "signal": event.get("original_signal") or event.get("signal") or {},
            }
            outcome = dict(base)
            outcome.update({
                "event_type": event_type,
                "finished_at": event.get("timestamp"),
                "current_price": event.get("entry_price", event.get("current_price", base.get("current_price"))),
                "lowest_price": event.get("lowest_price", base.get("lowest_price")),
                "rebound_pct": event.get("rebound_pct", base.get("rebound_pct")),
                "highest_rebound_pct": event.get(
                    "highest_rebound_pct", base.get("highest_rebound_pct", 0.0)
                ),
                "waiting_seconds": event.get("waiting_seconds", base.get("waiting_seconds")),
                "reason": event.get("reason"),
                "signal": event.get("signal") or base.get("signal") or {},
            })
            outcomes.append(outcome)
            active.pop(symbol, None)

    created_count = sum(
        1 for event in rebound_events
        if event.get("event_type") == "PENDING_REBOUND_CREATED"
    )
    confirmed = [x for x in outcomes if x.get("event_type") == "REBOUND_CONFIRMED"]
    cancelled = [
        x for x in outcomes
        if x.get("event_type") == "PENDING_REBOUND_CANCELLED_NOT_QUALIFIED"
    ]
    cutoff = [
        x for x in outcomes
        if x.get("event_type") == "PENDING_REBOUND_CANCELLED_ENTRY_CUTOFF"
    ]
    timeout = [x for x in outcomes if x.get("event_type") == "PENDING_REBOUND_TIMEOUT"]
    completed_count = len(outcomes)
    confirmation_rate = (
        len(confirmed) / completed_count * 100.0 if completed_count else 0.0
    )
    delays = [
        _safe_float(x.get("waiting_seconds"))
        for x in confirmed
        if _safe_float(x.get("waiting_seconds")) is not None
    ]

    stats = {
        "created": created_count,
        "active": len(active),
        "completed": completed_count,
        "confirmed": len(confirmed),
        "cancelled_not_qualified": len(cancelled),
        "entry_cutoff": len(cutoff),
        "timeout": len(timeout),
        "confirmation_rate": confirmation_rate,
        "average_confirmation_seconds": sum(delays) / len(delays) if delays else None,
    }
    return list(active.values()), outcomes, stats


def pending_rebound_lines(active_candidates):
    if not active_candidates:
        return ["None"]
    lines = []
    for row in sorted(
        active_candidates,
        key=lambda x: str(x.get("created_at", "")),
        reverse=True,
    ):
        sig = row.get("signal", {}) or {}
        lines.append(
            f"{row.get('created_at')} | {row.get('symbol')} | "
            f"drop={_safe_float(sig.get('flash_drop_pct'), 0.0):.2f}% | "
            f"pre_ret={_safe_float(sig.get('pre_return_pct'), 0.0):.2f}% | "
            f"pre_slope={_safe_float(sig.get('pre_slope_pct_per_hour'), 0.0):.2f}%/hr | "
            f"current={_safe_float(row.get('current_price'), 0.0):.2f} | "
            f"running_low={_safe_float(row.get('lowest_price'), 0.0):.2f} | "
            f"rebound={_safe_float(row.get('rebound_pct'), 0.0):.3f}% | "
            f"required={_safe_float(row.get('required_rebound_pct'), REBOUND_CONFIRMATION_PCT * 100):.3f}% | "
            f"age={_safe_float(row.get('waiting_seconds'), 0.0):.1f}s"
            + _volume_suffix(sig)
        )
    return lines


def rebound_outcome_lines(outcomes, max_items=5):
    if not outcomes:
        return ["None"]
    labels = {
        "REBOUND_CONFIRMED": "CONFIRMED",
        "PENDING_REBOUND_CANCELLED_NOT_QUALIFIED": "FAILED_NOT_QUALIFIED",
        "PENDING_REBOUND_CANCELLED_ENTRY_CUTOFF": "FAILED_ENTRY_CUTOFF",
        "PENDING_REBOUND_TIMEOUT": "FAILED_TIMEOUT",
    }
    lines = []
    for row in sorted(
        outcomes,
        key=lambda x: str(x.get("finished_at", "")),
        reverse=True,
    )[:max_items]:
        sig = row.get("signal", {}) or {}
        lines.append(
            f"{row.get('finished_at')} | {row.get('symbol')} | "
            f"outcome={labels.get(row.get('event_type'), row.get('event_type'))} | "
            f"reason={row.get('reason') or 'none'} | "
            f"drop={_safe_float(sig.get('flash_drop_pct'), 0.0):.2f}% | "
            f"low={_safe_float(row.get('lowest_price'), 0.0):.2f} | "
            f"final_rebound={_safe_float(row.get('rebound_pct'), 0.0):.3f}% | "
            f"max_rebound={_safe_float(row.get('highest_rebound_pct'), 0.0):.3f}% | "
            f"wait={_safe_float(row.get('waiting_seconds'), 0.0):.1f}s"
            + _volume_suffix(sig)
        )
    return lines


def rebound_summary_lines(stats):
    avg = stats.get("average_confirmation_seconds")
    return [
        f"Pending created today: {stats.get('created', 0)}",
        f"Currently pending: {stats.get('active', 0)}",
        f"Completed outcomes: {stats.get('completed', 0)}",
        f"Confirmed: {stats.get('confirmed', 0)}",
        f"Failed — no longer qualified: {stats.get('cancelled_not_qualified', 0)}",
        f"Failed — entry cutoff: {stats.get('entry_cutoff', 0)}",
        f"Failed — timeout: {stats.get('timeout', 0)}",
        f"Confirmation rate among completed: {stats.get('confirmation_rate', 0.0):.1f}%",
        f"Average confirmation delay: {avg:.1f}s" if avg is not None else "Average confirmation delay: n/a",
    ]


def _market_date_iso(value):
    """Return YYYY-MM-DD in America/New_York for an ISO timestamp."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(ZoneInfo("America/New_York")).date().isoformat()
    except Exception:
        # Existing ledger timestamps begin with an ISO date. This fallback keeps
        # malformed historical rows readable while avoiding last-update dates.
        text = str(value)
        return text[:10] if len(text) >= 10 else None




_PAPER_DAY_RECORD_CACHE = {}

def _paper_day_records(path, day):
    """Read and deduplicate one ledger day, cached by file modification time.

    The current paper summary and live deployment table share this exact data,
    avoiding a second full JSONL parse during the same writer cycle.
    """
    try:
        modified_ns = path.stat().st_mtime_ns if path.exists() else -1
    except Exception:
        modified_ns = -1
    key = (str(path), str(day), modified_ns)
    cached = _PAPER_DAY_RECORD_CACHE.get(key)
    if cached is not None:
        return cached

    records = {}
    if path.exists():
        try:
            with path.open() as source:
                for raw in source:
                    try:
                        record = json.loads(raw)
                    except Exception:
                        continue
                    trade_timestamp = str(
                        record.get("detected_at")
                        or record.get("signal_time")
                        or record.get("entry_time")
                        or record.get("confirmation_time")
                        or record.get("timestamp")
                        or ""
                    )
                    if _market_date_iso(trade_timestamp) != day:
                        continue
                    record_key = record.get("key") or (
                        trade_timestamp, record.get("symbol"), record.get("strategy_id")
                    )
                    records[str(record_key)] = record
        except Exception:
            records = {}

    # Keep only the newest cache entry per path/day and cap total growth.
    for old_key in list(_PAPER_DAY_RECORD_CACHE):
        if old_key[:2] == key[:2] and old_key != key:
            _PAPER_DAY_RECORD_CACHE.pop(old_key, None)
    _PAPER_DAY_RECORD_CACHE[key] = records
    if len(_PAPER_DAY_RECORD_CACHE) > 150:
        for old_key in list(_PAPER_DAY_RECORD_CACHE)[:50]:
            _PAPER_DAY_RECORD_CACHE.pop(old_key, None)
    return records


def universe_performance_lines(today):
    """Summarize closed paper outcomes by universe membership."""

    buckets = {}

    for label, path in _paper_series_definitions():
        if not path.exists():
            continue

        try:
            rows = path.read_text().splitlines()
        except Exception:
            continue

        for line in rows:
            try:
                rec = json.loads(line)
            except Exception:
                continue

            if rec.get("date") != today:
                continue

            tags = rec.get("universe_memberships", [])
            if not isinstance(tags, list):
                continue

            pnl = float(rec.get("pnl_usd", 0) or 0)

            for tag in tags:
                key = (label, tag)

                if key not in buckets:
                    buckets[key] = {
                        "trades": 0,
                        "wins": 0,
                        "pnl": 0.0,
                    }

                buckets[key]["trades"] += 1
                buckets[key]["pnl"] += pnl

                if pnl > 0:
                    buckets[key]["wins"] += 1

    if not buckets:
        return [
            "",
            "UNIVERSE PERFORMANCE BREAKDOWN",
            "No tagged outcomes yet.",
        ]

    lines = [
        "",
        "UNIVERSE PERFORMANCE BREAKDOWN",
        "",
    ]

    for (strategy, tag), data in sorted(buckets.items()):
        trades = data["trades"]
        win_rate = (data["wins"] / trades * 100) if trades else 0

        lines.append(
            f"{strategy} | {tag} | "
            f"trades={trades} "
            f"win_rate={win_rate:.1f}% "
            f"P/L_on_$1000={data['pnl']:+.2f}"
        )

    return lines


def _paper_pnl_stats(path, today):
    """Summarize today's closed and currently marked open paper P/L."""
    stats = {
        "trades": 0, "closed": 0, "open_marked": 0, "open_unavailable": 0,
        "closed_pnl": 0.0, "open_pnl": 0.0,
    }
    records = _paper_day_records(path, today)
    for record in records.values():
        stats["trades"] += 1
        if record.get("status") == "closed":
            pnl = _safe_float(record.get("pnl_usd"))
            if pnl is not None:
                stats["closed_pnl"] += pnl
            stats["closed"] += 1
        else:
            pnl = _safe_float(record.get("current_pnl_usd"))
            if pnl is None:
                stats["open_unavailable"] += 1
            else:
                stats["open_marked"] += 1
                stats["open_pnl"] += pnl
    return stats


def _event_after_start(event, start_utc=STRATEGY_LS_FORWARD_START_UTC):
    try:
        ts = datetime.fromisoformat(str(event.get("timestamp")).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc) >= datetime.fromisoformat(start_utc).astimezone(timezone.utc)
    except Exception:
        return False


def _load_symbol_tape(day, symbols):
    try:
        import pandas as pd
        path = Path("/data/tapes") / f"quotes_{day.replace('-', '')}.csv"
        if not path.exists():
            return None
        parts = []
        wanted = {str(x) for x in symbols}
        for chunk in pd.read_csv(path, usecols=["timestamp_utc", "symbol", "last_price"], dtype={"symbol":"string"}, chunksize=50000):
            chunk = chunk[chunk["symbol"].astype(str).isin(wanted)]
            if not chunk.empty:
                parts.append(chunk)
        if not parts:
            return None
        df = pd.concat(parts, ignore_index=True).rename(columns={"timestamp_utc":"timestamp", "last_price":"price"})
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
        df["price"] = pd.to_numeric(df["price"], errors="coerce")
        return df.dropna(subset=["timestamp","symbol","price"]).sort_values("timestamp")
    except Exception:
        return None


def _market_confirmed_at(timestamp):
    try:
        import pandas as pd
        ts = pd.Timestamp(timestamp)
        ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
        df = _load_symbol_tape(ts.strftime("%Y-%m-%d"), {"SPY", "QQQ"})
        if df is None or df.empty:
            return False, None
        best = None
        for symbol in ("SPY", "QQQ"):
            sdf = df[(df["symbol"].astype(str) == symbol) & (df["timestamp"] <= ts)].tail(400)
            if len(sdf) < 3:
                continue
            latest = float(sdf.iloc[-1]["price"])
            one_cut = ts - pd.Timedelta(minutes=1)
            five_cut = ts - pd.Timedelta(minutes=5)
            p1_rows = sdf[sdf["timestamp"] <= one_cut]
            p5_rows = sdf[sdf["timestamp"] <= five_cut]
            if p1_rows.empty or p5_rows.empty:
                continue
            ret1 = (latest / float(p1_rows.iloc[-1]["price"]) - 1) * 100
            ret5 = (latest / float(p5_rows.iloc[-1]["price"]) - 1) * 100
            candidate = {"symbol":symbol, "market_1m_return_pct":ret1, "market_5m_return_pct":ret5}
            if best is None or ret5 > best["market_5m_return_pct"]:
                best = candidate
        if best is None:
            return False, None
        ok = best["market_5m_return_pct"] >= -STRATEGY_S_MAX_MARKET_5M_LOSS_PCT and best["market_1m_return_pct"] >= STRATEGY_S_MIN_MARKET_1M_RETURN_PCT
        return ok, best
    except Exception:
        return False, None


def strategy_ls_eligible_events(source_events, variant):
    variant = str(variant).upper()
    out = []
    for event in source_events:
        if not _event_after_start(event) or not is_rth_timestamp(event.get("timestamp")):
            continue
        sig = event.get("signal", {}) or {}
        try:
            ok = False
            extra = {}
            if variant == "L":
                flash = float(sig.get("flash_volume_ratio"))
                rebound = float(sig.get("rebound_volume_ratio"))
                ok = flash >= STRATEGY_L_MIN_FLASH_VOL_RATIO and rebound <= flash * STRATEGY_L_MAX_REBOUND_TO_FLASH_RATIO
            elif variant == "M":
                ok = float(sig.get("distance_below_rolling_vwap_pct")) >= STRATEGY_M_MIN_DISTANCE_BELOW_VWAP_PCT
            elif variant == "P":
                ok = float(sig.get("pre_return_pct")) >= STRATEGY_P_MIN_PRE_RETURN_PCT and float(sig.get("pre_r2")) >= STRATEGY_P_MIN_PRE_R2
            elif variant == "Q":
                std = float(sig.get("pre30_return_std_pct"))
                units = float(sig.get("flash_drop_pct")) / std if std > 0 else 0.0
                ok = units >= STRATEGY_Q_MIN_VOLATILITY_UNITS
                extra["flash_drop_volatility_units"] = units
            elif variant == "R":
                ts = datetime.fromisoformat(str(event.get("timestamp")).replace("Z", "+00:00"))
                if ts.tzinfo is None: ts = ts.replace(tzinfo=timezone.utc)
                et = ts.astimezone(NY_TZ)
                ok = et.hour * 60 + et.minute < STRATEGY_R_END_MINUTE_ET
            elif variant == "S":
                ok, market = _market_confirmed_at(event.get("timestamp"))
                if market: extra.update(market)
            else:
                ok = True
            if ok:
                copied = dict(event)
                copied["signal"] = dict(sig)
                copied["signal"].update(extra)
                out.append(copied)
        except (TypeError, ValueError):
            continue
    return out


def strategy_dynamic_variant_lines(source_events, variant, max_items=5):
    """N adaptive trail and O second-leg entry; quote-path simulation is forward-only."""
    try:
        import pandas as pd
    except Exception as exc:
        return [f"unavailable: {type(exc).__name__}: {exc}"]
    variant = str(variant).upper()
    path = STRATEGY_LS_PATHS[variant]
    outcomes = load_trigger_outcomes(path)
    eligible = [e for e in source_events if _event_after_start(e) and is_rth_timestamp(e.get("timestamp"))]
    for event in eligible:
        sig = event.get("signal", {}) or {}
        source_key = trigger_key(event, "A")
        key = f"{variant}|{source_key}"
        if key in outcomes: continue
        try:
            entry = float(sig["entry_price"]); target = float(sig["target_price"])
            outcomes[key] = {"key":key,"strategy_id":variant,"timestamp":event.get("timestamp"),"symbol":event.get("symbol"),"source_entry":entry,"entry":entry,"target":target,"stop":float(sig.get("stop_price", entry*0.95)),"status":"open","paper_notional":1000.0,"highest_price":entry,"lowest_price":entry}
        except Exception:
            continue
    wanted = {}
    for rec in outcomes.values():
        if rec.get("status") != "closed": wanted.setdefault(str(rec.get("timestamp"))[:10], set()).add(rec.get("symbol"))
    tapes = {day:_load_symbol_tape(day, syms) for day,syms in wanted.items()}
    for rec in outcomes.values():
        if rec.get("status") == "closed": continue
        try:
            ts=pd.Timestamp(rec["timestamp"]); ts=ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
            df=tapes.get(ts.strftime("%Y-%m-%d"));
            if df is None: continue
            sdf=df[(df["symbol"].astype(str)==str(rec["symbol"])) & (df["timestamp"]>=ts)].sort_values("timestamp")
            if sdf.empty: continue
            entry=float(rec["entry"]); target=float(rec["target"]); stop=float(rec["stop"])
            high=entry; low=entry; activated=False; pullback_low=None; entered=(variant=="N"); exit_row=None; reason=None
            for _,row in sdf.iterrows():
                px=float(row["price"]); et=row["timestamp"].tz_convert(NY_TZ)
                if variant=="N":
                    high=max(high,px); low=min(low,px)
                    if px >= target: exit_row,reason=row,"target"; break
                    if px <= stop: exit_row,reason=row,"stop"; break
                    if px >= entry*(1+STRATEGY_N_ACTIVATION_GAIN_PCT/100): activated=True
                    if activated and px <= high*(1-STRATEGY_N_TRAIL_FROM_HIGH_PCT/100): exit_row,reason=row,"adaptive_trail"; break
                else:
                    if not entered:
                        high=max(high,px)
                        if pullback_low is None and high>entry and px <= high*(1-STRATEGY_O_PULLBACK_FROM_FIRST_HIGH_PCT/100):
                            pullback_low=px
                        elif pullback_low is not None:
                            pullback_low=min(pullback_low,px)
                            if px >= pullback_low*(1+STRATEGY_O_REBOUND_FROM_PULLBACK_LOW_PCT/100):
                                entered=True; entry=px; target=max(float(rec["target"]), entry*1.002); stop=entry*(1-STRATEGY_O_STOP_LOSS_FRACTION)
                                rec["entry"]=entry; rec["target"]=target; rec["stop"]=stop; rec["second_leg_entry_time"]=str(row["timestamp"]); high=entry; low=entry
                                continue
                    else:
                        high=max(high,px); low=min(low,px)
                        if px >= target: exit_row,reason=row,"target"; break
                        if px <= stop: exit_row,reason=row,"stop"; break
                if (et.hour,et.minute)>=(15,55):
                    exit_row=row; reason="end" if entered else "no_second_leg"; break
            rec.update({"highest_price":high,"lowest_price":low,"mfe_pct":(high/entry-1)*100 if entered else 0.0,"mae_pct":(low/entry-1)*100 if entered else 0.0,"last_checked":datetime.now(timezone.utc).isoformat()})
            if exit_row is not None:
                if reason == "no_second_leg":
                    exit_price=entry; ret=0.0
                else:
                    exit_price=target if reason=="target" else stop if reason=="stop" else float(exit_row["price"])
                    ret=(exit_price/entry-1)*100
                rec.update({"status":"closed","exit_time":str(exit_row["timestamp"]),"exit_price":exit_price,"exit_reason":reason,"ret_pct":ret,"pnl_usd":10*ret})
        except Exception:
            continue
    save_trigger_outcomes(outcomes,path)
    rows=sorted(outcomes.values(),key=lambda x:str(x.get("timestamp")),reverse=True)[:max_items]
    if not rows:return ["None"]
    return [f"{x.get('timestamp')} | {x.get('symbol')} | entry={float(x.get('entry',0)):.2f} | status={x.get('status')} | reason={x.get('exit_reason') or 'open'} | return={float(x.get('ret_pct',0) or 0):+.2f}% | P/L_on_$1000={float(x.get('pnl_usd',0) or 0):+.2f}" for x in rows]


def current_pnl_summary_lines(today):
    """Render one compact current P/L table across every paper strategy."""
    series = _paper_series_definitions()

    lines = [
        f"CURRENT PAPER P/L SUMMARY — US MARKET DATE {today}",
        "One market day only; trades are assigned by original detection/entry time in America/New_York.",
        "Basis: $1,000 per paper trade; closed realized P/L plus latest mark for open trades.",
    ]
    grand_total = 0.0
    grand_trades = 0
    grand_unavailable = 0

    for label, path in series:
        stats = _paper_pnl_stats(path, today)
        total = stats["closed_pnl"] + stats["open_pnl"]
        grand_total += total
        grand_trades += stats["trades"]
        grand_unavailable += stats["open_unavailable"]
        lines.append(
            f"{label}: current_total_P/L={total:+.2f} | "
            f"closed={stats['closed']} ({stats['closed_pnl']:+.2f}) | "
            f"open_marked={stats['open_marked']} ({stats['open_pnl']:+.2f}) | "
            f"open_unavailable={stats['open_unavailable']} | trades={stats['trades']}"
        )

    if grand_trades:
        lines.append(
            f"ALL PAPER SERIES: current_total_P/L={grand_total:+.2f} | "
            f"trades={grand_trades} | open_unavailable={grand_unavailable}"
        )
        lines.append(
            "Note: the all-series total combines overlapping research variants and is not a deployable portfolio P/L."
        )
    else:
        lines.append("No paper outcomes recorded today.")

    lines.extend(universe_performance_lines(today))

    return lines



def _paper_series_definitions():
    """Return the ordered paper series used by both summary tables."""
    return [
        ("A signal", SIGNAL_PAPER_OUTCOMES_JSONL),
        ("A near miss", NEAR_MISS_PAPER_JSONL),
        ("B signal", SIGNAL_PAPER_OUTCOMES_B_JSONL),
        ("B near miss", NEAR_MISS_PAPER_B_JSONL),
        ("C1 signal", SIGNAL_PAPER_OUTCOMES_C1_JSONL),
        ("C1 near miss", NEAR_MISS_PAPER_C1_JSONL),
        ("C2 signal", SIGNAL_PAPER_OUTCOMES_C2_JSONL),
        ("C2 near miss", NEAR_MISS_PAPER_C2_JSONL),
        ("C3 signal", SIGNAL_PAPER_OUTCOMES_C3_JSONL),
        ("C3 near miss", NEAR_MISS_PAPER_C3_JSONL),
        ("C4 signal", SIGNAL_PAPER_OUTCOMES_C4_JSONL),
        ("C4 near miss", NEAR_MISS_PAPER_C4_JSONL),
        ("D signal", SIGNAL_PAPER_OUTCOMES_D_JSONL),
        ("D near miss", NEAR_MISS_PAPER_D_JSONL),
        ("E signal", SIGNAL_PAPER_OUTCOMES_E_JSONL),
        ("E near miss", NEAR_MISS_PAPER_E_JSONL),
        ("F signal", SIGNAL_PAPER_OUTCOMES_F_JSONL),
        ("F near miss", NEAR_MISS_PAPER_F_JSONL),
        ("G signal", SIGNAL_PAPER_OUTCOMES_G_JSONL),
        ("G near miss", NEAR_MISS_PAPER_G_JSONL),
        ("H signal", SIGNAL_PAPER_OUTCOMES_H_JSONL),
        ("H near miss", NEAR_MISS_PAPER_H_JSONL),
        ("I signal", SIGNAL_PAPER_OUTCOMES_I_JSONL),
        ("J1 signal", SIGNAL_PAPER_OUTCOMES_J1_JSONL),
        ("J2 signal", SIGNAL_PAPER_OUTCOMES_J2_JSONL),
        ("J3 signal", SIGNAL_PAPER_OUTCOMES_J3_JSONL),
        ("J4 signal", SIGNAL_PAPER_OUTCOMES_J4_JSONL),
        ("J5 signal", SIGNAL_PAPER_OUTCOMES_J5_JSONL),
        ("J6 signal", SIGNAL_PAPER_OUTCOMES_J6_JSONL),
        ("K1 signal", SIGNAL_PAPER_OUTCOMES_K1_JSONL),
        ("K2 signal", SIGNAL_PAPER_OUTCOMES_K2_JSONL),
        ("K3 signal", SIGNAL_PAPER_OUTCOMES_K3_JSONL),
        ("K4 signal", SIGNAL_PAPER_OUTCOMES_K4_JSONL),
        ("K5 signal", SIGNAL_PAPER_OUTCOMES_K5_JSONL),
        ("K6 signal", SIGNAL_PAPER_OUTCOMES_K6_JSONL),
        ("K7 signal", SIGNAL_PAPER_OUTCOMES_K7_JSONL),
        ("K8 signal", SIGNAL_PAPER_OUTCOMES_K8_JSONL),
        ("K9 signal", SIGNAL_PAPER_OUTCOMES_K9_JSONL),
        ("L signal", SIGNAL_PAPER_OUTCOMES_L_JSONL),
        ("M signal", SIGNAL_PAPER_OUTCOMES_M_JSONL),
        ("N signal", SIGNAL_PAPER_OUTCOMES_N_JSONL),
        ("O signal", SIGNAL_PAPER_OUTCOMES_O_JSONL),
        ("P signal", SIGNAL_PAPER_OUTCOMES_P_JSONL),
        ("Q signal", SIGNAL_PAPER_OUTCOMES_Q_JSONL),
        ("R signal", SIGNAL_PAPER_OUTCOMES_R_JSONL),
        ("S signal", SIGNAL_PAPER_OUTCOMES_S_JSONL),
        ("TF1 signal", SIGNAL_PAPER_OUTCOMES_TF1_JSONL),
        ("BO1 signal", SIGNAL_PAPER_OUTCOMES_BO1_JSONL),
        ("OR1 signal", SIGNAL_PAPER_OUTCOMES_OR1_JSONL),
        ("RS1 signal", SIGNAL_PAPER_OUTCOMES_RS1_JSONL),
        ("RS2 signal", SIGNAL_PAPER_OUTCOMES_RS2_JSONL),
        ("VE1 signal", SIGNAL_PAPER_OUTCOMES_VE1_JSONL),
        ("VR1 signal", SIGNAL_PAPER_OUTCOMES_VR1_JSONL),
        ("M1 signal", SIGNAL_PAPER_OUTCOMES_M1_JSONL),
        ("M2 signal", SIGNAL_PAPER_OUTCOMES_M2_JSONL),
        ("M3 signal", SIGNAL_PAPER_OUTCOMES_M3_JSONL),
        ("RS3 signal", SIGNAL_PAPER_OUTCOMES_RS3_JSONL),
        ("MC1 signal", SIGNAL_PAPER_OUTCOMES_MC1_JSONL),
        ("TL1 signal", SIGNAL_PAPER_OUTCOMES_TL1_JSONL),
        ("AV1 signal", SIGNAL_PAPER_OUTCOMES_AV1_JSONL),
        ("TD1 signal", SIGNAL_PAPER_OUTCOMES_TD1_JSONL),
        ("SH1 signal", SIGNAL_PAPER_OUTCOMES_SH1_JSONL),
        ("CV1 signal", SIGNAL_PAPER_OUTCOMES_CV1_JSONL),
        ("HL1 signal", SIGNAL_PAPER_OUTCOMES_HL1_JSONL),
        ("VT1 signal", SIGNAL_PAPER_OUTCOMES_VT1_JSONL),
        ("PD1 signal", SIGNAL_PAPER_OUTCOMES_PD1_JSONL),
        ("EMA1 signal", SIGNAL_PAPER_OUTCOMES_EMA1_JSONL),
        ("EMA2 signal", SIGNAL_PAPER_OUTCOMES_EMA2_JSONL),
        ("EMA3 signal", SIGNAL_PAPER_OUTCOMES_EMA3_JSONL),
        ("SMA1 signal", SIGNAL_PAPER_OUTCOMES_SMA1_JSONL),
        ("VWEMA1 signal", SIGNAL_PAPER_OUTCOMES_VWEMA1_JSONL),
        ("GE1 signal", SIGNAL_PAPER_OUTCOMES_GE1_JSONL),
        ("GM1 signal", SIGNAL_PAPER_OUTCOMES_GM1_JSONL),
        ("GP1 signal", SIGNAL_PAPER_OUTCOMES_GP1_JSONL),
        ("GR1 signal", SIGNAL_PAPER_OUTCOMES_GR1_JSONL),
        ("GT1 signal", SIGNAL_PAPER_OUTCOMES_GT1_JSONL),
    ]


def _strategy_signal_series_definitions():
    """Return exactly one outcome series for each of the 65 strategies."""
    return [
        (label.removesuffix(" signal"), path)
        for label, path in _paper_series_definitions()
        if label.endswith(" signal")
    ]


LIVE_DEPLOYMENT_ACCOUNT_SIZE = 5000.0
LIVE_DEPLOYMENT_POSITION_SIZE = 1000.0
LIVE_DEPLOYMENT_SLOTS = int(LIVE_DEPLOYMENT_ACCOUNT_SIZE // LIVE_DEPLOYMENT_POSITION_SIZE)


def _parse_utc_timestamp(value):
    """Parse a stored timestamp into an aware UTC datetime, or return None."""
    try:
        ts = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)
    except Exception:
        return None


def _final_live_deployment_pnl(path, day, slots=LIVE_DEPLOYMENT_SLOTS):
    """Simulate one finalized market day using reusable fixed-size slots.

    Trades are considered in entry-time order. A trade is accepted when fewer
    than ``slots`` previously accepted trades remain open. Accepted capital is
    released at the recorded exit time. Only closed trades are used because this
    function feeds the durable final-history table.

    Returns None when the series has no trades or any trade for the day remains
    open/unavailable, so an incomplete session is never persisted as final.
    """
    records = _paper_day_records(path, day)
    trades = []
    for ordinal, rec in enumerate(records.values()):
        entry_time = _parse_utc_timestamp(rec.get("timestamp"))
        if entry_time is None or entry_time.astimezone(NY_TZ).date().isoformat() != day:
            continue
        if rec.get("status") != "closed":
            return None
        exit_time = _parse_utc_timestamp(rec.get("exit_time"))
        pnl = rec.get("pnl_usd")
        if exit_time is None or pnl is None:
            return None
        try:
            trades.append((entry_time, ordinal, exit_time, float(pnl)))
        except (TypeError, ValueError):
            return None

    if not trades:
        return None

    trades.sort(key=lambda item: (item[0], item[1]))
    active_exits = []
    simulated_pnl = 0.0
    for entry_time, _, exit_time, pnl in trades:
        while active_exits and active_exits[0] <= entry_time:
            heapq.heappop(active_exits)
        if len(active_exits) >= slots:
            continue
        heapq.heappush(active_exits, exit_time)
        simulated_pnl += pnl
    return round(simulated_pnl, 8)


def _load_daily_live_deployment_history():
    if not DAILY_LIVE_DEPLOYMENT_HISTORY_JSON.exists():
        return {}
    try:
        data = json.loads(DAILY_LIVE_DEPLOYMENT_HISTORY_JSON.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_daily_live_deployment_history(history):
    try:
        DAILY_LIVE_DEPLOYMENT_HISTORY_JSON.parent.mkdir(parents=True, exist_ok=True)
        tmp = DAILY_LIVE_DEPLOYMENT_HISTORY_JSON.with_suffix(".tmp")
        tmp.write_text(json.dumps(history, indent=2, sort_keys=True) + "\n")
        tmp.replace(DAILY_LIVE_DEPLOYMENT_HISTORY_JSON)
        return True
    except Exception:
        return False


def _final_daily_live_deployment_snapshot(day):
    """Build a completed $5k deployment snapshot for one market date."""
    snapshot = {}
    any_trades = False
    for label, path in _paper_series_definitions():
        stats = _paper_pnl_stats(path, day)
        if not stats["trades"]:
            snapshot[label] = None
            continue
        any_trades = True
        if stats["open_marked"] or stats["open_unavailable"]:
            return None
        value = _final_live_deployment_pnl(path, day)
        if value is None:
            return None
        snapshot[label] = value
    return snapshot if any_trades else None


def update_daily_live_deployment_history(today):
    """Persist one final $5k deployment result per completed market day.

    Once a date has been saved, normal 30-second writer cycles only read the
    small JSON history file; they do not replay every trade again.
    """
    history = _load_daily_live_deployment_history()
    if not _market_is_closed_now():
        return history

    market_today = datetime.now(timezone.utc).astimezone(NY_TZ).date().isoformat()
    if today != market_today:
        today = market_today
    if today in history:
        return history

    snapshot = _final_daily_live_deployment_snapshot(today)
    if snapshot is not None:
        history[today] = snapshot
        _save_daily_live_deployment_history(history)
    return history



def _live_record_times(record, now_utc):
    entry = _parse_utc_timestamp(
        record.get("detected_at") or record.get("signal_time") or
        record.get("entry_time") or record.get("confirmation_time") or
        record.get("timestamp")
    )
    if entry is None:
        return None, None
    if record.get("status") == "closed":
        release = _parse_utc_timestamp(
            record.get("exit_time") or record.get("closed_at") or record.get("outcome_time")
        )
        if release is None or release < entry:
            release = entry
    else:
        release = max(now_utc, entry)
    return entry, release


def _live_record_pnl(record):
    if record.get("status") == "closed":
        value = record.get("pnl_usd")
    else:
        value = record.get("current_pnl_usd")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _live_time_weighted_concurrency(intervals):
    if not intervals:
        return 0.0, 0
    events = []
    for start, end in intervals:
        events.append((start, 1))
        events.append((end, -1))
    events.sort(key=lambda item: (item[0], item[1]))
    current = peak = 0
    weighted = 0.0
    previous = events[0][0]
    for timestamp, delta in events:
        weighted += current * max(0.0, (timestamp - previous).total_seconds())
        current += delta
        peak = max(peak, current)
        previous = timestamp
    span = max(0.0, (events[-1][0] - events[0][0]).total_seconds())
    return (weighted / span if span else float(peak)), peak


def _current_live_deployment(path, day, slots=LIVE_DEPLOYMENT_SLOTS):
    now_utc = datetime.now(timezone.utc)
    records = _paper_day_records(path, day)
    prepared = []
    intervals = []
    unavailable = 0
    for ordinal, record in enumerate(records.values()):
        entry, release = _live_record_times(record, now_utc)
        if entry is None or release is None or entry.astimezone(NY_TZ).date().isoformat() != day:
            continue
        pnl = _live_record_pnl(record)
        if record.get("status") != "closed" and pnl is None:
            unavailable += 1
        prepared.append((entry, ordinal, release, record, pnl))
        intervals.append((entry, release))
    prepared.sort(key=lambda item: (item[0], item[1]))
    active = []
    accepted = skipped = 0
    live_pnl = 0.0
    for entry, _, release, record, pnl in prepared:
        while active and active[0] <= entry:
            heapq.heappop(active)
        if len(active) >= slots:
            skipped += 1
            continue
        accepted += 1
        heapq.heappush(active, release)
        if pnl is not None:
            live_pnl += pnl
    avg_open, max_open = _live_time_weighted_concurrency(intervals)
    total = len(prepared)
    return {
        "trades": total,
        "accepted": accepted,
        "skipped": skipped,
        "capture_pct": (accepted / total * 100.0) if total else 0.0,
        "live_pnl": live_pnl,
        "average_open": avg_open,
        "max_open": max_open,
        "open_unavailable": unavailable,
    }


def live_deployment_summary_lines(day):
    cache_key = str(day)
    cached = _LIVE_DEPLOYMENT_RESULT_CACHE.get(cache_key)
    if cached is not None:
        return cached

    rows = []
    for label, path in _paper_series_definitions():
        paper = _paper_pnl_stats(path, day)
        deployment = _current_live_deployment(path, day)
        paper_pnl = paper["closed_pnl"] + paper["open_pnl"]
        rows.append((label, paper_pnl, deployment))
    rows.sort(key=lambda item: (item[2]["live_pnl"], item[1]), reverse=True)
    lines = [
        f"LIVE DEPLOYMENT SIMULATION — US MARKET DATE {day}",
        f"Account=${LIVE_DEPLOYMENT_ACCOUNT_SIZE:,.0f} | position=${LIVE_DEPLOYMENT_POSITION_SIZE:,.0f} | reusable_slots={LIVE_DEPLOYMENT_SLOTS} | each strategy simulated independently.",
        "Open accepted trades use current marked P/L and continue occupying a slot. No slippage, spread, or execution failures included.",
        "Strategy                  Paper P/L   $5k P/L  Capture  Taken/All  Skipped  AvgOpen  MaxOpen",
        "------------------------  ----------  --------  -------  ---------  -------  -------  -------",
    ]
    any_unavailable = False
    for label, paper_pnl, d in rows:
        marker = "*" if d["open_unavailable"] else ""
        any_unavailable = any_unavailable or bool(marker)
        lines.append(
            f"{label[:24]:<24}  {paper_pnl:+10.2f}  {d['live_pnl']:+8.2f}{marker}  "
            f"{d['capture_pct']:6.1f}%  {d['accepted']:>4}/{d['trades']:<4}  "
            f"{d['skipped']:>7}  {d['average_open']:>7.2f}  {d['max_open']:>7}"
        )
    if any_unavailable:
        lines.append("* One or more open trades lacked a current mark; simulated P/L excludes those unavailable marks.")
    _LIVE_DEPLOYMENT_RESULT_CACHE[cache_key] = lines
    if len(_LIVE_DEPLOYMENT_RESULT_CACHE) > 10:
        _LIVE_DEPLOYMENT_RESULT_CACHE.pop(next(iter(_LIVE_DEPLOYMENT_RESULT_CACHE)))
    return lines

def daily_live_deployment_history_lines(today, max_days=10):
    """Render the persistent strategy-by-day $5k deployment matrix."""
    history = update_daily_live_deployment_history(today)
    days = sorted(history.keys())[-max_days:]
    series = _paper_series_definitions()
    lines = [
        "DAILY LIVE DEPLOYMENT HISTORY — FINAL CLOSED OUTCOMES ($5,000 ACCOUNT)",
        "Five reusable $1,000 slots; each strategy simulated independently; no spread, slippage, or execution failures.",
        f"Persistent source: {DAILY_LIVE_DEPLOYMENT_HISTORY_JSON}",
    ]
    if not days:
        lines.append("No completed market days have been saved yet.")
        return lines

    row_width = max(18, max(len(label) for label, _ in series) + 2)
    col_width = 12
    header = f"{'Strategy':<{row_width}}" + "".join(
        f"{day[5:]:>{col_width}}" for day in days
    )
    divider = "-" * len(header)
    lines.extend([header, divider])
    for label, _ in series:
        if not any(history.get(day, {}).get(label) is not None for day in days):
            continue
        cells = []
        for day in days:
            value = history.get(day, {}).get(label)
            cells.append(
                f"{'—':>{col_width}}" if value is None
                else f"{float(value):+{col_width}.2f}"
            )
        lines.append(f"{label:<{row_width}}" + "".join(cells))
    lines.append(divider)
    return lines


def _load_daily_pnl_history():
    """Load the durable end-of-day P/L matrix from disk."""
    if not DAILY_PNL_HISTORY_JSON.exists():
        return {}
    try:
        data = json.loads(DAILY_PNL_HISTORY_JSON.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_daily_pnl_history(history):
    """Atomically save the durable end-of-day P/L matrix."""
    try:
        DAILY_PNL_HISTORY_JSON.parent.mkdir(parents=True, exist_ok=True)
        tmp = DAILY_PNL_HISTORY_JSON.with_suffix(".tmp")
        tmp.write_text(json.dumps(history, indent=2, sort_keys=True) + "\n")
        tmp.replace(DAILY_PNL_HISTORY_JSON)
        return True
    except Exception:
        return False


def _market_is_closed_now():
    """True after 16:00 America/New_York on a weekday."""
    now_et = datetime.now(timezone.utc).astimezone(NY_TZ)
    return now_et.weekday() < 5 and (now_et.hour, now_et.minute) >= (16, 0)


def _final_daily_pnl_snapshot(day):
    """Build one final closed-outcome snapshot for a US market date.

    Returns None while any recorded paper trade for the date remains open.
    Series with no trades are stored as null so the rendered table shows a dash.
    """
    snapshot = {}
    any_trades = False
    any_open = False

    for label, path in _paper_series_definitions():
        stats = _paper_pnl_stats(path, day)
        if not stats["trades"]:
            snapshot[label] = None
            continue
        any_trades = True
        if stats["open_marked"] or stats["open_unavailable"]:
            any_open = True
        snapshot[label] = round(stats["closed_pnl"], 8)

    if not any_trades or any_open:
        return None
    return snapshot


def update_daily_pnl_history(today):
    """Persist today's completed P/L once the US market has closed.

    Re-running is intentional and idempotent: today's date key is overwritten,
    while every earlier date remains untouched. This also captures a late ledger
    correction without relying on a one-shot 21:00 UK scheduler.
    """
    history = _load_daily_pnl_history()
    if not _market_is_closed_now():
        return history

    market_today = datetime.now(timezone.utc).astimezone(NY_TZ).date().isoformat()
    if today != market_today:
        today = market_today

    snapshot = _final_daily_pnl_snapshot(today)
    if snapshot is not None:
        history[today] = snapshot
        _save_daily_pnl_history(history)
    return history



def _all_time_closed_stats(path):
    """Read one outcome ledger and summarize its newest closed trade records."""
    records = {}

    if path.exists():
        try:
            with path.open() as source:
                for raw in source:
                    try:
                        record = json.loads(raw)
                    except Exception:
                        continue

                    timestamp = str(
                        record.get("detected_at")
                        or record.get("signal_time")
                        or record.get("entry_time")
                        or record.get("confirmation_time")
                        or record.get("timestamp")
                        or ""
                    )
                    key = record.get("key") or (
                        timestamp,
                        record.get("symbol"),
                        record.get("strategy_id"),
                    )
                    records[str(key)] = record
        except Exception:
            records = {}

    closed = [
        record
        for record in records.values()
        if record.get("status") == "closed"
    ]
    wins = sum(
        1
        for record in closed
        if float(record.get("pnl_usd", 0) or 0) > 0
    )
    realized_pnl = sum(
        float(record.get("pnl_usd", 0) or 0)
        for record in closed
    )

    return_pct_sum = 0.0
    for record in closed:
        value = _safe_float(record.get("ret_pct"))

        if value is None:
            notional = float(record.get("paper_notional", 1000.0) or 1000.0)
            pnl = float(record.get("pnl_usd", 0) or 0)
            value = (pnl / notional * 100.0) if notional else 0.0

        return_pct_sum += value

    return {
        "closed_trades": len(closed),
        "wins": wins,
        "realized_pnl": realized_pnl,
        "return_pct_sum": return_pct_sum,
    }


def _write_strategy_performance_table(
    rows,
    today,
    historical_days,
    max_days=10,
):
    """Write a compact table intended for direct viewing with ``cat``."""
    days = sorted(set(historical_days) | {today})[-max_days:]
    strategy_width = 9
    day_width = 15

    lines = [
        "STRATEGY PERFORMANCE — $1,000 ASSIGNED TO EVERY TRADE",
        (
            "Daily cells show P/L / trades. Today's P/L includes "
            "marked-to-market open trades."
        ),
        (
            "This is signal-level research P/L, not a "
            "capital-constrained portfolio simulation."
        ),
        "",
    ]

    header = f"{'Strategy':<{strategy_width}}"
    header += "".join(
        f"{day[5:] + ' P/L/N':>{day_width}}"
        for day in days
    )
    header += (
        f"{'All P/L':>13}"
        f"{'Trades':>9}"
        f"{'Avg/trade':>12}"
        f"{'Win %':>9}"
        f"{'Open':>7}"
    )
    lines.extend([header, "-" * len(header)])

    for row in rows:
        rendered = f"{row['strategy_id']:<{strategy_width}}"

        for day in days:
            if day == today:
                pnl = row["today_pnl_per_1000"]
                trades = (
                    int(row["today_closed_trades"])
                    + int(row["today_open_trades"])
                )
            else:
                pnl = row.get(f"{day}_pnl_per_1000")
                trades = int(row.get(f"{day}_trades", 0) or 0)

            if pnl is None and trades == 0:
                cell = "—/0"
            else:
                cell = f"{float(pnl or 0):+.2f}/{trades}"

            rendered += f"{cell:>{day_width}}"

        rendered += (
            f"{float(row['all_time_realized_pnl_per_1000']):+13.2f}"
            f"{int(row['closed_trades_all_time']):>9}"
            f"{float(row['average_pnl_per_closed_trade']):+12.2f}"
            f"{float(row['win_rate_pct']):>9.1f}"
            f"{int(row['today_open_trades']):>7}"
        )
        lines.append(rendered)

    lines.extend([
        "-" * len(header),
        "P/L/N means paper P/L followed by number of trades for that date.",
    ])

    STRATEGY_PERFORMANCE_TABLE_TXT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    temporary = STRATEGY_PERFORMANCE_TABLE_TXT.with_suffix(".txt.tmp")
    temporary.write_text("\n".join(lines) + "\n")
    temporary.replace(STRATEGY_PERFORMANCE_TABLE_TXT)


def write_strategy_performance_csv(today):
    """Write machine-readable and human-readable strategy comparisons."""
    history = update_daily_pnl_history(today)
    historical_days = sorted(history)

    day_columns = []
    for day in historical_days:
        if day == today:
            continue
        day_columns.extend([
            f"{day}_pnl_per_1000",
            f"{day}_trades",
        ])

    fieldnames = [
        "strategy_id",
        "today_market_date",
        "today_pnl_per_1000",
        "today_closed_trades",
        "today_open_trades",
        "closed_trades_all_time",
        "wins_all_time",
        "win_rate_pct",
        "all_time_realized_pnl_per_1000",
        "all_time_return_pct_sum",
        "average_pnl_per_closed_trade",
        *day_columns,
    ]

    rows = []

    for strategy_id, outcome_path in _strategy_signal_series_definitions():
        today_stats = _paper_pnl_stats(outcome_path, today)
        all_time = _all_time_closed_stats(outcome_path)
        today_total = today_stats["closed_pnl"] + today_stats["open_pnl"]
        closed_trades = all_time["closed_trades"]
        win_rate = (
            all_time["wins"] / closed_trades * 100.0
            if closed_trades
            else 0.0
        )
        average_pnl = (
            all_time["realized_pnl"] / closed_trades
            if closed_trades
            else 0.0
        )

        row = {
            "strategy_id": strategy_id,
            "today_market_date": today,
            "today_pnl_per_1000": round(today_total, 4),
            "today_closed_trades": today_stats["closed"],
            "today_open_trades": (
                today_stats["open_marked"]
                + today_stats["open_unavailable"]
            ),
            "closed_trades_all_time": closed_trades,
            "wins_all_time": all_time["wins"],
            "win_rate_pct": round(win_rate, 4),
            "all_time_realized_pnl_per_1000": round(
                all_time["realized_pnl"],
                4,
            ),
            "all_time_return_pct_sum": round(
                all_time["return_pct_sum"],
                6,
            ),
            "average_pnl_per_closed_trade": round(
                average_pnl,
                4,
            ),
        }

        label = f"{strategy_id} signal"

        for day in historical_days:
            if day == today:
                continue

            historical_stats = _paper_pnl_stats(
                outcome_path,
                day,
            )
            row[f"{day}_pnl_per_1000"] = (
                history.get(day, {}).get(label)
            )
            row[f"{day}_trades"] = historical_stats["closed"]

        rows.append(row)

    STRATEGY_PERFORMANCE_CSV.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    temporary = STRATEGY_PERFORMANCE_CSV.with_suffix(".csv.tmp")

    with temporary.open("w", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    temporary.replace(STRATEGY_PERFORMANCE_CSV)
    _write_strategy_performance_table(
        rows,
        today,
        historical_days,
    )
    return rows


def daily_pnl_history_lines(today, max_days=10):
    """Render the persistent strategy-by-day P/L matrix."""
    history = update_daily_pnl_history(today)
    days = sorted(history.keys())[-max_days:]
    series = _paper_series_definitions()

    lines = [
        "DAILY PAPER P/L HISTORY — FINAL CLOSED OUTCOMES",
        "Rows are paper strategy series; columns are US market dates; basis is $1,000 per trade.",
        f"Persistent source: {DAILY_PNL_HISTORY_JSON}",
    ]
    if not days:
        lines.append("No completed market days have been saved yet.")
        return lines

    row_width = max(18, max(len(label) for label, _ in series) + 2)
    col_width = 12
    header = f"{'Strategy':<{row_width}}" + "".join(
        f"{day[5:]:>{col_width}}" for day in days
    )
    divider = "-" * len(header)
    lines.extend([header, divider])

    for label, _ in series:
        if not any(history.get(day, {}).get(label) is not None for day in days):
            continue
        cells = []
        for day in days:
            value = history.get(day, {}).get(label)
            if value is None:
                cells.append(f"{'—':>{col_width}}")
            else:
                cells.append(f"{float(value):+{col_width}.2f}")
        lines.append(f"{label:<{row_width}}" + "".join(cells))

    lines.append(divider)
    return lines



def _load_daily_market_behavior_history():
    """Load durable Strategy A day-behavior snapshots from disk."""
    if not DAILY_MARKET_BEHAVIOR_HISTORY_JSON.exists():
        return {}
    try:
        data = json.loads(DAILY_MARKET_BEHAVIOR_HISTORY_JSON.read_text())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_daily_market_behavior_history(history):
    """Atomically save durable Strategy A day-behavior snapshots."""
    try:
        DAILY_MARKET_BEHAVIOR_HISTORY_JSON.parent.mkdir(parents=True, exist_ok=True)
        tmp = DAILY_MARKET_BEHAVIOR_HISTORY_JSON.with_suffix(".tmp")
        tmp.write_text(json.dumps(history, indent=2, sort_keys=True) + "\n")
        tmp.replace(DAILY_MARKET_BEHAVIOR_HISTORY_JSON)
        return True
    except Exception:
        return False


def _median(values):
    values = sorted(float(value) for value in values)
    if not values:
        return None
    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]
    return (values[middle - 1] + values[middle]) / 2.0


def _strategy_a_closed_records_for_day(day):
    """Return Strategy A signal records for one day and whether any remain open."""
    records = []
    any_open = False
    if not SIGNAL_PAPER_OUTCOMES_JSONL.exists():
        return records, any_open
    try:
        with SIGNAL_PAPER_OUTCOMES_JSONL.open() as source:
            for raw in source:
                try:
                    record = json.loads(raw)
                except Exception:
                    continue
                if str(record.get("timestamp", ""))[:10] != day:
                    continue
                if str(record.get("strategy_id") or "A").upper() != "A":
                    continue
                if record.get("status") != "closed":
                    any_open = True
                    continue
                if record.get("ret_pct") is None:
                    continue
                records.append(record)
    except Exception:
        return [], False
    return records, any_open


def _classify_day_behavior(trade_count, day_score):
    """Fixed v1 descriptive labels; these do not change any strategy."""
    if trade_count < 5:
        return "INSUFFICIENT_DATA"
    if day_score >= 0.35:
        return "REBOUND_FRIENDLY"
    if day_score <= -0.35:
        return "REBOUND_FAILURE"
    return "MIXED"


def _final_daily_market_behavior_snapshot(day):
    """Build a final Strategy A behavior snapshot after all trades close.

    Day score v1 = average return + 0.25 * average MFE + 0.25 * average MAE.
    MAE is negative, so favorable excursion raises the score while adverse
    excursion lowers it. This score is descriptive research infrastructure only.
    """
    records, any_open = _strategy_a_closed_records_for_day(day)
    if not records or any_open:
        return None

    returns = [float(record.get("ret_pct", 0) or 0) for record in records]
    mfes = [float(record.get("mfe_pct", 0) or 0) for record in records]
    maes = [float(record.get("mae_pct", 0) or 0) for record in records]
    holdings = [
        float(record.get("holding_minutes"))
        for record in records
        if record.get("holding_minutes") is not None
    ]
    reasons = [str(record.get("exit_reason") or "").lower() for record in records]
    count = len(records)
    avg_return = sum(returns) / count
    avg_mfe = sum(mfes) / count
    avg_mae = sum(maes) / count
    day_score = avg_return + 0.25 * avg_mfe + 0.25 * avg_mae

    snapshot = {
        "reference_series": "A signal",
        "trade_count": count,
        "win_rate_pct": 100.0 * sum(value > 0 for value in returns) / count,
        "target_rate_pct": 100.0 * sum(reason == "target" for reason in reasons) / count,
        "stop_rate_pct": 100.0 * sum(reason == "stop" for reason in reasons) / count,
        "average_return_pct": avg_return,
        "average_mfe_pct": avg_mfe,
        "average_mae_pct": avg_mae,
        "median_holding_minutes": _median(holdings),
        "day_score_v1": day_score,
        "classification_v1": _classify_day_behavior(count, day_score),
        "score_formula": "avg_return + 0.25*avg_mfe + 0.25*avg_mae",
    }
    return {
        key: round(value, 8) if isinstance(value, float) else value
        for key, value in snapshot.items()
    }


def update_daily_market_behavior_history(today):
    """Persist today's finalized descriptive behavior snapshot after close."""
    history = _load_daily_market_behavior_history()
    if not _market_is_closed_now():
        return history

    market_today = datetime.now(timezone.utc).astimezone(NY_TZ).date().isoformat()
    if today != market_today:
        today = market_today

    snapshot = _final_daily_market_behavior_snapshot(today)
    if snapshot is not None:
        history[today] = snapshot
        _save_daily_market_behavior_history(history)
    return history


def daily_market_behavior_history_lines(today, max_days=10):
    """Render the persistent Strategy A day-behavior matrix."""
    history = update_daily_market_behavior_history(today)
    days = sorted(history.keys())[-max_days:]
    lines = [
        "DAILY MARKET BEHAVIOR HISTORY — STRATEGY A REFERENCE — SHADOW ONLY",
        "Descriptive final-day metrics only; this table does not alter entries or exits.",
        "Day score v1 = avg return + 0.25*avg MFE + 0.25*avg MAE.",
        f"Persistent source: {DAILY_MARKET_BEHAVIOR_HISTORY_JSON}",
    ]
    if not days:
        lines.append("No completed Strategy A market days have been saved yet.")
        return lines

    metrics = [
        ("Reference trades", "trade_count", "count"),
        ("Win rate", "win_rate_pct", "pct"),
        ("Target rate", "target_rate_pct", "pct"),
        ("Stop rate", "stop_rate_pct", "pct"),
        ("Avg return", "average_return_pct", "signed_pct"),
        ("Avg MFE", "average_mfe_pct", "signed_pct"),
        ("Avg MAE", "average_mae_pct", "signed_pct"),
        ("Median holding", "median_holding_minutes", "minutes"),
        ("Day score v1", "day_score_v1", "signed"),
        ("Classification", "classification_v1", "text"),
    ]
    row_width = max(len(label) for label, _, _ in metrics) + 2
    col_width = 20
    header = f"{'Metric':<{row_width}}" + "".join(
        f"{day[5:]:>{col_width}}" for day in days
    )
    divider = "-" * len(header)
    lines.extend([header, divider])

    for label, key, kind in metrics:
        cells = []
        for day in days:
            value = history.get(day, {}).get(key)
            if value is None:
                text = "—"
            elif kind == "count":
                text = str(int(value))
            elif kind == "pct":
                text = f"{float(value):.1f}%"
            elif kind == "signed_pct":
                text = f"{float(value):+.2f}%"
            elif kind == "minutes":
                text = f"{float(value):.1f}m"
            elif kind == "signed":
                text = f"{float(value):+.3f}"
            else:
                text = str(value)
            cells.append(f"{text:>{col_width}}")
        lines.append(f"{label:<{row_width}}" + "".join(cells))

    lines.append(divider)
    return lines

def main():
    print("leaderboard_writer.py starting lightweight mode", flush=True)

    while True:
        try:
            _cycle_start = time.time()
            print("TIMING_STAGE2 cycle_start", flush=True)

            _t = time.time()
            rows = load_recent_rows()
            events = load_recent_events()
            print(f"TIMING_STAGE2 load_rows_events: {time.time() - _t:.3f}s", flush=True)
            latest = rows[-1] if rows else None
            today = datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")

            today_rows = [
                r for r in rows
                if r.get("date") == today
                and is_rth_timestamp(r.get("timestamp"))
            ]
            today_events = [
                e for e in events
                if str(e.get("timestamp", "")).startswith(today)
                and is_rth_timestamp(e.get("timestamp"))
            ]
            signal_events_today = [e for e in today_events if e.get("event_type") == "SIGNAL" and event_strategy(e) == "A"]
            signal_events_b_today = [e for e in today_events if e.get("event_type") == "SIGNAL" and event_strategy(e) == "B"]
            signal_events_d_today = [e for e in today_events if e.get("event_type") == "SIGNAL" and event_strategy(e) == "D"]
            signal_events_h_today = [e for e in today_events if e.get("event_type") == "SIGNAL" and event_strategy(e) == "H"]
            rebound_events_today = [e for e in load_today_rebound_events(today) if event_strategy(e) == "A"]
            rebound_events_b_today = [e for e in load_today_rebound_events(today) if event_strategy(e) == "B"]
            rebound_events_d_today = [e for e in load_today_rebound_events(today) if event_strategy(e) == "D"]
            _t = time.time()
            active_rebounds, rebound_outcomes, rebound_stats = rebound_lifecycle(
                rebound_events_today
            )
            print(f"TIMING_STAGE2 rebound_lifecycle_A: {time.time() - _t:.3f}s", flush=True)
            active_rebounds_b, rebound_outcomes_b, rebound_stats_b = rebound_lifecycle(
                rebound_events_b_today
            )
            active_rebounds_d, rebound_outcomes_d, rebound_stats_d = rebound_lifecycle(
                rebound_events_d_today
            )
            trigger_events_today = [e for e in today_events if e.get("event_type") == "ENTRY_TRIGGER_OCO_ATTEMPT" and event_strategy(e) == "A"]
            execution_events_today = [e for e in today_events if e.get("event_type") in ("BUY_ATTEMPT", "BUY_RESPONSE", "BUY_ERROR", "SELL_ATTEMPT", "SELL_RESPONSE", "SELL_ERROR", "ENTRY_CANCEL_REQUESTED", "ENTRY_FILL_CONFIRMED", "TRIGGER_TRADE_CLOSED")]

            triggers_today = 0
            for row in today_rows:
                triggers_today = max(triggers_today, int(row.get("total_triggers_today", 0) or 0))

            # Stable threshold-defined candidate populations. These are not
            # daily rankings: every first qualifying symbol/day observation is retained.
            top_today = threshold_near_miss_candidates(today_events, "A")
            top_b_today = threshold_near_miss_candidates(today_events, "B")
            top_d_today = threshold_near_miss_candidates(today_events, "D")
            top_h_today = threshold_near_miss_candidates(today_events, "H")

            # Older A sessions may only have dashboard snapshots rather than explicit
            # NEAR_MISS events. Keep that fallback prospective and threshold-defined.
            if not top_today:
                fallback = []
                for row in today_rows:
                    for candidate in row.get("latest_nearest", []) or []:
                        c = dict(candidate)
                        c["seen_at"] = row.get("timestamp")
                        try:
                            score = float(c.get("miss_score", 999))
                        except (TypeError, ValueError):
                            continue
                        if 0.0 < score <= NEAR_MISS_SCORE_CUTOFF:
                            c["candidate_cutoff"] = NEAR_MISS_SCORE_CUTOFF
                            c["candidate_definition"] = "0 < miss_score <= cutoff"
                            fallback.append(c)
                first = {}
                for c in fallback:
                    key = (str(c.get("seen_at", ""))[:10], str(c.get("symbol") or "").upper())
                    if key[1] and (key not in first or str(c.get("seen_at")) < str(first[key].get("seen_at"))):
                        first[key] = c
                top_today = sorted(first.values(), key=lambda c: str(c.get("seen_at", "")))

            # E and F inherit the threshold population of their parent entry strategy,
            # then apply only their own additional overlay.
            top_e_today = [
                c for c in top_today
                if strategy_e_after_forward_start(c.get("seen_at"))
                and strategy_e_eligible_near_miss(c)
            ]
            top_f_today = [
                c for c in top_d_today
                if strategy_f_after_forward_start(c.get("seen_at"))
                and strategy_f_eligible_near_miss(c)
            ]

            by_day = {}
            for r in rows:
                d = r.get("date", "unknown")
                by_day.setdefault(d, {"best": None, "triggers": 0})
                by_day[d]["triggers"] = max(by_day[d]["triggers"], int(r.get("total_triggers_today", 0) or 0))
                for e in r.get("latest_nearest", []) or []:
                    if by_day[d]["best"] is None or float(e.get("miss_score", 999)) < float(by_day[d]["best"].get("miss_score", 999)):
                        by_day[d]["best"] = dict(e)

            print(f"TIMING_STAGE2 pre_health_sections: {time.time() - _cycle_start:.3f}s", flush=True)
            _t = time.time()
            append_auth_health_snapshot()
            print(f"TIMING_STAGE2 auth_snapshot: {time.time() - _t:.3f}s", flush=True)

            lines = [
                "BOT OUTPUT",
                f"Last update: {datetime.now(timezone.utc).isoformat()}",
                f"Status: {latest.get('status', 'unknown') if latest else 'unknown'}",
                "",
                *eligibility_health_lines(),
                "",
                *token_health_lines(),
                "",
                *storage_health_lines(),
                "",
                *cpu_health_lines(),
                "",
                *memory_health_lines(),
                "",
                "AUTH DOWNTIME / WARNING HISTORY TODAY",
                *auth_downtime_history_lines(),
                "",
                "STRATEGY A — ACTIVE THRESHOLDS",
                "flash_drop >= 1.00%",
                "pre_return >= 0.25%",
                "pre_slope >= 0.50%/hr",
                "max_flash_drop <= 12.00%",
                "",
                "STRATEGY A — LATEST NEAREST MISSES",
            ]

            if latest and latest.get("latest_nearest"):
                for e in latest["latest_nearest"][:5]:
                    lines.append(fmt_near(e))
            else:
                lines.append("None")

            lines += ["", "NEAR-MISS CANDIDATE DEFINITION"]
            lines += [
                f"fixed_cutoff: 0 < miss_score <= {NEAR_MISS_SCORE_CUTOFF:.2f}",
                "population_rule: first qualifying observation per symbol, per strategy, per market day",
                "selection_rule: no daily top-N ranking",
                "dataset_note: cutoff changes require a new versioned dataset",
            ]

            lines += ["", "STRATEGY A — THRESHOLD CANDIDATES TODAY"]
            if top_today:
                for e in top_today:
                    lines.append(f"{fmt_near(e)} | seen={e.get('seen_at')}")
            else:
                lines.append("None")

            lines += ["", "STRATEGY A — THRESHOLD-CANDIDATE PAPER OUTCOMES — PAPER ONLY"]
            for line in near_miss_paper_lines(top_today, max_items=5, strategy_id="A", outcomes_path=NEAR_MISS_PAPER_JSONL):
                lines.append(line)

            lines += ["", "STRATEGY A — PENDING REBOUND CANDIDATES — QUALIFIED, AWAITING CONFIRMATION"]
            for line in pending_rebound_lines(active_rebounds):
                lines.append(line)

            lines += ["", "STRATEGY A — REBOUND OUTCOMES TODAY"]
            for line in rebound_outcome_lines(rebound_outcomes, max_items=5):
                lines.append(line)

            lines += ["", "STRATEGY A — REBOUND SUMMARY TODAY"]
            lines.extend(rebound_summary_lines(rebound_stats))

            lines += ["", "STRATEGY A — TRIGGERS TODAY"]
            if latest and latest.get("latest_triggers"):
                for e in latest["latest_triggers"][:10]:
                    lines.append(str(e))
            else:
                lines.append("None")
            lines.append(f"Total triggers today: {triggers_today}")

            lines += ["", "STRATEGY A — TRIGGER TRADE LEDGER TODAY"]
            if trigger_events_today:
                for e in trigger_events_today[-50:]:
                    lines.append(summarize_trigger_event(e))
            else:
                lines.append("None")

            lines += ["", "STRATEGY A — REAL TRIGGER TRADE OUTCOMES"]
            for line in trigger_trade_outcome_lines(max_items=5):
                lines.append(line)

            lines += ["", "STRATEGY A — SIGNAL PAPER OUTCOMES"]
            for line in signal_paper_outcome_lines(
                [
                    e for e in events
                    if e.get("event_type") == "SIGNAL"
                    and event_strategy(e) == "A"
                    and is_rth_timestamp(e.get("timestamp"))
                ],
                max_items=5,
                strategy_id="A",
                outcomes_path=SIGNAL_PAPER_OUTCOMES_JSONL,
            ):
                lines.append(line)

            lines += ["", "STRATEGY A — FULL SIGNAL LEDGER TODAY"]
            if signal_events_today:
                for e in signal_events_today[-20:]:
                    lines.append(summarize_signal_event(e))
            else:
                lines.append("None")

            lines += ["", "========================", "STRATEGY B — PAPER SHADOW", "========================"]
            lines += ["", "STRATEGY B — ACTIVE THRESHOLDS"]
            lines += [
                "flash_drop >= 1.00%",
                "pre_return >= 0.25%",
                "pre_slope >= 0.50%/hr",
                "max_flash_drop <= 12.00%",
                "rebound_confirmation >= 0.20%",
                "stop_loss = 2.00%",
                "live_order_placement: DISABLED",
            ]

            lines += ["", "STRATEGY B — THRESHOLD CANDIDATES TODAY"]
            if top_b_today:
                for e in top_b_today:
                    lines.append(f"{fmt_near(e)} | seen={e.get('seen_at')}")
            else:
                lines.append("None")

            lines += ["", "STRATEGY B — THRESHOLD-CANDIDATE PAPER OUTCOMES — PAPER ONLY"]
            for line in near_miss_paper_lines(
                top_b_today, max_items=5, strategy_id="B", outcomes_path=NEAR_MISS_PAPER_B_JSONL,
                rebound_confirmation_pct=STRATEGY_B_REBOUND_CONFIRMATION_PCT,
                stop_loss_fraction=STRATEGY_B_STOP_LOSS_FRACTION_BELOW_ENTRY,
            ):
                lines.append(line)

            lines += ["", "STRATEGY B — PENDING REBOUND CANDIDATES — QUALIFIED, AWAITING CONFIRMATION"]
            lines.extend(pending_rebound_lines(active_rebounds_b))

            lines += ["", "STRATEGY B — REBOUND OUTCOMES TODAY"]
            lines.extend(rebound_outcome_lines(rebound_outcomes_b, max_items=5))

            lines += ["", "STRATEGY B — REBOUND SUMMARY TODAY"]
            lines.extend(rebound_summary_lines(rebound_stats_b))

            lines += ["", "STRATEGY B — SIGNAL PAPER OUTCOMES"]
            for line in signal_paper_outcome_lines(
                [
                    e for e in events
                    if e.get("event_type") == "SIGNAL"
                    and event_strategy(e) == "B"
                    and is_rth_timestamp(e.get("timestamp"))
                ],
                max_items=5,
                strategy_id="B",
                outcomes_path=SIGNAL_PAPER_OUTCOMES_B_JSONL,
            ):
                lines.append(line)

            lines += ["", "STRATEGY B — FULL SIGNAL LEDGER TODAY"]
            if signal_events_b_today:
                for e in signal_events_b_today[-20:]:
                    lines.append(summarize_signal_event(e))
            else:
                lines.append("None")

            lines += ["", "========================", "STRATEGY D — STRATEGY B CLONE / 0.90% FLASH", "========================"]
            lines += ["", "STRATEGY D — ACTIVE THRESHOLDS"]
            lines += [
                "flash_drop >= 0.90%",
                "pre_return >= 0.25%",
                "pre_slope >= 0.50%/hr",
                "max_flash_drop <= 12.00%",
                "rebound_confirmation >= 0.20%",
                "stop_loss = 2.00%",
                "live_order_placement: DISABLED",
            ]

            lines += ["", "STRATEGY D — THRESHOLD CANDIDATES TODAY"]
            if top_d_today:
                for e in top_d_today:
                    lines.append(f"{fmt_near(e)} | seen={e.get('seen_at')}")
            else:
                lines.append("None")

            lines += ["", "STRATEGY D — THRESHOLD-CANDIDATE PAPER OUTCOMES — PAPER ONLY"]
            for line in near_miss_paper_lines(
                top_d_today, max_items=5, strategy_id="D", outcomes_path=NEAR_MISS_PAPER_D_JSONL,
                rebound_confirmation_pct=STRATEGY_D_REBOUND_CONFIRMATION_PCT,
                stop_loss_fraction=STRATEGY_D_STOP_LOSS_FRACTION_BELOW_ENTRY,
            ):
                lines.append(line)

            lines += ["", "STRATEGY D — PENDING REBOUND CANDIDATES — QUALIFIED, AWAITING CONFIRMATION"]
            lines.extend(pending_rebound_lines(active_rebounds_d))

            lines += ["", "STRATEGY D — REBOUND OUTCOMES TODAY"]
            lines.extend(rebound_outcome_lines(rebound_outcomes_d, max_items=5))

            lines += ["", "STRATEGY D — REBOUND SUMMARY TODAY"]
            lines.extend(rebound_summary_lines(rebound_stats_d))

            lines += ["", "STRATEGY D — SIGNAL PAPER OUTCOMES"]
            for line in signal_paper_outcome_lines(
                [
                    e for e in events
                    if e.get("event_type") == "SIGNAL"
                    and event_strategy(e) == "D"
                    and is_rth_timestamp(e.get("timestamp"))
                ],
                max_items=5,
                strategy_id="D",
                outcomes_path=SIGNAL_PAPER_OUTCOMES_D_JSONL,
            ):
                lines.append(line)

            lines += ["", "STRATEGY D — FULL SIGNAL LEDGER TODAY"]
            if signal_events_d_today:
                for e in signal_events_d_today[-20:]:
                    lines.append(summarize_signal_event(e))
            else:
                lines.append("None")

            strategy_e_all_signals = [
                e for e in events
                if strategy_e_eligible_signal(e)
                and is_rth_timestamp(e.get("timestamp"))
                and strategy_e_after_forward_start(e.get("timestamp"))
            ]
            strategy_e_signals_today = [
                e for e in strategy_e_all_signals
                if str(e.get("timestamp", "")).startswith(today)
            ]

            lines += ["", "========================", "STRATEGY E — STRATEGY A + $1.2M FLASH LIQUIDITY FILTER", "========================"]
            lines += ["", "STRATEGY E — ACTIVE THRESHOLDS"]
            lines += [
                "entry_source: Strategy A confirmed SIGNAL entries",
                "flash_drop >= 1.00%",
                "pre_return >= 0.25%",
                "pre_slope >= 0.50%/hr",
                "max_flash_drop <= 12.00%",
                "rebound_confirmation >= 0.10%",
                "stop_loss = 5.00%",
                f"flash_$vol_3m >= ${STRATEGY_E_MIN_FLASH_DOLLAR_VOLUME_3M:,.0f}",
                f"forward_start_utc: {STRATEGY_E_FORWARD_START_UTC}",
                "missing/error flash-volume snapshots: EXCLUDED",
                "live_order_placement: DISABLED (leaderboard paper overlay)",
            ]

            lines += ["", "STRATEGY E — THRESHOLD CANDIDATES TODAY"]
            if top_e_today:
                for candidate in top_e_today:
                    lines.append(f"{fmt_near(candidate)}{_volume_suffix(candidate)} | seen={candidate.get('seen_at')}")
            else:
                lines.append("None")

            lines += ["", "STRATEGY E — THRESHOLD-CANDIDATE PAPER OUTCOMES — PAPER ONLY"]
            for line in near_miss_paper_lines(
                top_e_today,
                max_items=5,
                strategy_id="E",
                outcomes_path=NEAR_MISS_PAPER_E_JSONL,
                rebound_confirmation_pct=REBOUND_CONFIRMATION_PCT,
                stop_loss_fraction=STOP_LOSS_FRACTION_BELOW_ENTRY,
            ):
                lines.append(line)

            lines += ["", "STRATEGY E — SIGNAL PAPER OUTCOMES"]
            for line in signal_paper_outcome_lines(
                strategy_e_all_signals,
                max_items=5,
                strategy_id="E",
                outcomes_path=SIGNAL_PAPER_OUTCOMES_E_JSONL,
            ):
                lines.append(line)

            lines += ["", "STRATEGY E — FULL SIGNAL LEDGER TODAY"]
            if strategy_e_signals_today:
                for e in strategy_e_signals_today[-20:]:
                    lines.append(summarize_signal_event(e))
            else:
                lines.append("None")

            strategy_f_all_signals = [
                e for e in events
                if strategy_f_eligible_signal(e)
                and is_rth_timestamp(e.get("timestamp"))
                and strategy_f_after_forward_start(e.get("timestamp"))
            ]
            strategy_f_signals_today = [
                e for e in strategy_f_all_signals
                if str(e.get("timestamp", "")).startswith(today)
            ]

            lines += ["", "========================", "STRATEGY F — STRATEGY D + RELATIVE FLASH-VOLUME FILTER", "========================"]
            lines += ["", "STRATEGY F — ACTIVE THRESHOLDS"]
            lines += [
                "entry_source: Strategy D confirmed SIGNAL entries",
                f"flash_drop >= {STRATEGY_D_FLASH_DROP_PCT:.2f}%",
                "pre_return >= 0.25%",
                "pre_slope >= 0.50%/hr",
                "max_flash_drop <= 12.00%",
                f"rebound_confirmation >= {STRATEGY_D_REBOUND_CONFIRMATION_PCT * 100:.2f}%",
                f"stop_loss = {STRATEGY_D_STOP_LOSS_FRACTION_BELOW_ENTRY * 100:.2f}%",
                f"flash_vol_ratio >= {STRATEGY_F_MIN_FLASH_VOL_RATIO:.2f}x",
                f"forward_start_utc: {STRATEGY_F_FORWARD_START_UTC}",
                "missing/error flash-volume snapshots: EXCLUDED",
                "live_order_placement: DISABLED (leaderboard paper overlay)",
            ]

            lines += ["", "STRATEGY F — THRESHOLD CANDIDATES TODAY"]
            if top_f_today:
                for candidate in top_f_today:
                    lines.append(f"{fmt_near(candidate)}{_volume_suffix(candidate)} | seen={candidate.get('seen_at')}")
            else:
                lines.append("None")

            lines += ["", "STRATEGY F — THRESHOLD-CANDIDATE PAPER OUTCOMES — PAPER ONLY"]
            for line in near_miss_paper_lines(
                top_f_today,
                max_items=5,
                strategy_id="F",
                outcomes_path=NEAR_MISS_PAPER_F_JSONL,
                rebound_confirmation_pct=STRATEGY_D_REBOUND_CONFIRMATION_PCT,
                stop_loss_fraction=STRATEGY_D_STOP_LOSS_FRACTION_BELOW_ENTRY,
            ):
                lines.append(line)

            lines += ["", "STRATEGY F — SIGNAL PAPER OUTCOMES"]
            for line in signal_paper_outcome_lines(
                strategy_f_all_signals,
                max_items=5,
                strategy_id="F",
                outcomes_path=SIGNAL_PAPER_OUTCOMES_F_JSONL,
            ):
                lines.append(line)

            lines += ["", "STRATEGY F — FULL SIGNAL LEDGER TODAY"]
            if strategy_f_signals_today:
                for e in strategy_f_signals_today[-20:]:
                    lines.append(summarize_signal_event(e))
            else:
                lines.append("None")

            strategy_b_all_signals = [
                e for e in events
                if e.get("event_type") == "SIGNAL"
                and event_strategy(e) == "B"
                and is_rth_timestamp(e.get("timestamp"))
            ]

            lines += ["", "========================", "STRATEGY C — FORWARD PAPER EXIT RESEARCH", "========================"]
            lines += [
                f"forward_start_utc: {STRATEGY_C_FORWARD_START_UTC}",
                "entry_source: Strategy B SIGNAL entries",
                f"activation_gain: +{STRATEGY_C_ACTIVATION_GAIN_PCT:.2f}%",
                "protective_stop: Strategy B 2.00% stop",
                "end_of_day_exit: 15:55 ET",
                "live_order_placement: DISABLED",
            ]

            lines += ["", "STRATEGY C1 — 0.20% TRAILING PULLBACK AFTER ACTIVATION — B SIGNALS"]
            lines.extend(strategy_c_signal_paper_outcome_lines(
                strategy_b_all_signals,
                variant="C1",
                max_items=5,
                outcomes_path=SIGNAL_PAPER_OUTCOMES_C1_JSONL,
            ))
            lines += ["", "STRATEGY C1 — B NEAR-MISS ENTRIES — PAPER ONLY"]
            lines.extend(strategy_c_near_miss_paper_outcome_lines(
                variant="C1", max_items=5, outcomes_path=NEAR_MISS_PAPER_C1_JSONL
            ))

            lines += ["", "STRATEGY C2 — NO NEW HIGH FOR 30 SECONDS AFTER ACTIVATION — B SIGNALS"]
            lines.extend(strategy_c_signal_paper_outcome_lines(
                strategy_b_all_signals,
                variant="C2",
                max_items=5,
                outcomes_path=SIGNAL_PAPER_OUTCOMES_C2_JSONL,
            ))
            lines += ["", "STRATEGY C2 — B NEAR-MISS ENTRIES — PAPER ONLY"]
            lines.extend(strategy_c_near_miss_paper_outcome_lines(
                variant="C2", max_items=5, outcomes_path=NEAR_MISS_PAPER_C2_JSONL
            ))

            lines += ["", "STRATEGY C3 — 3 LOWER QUOTES / >=0.10% DECLINE AFTER ACTIVATION — B SIGNALS"]
            lines.extend(strategy_c_signal_paper_outcome_lines(
                strategy_b_all_signals,
                variant="C3",
                max_items=5,
                outcomes_path=SIGNAL_PAPER_OUTCOMES_C3_JSONL,
            ))
            lines += ["", "STRATEGY C3 — B NEAR-MISS ENTRIES — PAPER ONLY"]
            lines.extend(strategy_c_near_miss_paper_outcome_lines(
                variant="C3", max_items=5, outcomes_path=NEAR_MISS_PAPER_C3_JSONL
            ))

            lines += ["", "STRATEGY C4 — 30-SECOND SLOPE <= -0.20%/MIN AFTER ACTIVATION — B SIGNALS"]
            lines.extend(strategy_c_signal_paper_outcome_lines(
                strategy_b_all_signals,
                variant="C4",
                max_items=5,
                outcomes_path=SIGNAL_PAPER_OUTCOMES_C4_JSONL,
            ))
            lines += ["", "STRATEGY C4 — B NEAR-MISS ENTRIES — PAPER ONLY"]
            lines.extend(strategy_c_near_miss_paper_outcome_lines(
                variant="C4", max_items=5, outcomes_path=NEAR_MISS_PAPER_C4_JSONL
            ))

            lines += ["", "========================", "STRATEGY G — C4 EXIT WITH 1.50% STOP — FORWARD PAPER", "========================"]
            lines += [
                f"forward_start_utc: {STRATEGY_G_FORWARD_START_UTC}",
                "entry_source: Strategy B SIGNAL entries",
                f"activation_gain: +{STRATEGY_C_ACTIVATION_GAIN_PCT:.2f}%",
                f"negative_slope_exit: {STRATEGY_C4_NEGATIVE_SLOPE_PCT_PER_MINUTE:.2f}%/min over {STRATEGY_C4_SLOPE_WINDOW_SECONDS:.0f}s",
                f"protective_stop: {STRATEGY_G_STOP_LOSS_FRACTION_BELOW_ENTRY * 100:.2f}% below entry",
                "end_of_day_exit: 15:55 ET",
                "live_order_placement: DISABLED",
            ]
            lines += ["", "STRATEGY G — B SIGNALS"]
            lines.extend(strategy_c_signal_paper_outcome_lines(
                strategy_b_all_signals,
                variant="G",
                max_items=5,
                outcomes_path=SIGNAL_PAPER_OUTCOMES_G_JSONL,
                stop_loss_fraction=STRATEGY_G_STOP_LOSS_FRACTION_BELOW_ENTRY,
                forward_start_utc=STRATEGY_G_FORWARD_START_UTC,
            ))
            lines += ["", "STRATEGY G — B NEAR-MISS ENTRIES — PAPER ONLY"]
            lines.extend(strategy_c_near_miss_paper_outcome_lines(
                variant="G",
                max_items=5,
                outcomes_path=NEAR_MISS_PAPER_G_JSONL,
                stop_loss_fraction=STRATEGY_G_STOP_LOSS_FRACTION_BELOW_ENTRY,
                forward_start_utc=STRATEGY_G_FORWARD_START_UTC,
            ))


            strategy_h_all_signals = [
                e for e in events
                if e.get("event_type") == "SIGNAL"
                and event_strategy(e) == "H"
                and is_rth_timestamp(e.get("timestamp"))
            ]

            lines += ["", "========================", "STRATEGY H — FILTERED BROAD REBOUND — FORWARD PAPER", "========================"]
            lines += [
                f"forward_start_utc: {STRATEGY_H_FORWARD_START_UTC}",
                f"flash_drop: {STRATEGY_H_MIN_FLASH_DROP_PCT:.2f}% to {STRATEGY_H_MAX_FLASH_DROP_PCT:.2f}%",
                "pre_return >= 0.25%",
                "pre_slope >= 0.50%/hr",
                f"pre_slope <= {STRATEGY_H_MAX_PRE_SLOPE_PCT_PER_HOUR:.2f}%/hr",
                f"pre_r2 >= {STRATEGY_H_MIN_PRE_R2:.2f}",
                f"rebound_confirmation >= {STRATEGY_H_REBOUND_CONFIRMATION_PCT * 100:.2f}%",
                f"minimum remaining upside at entry >= {STRATEGY_H_MIN_REMAINING_UPSIDE_PCT:.2f}%",
                f"protective_stop: {STRATEGY_H_STOP_LOSS_FRACTION_BELOW_ENTRY * 100:.2f}% below entry",
                "target: existing 60% flash-recovery target",
                "end_of_day_exit: 15:55 ET",
                "live_order_placement: DISABLED",
            ]

            lines += ["", "STRATEGY H — THRESHOLD FILTER-BOUNDARY CANDIDATES TODAY"]
            if top_h_today:
                for candidate in top_h_today:
                    lines.append(f"{fmt_near(candidate)} | seen={candidate.get('seen_at')}")
            else:
                lines.append("None")

            lines += ["", "STRATEGY H — THRESHOLD-CANDIDATE PAPER OUTCOMES — PAPER ONLY"]
            lines.extend(near_miss_paper_lines(
                top_h_today,
                max_items=5,
                strategy_id="H",
                outcomes_path=NEAR_MISS_PAPER_H_JSONL,
                rebound_confirmation_pct=STRATEGY_H_REBOUND_CONFIRMATION_PCT,
                stop_loss_fraction=STRATEGY_H_STOP_LOSS_FRACTION_BELOW_ENTRY,
            ))

            lines += ["", "STRATEGY H — SIGNAL PAPER OUTCOMES"]
            lines.extend(signal_paper_outcome_lines(
                strategy_h_all_signals,
                max_items=5,
                strategy_id="H",
                outcomes_path=SIGNAL_PAPER_OUTCOMES_H_JSONL,
            ))

            lines += ["", "STRATEGY H — FULL SIGNAL LEDGER TODAY"]
            if signal_events_h_today:
                for event in signal_events_h_today[-50:]:
                    lines.append(summarize_signal_event(event))
            else:
                lines.append("None")

            strategy_i_all_signals = [
                e for e in events
                if strategy_i_eligible_signal(e)
                and is_rth_timestamp(e.get("timestamp"))
            ]

            lines += ["", "========================", "STRATEGY I — A WITH FAST REBOUND CONFIRMATION — FORWARD PAPER", "========================"]
            lines += [
                f"forward_start_utc: {STRATEGY_I_FORWARD_START_UTC}",
                "entry_source: Strategy A SIGNAL entries",
                f"confirmation_wait_seconds <= {STRATEGY_I_MAX_CONFIRMATION_DELAY_SECONDS:.0f}",
                "all other entry, target, stop, and EOD rules identical to Strategy A",
                "live_order_placement: DISABLED",
            ]
            lines += ["", "STRATEGY I — SIGNAL PAPER OUTCOMES"]
            lines.extend(signal_paper_outcome_lines(
                strategy_i_all_signals,
                max_items=5,
                strategy_id="I",
                outcomes_path=SIGNAL_PAPER_OUTCOMES_I_JSONL,
            ))

            strategy_j_source_signals = [
                e for e in events
                if e.get("event_type") == "SIGNAL"
                and event_strategy(e) == "B"
                and is_rth_timestamp(e.get("timestamp"))
            ]
            lines += ["", "========================", "STRATEGY J — EARLY FAILURE MANAGEMENT FAMILY — FORWARD PAPER", "========================"]
            lines += [
                f"forward_start_utc: {STRATEGY_J_FORWARD_START_UTC}",
                "entry_source: identical Strategy B SIGNAL entries",
                "target: Strategy B recorded recovery target",
                "checkpoint uses first quote at or after the configured elapsed time",
                "checkpoint failure rule: return <= 0.00%",
                "end_of_day_exit: 15:55 ET",
                "live_order_placement: DISABLED",
            ]
            for variant, config in STRATEGY_J_CONFIGS.items():
                checkpoint_text = (
                    f"{config['checkpoint_seconds']:.0f}s no-progress exit"
                    if config["checkpoint_seconds"] is not None else "no checkpoint"
                )
                lines += [
                    "",
                    f"STRATEGY {variant} — stop={config['stop_loss_fraction'] * 100:.2f}% | {checkpoint_text}",
                ]
                lines.extend(strategy_j_signal_paper_outcome_lines(
                    strategy_j_source_signals,
                    variant=variant,
                    max_items=5,
                    outcomes_path=STRATEGY_J_OUTCOME_PATHS[variant],
                    forward_start_utc=STRATEGY_J_FORWARD_START_UTC,
                ))


            strategy_k_source_signals = [
                e for e in events
                if e.get("event_type") == "SIGNAL"
                and event_strategy(e) == "A"
                and is_rth_timestamp(e.get("timestamp"))
            ]
            strategy_k_result = strategy_k_family_lines(
                strategy_k_source_signals,
                max_items=5,
                forward_start_utc=STRATEGY_K_FORWARD_START_UTC,
            )
            lines += ["", "========================", "STRATEGY K — POST-ENTRY EXIT RESEARCH FAMILY — FORWARD PAPER", "========================"]
            lines += [
                f"forward_start_utc: {STRATEGY_K_FORWARD_START_UTC}",
                "entry_source: identical Strategy A SIGNAL entries",
                "shared checkpoints: 15s, 30s, 60s, 90s, 120s, 180s, 300s",
                "shared metrics: return, MFE, MAE, first positive, first +0.10%, first +0.20%",
                "baseline target, Strategy A 5% stop and 15:55 ET exit remain active unless a configured K rule exits first; K9 force-closes at 30 minutes",
                "live_order_placement: DISABLED",
            ]
            lines += ["", "STRATEGY K — SHARED EARLY BEHAVIOR ANALYSIS"]
            lines.extend(strategy_k_result.get("analysis", ["None"]))
            for variant, config in STRATEGY_K_CONFIGS.items():
                lines += ["", f"STRATEGY {variant} — {config}"]
                lines.extend(strategy_k_result.get("variants", {}).get(variant, ["None"]))


            strategy_ls_source_signals = [
                e for e in events
                if e.get("event_type") == "SIGNAL"
                and event_strategy(e) == "A"
                and is_rth_timestamp(e.get("timestamp"))
            ]
            lines += ["", "========================", "STRATEGIES L-S — MEAN-REVERSION HYPOTHESIS PACK — FORWARD PAPER", "========================"]
            lines += [
                f"forward_start_utc: {STRATEGY_LS_FORWARD_START_UTC}",
                "entry_source: Strategy A signals unless explicitly stated",
                "all variants are isolated paper simulations; no live orders",
                "no historical backfill before deployment",
            ]
            ls_descriptions = {
                "L": "Exhaustion: flash volume >= 1.00x and rebound volume <= 75% of flash ratio",
                "M": "Rolling VWAP: flash snapshot at least 0.50% below frozen 45-minute volume-weighted price",
                "N": "Adaptive exit: activate at +0.30%, then exit on 0.20% pullback from high",
                "O": "Second leg: wait for 0.10% pullback then 0.10% renewed rebound before simulated entry",
                "P": "Strong stock: pre-return >= 0.75% and pre-trend R2 >= 0.50",
                "Q": "Volatility normalized: flash drop >= 3.0 pre-30-minute one-minute standard deviations",
                "R": "Time window: entries before 11:00 ET",
                "S": "Market confirmation: SPY or QQQ 5m >= -0.15% and 1m >= 0.00% at signal timestamp",
            }
            for variant in "LMNOPQRS":
                lines += ["", f"STRATEGY {variant} — {ls_descriptions[variant]}"]
                if variant in {"N", "O"}:
                    lines.extend(strategy_dynamic_variant_lines(strategy_ls_source_signals, variant, max_items=5))
                else:
                    eligible = strategy_ls_eligible_events(strategy_ls_source_signals, variant)
                    lines.extend(signal_paper_outcome_lines(eligible, max_items=5, strategy_id=variant, outcomes_path=STRATEGY_LS_PATHS[variant]))

            # Universe-method comparison across the independent strategy pack.
            universe_totals = {}
            for _sid, _path in INDEPENDENT_STRATEGY_PATHS.items():
                for _rec in load_trigger_outcomes(_path).values():
                    if str(_rec.get("timestamp", ""))[:10] != today:
                        continue
                    _u = str(_rec.get("primary_universe") or "UNKNOWN")
                    _bucket = universe_totals.setdefault(_u, {"trades": 0, "closed": 0, "pnl": 0.0, "wins": 0})
                    _bucket["trades"] += 1
                    if _rec.get("status") == "closed":
                        _bucket["closed"] += 1
                        _pnl = float(_rec.get("pnl_usd", 0) or 0)
                        _bucket["pnl"] += _pnl
                        _bucket["wins"] += int(_pnl > 0)

            lines += ["", "========================", "UNIVERSE METHOD COMPARISON — INDEPENDENT STRATEGIES", "========================"]
            if universe_totals:
                for _u in ("U1_CORE", "U2_STATIC", "U3_ROTATING", "DISCOVERY_ONLY", "UNKNOWN"):
                    if _u not in universe_totals:
                        continue
                    _b = universe_totals[_u]
                    _wr = 100.0 * _b["wins"] / _b["closed"] if _b["closed"] else 0.0
                    lines.append(f"{_u}: signals={_b['trades']} | closed={_b['closed']} | win_rate={_wr:.1f}% | closed_P/L={_b['pnl']:+.2f}")
                _promoted_records = []
                for _sid, _path in INDEPENDENT_STRATEGY_PATHS.items():
                    _promoted_records.extend([
                        _rec for _rec in load_trigger_outcomes(_path).values()
                        if str(_rec.get("timestamp", ""))[:10] == today and _rec.get("dynamic_promoted")
                    ])
                _promoted_closed = [_rec for _rec in _promoted_records if _rec.get("status") == "closed"]
                _promoted_pnl = sum(float(_rec.get("pnl_usd", 0) or 0) for _rec in _promoted_closed)
                lines.append(f"U4_DYNAMIC_PROMOTED overlay: signals={len(_promoted_records)} | closed={len(_promoted_closed)} | closed_P/L={_promoted_pnl:+.2f}")
            else:
                lines.append("No independent-strategy universe outcomes yet.")

            lines += ["", "========================", "INDEPENDENT STRATEGY RESEARCH PACK — NATIVE FORWARD PAPER", "========================"]
            lines += [
                f"forward_start_utc: {INDEPENDENT_FORWARD_START_UTC}",
                "entry_source: native strategy-specific scans across the full quote universe",
                "dependency_on_strategy_A: NONE",
                "live_order_placement: DISABLED",
                "paper_notional: $1,000 per signal",
                "note: BO1/VE1 currently use price-range confirmation; Schwab volume snapshots can be added after baseline collection",
                "note: VR1 uses a clearly labelled rolling price-mean proxy because the quote tape does not contain volume",
                "M1/M2/M3 test 15/30/60-minute distributed selloffs followed by stabilization and an initial rebound",
                "new 2026-08-03 pack: RS3, MC1, TL1, AV1, TD1, SH1, CV1, HL1, VT1 and PD1; all paper-only",
            ]
            for strategy_id, path in INDEPENDENT_STRATEGY_PATHS.items():
                strategy_events = [
                    e for e in events
                    if e.get("event_type") == "SIGNAL"
                    and event_strategy(e) == strategy_id
                    and _event_after_start(e, INDEPENDENT_FORWARD_START_UTC)
                    and is_rth_timestamp(e.get("timestamp"))
                ]
                lines += ["", f"STRATEGY {strategy_id} — {INDEPENDENT_STRATEGY_DESCRIPTIONS.get(strategy_id, strategy_id)}"]
                lines.extend(signal_paper_outcome_lines(
                    strategy_events,
                    max_items=5,
                    strategy_id=strategy_id,
                    outcomes_path=path,
                ))

            near_miss_events_today = [e for e in today_events if e.get("event_type") == "NEAR_MISS" and event_strategy(e) == "A"]
            lines += ["", "STRATEGY A — NEAR MISS EVENTS TODAY"]
            if near_miss_events_today:
                for e in near_miss_events_today[-10:]:
                    c = e.get("candidate", {}) or {}
                    lines.append(
                        f"{e.get('timestamp')} | {e.get('symbol')} | "
                        f"score={float(c.get('miss_score', 999)):.2f} | "
                        f"drop={float(c.get('flash_drop_pct', 0)):.2f}% | "
                        f"gap={float(c.get('gap', 0)):.2f}% | "
                        f"pre_ret={float(c.get('pre_return_pct', 0)):.2f}% | "
                        f"pre_slope={float(c.get('pre_slope_pct_per_hour', 0)):.2f}%/hr | "
                        f"fails={c.get('failed', 'unknown')} | "
                        f"price={float(c.get('price', 0)):.2f}"
                    )
                lines.append(f"Total near-miss events today: {len(near_miss_events_today)}")
            else:
                lines.append("None")

            signal_by_day = {}
            for e in events:
                if (
                    e.get("event_type") != "SIGNAL"
                    or not is_rth_timestamp(e.get("timestamp"))
                ):
                    continue
                ts = str(e.get("timestamp", ""))
                d = ts[:10] if len(ts) >= 10 else "unknown"
                signal_by_day.setdefault(d, []).append(e)

            lines += ["", "MULTI-DAY SIGNAL LEDGER"]
            if signal_by_day:
                for d in sorted(signal_by_day.keys())[-10:]:
                    lines.append(f"{d} | signals={len(signal_by_day[d])}")
                    for e in signal_by_day[d][-5:]:
                        lines.append("  " + summarize_signal_event(e))
            else:
                lines.append("No signal events yet.")

            lines += ["", "ORDER / EXECUTION EVENTS TODAY"]
            if execution_events_today:
                for e in execution_events_today[-20:]:
                    lines.append(summarize_execution_event(e))
            else:
                lines.append("None")

            exec_by_day = {}
            for e in events:
                ts = str(e.get("timestamp", ""))
                d = ts[:10] if len(ts) >= 10 else "unknown"
                et = e.get("event_type")
                exec_by_day.setdefault(d, {"buy_attempts": 0, "buy_responses": 0, "buy_errors": 0, "sell_attempts": 0, "sell_responses": 0, "sell_errors": 0})
                if et == "BUY_ATTEMPT":
                    exec_by_day[d]["buy_attempts"] += 1
                elif et == "BUY_RESPONSE":
                    exec_by_day[d]["buy_responses"] += 1
                elif et == "BUY_ERROR":
                    exec_by_day[d]["buy_errors"] += 1
                elif et == "SELL_ATTEMPT":
                    exec_by_day[d]["sell_attempts"] += 1
                elif et == "SELL_RESPONSE":
                    exec_by_day[d]["sell_responses"] += 1
                elif et == "SELL_ERROR":
                    exec_by_day[d]["sell_errors"] += 1

            lines += ["", "MULTI-DAY EXECUTION SUMMARY"]
            if exec_by_day:
                for d in sorted(exec_by_day.keys())[-10:]:
                    x = exec_by_day[d]
                    lines.append(
                        f"{d} | buy_attempts={x['buy_attempts']} buy_responses={x['buy_responses']} "
                        f"buy_errors={x['buy_errors']} sell_attempts={x['sell_attempts']} "
                        f"sell_responses={x['sell_responses']} sell_errors={x['sell_errors']}"
                    )
            else:
                lines.append("No execution events yet.")


            trigger_by_day = {}
            for e in events:
                if e.get("event_type") != "ENTRY_TRIGGER_OCO_ATTEMPT":
                    continue
                d = str(e.get("timestamp", ""))[:10]
                trigger_by_day.setdefault(d, []).append(e)

            lines += ["", "MULTI-DAY TRIGGER LEDGER"]
            if trigger_by_day:
                for d in sorted(trigger_by_day.keys())[-10:]:
                    lines.append(f"{d} | triggers={len(trigger_by_day[d])}")
                    for e in trigger_by_day[d][-20:]:
                        lines.append("  " + summarize_trigger_event(e))
            else:
                lines.append("No trigger events yet.")

            lines += ["", "MULTI-DAY SUMMARY"]
            if by_day:
                for d in sorted(by_day.keys())[-10:]:
                    b = by_day[d]["best"]
                    if b:
                        lines.append(
                            f"{d} | best={b.get('symbol')} score={float(b.get('miss_score', 999)):.2f} "
                            f"drop={float(b.get('flash_drop_pct', 0)):.2f}% "
                            f"gap={float(b.get('gap', 0)):.2f}% | "
                            f"pre_ret={float(b.get('pre_return_pct', 0)):.2f}% "
                            f"pre_slope={float(b.get('pre_slope_pct_per_hour', 0)):.2f}%/hr "
                            f"fails={b.get('failed', 'unknown')} | triggers={by_day[d]['triggers']}"
                        )
                    else:
                        lines.append(f"{d} | no nearest data | triggers={by_day[d]['triggers']}")
            else:
                lines.append("No history yet.")

            # Insert the current P/L summary near the top after every strategy
            # has refreshed its outcome file during this cycle.
            _timing_total_start = time.time()

            _t = time.time()
            _current_pnl_lines = current_pnl_summary_lines(today)
            print(f"TIMING current_pnl_summary: {time.time() - _t:.3f}s", flush=True)

            _t = time.time()
            _live_deployment_lines = live_deployment_summary_lines(today)
            print(f"TIMING live_deployment_summary: {time.time() - _t:.3f}s", flush=True)

            lines[3:3] = ["", *_current_pnl_lines, "", *_live_deployment_lines]

            # End the report with the persistent multi-day P/L matrix. After
            # the US close, today's finalized values are saved under its market
            # date; earlier dates remain available after ledgers roll forward.
            _performance_rows = write_strategy_performance_csv(today)
            print(
                f"STRATEGY_PERFORMANCE_CSV rows={len(_performance_rows)} "
                f"path={STRATEGY_PERFORMANCE_CSV}",
                flush=True,
            )
            lines += ["", *daily_pnl_history_lines(today)]
            lines += ["", *daily_live_deployment_history_lines(today)]
            lines += ["", *daily_market_behavior_history_lines(today)]
            _t = time.time()
            SUMMARY_TXT.write_text("\n".join(lines) + "\n")
            print(f"TIMING output_write: {time.time() - _t:.3f}s", flush=True)
            print(f"TIMING leaderboard_total: {time.time() - _timing_total_start:.3f}s", flush=True)

        except Exception as e:
            print(f"leaderboard error: {type(e).__name__}: {e}", flush=True)

        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
