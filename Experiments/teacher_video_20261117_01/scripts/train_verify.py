"""Isolated regression checks and explicit-output evaluation; never trains a model."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import copy
import hashlib
import json
from pathlib import Path
import sys
import time

RUN = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RUN / "source"))

import torch
from action_config_schema import (CONFIG_VERSION, DECODER_POLICY_VERSION, RESOURCE_IDS, RESOURCE_TO_ID,
                                  ModelOutputError, canonicalize_config, decode_config,
                                  format_input_text, legacy_decode_config)
from train_action_config import (json_line, prediction_metrics, split_by_group, structure,
                                 training_binding, validate_compile_evidence, validate_provenance)


def fixture_config(resource="nod.basic", duration=800, hold=0.2):
    controls = {"hold_ratio": hold}
    if resource != "blink.full":
        controls["amplitude_scale"] = 1.0
    return {"version": CONFIG_VERSION, "decision": "execute", "steps": [
        {"actions": [{"resource_id": resource, "cycles": [{"duration_ms": duration, "controls": controls}]}]}]}


def fixture_logits(resources=("nod.basic", "bow.basic"), stages=(0, 0), cycles=(1, 1)):
    result = {"decision": torch.tensor([[9.0, 0, 0, 0]]),
              "resource_id": torch.zeros(1, 2, len(RESOURCE_IDS)),
              "stage": torch.zeros(1, 2, 3), "cycle_count": torch.zeros(1, 2, 4),
              "h": torch.zeros(1, 256)}
    for slot, resource in enumerate(resources):
        result["resource_id"][0, slot, RESOURCE_TO_ID[resource]] = 9
        result["stage"][0, slot, stages[slot]] = 9
        result["cycle_count"][0, slot, cycles[slot]] = 9
    return result


def checks(report: Path):
    results = []

    def check(name, fn):
        try:
            evidence = fn()
            results.append({"name": name, "passed": True, "evidence": evidence})
        except Exception as exc:
            results.append({"name": name, "passed": False, "error": repr(exc)})

    def rejected(fn, exception, contains=""):
        try:
            fn()
        except exception as exc:
            assert contains in str(exc), str(exc)
            return str(exc)
        raise AssertionError(f"Expected {exception.__name__}.")

    params = torch.full((1, 2, 3, 3), 0.5)

    def conflict():
        logits = fixture_logits()
        old = legacy_decode_config(logits, params)
        old_resources = [a["resource_id"] for a in old["steps"][0]["actions"]]
        assert "bow.basic" not in old_resources, old
        error = rejected(lambda: decode_config(logits, params), ModelOutputError, "conflict")
        return {"original_top1_resources": ["nod.basic", "bow.basic"], "legacy_returned_resources": old_resources,
                "strict_error": error, "semantic_label_not_fabricated": True}
    check("parallel_conflict_no_unrelated_resource_substitution", conflict)

    def empty_execute():
        logits = fixture_logits(("PAD", "PAD"))
        assert legacy_decode_config(logits, params)["decision"] == "none"
        return rejected(lambda: decode_config(logits, params), ModelOutputError, "no active resource")
    check("empty_execute_is_technical_failure_not_none", empty_execute)
    check("active_slot_pad_stage_is_not_forced_execute", lambda: rejected(
        lambda: decode_config(fixture_logits(("nod.basic", "PAD"), (2, 0)), params), ModelOutputError, "stage=2"))
    check("active_slot_zero_cycle_is_not_forced_one", lambda: rejected(
        lambda: decode_config(fixture_logits(("nod.basic", "PAD"), cycles=(0, 0)), params), ModelOutputError, "cycle_count=0"))

    def sequence():
        cfg = decode_config(fixture_logits(stages=(0, 1), cycles=(1, 2)), params)
        assert [[a["resource_id"] for a in step["actions"]] for step in cfg["steps"]] == [["nod.basic"], ["bow.basic"]]
        assert len(cfg["steps"][1]["actions"][0]["cycles"]) == 2
        return cfg
    check("sequential_shared_channels_remain_valid_and_ordered", sequence)
    check("out_of_range_label_cannot_be_clamped", lambda: rejected(
        lambda: canonicalize_config(fixture_config(duration=100)), ValueError, "Invalid duration"))
    check("nonzero_short_hold_rejected", lambda: rejected(
        lambda: canonicalize_config(fixture_config(duration=800, hold=0.02)), ValueError, "hold_segment_too_short"))
    check("lookaround_hold_without_native_phase_rejected", lambda: rejected(
        lambda: canonicalize_config(fixture_config("look_around.basic", 1100, 0.1)), ValueError, "invalid_hold_mapping"))
    def compiled_label_binding():
        rows = [json_line(line) for line in (RUN / "data/cold_start.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
        row = next(item for item in rows if item["config"]["decision"] == "execute")
        binding = {"compiler_sha256": hashlib.sha256((RUN / "source/csharp/ActionConfigCompiler.cs").read_bytes()).hexdigest(),
                   "resource_sha256": hashlib.sha256((RUN / "source/csharp/ActionResourceCatalog.cs").read_bytes()).hexdigest()}
        validate_compile_evidence(row, binding)
        row["config"]["steps"][0]["actions"][0]["cycles"][0]["duration_ms"] += 1
        return rejected(lambda: validate_compile_evidence(row, binding), ValueError, "actually compiled")
    check("training_label_must_equal_actual_CSharp_compile_evidence", compiled_label_binding)
    check("explicit_zero_hold_remains_zero", lambda: canonicalize_config(fixture_config(hold=0)))

    valid = [{"text": "点头", "group_id": "g1", "split": "train"},
             {"text": "眨眼", "group_id": "g2", "split": "val"},
             {"text": "挥手", "group_id": "g3", "split": "test"}]
    def fixed_split():
        rows = split_by_group(valid)
        assert [r[0]["group_id"] for r in rows] == ["g1", "g2", "g3"]
        return "Predeclared train/val/test assignment retained."
    check("fixed_split_is_not_resampled", fixed_split)
    check("same_text_different_group_leakage_rejected", lambda: rejected(
        lambda: split_by_group(valid + [{"text": "点头！", "group_id": "different", "split": "test"}]), ValueError, "Cross-split leakage"))
    check("same_group_different_decision_leakage_rejected", lambda: rejected(
        lambda: split_by_group(valid + [{"text": "不点头", "group_id": "g1", "split": "val"}]), ValueError, "Cross-split leakage"))
    def role_policy():
        assert format_input_text("你好", "instruction") == "动作指令：你好"
        assert format_input_text("你好", "dialogue") == "角色台词表演：你好"
        return rejected(lambda: format_input_text("你好", None), ValueError, "input_role")
    check("instruction_and_dialogue_explicitly_separated", role_policy)
    check("missing_persona_blocks_training", lambda: rejected(
        lambda: training_binding(RUN / "MISSING_PERSONA_DO_NOT_CREATE.md", "fixture-rubric"), ValueError, "persona"))
    check("unbound_provenance_blocks_training", lambda: rejected(
        lambda: validate_provenance({"provenance": {}}, {"persona_sha256": "fixture-not-real", "review_rubric_version": "fixture"}), ValueError, "persona hash"))
    def admission(split, eligible):
        return {"split": split, "training_eligible": eligible, "source_type": "teacher_fixed_eval",
                "config": {"version": CONFIG_VERSION, "decision": "none", "steps": []},
                "provenance": {"persona_sha256": "fixture-not-real", "review_rubric_version": "fixture"}}
    binding_fixture = {"persona_sha256": "fixture-not-real", "review_rubric_version": "fixture"}
    check("persona_binding_does_not_admit_unreviewed_train_rows", lambda: rejected(
        lambda: validate_provenance(admission("train", False), binding_fixture), ValueError, "training_eligible=true"))
    check("test_row_not_training_eligible_is_kept_as_test", lambda: validate_provenance(admission("test", False), binding_fixture))
    check("duplicate_json_keys_rejected", lambda: rejected(
        lambda: json_line('{"raw_text":"a","raw_text":"b"}'), ValueError, "Duplicate JSON key"))

    def predicted_conditioning():
        class FakeHead:
            def forward_discrete(self, _):
                return fixture_logits(("blink.full", "PAD"))
            def forward_params(self, _, resources):
                assert resources.tolist() == [[RESOURCE_TO_ID["blink.full"], 0]], resources
                return params
        metrics, rows = prediction_metrics(FakeHead(), torch.zeros(1, 256), [
            {"text": "点头", "group_id": "fixture", "config": fixture_config()}])
        assert metrics["execute_structure_correct"] == 0
        assert rows[0]["predicted"]["steps"][0]["actions"][0]["resource_id"] == "blink.full"
        return {"gold_resource": "nod.basic", "params_conditioned_on": "blink.full", "structure_correct": 0}
    check("validation_parameters_use_predicted_not_gold_resource", predicted_conditioning)

    def fake_encoder(resources):
        from encoder import LocalEncoder
        from types import SimpleNamespace
        class Tokenizer:
            def encode(self, *_args, **_kwargs):
                return [1, 2]
            def __call__(self, *_args, **_kwargs):
                return {"input_ids": torch.ones(1, 2, dtype=torch.long), "attention_mask": torch.ones(1, 2, dtype=torch.long)}
        class Head:
            def forward_discrete(self, _):
                return fixture_logits(resources)
            def forward_params(self, _, resources):
                return params
        encoder = LocalEncoder.__new__(LocalEncoder)
        encoder.config_head_manifest = {"capability_profile": "fixture", "resource_catalog_version": "fixture",
                                       "parameter_schema_version": CONFIG_VERSION, "label_policy_version": "fixture"}
        encoder.config_head = Head()
        encoder.config_backbone = lambda **kwargs: SimpleNamespace(last_hidden_state=torch.zeros(1, 2, 256))
        encoder.tokenizer = Tokenizer()
        encoder.torch = torch
        encoder._legacy_baseline_evaluation = False
        request = {"text": "点头", "input_role": "instruction", "request_id": "fixture", **encoder.config_head_manifest}
        return encoder, request
    def strict_missing_manifest_policy():
        encoder, request = fake_encoder(("nod.basic", "bow.basic"))
        return rejected(lambda: encoder.configure(request), ModelOutputError, "conflict")
    check("normal_configure_without_decoder_policy_is_strict", strict_missing_manifest_policy)
    def runtime_numeric_guard():
        encoder, request = fake_encoder(("nod.basic", "PAD"))
        request["text"] = "点头一次，每次用800毫秒"
        try:
            encoder.configure(request)
        except ModelOutputError as exc:
            assert exc.raw_config["decision"] == "execute"
            assert exc.constraint_audit["violations"]
            return {"technical_error": str(exc), "raw_prediction_preserved": True}
        raise AssertionError("Runtime silently ignored exact duration.")
    check("runtime_explicit_number_guard_preserves_raw_failure", runtime_numeric_guard)

    persona = RUN.parents[1] / "Docs" / "ActionLanguage" / "personas" / "gemini-cyber-cat.md"
    result = {"passed": sum(row["passed"] for row in results), "total": len(results), "training_started": False,
              "shared_files_modified": False, "persona_status": "file_present_rubric_pending" if persona.is_file() else "pending",
              "persona_sha256": hashlib.sha256(persona.read_bytes()).hexdigest() if persona.is_file() else None, "checks": results}
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passed": result["passed"], "total": len(results), "report": str(report)}, ensure_ascii=False))
    return 0 if all(row["passed"] for row in results) else 1


def constraint_results(row, predicted):
    """Only evaluate explicitly stored target associations; never guess numeric scope."""
    results = []
    for constraint in row.get("constraints", []):
        item = {"constraint": constraint, "passed": False}
        try:
            actions = [action for step in predicted["steps"] for action in sorted(step["actions"], key=lambda a: RESOURCE_TO_ID[a["resource_id"]])]
            action = actions[constraint["action_index"]]
            cycle = action["cycles"][constraint["cycle_index"]]
            field = constraint["field"]
            value = cycle[field] if field == "duration_ms" else cycle["controls"][field]
            if "reference_cycle_index" in constraint:
                other = action["cycles"][constraint["reference_cycle_index"]]
                reference = other[field] if field == "duration_ms" else other["controls"][field]
                delta = constraint.get("min_delta", 0)
                relation = constraint["relation"]
                item["passed"] = value > reference and value - reference >= delta if relation == ">" else value < reference and reference - value >= delta if relation == "<" else value == reference
                item.update(actual=value, reference_actual=reference)
            else:
                item["passed"] = abs(value - constraint["value"]) <= constraint.get("tolerance", 0)
                item.update(actual=value)
        except (KeyError, IndexError, TypeError):
            item["error"] = "Predicted structure or explicit constraint association unavailable."
        results.append(item)
    return results


def evaluate(args):
    from encoder import LocalEncoder
    from input_constraints import validate_instruction_constraints
    encoder = LocalEncoder(threads=2, config_head_dir=args.checkpoint_dir,
                           legacy_baseline_evaluation=args.legacy_baseline)
    manifest = encoder.config_head_manifest
    counts = Counter()
    confusion = defaultdict(Counter)
    parameter_errors = defaultdict(list)
    output_rows = []
    for line in args.dataset.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        row = json_line(line)
        gold = row["config"]
        decision = gold["decision"]
        counts["total"] += 1
        counts[f"gold_{decision}"] += 1
        expected_checks = row.get("objective_constraint_checks", {}).get("checks", [])
        counts["objective_constraints_total"] += len(expected_checks)
        gold_unresolved = row.get("objective_constraint_checks", {}).get("unresolved", [])
        counts["gold_scope_unresolved_rows"] += bool(gold_unresolved)
        result = {"candidate_id": row.get("candidate_id"), "raw_text": row["raw_text"], "group_id": row["group_id"],
                  "gold": gold, "gold_scope_unresolved": gold_unresolved,
                  "metric_exclusions": row.get("metric_exclusions", [])}
        try:
            response = encoder.configure({"text": row["raw_text"], "input_role": row.get("input_role"),
                "request_id": f"isolated-eval-{counts['total']}",
                **{key: manifest[key] for key in ("capability_profile", "resource_catalog_version", "parameter_schema_version", "label_policy_version")}})
            predicted = response["config"]
            result.update(predicted=predicted, inference_ms=response["inference_ms"])
            confusion[decision][predicted["decision"]] += 1
            match = structure(gold) == structure(predicted)
            counts["decision_correct"] += int(decision == predicted["decision"])
            counts["structure_correct"] += int(match)
            counts["execute_structure_correct"] += int(decision == "execute" and match)
            counts[f"false_execute_{decision}"] += int(decision != "execute" and predicted["decision"] == "execute")
            if match and decision == "execute" and "unconstrained_parameter_mae" not in row.get("metric_exclusions", []):
                for gs, ps in zip(gold["steps"], predicted["steps"]):
                    for ga, pa in zip(sorted(gs["actions"], key=lambda a: a["resource_id"]), sorted(ps["actions"], key=lambda a: a["resource_id"])):
                        for gc, pc in zip(ga["cycles"], pa["cycles"]):
                            parameter_errors["duration_ms"].append(abs(gc["duration_ms"] - pc["duration_ms"]))
                            for field in gc["controls"]:
                                parameter_errors[field].append(abs(gc["controls"][field] - pc["controls"][field]))
            result["constraints"] = constraint_results(row, predicted)
            counts["constraint_total"] += len(result["constraints"])
            counts["constraint_passed"] += sum(item["passed"] for item in result["constraints"])
            objective = validate_instruction_constraints(row["raw_text"], predicted)
            result["objective_constraint_checks"] = objective
            counts["predicted_scope_unresolved_rows"] += bool(objective["unresolved"])
            def identity(item):
                return tuple(item.get(k) for k in ("kind", "action_index", "cycle_index", "reference_cycle_index", "field", "span"))
            actual_checks = {identity(item): item for item in objective["checks"]}
            passed_objectives = sum(bool(actual_checks.get(identity(item), {}).get("passed")) for item in expected_checks) if match else 0
            counts["objective_constraints_passed"] += passed_objectives
            result["objective_constraints_passed_matching_structure"] = passed_objectives
        except (ModelOutputError, ValueError) as exc:
            counts["technical_errors"] += 1
            confusion[decision]["technical_error"] += 1
            result["technical_error"] = str(exc)
            if hasattr(exc, "raw_config"):
                result["raw_prediction_before_guard"] = exc.raw_config
                result["objective_constraint_checks"] = exc.constraint_audit
                counts["instruction_guard_rejections"] += 1
                counts["predicted_scope_unresolved_rows"] += bool(exc.constraint_audit["unresolved"])
            counts["constraint_total"] += len(row.get("constraints", []))
        output_rows.append(result)
    report = {"checkpoint_id": manifest["checkpoint_id"], "checkpoint_dir": str(args.checkpoint_dir.resolve()),
              "checkpoint_sha256": {name: hashlib.sha256((args.checkpoint_dir / name).read_bytes()).hexdigest()
                  for name in ("config_head.pt", "backbone_state.pt", "manifest.json") if (args.checkpoint_dir / name).is_file()},
              "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
              "execution_source_sha256": {str(path.relative_to(RUN)): hashlib.sha256(path.read_bytes()).hexdigest()
                  for path in (RUN / "source/encoder.py", RUN / "source/action_config_schema.py", RUN / "source/input_constraints.py", Path(__file__).resolve())},
              "input_policy": manifest.get("input_policy", "legacy_raw_text"),
              "decoder_policy": "explicit_legacy_baseline" if args.legacy_baseline else DECODER_POLICY_VERSION,
              "metrics": dict(counts), "confusion": {k: dict(v) for k, v in confusion.items()},
              "parameter_mae_matching_structure": {k: {"count": len(v), "mae": sum(v) / len(v)} for k, v in parameter_errors.items()},
              "training_started": False, "release_approved": False,
              "limitations": ["Same frozen weights: strict-vs-legacy is decoder/guard diagnosis, not model improvement.", "No Unity/video rendering is performed by this script.", "Baseline may have seen the same semantic families; this is not independent generalization.", "Numeric grammar is partial; unresolved scopes count separately and are never treated as success.", "Unconstrained parameter MAE is excluded when requested by evaluation rows."],
              "predictions": output_rows}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(args.report), "metrics": dict(counts)}, ensure_ascii=False))
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    tests = sub.add_parser("checks")
    tests.add_argument("--report", type=Path, default=RUN / "reports" / "code_audit_checks.json")
    evaluation = sub.add_parser("evaluate")
    evaluation.add_argument("--checkpoint-dir", type=Path, required=True)
    evaluation.add_argument("--dataset", type=Path, required=True)
    evaluation.add_argument("--report", type=Path, required=True)
    evaluation.add_argument("--legacy-baseline", action="store_true", help="Explicitly reproduce the unsafe old decoder for frozen baseline measurement only. Normal inference is always strict.")
    args = parser.parse_args()
    if not args.report.resolve().is_relative_to(RUN.resolve()):
        raise ValueError("Reports must stay in this experiment directory.")
    return checks(args.report) if args.command == "checks" else evaluate(args)


if __name__ == "__main__":
    raise SystemExit(main())
