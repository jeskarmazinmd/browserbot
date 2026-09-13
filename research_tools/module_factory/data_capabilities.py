"""
Data capability awareness for Module Factory.

The factory must distinguish:

    "I tested this and it failed"

from:

    "I cannot properly test this because I do not observe
     the required information."

This module describes the information available to the research
system and evaluates the observability of research ideas.

It does not fetch data and does not inspect validation tapes.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from research_tools.module_factory.idea_library import (
    ResearchIdea,
)


TESTABILITY = (
    "FULLY_TESTABLE",
    "PARTIALLY_TESTABLE",
    "BLOCKED",
)


@dataclass(frozen=True)
class DataCapability:
    name: str
    available: bool
    resolution: str = ""
    source: str = ""
    fields: tuple[str, ...] = ()
    substitutes: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True)
class DataRequirement:
    capability: str
    required: bool = True
    substitutes: tuple[str, ...] = ()
    reason: str = ""


@dataclass(frozen=True)
class TestabilityAssessment:
    idea_id: str
    status: str
    available: tuple[str, ...]
    substituted: tuple[str, ...]
    missing_required: tuple[str, ...]
    missing_optional: tuple[str, ...]
    fidelity: float
    notes: tuple[str, ...] = ()

    def __post_init__(self):
        if self.status not in TESTABILITY:
            raise ValueError(
                f"invalid status: {self.status}"
            )


class DataCapabilities:
    def __init__(
        self,
        capabilities: tuple[
            DataCapability, ...
        ] = (),
    ):
        self._items = {
            item.name: item
            for item in capabilities
        }

    def add(
        self,
        capability: DataCapability,
    ) -> None:
        self._items[
            capability.name
        ] = capability

    def get(
        self,
        name: str,
    ) -> DataCapability | None:
        return self._items.get(name)

    def available(
        self,
        name: str,
    ) -> bool:
        item = self.get(name)

        return bool(
            item is not None
            and item.available
        )

    def current(
        self,
    ) -> tuple[DataCapability, ...]:
        return tuple(
            sorted(
                self._items.values(),
                key=lambda item: item.name,
            )
        )

    def available_names(
        self,
    ) -> set[str]:
        return {
            item.name
            for item in self._items.values()
            if item.available
        }


# Maps conceptual observables from the Idea Library to the
# information capabilities they ideally require.
#
# Some current features are derived from minute prices and are
# therefore fully testable even without richer raw market data.
OBSERVABLE_REQUIREMENTS = {
    "return": (
        DataRequirement(
            "minute_price",
            reason="Price changes require price history.",
        ),
    ),
    "relative_return": (
        DataRequirement(
            "minute_price",
        ),
        DataRequirement(
            "market_context",
        ),
    ),
    "market_return": (
        DataRequirement(
            "market_context",
        ),
    ),
    "cross_sectional_rank": (
        DataRequirement(
            "cross_sectional_universe",
        ),
    ),
    "residual_return": (
        DataRequirement(
            "minute_price",
        ),
        DataRequirement(
            "market_context",
        ),
    ),
    "volatility": (
        DataRequirement(
            "minute_price",
        ),
    ),
    "acceleration": (
        DataRequirement(
            "minute_price",
        ),
    ),
    "range_position": (
        DataRequirement(
            "minute_price",
        ),
    ),
    "autocorrelation": (
        DataRequirement(
            "minute_price",
        ),
    ),
    "sign_persistence": (
        DataRequirement(
            "minute_price",
        ),
    ),
    "skew": (
        DataRequirement(
            "minute_price",
        ),
    ),
    "kurtosis": (
        DataRequirement(
            "minute_price",
        ),
    ),
    "volume": (
        DataRequirement(
            "volume",
            substitutes=(
                "quote_activity",
            ),
            reason=(
                "True traded volume is preferred; "
                "quote activity is only a proxy."
            ),
        ),
    ),
    "spread": (
        DataRequirement(
            "bid_ask",
            reason=(
                "Spread requires bid and ask observations."
            ),
        ),
    ),
    "liquidity": (
        DataRequirement(
            "bid_ask",
            substitutes=(
                "volume",
                "quote_activity",
            ),
            reason=(
                "Bid/ask is preferred for direct "
                "short-horizon liquidity measurement."
            ),
        ),
    ),
    "trade_count": (
        DataRequirement(
            "trades",
        ),
    ),
    "order_flow": (
        DataRequirement(
            "trades",
            substitutes=(
                "quote_activity",
            ),
        ),
    ),
    "order_imbalance": (
        DataRequirement(
            "order_book",
            substitutes=(
                "trades",
            ),
        ),
    ),
    "depth": (
        DataRequirement(
            "order_book",
        ),
    ),
    "sector_return": (
        DataRequirement(
            "sector_context",
        ),
    ),
    "industry_return": (
        DataRequirement(
            "industry_context",
        ),
    ),
    "options_iv": (
        DataRequirement(
            "options",
        ),
    ),
    "options_skew": (
        DataRequirement(
            "options",
        ),
    ),
    "event_state": (
        DataRequirement(
            "events",
        ),
    ),
    "news_state": (
        DataRequirement(
            "news",
        ),
    ),
    "fundamental_state": (
        DataRequirement(
            "fundamentals",
        ),
    ),
    "subminute_return": (
        DataRequirement(
            "subminute_price",
        ),
    ),
}


def requirements_for_idea(
    idea: ResearchIdea,
) -> tuple[DataRequirement, ...]:
    requirements = []

    seen = set()

    for observable in idea.observables:
        for requirement in (
            OBSERVABLE_REQUIREMENTS.get(
                observable,
                (),
            )
        ):
            key = (
                requirement.capability,
                requirement.required,
                requirement.substitutes,
            )

            if key in seen:
                continue

            seen.add(key)
            requirements.append(
                requirement
            )

    return tuple(requirements)


def assess_idea(
    idea: ResearchIdea,
    capabilities: DataCapabilities,
) -> TestabilityAssessment:
    requirements = requirements_for_idea(
        idea
    )

    available = []
    substituted = []
    missing_required = []
    missing_optional = []
    notes = []

    if not requirements:
        return TestabilityAssessment(
            idea_id=idea.idea_id,
            status="PARTIALLY_TESTABLE",
            available=(),
            substituted=(),
            missing_required=(),
            missing_optional=(),
            fidelity=0.5,
            notes=(
                "No explicit capability mapping exists "
                "for this idea's observables.",
            ),
        )

    total_weight = 0.0
    achieved_weight = 0.0

    for requirement in requirements:
        weight = (
            1.0
            if requirement.required
            else 0.5
        )

        total_weight += weight

        if capabilities.available(
            requirement.capability
        ):
            available.append(
                requirement.capability
            )
            achieved_weight += weight
            continue

        substitute = next(
            (
                name
                for name
                in requirement.substitutes
                if capabilities.available(name)
            ),
            None,
        )

        if substitute is not None:
            substituted.append(
                f"{requirement.capability}"
                f"<-{substitute}"
            )

            # A proxy is useful, but not equivalent to
            # observing the intended variable.
            achieved_weight += (
                weight * 0.55
            )

            notes.append(
                f"{requirement.capability} "
                f"approximated by {substitute}"
            )
            continue

        if requirement.required:
            missing_required.append(
                requirement.capability
            )
        else:
            missing_optional.append(
                requirement.capability
            )

        if requirement.reason:
            notes.append(
                requirement.reason
            )

    fidelity = (
        achieved_weight / total_weight
        if total_weight
        else 0.0
    )

    if missing_required:
        if achieved_weight > 0:
            status = "PARTIALLY_TESTABLE"
        else:
            status = "BLOCKED"

    elif substituted:
        status = "PARTIALLY_TESTABLE"

    else:
        status = "FULLY_TESTABLE"

    return TestabilityAssessment(
        idea_id=idea.idea_id,
        status=status,
        available=tuple(
            sorted(set(available))
        ),
        substituted=tuple(
            sorted(set(substituted))
        ),
        missing_required=tuple(
            sorted(
                set(missing_required)
            )
        ),
        missing_optional=tuple(
            sorted(
                set(missing_optional)
            )
        ),
        fidelity=round(
            fidelity,
            6,
        ),
        notes=tuple(notes),
    )


def current_factory_capabilities(
) -> DataCapabilities:
    """
    Conservative description of information VERIFIED in the
    existing Schwab minute-snapshot research tapes.

    Important distinctions:
    - bid/ask is sampled top-of-book, not a full order book.
    - last trade/size is a snapshot, not a complete trade tape.
    - sizes are not cumulative minute volume.
    - millisecond event timestamps do not create a sub-minute
      price history.
    """

    return DataCapabilities(
        (
            DataCapability(
                name="minute_price",
                available=True,
                resolution="1 minute",
                source="Schwab minute quote tapes",
                fields=(
                    "legacy_price",
                    "last",
                    "mark",
                    "regular_last",
                ),
            ),
            DataCapability(
                name="market_context",
                available=True,
                resolution="1 minute",
                source="SPY in minute tapes",
                fields=("SPY",),
            ),
            DataCapability(
                name="cross_sectional_universe",
                available=True,
                resolution="1 minute",
                source="multi-symbol minute tapes",
                notes=(
                    "Thousands of simultaneously "
                    "observed securities."
                ),
            ),
            DataCapability(
                name="bid_ask",
                available=True,
                resolution="sampled once per minute",
                source="Schwab minute quote tapes",
                fields=(
                    "bid",
                    "ask",
                    "bid_time_ms",
                    "ask_time_ms",
                ),
                notes=(
                    "Verified top-of-book snapshots; "
                    "not full depth."
                ),
            ),
            DataCapability(
                name="quoted_depth",
                available=True,
                resolution="sampled once per minute",
                source="Schwab minute quote tapes",
                fields=(
                    "bid_size_raw",
                    "ask_size_raw",
                ),
                notes=(
                    "Displayed best bid/ask sizes only."
                ),
            ),
            DataCapability(
                name="trade_snapshot",
                available=True,
                resolution="sampled once per minute",
                source="Schwab minute quote tapes",
                fields=(
                    "last",
                    "last_size_raw",
                    "trade_time_ms",
                    "last_mic",
                ),
                notes=(
                    "Most recent observed trade state; "
                    "not a complete trade stream."
                ),
            ),
            DataCapability(
                name="quote_timing",
                available=True,
                resolution="millisecond timestamps",
                source="Schwab minute quote tapes",
                fields=(
                    "quote_time_ms",
                    "bid_time_ms",
                    "ask_time_ms",
                    "observed_at_utc",
                ),
            ),
            DataCapability(
                name="venue_context",
                available=True,
                resolution="sampled once per minute",
                source="Schwab minute quote tapes",
                fields=(
                    "last_mic",
                    "bid_mic",
                    "ask_mic",
                ),
            ),
            DataCapability(
                name="quote_activity",
                available=True,
                resolution="snapshot-derived proxy",
                source="Schwab minute quote tapes",
                substitutes=(
                    "volume",
                    "trades",
                ),
                notes=(
                    "Can derive quote freshness/change "
                    "proxies, but not event counts."
                ),
            ),
            DataCapability(
                name="volume",
                available=False,
                substitutes=(
                    "trade_snapshot",
                    "quote_activity",
                ),
                notes=(
                    "last_size_raw is not cumulative "
                    "minute volume."
                ),
            ),
            DataCapability(
                name="trades",
                available=False,
                substitutes=(
                    "trade_snapshot",
                    "quote_activity",
                ),
                notes=(
                    "No complete sequence of trades."
                ),
            ),
            DataCapability(
                name="order_book",
                available=False,
                substitutes=(
                    "quoted_depth",
                ),
                notes=(
                    "Only best bid/ask and displayed "
                    "sizes are observed."
                ),
            ),
            DataCapability(
                name="subminute_price",
                available=False,
                substitutes=(
                    "quote_timing",
                    "trade_snapshot",
                ),
                notes=(
                    "Millisecond timestamps describe "
                    "event freshness, not a sub-minute "
                    "price path."
                ),
            ),
            DataCapability(
                name="sector_context",
                available=False,
            ),
            DataCapability(
                name="industry_context",
                available=False,
            ),
            DataCapability(
                name="options",
                available=False,
            ),
            DataCapability(
                name="events",
                available=False,
            ),
            DataCapability(
                name="news",
                available=False,
            ),
            DataCapability(
                name="fundamentals",
                available=False,
            ),
        )
    )
