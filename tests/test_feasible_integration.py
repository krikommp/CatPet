"""Inference and metric contracts using fake predictions, never training/review data."""
from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools/ActionEncoder"))

import torch

from action_config_schema import (
    ActionConfigV02Model, CAPABILITY_PROFILE, CONFIG_VERSION, DECISIONS, INPUT_POLICY_VERSION,
    LABEL_POLICY_VERSION, ModelOutputError, RESOURCE_CATALOG_VERSION, RESOURCE_IDS, RESOURCE_TO_ID,
    decode_config, validate_training_config,
)
from config_prediction import (
    FEASIBLE_MODEL_ARCHITECTURE, LEGACY_MODEL_ARCHITECTURE, SELECTION_RULE_VERSION,
    architecture_policies, create_config_head, predict_config, validate_head_manifest,
    raw_prediction_record, RawPredictionMetrics,
)
from encoder import LocalEncoder
from feasible_config import FeasibleActionConfigModel
from train_action_config import prediction_metrics, write_epoch_predictions


def logits(*actions, decision="execute"):
    result = {"h": torch.zeros(1, 256), "decision": torch.zeros(1, len(DECISIONS)),
              "resource_id": torch.zeros(1, 2, len(RESOURCE_IDS)),
              "stage": torch.zeros(1, 2, 3), "cycle_count": torch.zeros(1, 2, 4)}
    result["decision"][0, DECISIONS.index(decision)] = 10
    for slot in range(2):
        rid, stage, count = actions[slot] if slot < len(actions) else ("PAD", 2, 0)
        result["resource_id"][0, slot, RESOURCE_TO_ID[rid]] = 10
        result["stage"][0, slot, stage] = 10
        result["cycle_count"][0, slot, count] = 10
    return result


def parameters(hold_gate=1.0):
    return {"values": torch.full((1, 2, 3, 3), 0.5),
            "hold_logits": torch.full((1, 2, 3), hold_gate)}


class FixedHead:
    def __init__(self, discrete, params):
        self.discrete, self.params = discrete, params

    def forward_discrete(self, features):
        return self.discrete

    def forward_params(self, h, resources):
        torch.testing.assert_close(resources, self.discrete["resource_id"].argmax(-1))
        return self.params


class FakeTokenizer:
    def encode(self, *args, **kwargs):
        return [1, 2]

    def __call__(self, texts, **kwargs):
        return {"input_ids": torch.ones(len(texts), 2, dtype=torch.long),
                "attention_mask": torch.ones(len(texts), 2, dtype=torch.long)}


def fake_encoder(head, policies):
    result = LocalEncoder.__new__(LocalEncoder)
    result.torch, result.tokenizer, result.config_head = torch, FakeTokenizer(), head
    result.config_head_manifest = {"capability_profile": CAPABILITY_PROFILE,
        "resource_catalog_version": RESOURCE_CATALOG_VERSION, "parameter_schema_version": CONFIG_VERSION,
        "label_policy_version": LABEL_POLICY_VERSION, "input_policy": INPUT_POLICY_VERSION, **policies}
    result.config_backbone = lambda **inputs: SimpleNamespace(
        last_hidden_state=torch.zeros(inputs["input_ids"].shape[0], 2, 256))
    return result


def request(text, role="instruction"):
    return {"text": text, "input_role": role, "request_id": "TEST_FIXTURE_NOT_REAL_REVIEW",
            "capability_profile": CAPABILITY_PROFILE, "resource_catalog_version": RESOURCE_CATALOG_VERSION,
            "parameter_schema_version": CONFIG_VERSION, "label_policy_version": LABEL_POLICY_VERSION}


class FeasibleIntegrationTests(unittest.TestCase):
    def test_invalid_structure_does_not_erase_raw_execute_decision(self):
        disc = logits(("nod.basic", 0, 1))
        disc["stage"][0, 1, 2] = float("nan")
        raw = raw_prediction_record(disc)
        self.assertFalse(raw["finite"])
        self.assertTrue(raw["head_finite"]["decision"])
        self.assertEqual(raw["decision"], "execute")
        metrics = RawPredictionMetrics()
        metrics.add(raw, {"version": CONFIG_VERSION, "decision": "none", "steps": []})
        self.assertEqual(metrics.summary()["false_execution"], 1)
        self.assertEqual(metrics.summary()["nonexecute_specificity"], 0)

    def test_missing_architecture_and_explicit_legacy_keep_original_class(self):
        for manifest in ({}, architecture_policies(LEGACY_MODEL_ARCHITECTURE)):
            self.assertEqual(validate_head_manifest(manifest), LEGACY_MODEL_ARCHITECTURE)
            head = create_config_head(validate_head_manifest(manifest), hidden_size=8)
            self.assertIs(type(head), ActionConfigV02Model)
        feasible = create_config_head(FEASIBLE_MODEL_ARCHITECTURE, hidden_size=8)
        self.assertIs(type(feasible), FeasibleActionConfigModel)

    def test_new_architecture_requires_all_matching_policy_versions(self):
        policies = architecture_policies(FEASIBLE_MODEL_ARCHITECTURE)
        self.assertEqual(validate_head_manifest(policies), FEASIBLE_MODEL_ARCHITECTURE)
        for field in ("parameterization_policy", "binding_policy", "decoder_policy"):
            for broken in ({key: value for key, value in policies.items() if key != field},
                           {**policies, field: "unsupported-version"}):
                with self.subTest(field=field, broken=broken), self.assertRaises(ValueError):
                    validate_head_manifest(broken)
        with self.assertRaises(ValueError):
            validate_head_manifest({"model_architecture": "future-model"})
        with self.assertRaises(ValueError):
            validate_head_manifest({"binding_policy": policies["binding_policy"]})

    def test_state_dicts_cannot_silently_cross_architectures(self):
        legacy = create_config_head(LEGACY_MODEL_ARCHITECTURE, hidden_size=8)
        feasible = create_config_head(FEASIBLE_MODEL_ARCHITECTURE, hidden_size=8)
        with self.assertRaises(RuntimeError):
            feasible.load_state_dict(legacy.state_dict(), strict=True)
        with self.assertRaises(RuntimeError):
            legacy.load_state_dict(feasible.state_dict(), strict=True)

    def test_binding_precedes_hold_construction_and_retains_structure(self):
        discrete = logits(("nod.basic", 0, 1))
        params = parameters()
        params["values"][..., 0] = 1.0  # Predicted 2200 ms; exact request is the minimum 420 ms.
        params["values"][..., 2] = 0.0  # Smallest feasible positive hold depends on the exact duration.
        predicted, audit = predict_config(discrete, params, "点头一次，每次420毫秒",
                                          architecture=FEASIBLE_MODEL_ARCHITECTURE)
        validate_training_config(predicted)
        cycle = predicted["steps"][0]["actions"][0]["cycles"][0]
        self.assertEqual(cycle["duration_ms"], 420)
        self.assertGreaterEqual(cycle["controls"]["hold_ratio"], 0.18)
        self.assertEqual(audit["binding_audit"]["bindings"][0]["previous_predicted_ms"], 2200)
        self.assertFalse(audit["constraint_audit"]["violations"])
        self.assertEqual(audit["raw_prediction"]["resource_ids"], ["nod.basic", "PAD"])
        json.dumps(audit, ensure_ascii=False)

    def test_canonical_binding_survives_reversed_prediction_slot_order(self):
        discrete = logits(("nod.basic", 1, 1), ("wave.basic", 0, 1))
        predicted, audit = predict_config(discrete, parameters(), "挥手一次每次1.5秒，然后点头一次每次1.2秒",
                                          architecture=FEASIBLE_MODEL_ARCHITECTURE)
        actions = [step["actions"][0] for step in predicted["steps"]]
        self.assertEqual([a["resource_id"] for a in actions], ["wave.basic", "nod.basic"])
        self.assertEqual([a["cycles"][0]["duration_ms"] for a in actions], [1500, 1200])
        self.assertEqual(audit["raw_prediction"]["resource_ids"], ["nod.basic", "wave.basic"])

    def test_legacy_prediction_is_unchanged_and_never_binds_literal(self):
        discrete, params = logits(("nod.basic", 0, 1)), parameters()["values"]
        expected = decode_config(discrete, params)
        with mock.patch("literal_bindings.extract_exact_duration_bindings", side_effect=AssertionError("Legacy binding")):
            actual, audit = predict_config(discrete, params, "点头", architecture=LEGACY_MODEL_ARCHITECTURE)
            self.assertEqual(actual, expected)
            self.assertIsNone(audit["binding_audit"])
            with self.assertRaises(ModelOutputError):
                predict_config(discrete, params, "点头一次每次1.2秒", architecture=LEGACY_MODEL_ARCHITECTURE)

    def test_final_guard_rejects_contradictory_bound_relation(self):
        with self.assertRaises(ModelOutputError) as raised:
            predict_config(logits(("nod.basic", 0, 2)), parameters(),
                "点头两次，第一次1.2秒，第二次800毫秒，第二次比第一次慢",
                architecture=FEASIBLE_MODEL_ARCHITECTURE)
        error = raised.exception
        self.assertTrue(error.binding_audit["accepted"])
        self.assertTrue(error.constraint_audit["violations"])
        self.assertEqual([c["duration_ms"] for c in error.raw_config["steps"][0]["actions"][0]["cycles"]], [1200, 800])

    def test_binding_rejection_audit_and_raw_decision_survive_shared_helper(self):
        with self.assertRaises(ModelOutputError) as raised:
            predict_config(logits(("nod.basic", 0, 1)), parameters(), "点头两次，每次1秒",
                           architecture=FEASIBLE_MODEL_ARCHITECTURE)
        self.assertFalse(raised.exception.binding_audit["accepted"])
        self.assertTrue(raised.exception.binding_audit["rejections"])
        self.assertEqual(raised.exception.raw_prediction["decision"], "execute")

    def test_dialogue_uses_no_literals_and_never_changes_semantic_decision(self):
        for role, decision in (("dialogue", "execute"), ("instruction", "none")):
            predicted, audit = predict_config(logits(("nod.basic", 0, 1), decision=decision), parameters(),
                "点头一次每次1.2秒", input_role=role, architecture=FEASIBLE_MODEL_ARCHITECTURE)
            self.assertEqual(predicted["decision"], decision)
            self.assertEqual(audit["binding_audit"]["bindings"], [])
            if decision == "execute":
                self.assertNotEqual(predicted["steps"][0]["actions"][0]["cycles"][0]["duration_ms"], 1200)

    def test_rejected_execute_is_not_correct_nonexecution_classification(self):
        sample = {"text": "不要点头", "input_role": "instruction", "group_id": "TEST_FIXTURE",
                  "config": {"version": CONFIG_VERSION, "decision": "none", "steps": []}}
        metrics, predictions = prediction_metrics(FixedHead(logits(("nod.basic", 0, 1)), parameters()),
            torch.zeros(1, 256), [sample], FEASIBLE_MODEL_ARCHITECTURE)
        self.assertEqual(metrics["technical_errors"], 1)
        self.assertEqual(metrics["nonexecute_specificity"], 0)
        self.assertEqual(metrics["raw"]["nonexecute_specificity"], 0)
        self.assertEqual(metrics["raw"]["decision_correct"], 0)
        self.assertEqual(metrics["raw"]["false_execution"], 1)
        self.assertEqual(metrics["selection_rule_version"], SELECTION_RULE_VERSION)
        self.assertEqual(metrics["selection_score"], -1)
        self.assertEqual(predictions[0]["raw_prediction"]["decision"], "execute")

    def test_local_encoder_and_training_evaluation_use_identical_bound_config(self):
        head = FixedHead(logits(("nod.basic", 0, 1)), parameters())
        local = fake_encoder(head, architecture_policies(FEASIBLE_MODEL_ARCHITECTURE))
        text = "点头一次每次1.2秒"
        response = local.configure(request(text))
        sample = {"text": text, "input_role": "instruction", "group_id": "TEST_FIXTURE", "config": response["config"]}
        metrics, records = prediction_metrics(head, torch.zeros(1, 256), [sample], FEASIBLE_MODEL_ARCHITECTURE)
        self.assertEqual(records[0]["predicted"], response["config"])
        self.assertEqual(records[0]["binding_audit"], response["binding_audit"])
        self.assertEqual(metrics["raw"]["resource_slot_accuracy"], 1)
        self.assertEqual(metrics["raw"]["active_cycle_count_accuracy"], 1)
        self.assertEqual(metrics["execute_structure_accuracy"], 1)

    def test_local_encoder_with_omitted_architecture_keeps_legacy_output(self):
        head = FixedHead(logits(("nod.basic", 0, 1)), parameters()["values"])
        local = fake_encoder(head, {})
        response = local.configure(request("点头"))
        self.assertEqual(response["config"], decode_config(head.discrete, head.params))
        self.assertEqual(response["model_architecture"], LEGACY_MODEL_ARCHITECTURE)
        self.assertIsNone(response["binding_audit"])

    def test_diagnostic_evaluator_preserves_raw_errors_and_provenance(self):
        from retrain_and_eval import build_parser, evaluate
        local = fake_encoder(FixedHead(logits(("nod.basic", 0, 1)), parameters()),
                             architecture_policies(FEASIBLE_MODEL_ARCHITECTURE))
        local.config_head_manifest["checkpoint_id"] = "TEST_FIXTURE"
        with tempfile.TemporaryDirectory() as folder:
            folder = Path(folder)
            checkpoint = folder / "TEST_FIXTURE_checkpoint"
            checkpoint.mkdir()
            (checkpoint / "manifest.json").write_text(json.dumps(local.config_head_manifest), encoding="utf-8")
            dataset = folder / "TEST_FIXTURE_dataset.jsonl"
            dataset.write_text(json.dumps({"raw_text": "不要点头", "input_role": "instruction", "split": "test",
                "test_fixture": True, "config": {"version": CONFIG_VERSION, "decision": "none", "steps": []}},
                ensure_ascii=False) + "\n", encoding="utf-8")
            args = build_parser().parse_args(["evaluate", "--checkpoint-dir", str(checkpoint),
                "--dataset", str(dataset), "--report", str(folder / "report.json")])
            with mock.patch("encoder.LocalEncoder", return_value=local):
                report = evaluate(args)
            self.assertEqual(report["metrics"]["technical_errors"], 1)
            self.assertEqual(report["metrics"]["nonexecute_specificity"], 0)
            self.assertEqual(report["raw_prediction_metrics"]["false_execution"], 1)
            self.assertEqual(report["raw_prediction_metrics"]["nonexecute_specificity"], 0)
            self.assertTrue({"feasible_config.py", "literal_bindings.py", "config_prediction.py"}
                            <= set(report["execution_source_sha256"]))
            self.assertFalse(report["release_approved"])
            self.assertFalse(report["training_started"])

    def test_wrapper_forwards_architecture_and_learning_rates(self):
        from retrain_and_eval import build_parser, train_command
        with tempfile.TemporaryDirectory() as folder:
            args = build_parser().parse_args(["train", "--snapshot-manifest", "TEST_FIXTURE.json",
                "--out-dir", str(Path(folder) / "output"), "--model-architecture", FEASIBLE_MODEL_ARCHITECTURE,
                "--epochs", "80", "--batch-size", "16", "--lr", "0.0007", "--backbone-lr", "0.00005"])
            command = train_command(args)
            self.assertEqual(command[command.index("--model-architecture") + 1], FEASIBLE_MODEL_ARCHITECTURE)
            self.assertEqual(float(command[command.index("--lr") + 1]), 0.0007)
            self.assertEqual(float(command[command.index("--backbone-lr") + 1]), 0.00005)
            self.assertFalse(args.out_dir.exists())

    def test_train_and_validation_predictions_are_exclusive_and_no_epoch_test(self):
        with tempfile.TemporaryDirectory() as folder:
            path = write_epoch_predictions(Path(folder), 1, [{"test_fixture": True}], "train")
            self.assertEqual(path.name, "epoch_1_train_predictions.jsonl")
            with self.assertRaises(FileExistsError):
                write_epoch_predictions(Path(folder), 1, [], "train")
            with self.assertRaises(ValueError):
                write_epoch_predictions(Path(folder), 1, [], "test")


if __name__ == "__main__":
    unittest.main()
