"""Regression tests for frozen v0.2 training orchestration; never runs an epoch.

Any review records constructed here are visibly named TEST_FIXTURE_NOT_REAL_REVIEW,
live only in a disposable test directory, and are not collected training data.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from training_data import (ROOT, build_samples, check_snapshot_unchanged, dataset_summary,
                           ensure_new_output_dir, file_sha256, load_snapshot, split_by_group)


def rows_fixture():
    return [{"raw_text": text, "config": {"version": "action-config.v0.2", "decision": decision, "steps": []},
             "input_role": "instruction", "group_id": f"g-{split}", "semantic_family_id": f"family-{split}",
             "split": split, "source_type": "ai_semantic_reviewed", "training_eligible": split == "train",
             "candidate_id": f"fixture-{split}", "parent_candidate_id": "", "provenance": {}}
            for split, text, decision in (("train", "不用动", "none"), ("val", "请飞起来", "unsupported"),
                                         ("test", "那个动作", "ambiguous"))]


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        temporary_root = ROOT / "Experiments/workflow_fix_20261117/tests_tmp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="training-fixture-", dir=temporary_root)
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)

    def export_fixture(self):
        from review_evidence import canonical_hash, export_snapshot
        fixture_files = {}
        for key in ("persona_file", "compiler_file", "resource_file", "native_profile_file"):
            path = self.folder / f"TEST_FIXTURE_{key}.txt"
            path.write_text(f"TEST_FIXTURE_NOT_REAL_REVIEW {key}", encoding="utf-8")
            fixture_files[key] = path
        binding = dict(zip(("persona_sha256", "compiler_sha256", "resource_sha256", "native_profile_sha256"),
                           (file_sha256(fixture_files[key]) for key in fixture_files)))
        rows = rows_fixture()
        for row in rows:
            row["test_fixture"] = True
            row["generation"] = {"provider": "TEST_FIXTURE_NOT_REAL_REVIEW", "model": "fixture-model",
                                 "context_id": "fixture-generator", "prompt_version": "fixture-v1"}
            row["review"] = {**binding, "provider": "TEST_FIXTURE_NOT_REAL_REVIEW", "model": "fixture-model",
                "candidate_id": row["candidate_id"], "parent_candidate_id": row["parent_candidate_id"], "input_role": row["input_role"],
                "raw_text_sha256": hashlib.sha256(row["raw_text"].encode("utf-8")).hexdigest(),
                "context_id": "fixture-independent-reviewer", "prompt_version": "fixture-v1", "reviewer_type": "AI",
                "status": "accepted", "semantic_match": True, "rubric_version": "fixture-rubric-v1",
                "reviewed_at": "2026-11-17T10:00:00Z", "config_sha256": canonical_hash(row["config"]),
                "scores": {"semantic": 1}, "rationale": "TEST FIXTURE ONLY, no actual AI review occurred."}
        records = self.folder / "TEST_FIXTURE_records.jsonl"
        records.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
        manifest = export_snapshot(records, self.folder / "snapshot", rubric_version="fixture-rubric-v1", **fixture_files)
        return manifest, fixture_files, records

    def test_semantic_family_cannot_cross_decision_buckets(self):
        rows = rows_fixture()
        rows[1]["semantic_family_id"] = rows[0]["semantic_family_id"]
        with self.assertRaisesRegex(ValueError, "Cross-split leakage"):
            split_by_group(rows)

    def test_same_text_different_group_cannot_leak(self):
        rows = rows_fixture()
        rows[2]["raw_text"] = rows[0]["raw_text"] + "！"
        with self.assertRaisesRegex(ValueError, "Cross-split leakage"):
            split_by_group(rows)

    def test_same_group_different_text_cannot_leak(self):
        rows = rows_fixture()
        rows[2]["group_id"] = rows[0]["group_id"]
        with self.assertRaisesRegex(ValueError, "Cross-split leakage"):
            split_by_group(rows)

    def test_old_test_cannot_return_to_train(self):
        rows = rows_fixture()
        rows[0]["provenance"]["original_split"] = "test"
        with self.assertRaisesRegex(ValueError, "held-out"):
            split_by_group(rows)

    def test_training_requires_explicit_admission(self):
        for value in (None, False):
            rows = rows_fixture()
            rows[0]["training_eligible"] = value
            with self.assertRaisesRegex(ValueError, "training_eligible=true"):
                split_by_group(rows)

    def test_test_false_is_not_treated_as_train(self):
        train, val, test = split_by_group(rows_fixture())
        self.assertEqual([r["split"] for r in train + val + test], ["train", "val", "test"])
        self.assertFalse(test[0]["training_eligible"])

    def test_existing_empty_output_also_cannot_be_overwritten(self):
        target = self.folder / "existing"
        target.mkdir()
        with self.assertRaises(FileExistsError):
            ensure_new_output_dir(target)
        self.assertEqual(list(target.iterdir()), [])

    def test_default_checkpoint_is_never_a_training_target(self):
        target = ROOT / "Tools/ActionEncoder/checkpoints/v02_latest"
        before = file_sha256(target / "manifest.json")
        with self.assertRaisesRegex(ValueError, "latest/v02_latest"):
            ensure_new_output_dir(target)
        self.assertEqual(file_sha256(target / "manifest.json"), before)

    def test_real_export_and_validation_need_no_human_keep(self):
        manifest, _, _ = self.export_fixture()
        rows, _ = load_snapshot(manifest)
        self.assertEqual(len(rows), 3)
        self.assertTrue(rows[0]["training_eligible"])
        self.assertNotIn("human_keep", rows[0])
        self.assertIn("execute", dataset_summary(rows)["missing_train_decisions"])

    def test_dataset_content_change_is_detected(self):
        manifest, _, _ = self.export_fixture()
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
        dataset = manifest.parent / metadata["dataset"]["path"]
        dataset.write_bytes(dataset.read_bytes() + b" ")
        with self.assertRaisesRegex(ValueError, "dataset hash"):
            load_snapshot(manifest)

    def test_frozen_persona_change_is_detected(self):
        manifest, _, _ = self.export_fixture()
        metadata = json.loads(manifest.read_text(encoding="utf-8"))
        persona = manifest.parent / metadata["persona"]["path"]
        persona.write_text("changed fixture persona", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "artifact hash"):
            load_snapshot(manifest)

    def test_manifest_changes_during_operation_are_detected(self):
        manifest, _, _ = self.export_fixture()
        before = file_sha256(manifest)
        manifest.write_bytes(manifest.read_bytes() + b"\n")
        with self.assertRaisesRegex(ValueError, "manifest changed"):
            check_snapshot_unchanged(manifest, before)

    def test_roles_and_ordinary_wording_not_rejected_as_numbers(self):
        class Tokenizer:
            def encode(self, *args, **kwargs): return [1, 2]
        rows = rows_fixture()
        rows[0]["raw_text"] = "一边轻轻点头，一边和我打个招呼"
        rows[0]["config"] = {"version": "action-config.v0.2", "decision": "execute", "steps": [{"actions": [
            {"resource_id": "nod.basic", "cycles": [{"duration_ms": 800, "controls": {"amplitude_scale": 0.8, "hold_ratio": 0.2}}]},
            {"resource_id": "wave.basic", "cycles": [{"duration_ms": 1000, "controls": {"amplitude_scale": 0.8, "hold_ratio": 0.2}}]}]}]}
        rows[1]["input_role"] = "dialogue"
        samples = build_samples(rows, Tokenizer(), 128)
        self.assertTrue(samples[0]["model_text"].startswith("动作指令："))
        self.assertTrue(samples[1]["model_text"].startswith("角色台词表演："))

    def test_explicit_wrong_count_is_rejected_by_loader(self):
        class Tokenizer:
            def encode(self, *args, **kwargs): return [1, 2]
        rows = rows_fixture()
        rows[0]["raw_text"] = "请点头两次"
        rows[0]["config"] = {"version": "action-config.v0.2", "decision": "execute", "steps": [{"actions": [
            {"resource_id": "nod.basic", "cycles": [{"duration_ms": 800, "controls": {"amplitude_scale": 0.8, "hold_ratio": 0.2}}]}]}]}
        with self.assertRaisesRegex(ValueError, "instruction constraint"):
            build_samples(rows, Tokenizer(), 128)

    def test_validation_conditions_parameters_on_actual_predicted_resource(self):
        import torch
        from action_config_schema import RESOURCE_IDS, RESOURCE_TO_ID, ModelOutputError
        from train_action_config import prediction_metrics
        class FakeHead:
            def forward_discrete(self, features):
                value = {"h": torch.zeros(1, 256), "decision": torch.tensor([[10., 0, 0, 0]]),
                         "resource_id": torch.zeros(1, 2, len(RESOURCE_IDS)), "stage": torch.zeros(1, 2, 3),
                         "cycle_count": torch.zeros(1, 2, 4)}
                value["resource_id"][0, 0, RESOURCE_TO_ID["blink.full"]] = 10
                value["resource_id"][0, 1, 0] = 10
                value["stage"][0, 0, 0] = 10
                value["cycle_count"][0, 0, 1] = 10
                return value
            def forward_params(inner, h, resource_ids):
                self.assertEqual(resource_ids.tolist(), [[RESOURCE_TO_ID["blink.full"], 0]])
                return torch.full((1, 2, 3, 3), 0.5)
        gold = {"version": "action-config.v0.2", "decision": "execute", "steps": [{"actions": [
            {"resource_id": "nod.basic", "cycles": [{"duration_ms": 800, "controls": {"amplitude_scale": 0.8, "hold_ratio": 0.2}}]}]}]}
        sample = {"text": "点头", "input_role": "instruction", "group_id": "fixture", "config": gold}
        metrics, predictions = prediction_metrics(FakeHead(), torch.zeros(1, 256), [sample])
        self.assertEqual(metrics["execute_structure_correct"], 0)
        self.assertEqual(predictions[0]["input_role"], "instruction")
        with mock.patch("train_action_config.decode_config", side_effect=ModelOutputError("fixture technical failure")):
            _, failures = prediction_metrics(FakeHead(), torch.zeros(1, 256), [{**sample, "input_role": "dialogue"}])
        self.assertEqual(failures[0]["input_role"], "dialogue")
        self.assertEqual(failures[0]["technical_error"], "fixture technical failure")

    def test_epoch_predictions_persist_roles_and_never_overwrite(self):
        from train_action_config import write_epoch_predictions
        predictions = [{"raw_text": "点头", "input_role": "instruction", "predicted": {"decision": "execute"}},
                       {"raw_text": "你好", "input_role": "dialogue", "technical_error": "fixture failure"}]
        path = write_epoch_predictions(self.folder, 3, predictions)
        self.assertEqual(path.name, "epoch_3_validation_predictions.jsonl")
        self.assertEqual([json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()], predictions)
        with self.assertRaises(FileExistsError):
            write_epoch_predictions(self.folder, 3, [])

    def test_validate_only_does_not_initialize_training_or_create_checkpoint(self):
        from train_action_config import main
        manifest, _, _ = self.export_fixture()
        output = self.folder / "must-not-exist"
        with mock.patch("train_action_config.BertModel.from_pretrained", side_effect=AssertionError("Backbone training initialized")):
            main(["--snapshot-manifest", str(manifest), "--out-dir", str(output), "--validate-only"])
        self.assertFalse(output.exists())

    def test_test_fixture_cannot_start_actual_training(self):
        from train_action_config import main
        manifest, _, _ = self.export_fixture()
        output = self.folder / "blocked-fixture-training"
        with mock.patch("train_action_config.BertModel.from_pretrained", side_effect=AssertionError("Unexpected training initialization")):
            with self.assertRaisesRegex(ValueError, "Test fixtures"):
                main(["--snapshot-manifest", str(manifest), "--out-dir", str(output)])
        self.assertFalse(output.exists())

    def test_wrapper_has_explicit_stages_no_implicit_train(self):
        from retrain_and_eval import build_parser, main
        manifest, _, _ = self.export_fixture()
        with mock.patch("retrain_and_eval.subprocess.run", side_effect=AssertionError("Unexpected training process")):
            main(["validate", "--snapshot-manifest", str(manifest)])
        with self.assertRaises(SystemExit):
            build_parser().parse_args([])

    def test_report_creation_never_overwrites(self):
        from retrain_and_eval import write_report
        report = self.folder / "report.json"
        write_report(report, {"release_approved": False})
        before = file_sha256(report)
        with self.assertRaises(FileExistsError):
            write_report(report, {"release_approved": True})
        self.assertEqual(file_sha256(report), before)

    def evaluation_file(self, rows):
        path = self.folder / "diagnostic.jsonl"
        path.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n", encoding="utf-8")
        return argparse.Namespace(dataset=path, snapshot_manifest=None, split="test")

    def test_raw_evaluation_filters_declared_split(self):
        from retrain_and_eval import load_evaluation_rows
        rows, origin = load_evaluation_rows(self.evaluation_file(rows_fixture()))
        self.assertEqual([row["split"] for row in rows], ["test"])
        self.assertEqual(origin["source_row_count"], 3)
        self.assertEqual(origin["evaluated_row_count"], 1)
        self.assertEqual(origin["split_scope"], "test")

    def test_raw_evaluation_mixed_missing_split_is_rejected(self):
        from retrain_and_eval import load_evaluation_rows
        rows = rows_fixture()
        del rows[0]["split"]
        with self.assertRaisesRegex(ValueError, "every row"):
            load_evaluation_rows(self.evaluation_file(rows))

    def test_unlabelled_evaluation_is_explicitly_diagnostic_only(self):
        from retrain_and_eval import load_evaluation_rows
        rows = rows_fixture()
        for row in rows:
            del row["split"]
        actual, origin = load_evaluation_rows(self.evaluation_file(rows))
        self.assertEqual(len(actual), 3)
        self.assertEqual(origin["split_scope"], "unspecified_diagnostic_input")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, default=ROOT / "Experiments/workflow_fix_20261117/reports/training_checks.json")
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(WorkflowTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    report = {"tests_run": result.testsRun, "failures": [{"test": str(test), "traceback": trace} for test, trace in result.failures],
              "errors": [{"test": str(test), "traceback": trace} for test, trace in result.errors],
              "passed": result.wasSuccessful(), "training_started": False, "test_reviews_are_fixtures_not_real_evidence": True,
              "source_sha256": {name: file_sha256(Path(__file__).with_name(name)) for name in (
                  "training_data.py", "train_action_config.py", "retrain_and_eval.py", "review_evidence.py", "input_constraints.py")}}
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
