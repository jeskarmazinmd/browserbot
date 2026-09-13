"""Runtime contract for Factory-generated paper/shadow strategies.

Factory strategies are deliberately data-only specifications interpreted by
this module.  They cannot contain arbitrary Python code and have no broker,
account, order-placement, or market-data client.

The original single-feature/threshold contract remains supported.  Richer
Factory hypotheses can use a small bounded expression/predicate language.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping


PAPER_ONLY = True
LIVE_ORDER_PLACEMENT = False

_ALLOWED_EXPRESSION_OPS = frozenset({
    "feature",
    "constant",
    "add",
    "subtract",
    "multiply",
    "divide",
    "negate",
    "abs",
})

_ALLOWED_PREDICATE_OPS = frozenset({
    "gt",
    "gte",
    "lt",
    "lte",
    "between",
    "all",
    "any",
    "not",
})


def _finite_number(value: Any) -> float | None:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _evaluate_expression(
    expression: Mapping[str, Any],
    features: Mapping[str, float],
) -> float | None:
    if not isinstance(expression, Mapping):
        return None

    op = expression.get("op")

    if op == "feature":
        name = expression.get("name")
        if not isinstance(name, str) or not name:
            return None
        return _finite_number(features.get(name))

    if op == "constant":
        return _finite_number(expression.get("value"))

    if op in {"add", "subtract", "multiply", "divide"}:
        left = _evaluate_expression(
            expression.get("left", {}),
            features,
        )
        right = _evaluate_expression(
            expression.get("right", {}),
            features,
        )
        if left is None or right is None:
            return None

        if op == "add":
            return left + right
        if op == "subtract":
            return left - right
        if op == "multiply":
            return left * right
        if right == 0:
            return None
        return left / right

    if op in {"negate", "abs"}:
        value = _evaluate_expression(
            expression.get("value", {}),
            features,
        )
        if value is None:
            return None
        if op == "negate":
            return -value
        return abs(value)

    return None


def _evaluate_predicate(
    predicate: Mapping[str, Any],
    features: Mapping[str, float],
) -> bool:
    if not isinstance(predicate, Mapping):
        return False

    op = predicate.get("op")

    if op in {"gt", "gte", "lt", "lte"}:
        left = _evaluate_expression(
            predicate.get("left", {}),
            features,
        )
        right = _evaluate_expression(
            predicate.get("right", {}),
            features,
        )
        if left is None or right is None:
            return False

        if op == "gt":
            return left > right
        if op == "gte":
            return left >= right
        if op == "lt":
            return left < right
        return left <= right

    if op == "between":
        value = _evaluate_expression(
            predicate.get("value", {}),
            features,
        )
        low = _evaluate_expression(
            predicate.get("low", {}),
            features,
        )
        high = _evaluate_expression(
            predicate.get("high", {}),
            features,
        )
        if value is None or low is None or high is None:
            return False
        return low <= value <= high

    if op in {"all", "any"}:
        items = predicate.get("items")
        if not isinstance(items, (list, tuple)) or not items:
            return False
        values = [
            _evaluate_predicate(item, features)
            for item in items
        ]
        if op == "all":
            return all(values)
        return any(values)

    if op == "not":
        item = predicate.get("item")
        if not isinstance(item, Mapping):
            return False
        return not _evaluate_predicate(item, features)

    return False


def _validate_expression(expression: Mapping[str, Any]) -> None:
    if not isinstance(expression, Mapping):
        raise ValueError("expression must be a mapping")

    op = expression.get("op")
    if op not in _ALLOWED_EXPRESSION_OPS:
        raise ValueError(
            f"unsupported generated expression op: {op!r}"
        )

    if op == "feature":
        name = expression.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("feature expression requires name")
        return

    if op == "constant":
        if _finite_number(expression.get("value")) is None:
            raise ValueError(
                "constant expression requires finite value"
            )
        return

    if op in {"add", "subtract", "multiply", "divide"}:
        _validate_expression(expression.get("left", {}))
        _validate_expression(expression.get("right", {}))
        return

    _validate_expression(expression.get("value", {}))


def _validate_predicate(predicate: Mapping[str, Any]) -> None:
    if not isinstance(predicate, Mapping):
        raise ValueError("predicate must be a mapping")

    op = predicate.get("op")
    if op not in _ALLOWED_PREDICATE_OPS:
        raise ValueError(
            f"unsupported generated predicate op: {op!r}"
        )

    if op in {"gt", "gte", "lt", "lte"}:
        _validate_expression(predicate.get("left", {}))
        _validate_expression(predicate.get("right", {}))
        return

    if op == "between":
        _validate_expression(predicate.get("value", {}))
        _validate_expression(predicate.get("low", {}))
        _validate_expression(predicate.get("high", {}))
        return

    if op in {"all", "any"}:
        items = predicate.get("items")
        if not isinstance(items, (list, tuple)) or not items:
            raise ValueError(
                f"{op} predicate requires non-empty items"
            )
        for item in items:
            _validate_predicate(item)
        return

    _validate_predicate(predicate.get("item", {}))


@dataclass(frozen=True)
class GeneratedStrategySpec:
    module_id: str
    hypothesis_id: str
    specification_hash: str
    scientist: str
    feature: str
    horizon: int
    direction: int
    threshold: float | None = None
    expression: Mapping[str, Any] | None = None
    predicate: Mapping[str, Any] | None = None

    def __post_init__(self):
        if not self.module_id:
            raise ValueError("module_id required")
        if not self.hypothesis_id:
            raise ValueError("hypothesis_id required")
        if not self.specification_hash:
            raise ValueError("specification_hash required")
        if not self.feature and self.expression is None:
            raise ValueError(
                "feature or expression required"
            )
        if self.horizon <= 0:
            raise ValueError("horizon must be positive")
        if self.direction not in (-1, 1):
            raise ValueError(
                "direction must be -1 or +1"
            )
        if self.expression is not None:
            _validate_expression(self.expression)
        if self.predicate is not None:
            _validate_predicate(self.predicate)


@dataclass(frozen=True)
class GeneratedSignal:
    strategy_id: str
    symbol: str
    timestamp: Any
    direction: int
    horizon: int
    data: Mapping[str, Any]


class GeneratedStrategy:
    """Bounded interpreter for Factory-generated paper strategies."""

    PAPER_ONLY = True
    LIVE_ORDER_PLACEMENT = False

    def __init__(self, spec: GeneratedStrategySpec):
        self.spec = spec
        self.name = spec.module_id

    @property
    def strategy_id(self) -> str:
        return self.spec.module_id

    def evaluate_row(
        self,
        *,
        symbol: str,
        timestamp: Any,
        features: Mapping[str, float],
    ) -> GeneratedSignal | None:
        if self.spec.expression is None:
            expression = {
                "op": "feature",
                "name": self.spec.feature,
            }
        else:
            expression = self.spec.expression

        value = _evaluate_expression(
            expression,
            features,
        )
        if value is None:
            return None

        if self.spec.predicate is not None:
            if not _evaluate_predicate(
                self.spec.predicate,
                features,
            ):
                return None
        else:
            threshold = self.spec.threshold
            if threshold is not None:
                if (
                    self.spec.direction > 0
                    and value < threshold
                ):
                    return None
                if (
                    self.spec.direction < 0
                    and value > threshold
                ):
                    return None

        return GeneratedSignal(
            strategy_id=self.spec.module_id,
            symbol=str(symbol),
            timestamp=timestamp,
            direction=self.spec.direction,
            horizon=self.spec.horizon,
            data={
                "factory_generated": True,
                "hypothesis_id":
                    self.spec.hypothesis_id,
                "specification_hash":
                    self.spec.specification_hash,
                "scientist": self.spec.scientist,
                "feature": self.spec.feature,
                "feature_value": value,
                "threshold": self.spec.threshold,
                "expression": self.spec.expression,
                "predicate": self.spec.predicate,
                "paper_only": True,
                "live_order_placement": False,
            },
        )
