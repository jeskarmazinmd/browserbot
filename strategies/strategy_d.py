from typing import Any
from engine.events import SignalEvent
from ._flash_common import FlashReboundState

class StrategyD(FlashReboundState):
    name = "D"
    STRATEGY_ID = "D"

    def on_snapshot(self, snapshot) -> list[SignalEvent]:
        self._update(snapshot)
        signals = []

        for symbol, quote in snapshot.quotes.items():
            price = float(quote.price)
            low = self.low.get(symbol, price)

            drop_pct = ((low / price) - 1.0) * 100.0 if price else 0.0
            rebound_pct = ((price / low) - 1.0) * 100.0 if low else 0.0

            if drop_pct >= 0.9 and rebound_pct >= 0.2:
                signals.append(
                    SignalEvent(
                        timestamp=snapshot.timestamp,
                        strategy_id=self.STRATEGY_ID,
                        symbol=symbol,
                        signal_type="SIGNAL",
                        data={
                            "entry_price": price,
                            "stop_price": price * (1.0 - 0.02),
                            "setup": "0.9% flash drop, 0.2% rebound",
                            "live_order_placement": False,
                            "flash_drop_pct": drop_pct,
                            "rebound_pct": rebound_pct,
                        },
                    )
                )
                self._reset_if_recovered(symbol, price)

        return signals
