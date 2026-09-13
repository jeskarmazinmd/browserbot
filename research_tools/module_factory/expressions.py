"""
Mathematical expression generation for Module Factory.

The factory is not given named trading strategies.  It constructs new
observables from existing observables and submits them to the same agnostic
discovery machinery.

Generation 1 deliberately favors simple, interpretable mathematics.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from research_tools.module_factory.feature_matrix import FeatureRow


COMMUTATIVE = {"add", "multiply"}
BINARY = {"add", "subtract", "multiply", "divide"}
UNARY = {"absolute", "square"}


@dataclass(frozen=True)
class ExpressionSpec:
    operation: str
    left: str
    right: str | None = None
    generation: int = 1

    @property
    def canonical(self) -> dict:
        left = self.left
        right = self.right

        if (
            self.operation in COMMUTATIVE
            and right is not None
            and right < left
        ):
            left, right = right, left

        return {
            "operation": self.operation,
            "left": left,
            "right": right,
            "generation": self.generation,
        }

    @property
    def expression_id(self) -> str:
        payload = json.dumps(
            self.canonical,
            sort_keys=True,
            separators=(",", ":"),
        )
        return "EX-" + hashlib.sha1(
            payload.encode()
        ).hexdigest()[:12].upper()

    @property
    def name(self) -> str:
        op = self.operation

        if op == "absolute":
            return f"abs({self.left})"

        if op == "square":
            return f"square({self.left})"

        symbol = {
            "add": "+",
            "subtract": "-",
            "multiply": "*",
            "divide": "/",
        }[op]

        return f"({self.left}{symbol}{self.right})"


def _safe_number(value) -> float | None:
    if not isinstance(value, (int, float)):
        return None

    value = float(value)

    if not math.isfinite(value):
        return None

    return value


def evaluate_expression(
    expression: ExpressionSpec,
    features: dict[str, float],
) -> float:
    left = _safe_number(features.get(expression.left))

    if left is None:
        return math.nan

    op = expression.operation

    if op == "absolute":
        return abs(left)

    if op == "square":
        value = left * left
        return value if math.isfinite(value) else math.nan

    right = _safe_number(features.get(expression.right))

    if right is None:
        return math.nan

    if op == "add":
        value = left + right

    elif op == "subtract":
        value = left - right

    elif op == "multiply":
        value = left * right

    elif op == "divide":
        scale = max(abs(left), abs(right), 1.0)
        epsilon = 1e-12 * scale

        if abs(right) <= epsilon:
            return math.nan

        value = left / right

    else:
        raise ValueError(
            f"unknown expression operation: {op}"
        )

    return value if math.isfinite(value) else math.nan


def _family(name: str) -> str:
    if "_" not in name:
        return name

    # Remove trailing integer lookback when present.
    head, tail = name.rsplit("_", 1)

    if tail.isdigit():
        return head

    return name


def _lookback(name: str) -> int | None:
    if "_" not in name:
        return None

    tail = name.rsplit("_", 1)[-1]

    return int(tail) if tail.isdigit() else None


def generate_unary(
    feature_names: list[str],
) -> list[ExpressionSpec]:

    result = []

    for feature in sorted(set(feature_names)):
        result.append(
            ExpressionSpec(
                operation="absolute",
                left=feature,
            )
        )
        result.append(
            ExpressionSpec(
                operation="square",
                left=feature,
            )
        )

    return result


def generate_timescale_expressions(
    feature_names: list[str],
) -> list[ExpressionSpec]:
    """
    Compare the same mathematical quantity across different horizons.

    Examples:
        return_5 - return_20
        volatility_5 / volatility_20

    No market interpretation is imposed.
    """

    grouped: dict[str, list[tuple[int, str]]] = {}

    for feature in sorted(set(feature_names)):
        lookback = _lookback(feature)

        if lookback is None:
            continue

        grouped.setdefault(
            _family(feature),
            [],
        ).append((lookback, feature))

    result = []

    for items in grouped.values():
        items.sort()

        for i, (_, shorter) in enumerate(items):
            for _, longer in items[i + 1:]:
                result.append(
                    ExpressionSpec(
                        operation="subtract",
                        left=shorter,
                        right=longer,
                    )
                )
                result.append(
                    ExpressionSpec(
                        operation="divide",
                        left=shorter,
                        right=longer,
                    )
                )

    return result


def generate_pairwise(
    feature_names: list[str],
    *,
    operations: tuple[str, ...] = (
        "subtract",
        "multiply",
        "divide",
    ),
    max_pairs: int | None = None,
) -> list[ExpressionSpec]:
    """
    Broad cross-family mathematical interaction generator.

    Deterministic ordering allows reproducible bounded searches.
    """

    features = sorted(set(feature_names))
    result = []
    pairs_seen = 0

    for i, left in enumerate(features):
        for right in features[i + 1:]:
            if max_pairs is not None and pairs_seen >= max_pairs:
                return result

            pairs_seen += 1

            for operation in operations:
                result.append(
                    ExpressionSpec(
                        operation=operation,
                        left=left,
                        right=right,
                    )
                )

                # Subtraction and division are directional.
                if operation in {"subtract", "divide"}:
                    result.append(
                        ExpressionSpec(
                            operation=operation,
                            left=right,
                            right=left,
                        )
                    )

    return result


def generation_one(
    feature_names: list[str],
    *,
    include_broad_pairwise: bool = True,
    max_pairs: int | None = None,
) -> list[ExpressionSpec]:

    expressions = []

    expressions.extend(generate_unary(feature_names))
    expressions.extend(
        generate_timescale_expressions(feature_names)
    )

    if include_broad_pairwise:
        expressions.extend(
            generate_pairwise(
                feature_names,
                max_pairs=max_pairs,
            )
        )

    unique = {}

    for expression in expressions:
        unique[expression.expression_id] = expression

    return sorted(
        unique.values(),
        key=lambda x: x.expression_id,
    )


def add_expressions_to_rows(
    rows: list[FeatureRow],
    expressions: list[ExpressionSpec],
) -> list[FeatureRow]:
    """
    Add generated mathematical observables to existing rows.

    Forward outcomes are untouched.
    """

    for row in rows:
        additions = {}

        for expression in expressions:
            additions[expression.expression_id] = (
                evaluate_expression(
                    expression,
                    row.features,
                )
            )

        row.features.update(additions)

    return rows


def expression_catalog(
    expressions: list[ExpressionSpec],
) -> dict[str, ExpressionSpec]:
    return {
        expression.expression_id: expression
        for expression in expressions
    }
