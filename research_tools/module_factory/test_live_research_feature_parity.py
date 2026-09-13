import math
import unittest
from datetime import datetime, timedelta, timezone

from research_tools.cascade_reversal_study import Bar

from research_tools.module_factory.feature_matrix import (
    build_feature_matrix,
)

from research_tools.module_factory.live_feature_engine import (
    LiveFeatureEngine,
)

from research_tools.module_factory.live_minute_feed import (
    CompletedMinute,
)


class LiveResearchFeatureParityTests(unittest.TestCase):
    def setUp(self):
        self.base = datetime(
            2026,
            9,
            3,
            14,
            0,
            tzinfo=timezone.utc,
        )

    def price_aaa(self, i):
        # Deliberately nonlinear and asymmetric.
        return (
            100.0
            + 0.07 * i
            + 0.9 * math.sin(i / 4.3)
            + 0.35 * math.cos(i / 9.1)
            + (i % 7) * 0.013
        )

    def price_bbb(self, i):
        return (
            75.0
            - 0.025 * i
            + 0.65 * math.sin(i / 5.7)
            - 0.22 * math.cos(i / 3.8)
            + (i % 5) * 0.019
        )

    def price_spy(self, i):
        return (
            500.0
            + 0.04 * i
            + 1.1 * math.sin(i / 8.2)
            + 0.18 * math.cos(i / 2.9)
        )

    def bar(self, minute, price):
        return Bar(
            minute=minute,
            open=price,
            high=price + 0.01,
            low=price - 0.01,
            close=price,
        )

    def histories(self, count=90):
        bars = {
            "AAA": [],
            "BBB": [],
            "SPY": [],
        }

        minutes = []

        for i in range(count):
            minute = self.base + timedelta(minutes=i)

            aaa = self.price_aaa(i)
            bbb = self.price_bbb(i)
            spy = self.price_spy(i)

            bars["AAA"].append(
                self.bar(minute, aaa)
            )
            bars["BBB"].append(
                self.bar(minute, bbb)
            )
            bars["SPY"].append(
                self.bar(minute, spy)
            )

            minutes.append(
                CompletedMinute(
                    minute=minute,
                    prices={
                        "AAA": aaa,
                        "BBB": bbb,
                        "SPY": spy,
                    },
                )
            )

        return bars, minutes

    def test_every_common_feature_matches(self):
        bars, minutes = self.histories()

        research_rows = build_feature_matrix(
            bars,
            horizons=(1,),
            max_lookback=60,
            stride=1,
        )

        research = {
            (row.symbol, row.minute): row
            for row in research_rows
        }

        engine = LiveFeatureEngine(
            max_history_minutes=121
        )

        compared_rows = 0
        compared_features = 0
        self._mismatches = {}

        for completed in minutes:
            live_rows = engine.consume(completed)

            for live in live_rows:
                key = (
                    live.symbol,
                    live.timestamp,
                )

                # Research rows require a forward outcome,
                # so the final historical minute is omitted.
                # Parity concerns feature semantics only:
                # compare timestamps available in both paths.
                historical = research.get(key)

                if historical is None:
                    continue

                unsupported_live = {
                    f"range_position_{lookback}"
                    for lookback in (5, 10, 20, 30, 60)
                }

                self.assertFalse(
                    unsupported_live
                    & set(live.features),
                    msg=(
                        "OHLC-dependent range_position "
                        "features must not be exposed "
                        "by the close-only live engine"
                    ),
                )

                expected_live_names = (
                    set(historical.features)
                    - unsupported_live
                )

                self.assertEqual(
                    set(live.features),
                    expected_live_names,
                    msg=(
                        "Live feature vocabulary differs "
                        "from the reproducible research "
                        "feature vocabulary"
                    ),
                )

                mismatches = {}

                for name in sorted(
                    expected_live_names
                ):
                    live_value = live.features[name]
                    research_value = (
                        historical.features[name]
                    )

                    if (
                        math.isnan(live_value)
                        and math.isnan(research_value)
                    ):
                        continue

                    if not math.isclose(
                        live_value,
                        research_value,
                        rel_tol=1e-12,
                        abs_tol=1e-12,
                    ):
                        mismatches.setdefault(
                            name,
                            (
                                live_value,
                                research_value,
                            ),
                        )

                    compared_features += 1

                if mismatches:
                    self._mismatches.update(
                        mismatches
                    )

                compared_rows += 1

                compared_rows += 1

        self.assertFalse(
            self._mismatches,
            msg=(
                "Feature mismatches: "
                + ", ".join(
                    f"{name}="
                    f"live:{values[0]!r}/"
                    f"research:{values[1]!r}"
                    for name, values
                    in sorted(
                        self._mismatches.items()
                    )
                )
            ),
        )

        # 90 minutes gives plenty of post-warmup
        # comparisons for two non-SPY symbols.
        self.assertGreater(
            compared_rows,
            20,
        )

        self.assertGreater(
            compared_features,
            1000,
        )

    def test_live_engine_has_no_research_outcomes(self):
        _, minutes = self.histories(70)

        engine = LiveFeatureEngine(
            max_history_minutes=121
        )

        rows = ()

        for completed in minutes:
            rows = engine.consume(completed)

        self.assertTrue(rows)

        for row in rows:
            self.assertFalse(
                hasattr(row, "forward_returns")
            )

            self.assertFalse(
                any(
                    "forward" in name.lower()
                    or "future" in name.lower()
                    for name in row.features
                )
            )


if __name__ == "__main__":
    unittest.main()
