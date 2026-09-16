"""Self-contained prospective short-only equity experiment: SHTVOL1."""
from __future__ import annotations
from collections import defaultdict, deque
from datetime import datetime, timezone
import statistics

STRATEGY_ID = 'SHTVOL1'
FAMILY = "SHORT10"
PAPER_ONLY = True
LIVE_ORDER_PLACEMENT = False
FORWARD_START_UTC = "2026-08-10T13:30:00+00:00"
SIDE = "SHORT"
MODE = 'VOL_SHOCK'
PARAMS = {'window': 20, 'z': -2.0, 'ret3': -0.12, 'target': 0.65, 'stop': 0.5}
UNIVERSE = ('SPY', 'QQQ', 'IWM', 'DIA', 'XLK', 'XLF', 'XLE', 'XLV', 'XLY', 'XLP', 'XLI', 'XLU', 'SMH', 'IYT', 'GLD', 'SLV', 'USO', 'TLT', 'NVDA', 'AMD', 'AVGO', 'MSFT', 'AAPL', 'GOOGL', 'META', 'AMZN', 'TSLA', 'NFLX', 'ORCL', 'CRM', 'MU', 'INTC')
MAX_HISTORY = 66


def _ret(prices, minutes):
    if len(prices) < minutes + 1 or prices[-minutes - 1] <= 0:
        return None
    return (prices[-1] / prices[-minutes - 1] - 1) * 100


class Strategy:
    name = STRATEGY_ID

    def __init__(self):
        self._h = defaultdict(lambda: deque(maxlen=MAX_HISTORY))
        self._last = None

    def evaluate(self, snapshot):
        now = snapshot["timestamp"]
        if isinstance(now, str):
            now = datetime.fromisoformat(now.replace("Z", "+00:00"))
        now = now.astimezone(timezone.utc)
        quotes = snapshot.get("quotes", {})
        for symbol in UNIVERSE:
            q = quotes.get(symbol)
            if q and q.get("realtime") is True and float(q.get("bid") or 0) > 0 and float(q.get("ask") or 0) >= float(q.get("bid") or 0):
                self._h[symbol].append((float(q["bid"]) + float(q["ask"])) / 2)
        if now < datetime.fromisoformat(FORWARD_START_UTC):
            return []
        if self._last and (now - self._last).total_seconds() < 20 * 60:
            return []

        candidates = []
        spy5 = _ret(list(self._h["SPY"]), 5)

        for symbol in UNIVERSE:
            q = quotes.get(symbol)
            if not q:
                continue
            p = list(self._h[symbol])
            score = None
            metrics = {"mode": MODE}

            if MODE == "DOWN_TREND" and len(p) >= 31:
                r30, r5 = _ret(p, 30), _ret(p, 5)
                down = sum(b < a for a, b in zip(p[-31:], p[-30:])) / 30
                if r30 is not None and r5 is not None and r30 <= PARAMS["ret30"] and r5 <= PARAMS["ret5"] and down >= PARAMS["down"]:
                    score = -r30 - r5
                    metrics.update({"return_30m_pct": r30, "return_5m_pct": r5, "down_fraction": down})

            elif MODE == "DOWN_ACCEL" and len(p) >= 11:
                r10, r3 = _ret(p, 10), _ret(p, 3)
                if r10 is not None and r3 is not None and r10 <= PARAMS["ret10"] and r3 <= PARAMS["ret3"]:
                    score = -r10 - 2 * r3
                    metrics.update({"return_10m_pct": r10, "return_3m_pct": r3})

            elif MODE == "BREAKDOWN":
                w = int(PARAMS["window"])
                if len(p) >= w + 1:
                    prior = p[-w-1:-1]; hi, lo, cur = max(prior), min(prior), p[-1]
                    width = (hi / lo - 1) * 100 if lo > 0 else 999
                    threshold = lo * (1 - PARAMS["buffer"] / 100)
                    if width <= PARAMS["range"] and cur <= threshold:
                        score = (lo / cur - 1) * 100
                        metrics.update({"prior_range_pct": width, "breakdown_pct": (cur / lo - 1) * 100})

            elif MODE == "FAILED_HIGH":
                w = int(PARAMS["window"])
                if len(p) >= w + 1:
                    window = p[-w-1:]; start, cur, high = window[0], window[-1], max(window)
                    rise = (high / start - 1) * 100 if start > 0 else 0
                    pullback = (high / cur - 1) * 100 if cur > 0 else 0
                    r1 = _ret(p, 1)
                    if r1 is not None and rise >= PARAMS["rise"] and pullback >= PARAMS["pullback"] and r1 < 0:
                        score = rise + pullback
                        metrics.update({"rise_to_high_pct": rise, "pullback_from_high_pct": pullback, "return_1m_pct": r1})

            elif MODE == "REL_WEAK" and symbol != "SPY":
                n = int(PARAMS["lookback"]); own = _ret(p, n); spy = _ret(list(self._h["SPY"]), n)
                if own is not None and spy is not None and own <= PARAMS["own"] and own - spy <= PARAMS["excess"]:
                    score = -(own - spy)
                    metrics.update({"return_pct": own, "spy_return_pct": spy, "excess_vs_spy_pct": own - spy})

            elif MODE == "OVERBOUGHT_FAIL" and len(p) >= 31:
                r30, r5 = _ret(p, 30), _ret(p, 5)
                if r30 is not None and r5 is not None and r30 >= PARAMS["ret30"] and r5 <= PARAMS["ret5"]:
                    score = r30 - r5
                    metrics.update({"return_30m_pct": r30, "reversal_5m_pct": r5})

            elif MODE == "GAP_FADE" and len(p) >= 6:
                close = float(q.get("close") or 0); cur = p[-1]; r5 = _ret(p, 5)
                gap = (cur / close - 1) * 100 if close > 0 else None
                if gap is not None and r5 is not None and gap >= PARAMS["gap"] and r5 <= PARAMS["ret5"]:
                    score = gap - r5
                    metrics.update({"gap_vs_close_pct": gap, "return_5m_pct": r5})

            elif MODE == "VOL_SHOCK":
                w = int(PARAMS["window"])
                if len(p) >= w + 4:
                    one = [(b / a - 1) * 100 for a, b in zip(p[-w-4:-4], p[-w-3:-3]) if a > 0]
                    r3 = _ret(p, 3); sd = statistics.pstdev(one) if len(one) >= 10 else 0
                    z = r3 / (sd * (3 ** 0.5)) if r3 is not None and sd > 0 else 0
                    if r3 is not None and r3 <= PARAMS["ret3"] and z <= PARAMS["z"]:
                        score = -z
                        metrics.update({"return_3m_pct": r3, "shock_z": z, "one_minute_vol_pct": sd})

            elif MODE == "MARKET_CONFIRM" and symbol != "SPY" and spy5 is not None:
                r5 = _ret(p, 5)
                if r5 is not None and spy5 <= PARAMS["spy5"] and r5 <= PARAMS["ret5"] and r5 - spy5 <= PARAMS["excess"]:
                    score = -r5 - spy5
                    metrics.update({"return_5m_pct": r5, "spy_return_5m_pct": spy5, "excess_vs_spy_pct": r5 - spy5})

            if score is not None:
                candidates.append((score, symbol, q, metrics))

        if MODE == "BREADTH_DOWN":
            rows = []
            for symbol in UNIVERSE:
                r5 = _ret(list(self._h[symbol]), 5)
                if r5 is not None and quotes.get(symbol):
                    rows.append((symbol, r5, quotes[symbol]))
            if len(rows) >= 12:
                breadth = sum(r5 < 0 for _, r5, _ in rows) / len(rows)
                weakest = min(rows, key=lambda x: x[1])
                if breadth >= PARAMS["breadth"] and weakest[1] <= PARAMS["ret5"]:
                    candidates.append((-weakest[1], weakest[0], weakest[2], {"mode": MODE, "negative_breadth": breadth, "return_5m_pct": weakest[1]}))

        if not candidates:
            return []
        _, symbol, q, metrics = max(candidates, key=lambda x: x[0])
        self._last = now
        return [{
            "strategy_id": STRATEGY_ID, "timestamp": now.isoformat(),
            "symbol": symbol, "side": "SHORT", "bid": float(q["bid"]), "ask": float(q["ask"]),
            "target_pct": PARAMS["target"], "stop_pct": PARAMS["stop"],
            "max_hold_minutes": 120, "paper_only": True,
            "live_order_placement": False, "research": metrics,
        }]
