"""Versioned config-head dispatch and one strict inference path shared by evaluation.

Architecture is manifest controlled. An omitted architecture always means the
original head; merely installing this module never changes an old checkpoint.
"""
from __future__ import annotations

from collections import Counter

import torch

from action_config_schema import (
    ActionConfigV02Model, DECISIONS, DECODER_POLICY_VERSION as LEGACY_DECODER_POLICY,
    ModelOutputError, RESOURCE_IDS, canonicalize_config, decode_config,
)

LEGACY_MODEL_ARCHITECTURE = "action-config-head.legacy-v1"
FEASIBLE_MODEL_ARCHITECTURE = "action-config-head.feasible-v1"
MODEL_ARCHITECTURES = (LEGACY_MODEL_ARCHITECTURE, FEASIBLE_MODEL_ARCHITECTURE)
SELECTION_RULE_VERSION = "raw-decision-valid-execute-raw-specificity.v1"


def architecture_policies(architecture: str) -> dict:
    if architecture == LEGACY_MODEL_ARCHITECTURE:
        return {"model_architecture": architecture, "decoder_policy": LEGACY_DECODER_POLICY}
    if architecture == FEASIBLE_MODEL_ARCHITECTURE:
        from feasible_config import PARAMETERIZATION_VERSION, DECODER_POLICY_VERSION
        from literal_bindings import BINDING_POLICY_VERSION
        return {"model_architecture": architecture, "parameterization_policy": PARAMETERIZATION_VERSION,
                "binding_policy": BINDING_POLICY_VERSION, "decoder_policy": DECODER_POLICY_VERSION}
    raise ValueError(f"Unsupported model_architecture: {architecture}.")


def validate_head_manifest(manifest: dict) -> str:
    architecture = manifest.get("model_architecture", LEGACY_MODEL_ARCHITECTURE)
    expected = architecture_policies(architecture)
    for name, version in expected.items():
        # Historical manifests omitted these fields. They still select the legacy path.
        if architecture == LEGACY_MODEL_ARCHITECTURE and name not in manifest:
            continue
        if manifest.get(name) != version:
            raise ValueError(f"Unsupported {name}: {manifest.get(name)!r}; expected {version!r}.")
    if architecture == LEGACY_MODEL_ARCHITECTURE:
        for name in ("parameterization_policy", "binding_policy"):
            if manifest.get(name) is not None:
                raise ValueError(f"Legacy architecture cannot declare {name}.")
    return architecture


def create_config_head(architecture: str, **kwargs):
    architecture_policies(architecture)
    if architecture == FEASIBLE_MODEL_ARCHITECTURE:
        from feasible_config import FeasibleActionConfigModel
        return FeasibleActionConfigModel(**kwargs)
    return ActionConfigV02Model(**kwargs)


def slice_parameters(params, index: int):
    if isinstance(params, dict):
        return {name: values[index:index + 1] for name, values in params.items()}
    return params[index:index + 1]


def raw_prediction_record(disc: dict) -> dict:
    head_finite = {name: bool(torch.isfinite(disc[name]).all())
                   for name in ("decision", "resource_id", "stage", "cycle_count")}
    finite = all(head_finite.values())
    return {"finite": finite,
            "head_finite": head_finite,
            "decision": DECISIONS[int(disc["decision"][0].argmax().item())] if head_finite["decision"] else None,
            "resource_ids": [RESOURCE_IDS[int(value)] for value in disc["resource_id"][0].argmax(-1).tolist()],
            "stages": disc["stage"][0].argmax(-1).tolist(),
            "cycle_counts": disc["cycle_count"][0].argmax(-1).tolist()}


def predict_config(disc: dict, params, text: str, input_role: str = "instruction",
                   architecture: str = LEGACY_MODEL_ARCHITECTURE, *, legacy_decoder=None) -> tuple[dict, dict]:
    """Bind only exact durations, before feasible hold construction; then run strict guard.

    No decision, resource, stage, or cycle count is changed to match the text.
    Exceptions retain raw logits' choices and any intermediate config for auditing.
    """
    from input_constraints import validate_instruction_constraints
    if input_role not in {"instruction", "dialogue"}:
        raise ValueError("input_role must be instruction or dialogue.")
    audit = {"raw_prediction": raw_prediction_record(disc), "binding_audit": None,
             "constraint_audit": None}
    predicted = None
    try:
        if architecture == FEASIBLE_MODEL_ARCHITECTURE:
            from feasible_config import decode_feasible_config
            from literal_bindings import extract_exact_duration_bindings
            predicted = decode_feasible_config(disc, params)
            overrides, binding_audit = extract_exact_duration_bindings(text, predicted, input_role=input_role)
            audit["binding_audit"] = binding_audit
            if binding_audit.get("violations") or binding_audit.get("unresolved"):
                raise ModelOutputError("Explicit duration binding has invalid or unresolved scope.")
            predicted = decode_feasible_config(disc, params, duration_overrides=overrides)
        elif architecture == LEGACY_MODEL_ARCHITECTURE:
            predicted = (legacy_decoder or decode_config)(disc, params)
        else:
            raise ValueError(f"Unsupported model_architecture: {architecture}.")
        if input_role == "instruction":
            audit["constraint_audit"] = validate_instruction_constraints(text, predicted)
            if audit["constraint_audit"]["violations"] or audit["constraint_audit"]["unresolved"]:
                raise ModelOutputError("Prediction violates explicit instruction constraints or has unresolved numeric scope.")
        return predicted, audit
    except ModelOutputError as exc:
        exc.raw_prediction = audit["raw_prediction"]
        exc.binding_audit = audit["binding_audit"] or getattr(exc, "binding_audit", None)
        exc.constraint_audit = audit["constraint_audit"] or getattr(exc, "constraint_audit", None)
        if predicted is not None:
            exc.raw_config = predicted
        raise


class RawPredictionMetrics:
    """Metrics on discrete choices before a decoder or instruction guard can reject."""

    def __init__(self):
        self.counts = Counter()
        self.per_decision = {decision: Counter() for decision in DECISIONS}

    def add(self, raw: dict, gold: dict) -> None:
        counts = self.counts
        expected = gold["decision"]
        counts["total"] += 1
        self.per_decision[expected]["total"] += 1
        correct = raw["finite"] and raw["decision"] == expected
        counts["decision_correct"] += int(correct)
        self.per_decision[expected]["correct"] += int(correct)
        if expected != "execute":
            counts["nonexecute_total"] += 1
            counts["nonexecute_prediction"] += int(raw["finite"] and raw["decision"] in DECISIONS[1:])
            counts["false_execution"] += int(raw["decision"] == "execute")
            return
        targets = canonicalize_config(gold)
        for slot, rid in enumerate(targets["resource_id"]):
            counts["resource_slots"] += 1
            counts["resource_correct"] += int(raw["finite"] and raw["resource_ids"][slot] == RESOURCE_IDS[rid])
            if rid:
                counts["active_slots"] += 1
                counts["stage_correct"] += int(raw["finite"] and raw["stages"][slot] == targets["stage"][slot])
                counts["cycle_count_correct"] += int(raw["finite"] and raw["cycle_counts"][slot] == targets["cycle_count"][slot])

    def summary(self) -> dict:
        counts = self.counts
        represented = [values for values in self.per_decision.values() if values["total"]]
        return {**counts, "per_decision": {key: dict(value) for key, value in self.per_decision.items()},
                "decision_accuracy": counts["decision_correct"] / max(1, counts["total"]),
                "macro_decision_accuracy": sum(v["correct"] / v["total"] for v in represented) / max(1, len(represented)),
                "nonexecute_specificity": counts["nonexecute_prediction"] / max(1, counts["nonexecute_total"]),
                "resource_slot_accuracy": counts["resource_correct"] / max(1, counts["resource_slots"]),
                "active_stage_accuracy": counts["stage_correct"] / max(1, counts["active_slots"]),
                "active_cycle_count_accuracy": counts["cycle_count_correct"] / max(1, counts["active_slots"])}
