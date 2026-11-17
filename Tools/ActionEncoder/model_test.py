"""Legacy diagnostic only: test v0.2 HTTP/output behavior; never train or approve a model.

Use retrain_and_eval.py evaluate for the current frozen-data evaluation workflow.
Legacy datasets without input_role require an explicit --input-role override.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
from http.server import HTTPServer
import json
import math
from pathlib import Path
import statistics
import threading
from urllib import error, request

from action_config_schema import (CONFIG_VERSION, DECISIONS, MAX_ACTIONS, MAX_CYCLES,
                                  RESOURCE_SPECS, ModelOutputError, canonicalize_config)
from encoder import DEFAULT_CONFIG_HEAD_DIR, ROOT, LocalEncoder
from server import make_handler, strict_json
from validate_v02_corpus import load_channels_map

DEFAULT_REPORT = ROOT / ".action-encoder" / "model-test-report.json"


def ratio(correct: int, total: int) -> dict:
    return {"correct": correct, "total": total, "accuracy": round(correct / total, 6) if total else None}


def validate_config(config: dict, channels: dict[str, set[str]]) -> None:
    """Check observable output constraints; this does not compile or render in Unity."""
    canonicalize_config(config)
    if not isinstance(config, dict) or config.get("version") != CONFIG_VERSION:
        raise ValueError("expected action-config.v0.2")
    if config.get("decision") not in DECISIONS:
        raise ValueError("unknown decision")
    steps = config.get("steps")
    if not isinstance(steps, list):
        raise ValueError("steps must be a list")
    if config["decision"] != "execute":
        if steps:
            raise ValueError("non-execute must have empty steps")
        return
    if not 1 <= len(steps) <= 2:
        raise ValueError("execute requires 1..2 steps")
    action_count = 0
    for step in steps:
        actions = step.get("actions") if isinstance(step, dict) else None
        if not isinstance(actions, list) or not actions:
            raise ValueError("each step requires actions")
        used_channels: set[str] = set()
        for action in actions:
            rid = action.get("resource_id")
            if rid not in RESOURCE_SPECS:
                raise ValueError(f"unknown resource {rid}")
            overlap = used_channels & channels[rid]
            if overlap:
                raise ValueError(f"parallel channel conflict: {sorted(overlap)}")
            used_channels |= channels[rid]
            action_count += 1
            cycles = action.get("cycles")
            if not isinstance(cycles, list) or not 1 <= len(cycles) <= MAX_CYCLES:
                raise ValueError("cycles must contain 1..3 entries")
            spec = RESOURCE_SPECS[rid]
            for cycle in cycles:
                duration = cycle.get("duration_ms")
                if type(duration) is not int or not spec["min_dur"] <= duration <= spec["max_dur"]:
                    raise ValueError(f"invalid duration for {rid}")
                controls = cycle.get("controls")
                expected = {"hold_ratio"}
                if spec["supports_amp"]:
                    expected.add("amplitude_scale")
                if not isinstance(controls, dict) or set(controls) != expected:
                    raise ValueError(f"invalid controls for {rid}")
                for name, low, high in (("hold_ratio", "min_hold", "max_hold"),
                                        ("amplitude_scale", "min_amp", "max_amp")):
                    if name not in expected:
                        continue
                    value = controls[name]
                    if type(value) not in (int, float) or not math.isfinite(value) or not spec[low] <= value <= spec[high]:
                        raise ValueError(f"invalid {name} for {rid}")
    if not 1 <= action_count <= MAX_ACTIONS:
        raise ValueError("execute requires 1..2 actions in total")


def ordered_actions(config: dict) -> list[list[dict]]:
    # Only parallel action order is interchangeable. Steps and cycles retain their order.
    return [sorted(step["actions"], key=lambda action: action["resource_id"])
            for step in config["steps"]]


def structure(config: dict) -> tuple:
    return (config["decision"], tuple(tuple((action["resource_id"], len(action["cycles"]))
                                           for action in actions)
                                       for actions in ordered_actions(config)))


def parameter_errors(gold: dict, predicted: dict) -> dict[str, list[float]]:
    """Compare only matching action structures; each cycle is one parameter observation."""
    values = {"duration_ms": [], "amplitude_scale": [], "hold_ratio": []}
    if gold["decision"] != "execute" or structure(gold) != structure(predicted):
        return values
    for gold_step, pred_step in zip(ordered_actions(gold), ordered_actions(predicted)):
        for gold_action, pred_action in zip(gold_step, pred_step):
            for gold_cycle, pred_cycle in zip(gold_action["cycles"], pred_action["cycles"]):
                values["duration_ms"].append(abs(gold_cycle["duration_ms"] - pred_cycle["duration_ms"]))
                for name in ("amplitude_scale", "hold_ratio"):
                    if name in gold_cycle["controls"]:
                        values[name].append(abs(gold_cycle["controls"][name] - pred_cycle["controls"][name]))
    return values


def configure_request(text: str, manifest: dict, request_id: str, input_role: str) -> dict:
    if input_role not in {"instruction", "dialogue"}:
        raise ValueError("input_role must be explicitly instruction or dialogue")
    return {"request_id": request_id, "text": text, "input_role": input_role,
            **{key: manifest[key] for key in ("capability_profile", "resource_catalog_version",
                                             "parameter_schema_version", "label_policy_version")}}


def http_checks(encoder: LocalEncoder, manifest: dict, channels: dict[str, set[str]]) -> list[dict]:
    checks = []
    httpd = HTTPServer(("127.0.0.1", 0), make_handler(encoder))
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{httpd.server_port}"

    def call(path: str, payload=None, raw: bytes | None = None) -> tuple[int, dict]:
        data = raw if raw is not None else (json.dumps(payload).encode("utf-8") if payload is not None else None)
        req = request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
        try:
            with request.urlopen(req, timeout=30) as response:
                return response.status, json.load(response)
        except error.HTTPError as failure:
            return failure.code, json.load(failure)

    def check(name: str, operation):
        try:
            operation()
            checks.append({"name": name, "passed": True})
        except Exception as exc:
            checks.append({"name": name, "passed": False, "error": str(exc)})

    def health():
        status, body = call("/health")
        if status != 200 or not body["action_config_head"]["can_generate_configs"]:
            raise AssertionError("health does not expose the loaded config head")
        if body["action_config_head"]["checkpoint_id"] != manifest["checkpoint_id"]:
            raise AssertionError("health checkpoint differs from requested checkpoint")

    def configure():
        status, body = call("/configure", configure_request("眨一下眼", manifest, "http-smoke", "instruction"))
        if status != 200 or body.get("request_id") != "http-smoke":
            raise AssertionError(f"configure failed: {status} {body}")
        if body.get("input_role") != "instruction":
            raise AssertionError("configure did not preserve explicit input_role")
        validate_config(body["config"], channels)

    def rejected(payload: dict, code: str):
        status, body = call("/configure", payload)
        if status != 400 or body.get("error", {}).get("code") != code:
            raise AssertionError(f"expected 400/{code}, received {status} {body}")

    def malformed():
        for raw in (b'{"text":"a","text":"b"}', b'{"text":NaN}'):
            status, body = call("/configure", raw=raw)
            if status != 400 or body.get("error", {}).get("code") != "invalid_request":
                raise AssertionError("duplicate keys/non-finite JSON must be rejected")

    try:
        check("http_health", health)
        check("http_configure", configure)
        check("reject_empty_text", lambda: rejected(configure_request(" ", manifest, "empty", "instruction"), "invalid_request"))
        check("reject_overlong_without_truncation", lambda: rejected(
            configure_request("点" * (int(manifest["max_length"]) + 8), manifest, "long", "instruction"), "input_too_long"))
        for key in ("capability_profile", "resource_catalog_version", "parameter_schema_version", "label_policy_version"):
            payload = configure_request("点头", manifest, "version", "instruction")
            payload[key] = "wrong-version"
            check(f"reject_mismatched_{key}", lambda payload=payload: rejected(payload, "version_mismatch"))
        check("reject_malformed_json", malformed)
    finally:
        httpd.shutdown()
        thread.join(timeout=5)
        httpd.server_close()
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint-dir", type=Path, default=DEFAULT_CONFIG_HEAD_DIR)
    parser.add_argument("--dataset", type=Path, help="Defaults to the checkpoint's test_split.jsonl")
    parser.add_argument("--input-role", choices=("instruction", "dialogue"),
                        help="Explicit role for legacy rows missing input_role; existing row roles are preserved.")
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--threads", type=int, choices=range(1, 17), default=2)
    args = parser.parse_args()
    if args.report.resolve().is_relative_to(args.checkpoint_dir.resolve()):
        parser.error("Write the diagnostic report outside the checkpoint directory.")
    dataset = args.dataset or args.checkpoint_dir / "test_split.jsonl"
    manifest = json.loads((args.checkpoint_dir / "manifest.json").read_text(encoding="utf-8"))
    channels = load_channels_map()
    rows, dataset_errors = [], []
    for line_no, line in enumerate(dataset.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = strict_json(line.encode("utf-8"))
            if not isinstance(row, dict) or not isinstance(row.get("raw_text"), str) or not row["raw_text"].strip():
                raise ValueError("raw_text must be a non-empty string")
            role = row.get("input_role", args.input_role)
            if role not in {"instruction", "dialogue"}:
                raise ValueError("row requires input_role; legacy rows need explicit --input-role")
            config = row.get("config") if isinstance(row.get("config"), dict) else strict_json(row["config_json"].encode("utf-8"))
            validate_config(config, channels)
            rows.append({**row, "input_role": role, "config": config})
        except Exception as exc:
            dataset_errors.append({"line": line_no, "error": str(exc)})

    encoder = LocalEncoder(threads=args.threads, config_head_dir=args.checkpoint_dir)
    if not encoder.config_head_info["can_generate_configs"]:
        raise ValueError("The selected checkpoint does not contain a trained v0.2 config head.")
    checks = http_checks(encoder, manifest, channels)
    checks.append({"name": "dataset_valid_and_nonempty", "passed": bool(rows) and not dataset_errors,
                   "invalid_rows": len(dataset_errors)})
    correct = Counter()
    totals = Counter()
    confusion = {decision: Counter() for decision in DECISIONS}
    errors = {"duration_ms": [], "amplitude_scale": [], "hold_ratio": []}
    latencies, failures, invalid_examples, technical_errors = [], [], [], []
    structure_correct = invalid_predictions = inference_errors = 0
    for index, row in enumerate(rows):
        gold = row["config"]
        expected = gold["decision"]
        totals[expected] += 1
        try:
            response = encoder.configure(configure_request(row["raw_text"], manifest, f"model-test-{index}", row["input_role"]))
            if response.get("input_role") != row["input_role"]:
                raise RuntimeError("response input_role differs from requested input_role")
            predicted = response["config"]
            latencies.append(response["inference_ms"])
            validation_error = None
            try:
                validate_config(predicted, channels)
            except Exception as exc:
                invalid_predictions += 1
                validation_error = str(exc)
                if len(invalid_examples) < 20:
                    invalid_examples.append({"raw_text": row["raw_text"], "input_role": row["input_role"], "predicted": predicted,
                                             "validation_error": validation_error})
                raise ModelOutputError(f"invalid returned config: {validation_error}") from exc
            confusion[expected][predicted["decision"]] += 1
            if predicted["decision"] == expected:
                correct[expected] += 1
            matches = structure(gold) == structure(predicted)
            if expected == "execute" and matches and validation_error is None:
                structure_correct += 1
                for name, values in parameter_errors(gold, predicted).items():
                    errors[name].extend(values)
            if (not matches or validation_error) and len(failures) < 20:
                failures.append({"raw_text": row["raw_text"], "input_role": row["input_role"], "expected": gold, "predicted": predicted,
                                 "validation_error": validation_error})
        except Exception as exc:
            inference_errors += 1
            technical_errors.append({"row_index": index, "raw_text": row["raw_text"], "input_role": row["input_role"],
                                     "code": "model_output_invalid" if isinstance(exc, ModelOutputError) else "inference_error",
                                     "error_type": type(exc).__name__, "message": str(exc),
                                     "raw_config": getattr(exc, "raw_config", None),
                                     "constraint_audit": getattr(exc, "constraint_audit", None)})

    checks.append({"name": "inference_completed", "passed": inference_errors == 0, "errors": inference_errors})
    checks.append({"name": "predictions_obey_resource_constraints", "passed": invalid_predictions == 0,
                   "invalid_predictions": invalid_predictions})
    texts = Counter((row["input_role"], row["raw_text"].strip()) for row in rows)
    false_execute = {decision: {"count": confusion[decision]["execute"], "total": totals[decision],
                               "rate": round(confusion[decision]["execute"] / totals[decision], 6) if totals[decision] else None}
                     for decision in DECISIONS if decision != "execute"}
    report = {
        "stage": "legacy_diagnostic_only", "training_started": False, "training_admission": False,
        "model_version": manifest.get("model_version"), "checkpoint_id": manifest.get("checkpoint_id"),
        "checkpoint_dir": str(args.checkpoint_dir.resolve()),
        "dataset": {"path": str(dataset.resolve()), "sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
                    "valid_samples": len(rows), "invalid_rows": dataset_errors,
                    "legacy_missing_role_override": args.input_role,
                    "role_counts": dict(Counter(row["input_role"] for row in rows)),
                    "duplicate_texts": sum(count - 1 for count in texts.values()),
                    "independence": "not_verified",
                    "note": "Checkpoint holdout by default. Training overlap and visual labels are not verified."},
        "checks": checks,
        "metrics": {
            "decision": {**ratio(sum(correct.values()), len(rows)),
                         "denominator_note": "All valid input rows; technical errors count as unsuccessful without becoming semantic labels.",
                         "by_class": {decision: ratio(correct[decision], totals[decision]) for decision in DECISIONS},
                         "confusion": {decision: dict(counts) for decision, counts in confusion.items()}},
            "execute_structure": ratio(structure_correct, totals["execute"]),
            "parameters_on_valid_matching_structure": {
                "matching_samples": structure_correct,
                "note": "MAE excludes wrong resources/order/count and invalid predictions; it is not overall action accuracy.",
                **{name: {"observations": len(values), "mae": round(statistics.mean(values), 6) if values else None}
                   for name, values in errors.items()}},
            "false_execute": false_execute,
            "latency_ms": {"observations": len(latencies),
                           "mean": round(statistics.mean(latencies), 3) if latencies else None,
                           "median": round(statistics.median(latencies), 3) if latencies else None,
                           "p95": round(sorted(latencies)[max(0, math.ceil(len(latencies) * .95) - 1)], 3) if latencies else None},
        },
        "failure_examples": failures,
        "technical_errors": technical_errors,
        "invalid_prediction_examples": invalid_examples,
        "assessment": {
            "automated_checks_passed": all(check["passed"] for check in checks),
            "all_decision_classes_present": all(totals[decision] > 0 for decision in DECISIONS),
            "release_approved": False,
            "note": "Diagnostic report only: no release thresholds, independent generalization proof, Unity compilation, or visual/user acceptance. Missing classes or small datasets cannot establish model quality.",
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"report": str(args.report.resolve()), "samples": len(rows),
                      "decision_accuracy": report["metrics"]["decision"]["accuracy"],
                      "execute_structure_accuracy": report["metrics"]["execute_structure"]["accuracy"],
                      **report["assessment"]}, ensure_ascii=False, indent=2))
    return 0 if report["assessment"]["automated_checks_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
