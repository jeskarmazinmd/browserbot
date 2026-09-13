"""Compile frozen causal hypotheses into bounded, data-only strategies.

This is intentionally an interpreter target, not a Python code generator.
Only the expression/predicate grammar validated by GeneratedStrategySpec can
reach the shadow runtime.
"""

from __future__ import annotations

from typing import Any, Mapping

from research_tools.module_factory.generated_strategy import GeneratedStrategySpec


def _module_id(hypothesis_id: str, label: str) -> str:
    suffix = hypothesis_id.split(":")[-1][:12].upper()
    clean = "".join(char if char.isalnum() else "_" for char in label.upper())
    return f"FM_{suffix}_{clean[:16]}"


def compile_frozen_hypothesis(frozen: Any) -> tuple[GeneratedStrategySpec, ...]:
    """Translate supported causal parameter shapes without scientist coupling.

    Scientists may emit explicit ``generated_rules``. Legacy discoveries are
    inferred from threshold parameter conventions for backward compatibility.
    Unsupported shapes fail closed and remain historical research records.
    """
    source = frozen.specification
    params = dict(source.parameters)
    rules = params.get("generated_rules")
    if rules is None:
        if all(key in params for key in ("low_threshold", "high_threshold", "direction_low", "direction_high")):
            condition_feature = (
                source.features[1]
                if source.scientist == "regime" and len(source.features) > 1
                else source.features[0]
            )
            rules = (
                {"label": "LOW", "direction": params["direction_low"],
                 "predicate": {"op": "lte", "left": {"op": "feature", "name": condition_feature},
                               "right": {"op": "constant", "value": params["low_threshold"]}}},
                {"label": "HIGH", "direction": params["direction_high"],
                 "predicate": {"op": "gte", "left": {"op": "feature", "name": condition_feature},
                               "right": {"op": "constant", "value": params["high_threshold"]}}},
            )
        elif "threshold" in params and source.direction in (-1, 1):
            rules = ({"label": "MAIN", "direction": source.direction,
                      "threshold": params["threshold"]},)
        elif "predicate" in params and source.direction in (-1, 1):
            rules = ({"label": "MAIN", "direction": source.direction,
                      "predicate": params["predicate"],
                      "expression": params.get("expression")},)
        else:
            return ()
    if not isinstance(rules, (list, tuple)) or not rules:
        return ()

    compiled = []
    for index, raw in enumerate(rules):
        if not isinstance(raw, Mapping):
            return ()
        label = str(raw.get("label") or index)
        direction = int(raw.get("direction", source.direction or 0))
        feature = str(raw.get("feature") or source.features[0])
        compiled.append(GeneratedStrategySpec(
            module_id=_module_id(frozen.hypothesis_id, label),
            hypothesis_id=frozen.hypothesis_id,
            specification_hash=frozen.specification_hash,
            scientist=source.scientist,
            feature=feature,
            horizon=int(raw.get("horizon", source.horizon)),
            direction=direction,
            threshold=(None if raw.get("threshold") is None else float(raw["threshold"])),
            expression=raw.get("expression"),
            predicate=raw.get("predicate"),
        ))
    return tuple(compiled)
