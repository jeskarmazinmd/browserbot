"""
Exact semantic canonicalization for Module Factory.

Purpose
-------
Identify expressions that are provably the same observable before
hypotheses consume validation capacity.

This module is intentionally conservative. It performs only exact
rewrites whose semantics are known from the Factory feature definitions.

Current exact identity:

    spy_relative_return_N
        = return_N - SPY_return_N

Therefore:

    return_N - spy_relative_return_N
        = SPY_return_N

No empirical similarity, correlation-based merging, or approximate
algebra is performed here.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass


COMMUTATIVE_OPERATIONS = {
    "add",
    "multiply",
}

BINARY_OPERATIONS = {
    "add",
    "subtract",
    "multiply",
    "divide",
}

_RELATIVE_RETURN_RE = re.compile(
    r"^spy_relative_return_(\d+)$"
)

_RETURN_RE = re.compile(
    r"^return_(\d+)$"
)


@dataclass(frozen=True)
class CanonicalExpression:
    operation: str
    operands: tuple["CanonicalExpression", ...] = ()
    value: str | None = None
    lookback: int | None = None

    def __post_init__(self) -> None:
        if not self.operation.strip():
            raise ValueError(
                "operation cannot be empty"
            )

        if self.lookback is not None:
            if self.lookback <= 0:
                raise ValueError(
                    "lookback must be positive"
                )

    def identity_payload(self):
        return {
            "operation": self.operation,
            "operands": [
                operand.identity_payload()
                for operand in self.operands
            ],
            "value": self.value,
            "lookback": self.lookback,
        }

    @property
    def semantic_key(self) -> str:
        payload = json.dumps(
            self.identity_payload(),
            sort_keys=True,
            separators=(",", ":"),
        )

        digest = hashlib.sha256(
            payload.encode()
        ).hexdigest()[:20]

        return f"semantic:{digest}"


def _sort_key(
    expression: CanonicalExpression,
) -> str:
    return json.dumps(
        expression.identity_payload(),
        sort_keys=True,
        separators=(",", ":"),
    )


def _feature_expression(
    name: str,
) -> CanonicalExpression:
    relative_match = (
        _RELATIVE_RETURN_RE.fullmatch(name)
    )

    if relative_match is not None:
        lookback = int(
            relative_match.group(1)
        )

        own_return = CanonicalExpression(
            operation="feature",
            value=f"return_{lookback}",
        )

        spy_return = CanonicalExpression(
            operation="market_return",
            value="SPY",
            lookback=lookback,
        )

        return _canonical_binary(
            "subtract",
            own_return,
            spy_return,
        )

    return CanonicalExpression(
        operation="feature",
        value=name,
    )


def _matching_return_lookback(
    expression: CanonicalExpression,
) -> int | None:
    if expression.operation != "feature":
        return None

    if expression.value is None:
        return None

    match = _RETURN_RE.fullmatch(
        expression.value
    )

    if match is None:
        return None

    return int(match.group(1))


def _canonical_binary(
    operation: str,
    left: CanonicalExpression,
    right: CanonicalExpression,
) -> CanonicalExpression:
    if operation not in BINARY_OPERATIONS:
        raise ValueError(
            f"unsupported binary operation: "
            f"{operation}"
        )

    if operation in COMMUTATIVE_OPERATIONS:
        operands = tuple(
            sorted(
                (left, right),
                key=_sort_key,
            )
        )

        return CanonicalExpression(
            operation=operation,
            operands=operands,
        )

    # Exact semantic reduction:
    #
    # return_N
    #   - (return_N - SPY_return_N)
    # = SPY_return_N
    #
    # This corresponds exactly to:
    #
    # return_N - spy_relative_return_N
    #
    if (
        operation == "subtract"
        and right.operation == "subtract"
        and len(right.operands) == 2
    ):
        inner_left, inner_right = (
            right.operands
        )

        outer_lookback = (
            _matching_return_lookback(left)
        )

        inner_lookback = (
            _matching_return_lookback(
                inner_left
            )
        )

        if (
            outer_lookback is not None
            and outer_lookback
            == inner_lookback
            and left == inner_left
            and inner_right.operation
            == "market_return"
            and inner_right.value == "SPY"
            and inner_right.lookback
            == outer_lookback
        ):
            return inner_right

    return CanonicalExpression(
        operation=operation,
        operands=(left, right),
    )


def canonicalize_expression(
    *,
    feature: str | None = None,
    operation: str | None = None,
    left: str | None = None,
    right: str | None = None,
) -> CanonicalExpression:
    """
    Canonicalize either one named feature or one binary expression.

    Exactly one of these forms is accepted:

        canonicalize_expression(feature="return_30")

    or:

        canonicalize_expression(
            operation="subtract",
            left="return_30",
            right="spy_relative_return_30",
        )
    """

    if feature is not None:
        if (
            operation is not None
            or left is not None
            or right is not None
        ):
            raise ValueError(
                "feature form cannot include "
                "operation operands"
            )

        if not feature.strip():
            raise ValueError(
                "feature cannot be empty"
            )

        return _feature_expression(
            feature
        )

    if operation is None:
        raise ValueError(
            "operation is required"
        )

    if left is None or right is None:
        raise ValueError(
            "binary operation requires "
            "left and right"
        )

    if (
        not left.strip()
        or not right.strip()
    ):
        raise ValueError(
            "expression operands cannot "
            "be empty"
        )

    left_expression = (
        _feature_expression(left)
    )

    right_expression = (
        _feature_expression(right)
    )

    return _canonical_binary(
        operation,
        left_expression,
        right_expression,
    )
