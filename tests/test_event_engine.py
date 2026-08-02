from datetime import datetime, timezone

from engine.events import QuoteEvent
from engine.dispatcher import EventDispatcher
from tests.event_strategies.test_strategy import TestStrategy


dispatcher = EventDispatcher()
dispatcher.register(TestStrategy())

for price in [100, 101, 102]:
    signals = dispatcher.dispatch_quote(
        QuoteEvent(
            timestamp=datetime.now(timezone.utc),
            symbol="TEST",
            price=price,
        )
    )

    if signals:
        print(signals)
