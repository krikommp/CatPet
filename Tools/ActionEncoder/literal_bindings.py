"""Auditable exact-duration bindings for the existing instruction grammar.

The model owns decision, resources, stages and cycle counts. This module returns
only literal duration overrides; it never edits the supplied prediction. The
caller must decode again with these overrides (including feasible hold mapping)
and run the shared instruction guard on that final result.
"""
from __future__ import annotations

import copy
import re
from typing import Any

from action_config_schema import (
    ModelOutputError, RESOURCE_SPECS, RESOURCE_TO_ID, format_input_text,
    validate_training_config,
)
from input_constraints import (
    ALIASES, DURATION, NUMBER, ORDINAL, number_value, validate_instruction_constraints,
)

BINDING_POLICY_VERSION = "explicit-duration-binding.v1"
_CLAUSES = re.compile(r"[^，,；;。]+")
_DIRECT_NEGATION = r"(?:不要|不许|不能|不得|禁止|别|不需要|无需)\s*"
_REQUEST_PREFIX = r"(?:(?:然后|接着|随后|同时|先|再|请你|请|麻烦你|麻烦|帮我)\s*){0,3}"
_CYCLE_SCOPE = r"(?:每[次下遍]|" + ORDINAL.pattern + r")"
_DURATION_COPULA = r"(?:(?:用时|时长|持续时间|持续|耗时|用)\s*)?(?:(?:为|是)\s*)?"


def _positive_clause_patterns(rid: str) -> tuple[re.Pattern, re.Pattern]:
    """A deliberately small positive grammar, intersected with the old guard.

    After a known request/action/count prefix, a duration clause may contain
    only a cycle scope, a duration copula, and the literal. Further literals
    require their own ordinal/each scope. Unknown qualifiers and unrelated
    nouns cannot be removed or ignored to make a clause match.
    """
    action = r"(?:" + ALIASES[rid] + r")(?:\s*" + NUMBER + r"[次下遍])?"
    declaration = re.compile(r"\s*" + _REQUEST_PREFIX + action + r"\s*")
    # Both 点头第一次1秒 and 第一次点头1秒 carry an explicit local scope.
    first_scope = (r"(?:" + _REQUEST_PREFIX + action + r"\s*(?:" + _CYCLE_SCOPE + r"\s*)?|"
                   + _CYCLE_SCOPE + r"\s*" + _REQUEST_PREFIX + action + r"\s*|"
                   + r"(?:" + _CYCLE_SCOPE + r"\s*)?)")
    exact = _DURATION_COPULA + DURATION.pattern
    continuation = r"\s*" + _CYCLE_SCOPE + r"\s*(?:" + action + r"\s*)?" + exact
    duration = re.compile(r"\s*" + first_scope + exact
                          + r"(?:" + continuation + r")*\s*", re.I)
    return declaration, duration


def _unsupported_positive_context(
    text: str, checks: list[dict[str, Any]], flat: list[tuple[int, dict[str, Any]]],
) -> dict[str, Any] | None:
    """Require positive syntax for each bound clause and its action anchors.

    The shared guard supplies resource/count/reference checks, but its numeric
    recognition alone is not authorization to overwrite a model duration.
    Without any exact check this additional grammar is inapplicable.
    """
    exact_checks = [check for check in checks if check["kind"] == "exact_duration_ms"]
    if not exact_checks:
        return None
    rids = {flat[check["action_index"]][1]["resource_id"] for check in exact_checks}
    patterns = {rid: _positive_clause_patterns(rid) for rid in rids}
    active_rid = None
    for clause_match in _CLAUSES.finditer(text):
        clause = clause_match.group()
        reason = None
        if DURATION.search(clause):
            scoped_rids = {flat[check["action_index"]][1]["resource_id"]
                           for check in exact_checks if check["span"] == clause}
            if len(scoped_rids) != 1 or not patterns[next(iter(scoped_rids))][1].fullmatch(clause):
                reason = "unrecognized_exact_duration_clause"
            else:
                rid = next(iter(scoped_rids))
                if re.search(ALIASES[rid], clause):
                    active_rid = rid
                elif active_rid != rid:
                    reason = "interrupted_positive_action_scope"
        else:
            active_rid = None
            for rid, (declaration, _) in patterns.items():
                if re.search(ALIASES[rid], clause):
                    if declaration.fullmatch(clause):
                        active_rid = rid
                    else:
                        reason = "unrecognized_positive_action_anchor"
                        break
        if reason:
            return {"reason": reason, "span": clause,
                    "start": clause_match.start(), "end": clause_match.end()}
    return None


def _source_spans(text: str, check: dict[str, Any]) -> list[dict[str, Any]]:
    """Recover provenance only for exact checks already parsed by the guard.

    This deliberately does not introduce an alternative duration grammar. A
    repeated identical literal can supply multiple pieces of matching evidence;
    all their original offsets are retained, rather than guessing one location.
    """
    sources = []
    for clause_match in _CLAUSES.finditer(text):
        clause = clause_match.group()
        if clause != check["span"]:
            continue
        ordinals = list(ORDINAL.finditer(clause))
        for literal in DURATION.finditer(clause):
            expected = number_value(literal.group(1))
            expected *= 1 if literal.group(2).lower() in ("毫秒", "ms") else 1000
            if expected != check["expected"]:
                continue
            preceding = [ordinal for ordinal in ordinals if ordinal.end() <= literal.start()]
            if preceding:
                if number_value(preceding[-1].group(1)) - 1 != check["cycle_index"]:
                    continue
            elif check["cycle_index"] != 0 and not re.search(r"每[次下遍]", clause[:literal.start()]):
                continue
            start, end = clause_match.start() + literal.start(), clause_match.start() + literal.end()
            sources.append({
                "text": text[start:end], "start": start, "end": end,
                "scope_text": clause, "scope_start": clause_match.start(),
                "scope_end": clause_match.end(),
            })
    return sources


def extract_exact_duration_bindings(
    text: str, config: dict[str, Any], input_role: str = "instruction",
) -> tuple[dict[tuple[int, int], int], dict[str, Any]]:
    """Return text-derived overrides indexed by canonical action and cycle.

    Only positively scoped clauses also supported by the shared guard can bind.
    Unresolved syntax, contradictory literals, wrong resource/count selection,
    invalid references, and non-duration constraint violations fail closed with
    ``ModelOutputError.binding_audit``. Duration-dependent comparisons involving
    a binding are deferred to the caller's mandatory final guard.
    """
    format_input_text(text, input_role)  # Validate the public role/text contract.
    audit: dict[str, Any] = {
        "policy": BINDING_POLICY_VERSION, "input_role": input_role,
        "no_silent_repair": True, "coverage_is_partial": True,
        "binding_syntax": "positive-exact-clause-subset",
        "structural_fields_unchanged": True, "bindings": [],
        "rejections": [], "deferred_duration_constraints": [],
        "accepted": False,
        "final_instruction_guard_required": input_role == "instruction" and isinstance(config, dict) and config.get("decision") == "execute",
    }

    def reject(kind: str, **details: Any) -> None:
        audit["rejections"].append({"kind": kind, **details})
        failure = ModelOutputError(f"Explicit duration binding rejected: {kind}.")
        failure.binding_audit = copy.deepcopy(audit)
        failure.constraint_audit = copy.deepcopy(audit.get("constraint_audit"))
        failure.raw_config = copy.deepcopy(config)
        raise failure

    try:
        validate_training_config(config)
    except (TypeError, ValueError, KeyError) as exc:
        reject("invalid_predicted_config", detail=str(exc))

    flat = [(stage, action) for stage, step in enumerate(config["steps"])
            for action in sorted(step["actions"], key=lambda action: RESOURCE_TO_ID[action["resource_id"]])]
    audit["unchanged_structural_fields"] = {
        "decision": config["decision"], "stage_count": len(config["steps"]),
        "actions": [{"action_index": ai, "stage": stage, "resource_id": action["resource_id"],
                     "cycle_count": len(action["cycles"])} for ai, (stage, action) in enumerate(flat)],
    }
    applicable = input_role == "instruction" and config["decision"] == "execute"
    audit["execution_constraints_applicable"] = applicable
    if not applicable:
        audit.update(accepted=True, bypass_reason="dialogue" if input_role == "dialogue" else "non_execution")
        return {}, audit

    guard = validate_instruction_constraints(text, config)
    audit["constraint_audit"] = guard
    if guard["unresolved"]:
        reject("unresolved_instruction_constraints", unresolved=guard["unresolved"])
    # A direct scoped prohibition is stronger evidence than the prediction. Do
    # not reinterpret generic negation (e.g. 别紧张) as an action prohibition.
    for ai, (_, action) in enumerate(flat):
        negated = re.search(_DIRECT_NEGATION + r"(?:" + ALIASES[action["resource_id"]] + r")", text)
        if negated:
            reject("explicitly_negated_predicted_action", action_index=ai,
                   resource_id=action["resource_id"], span=negated.group(),
                   start=negated.start(), end=negated.end())

    unsupported_context = _unsupported_positive_context(text, guard["checks"], flat)
    if unsupported_context:
        reject("unsupported_literal_context", **unsupported_context)

    overrides: dict[tuple[int, int], int] = {}
    entries: dict[tuple[int, int], dict[str, Any]] = {}
    for check in guard["checks"]:
        if check["kind"] != "exact_duration_ms":
            continue
        ai, ci, duration = check["action_index"], check["cycle_index"], check["expected"]
        stage, action = flat[ai]
        rid = action["resource_id"]
        if not 0 <= ci < len(action["cycles"]):
            reject("missing_predicted_cycle", action_index=ai, cycle_index=ci, span=check["span"])
        spec = RESOURCE_SPECS[rid]
        if not spec["min_dur"] <= duration <= spec["max_dur"]:
            reject("duration_out_of_resource_bounds", action_index=ai, cycle_index=ci,
                   resource_id=rid, exact_duration_ms=duration, span=check["span"])
        sources = _source_spans(text, check)
        if not sources:
            reject("unresolved_literal_provenance", check=check)
        key = ai, ci
        if key in overrides and overrides[key] != duration:
            reject("contradictory_exact_durations", action_index=ai, cycle_index=ci,
                   exact_duration_ms=duration, previous_literal_ms=overrides[key], sources=sources)
        if key not in entries:
            entries[key] = {
                "action_index": ai, "cycle_index": ci, "stage": stage, "resource_id": rid,
                "exact_duration_ms": duration,
                "previous_predicted_ms": action["cycles"][ci]["duration_ms"], "sources": [],
            }
            audit["bindings"].append(entries[key])
        for source in sources:
            if source not in entries[key]["sources"]:
                entries[key]["sources"].append(source)
        overrides[key] = duration

    if overrides:
        # A correctly bound requested action must not conceal an unrelated extra
        # predicted resource. This is a rejection, never a resource substitution.
        for ai, (_, action) in enumerate(flat):
            if not re.search(ALIASES[action["resource_id"]], text):
                reject("unmentioned_predicted_resource", action_index=ai, resource_id=action["resource_id"])

    for check in guard["checks"]:
        if check["kind"] == "exact_duration_ms":
            continue
        dependent = check.get("field") in {"duration_ms", "hold_time_ms"} and any(
            (check["action_index"], check.get(name)) in overrides
            for name in ("cycle_index", "reference_cycle_index")
        )
        if dependent:
            audit["deferred_duration_constraints"].append(check)
        elif not check["passed"]:
            reject("non_binding_constraint_violation", check=check)

    audit.update(accepted=True, binding_count=len(overrides))
    return overrides, audit
