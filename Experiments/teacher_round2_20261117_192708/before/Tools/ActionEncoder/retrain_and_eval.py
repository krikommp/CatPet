"""Explicit v0.2 prepare, validate, train and evaluate commands.

No command promotes a model to ready, replaces latest/v02_latest, restarts a service,
requires human keep, or automatically chains preparation into training.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import subprocess
import sys

from training_data import ROOT, dataset_summary, ensure_new_output_dir, file_sha256, load_snapshot

TOOLS_DIR = Path(__file__).resolve().parent


def write_report(path: Path, report: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def structure(config: dict) -> tuple:
    return config["decision"], tuple(tuple(sorted((action["resource_id"], len(action["cycles"]))
                                                for action in step["actions"])) for step in config["steps"])


def train_command(args) -> list[str]:
    ensure_new_output_dir(args.out_dir)
    return [sys.executable, str(TOOLS_DIR / "train_action_config.py"),
            "--snapshot-manifest", str(args.snapshot_manifest), "--out-dir", str(args.out_dir),
            "--epochs", str(args.epochs), "--batch-size", str(args.batch_size),
            "--unfreeze-layers", str(args.unfreeze_layers), "--threads", str(args.threads)]


def load_evaluation_rows(args) -> tuple[list[dict], dict]:
    if args.split not in {"val", "test"}:
        raise ValueError("Evaluation split must be val or test; training data is not a holdout.")
    if args.snapshot_manifest:
        rows, snapshot = load_snapshot(args.snapshot_manifest)
        rows = [row for row in rows if row["split"] == args.split]
        data_origin = {"snapshot_manifest": str(args.snapshot_manifest.resolve()),
                       "snapshot_manifest_sha256": file_sha256(args.snapshot_manifest),
                       "split_scope": args.split, "validated_frozen_snapshot": True}
    else:
        from review_evidence import strict_json
        rows = [strict_json(line) for line in args.dataset.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
        if any(not isinstance(row, dict) for row in rows):
            raise ValueError("Evaluation JSONL rows must be objects.")
        data_origin = {"dataset": str(args.dataset.resolve()), "dataset_sha256": file_sha256(args.dataset),
                       "validated_frozen_snapshot": False, "scope": "diagnostic_only_not_training_admission",
                       "source_row_count": len(rows)}
        if any("split" in row for row in rows):
            if any(row.get("split") not in {"train", "val", "test"} for row in rows):
                raise ValueError("A dataset with split fields must declare a valid split on every row.")
            rows = [row for row in rows if row["split"] == args.split]
            data_origin["split_scope"] = args.split
        else:
            data_origin["split_scope"] = "unspecified_diagnostic_input"
            data_origin["note"] = "No split labels supplied: this report does not establish a held-out test set."
    if not rows:
        raise ValueError("Selected evaluation split is empty.")
    data_origin["evaluated_row_count"] = len(rows)
    return rows, data_origin


def evaluate(args) -> dict:
    from action_config_schema import canonicalize_config
    from encoder import LocalEncoder
    from input_constraints import validate_instruction_constraints
    source_paths = [TOOLS_DIR / name for name in ("retrain_and_eval.py", "encoder.py", "action_config_schema.py", "input_constraints.py")]
    source_hashes = {path.name: file_sha256(path) for path in source_paths}
    if args.report.exists():
        raise FileExistsError(f"Refusing to overwrite a report: {args.report}")
    if args.report.resolve().is_relative_to(args.checkpoint_dir.resolve()):
        raise ValueError("Write diagnostic reports outside checkpoint directories.")
    rows, data_origin = load_evaluation_rows(args)
    for index, row in enumerate(rows, 1):
        if row.get("input_role") not in {"instruction", "dialogue"}:
            raise ValueError(f"Evaluation row {index} requires explicit input_role.")
        # Shape/parameter correctness is required for reference labels; no video claim is inferred.
        canonicalize_config(row["config"])
    encoder = LocalEncoder(config_head_dir=args.checkpoint_dir, threads=args.threads)
    manifest = encoder.config_head_manifest
    if not manifest:
        raise ValueError("The checkpoint must contain a trained v0.2 configuration head.")
    counts = Counter()
    confusion = defaultdict(Counter)
    predictions = []
    for index, row in enumerate(rows):
        gold = row["config"]
        expected = gold["decision"]
        counts["total"] += 1
        counts[f"gold_{expected}"] += 1
        result = {"raw_text": row["raw_text"], "input_role": row["input_role"], "group_id": row.get("group_id"), "expected": gold}
        request = {"text": row["raw_text"], "input_role": row["input_role"], "request_id": f"frozen-eval-{index}",
                   **{key: manifest[key] for key in ("capability_profile", "resource_catalog_version", "parameter_schema_version", "label_policy_version")}}
        try:
            response = encoder.configure(request)
            predicted = response["config"]
            result.update(predicted=predicted, inference_ms=response["inference_ms"])
            counts["decision_correct"] += int(predicted["decision"] == expected)
            counts["structure_correct"] += int(structure(predicted) == structure(gold))
            counts["execute_structure_correct"] += int(expected == "execute" and structure(predicted) == structure(gold))
            if expected != "execute":
                counts[f"false_execute_{expected}"] += int(predicted["decision"] == "execute")
            confusion[expected][predicted["decision"]] += 1
            if row["input_role"] == "instruction":
                result["explicit_instruction_constraints"] = validate_instruction_constraints(row["raw_text"], predicted)
        except Exception as exc:
            # A failed prediction remains a technical error, never a fabricated semantic class.
            counts["technical_errors"] += 1
            confusion[expected]["technical_error"] += 1
            result["technical_error"] = {"type": type(exc).__name__, "message": str(exc)}
            for field in ("raw_config", "constraint_audit"):
                if hasattr(exc, field):
                    result[field] = getattr(exc, field)
        predictions.append(result)
    if any(file_sha256(path) != source_hashes[path.name] for path in source_paths):
        raise ValueError("Inference sources changed during evaluation; rerun after they are stable.")
    return {"stage": "diagnostic_report", "checkpoint_id": manifest["checkpoint_id"],
            "execution_source_sha256": source_hashes,
            "input_policy": manifest.get("input_policy", "legacy_raw_text"),
            "checkpoint_sha256": {name: file_sha256(args.checkpoint_dir / name)
                for name in ("config_head.pt", "backbone_state.pt", "manifest.json") if (args.checkpoint_dir / name).exists()},
            "data": data_origin, "metrics": dict(counts), "confusion": {key: dict(value) for key, value in confusion.items()},
            "predictions": predictions, "release_approved": False, "training_started": False,
            "limitations": ["No Unity playback or video review is performed by this evaluator.",
                            "Semantic-family independence from an older checkpoint is not inferred.",
                            "Unconstrained parameter MAE is not a success metric; explicit instruction checks retain unresolved scopes."]}


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prepare = commands.add_parser("prepare", help="Validate review evidence and freeze data; never starts training.")
    prepare.add_argument("--records", type=Path, required=True)
    prepare.add_argument("--out-dir", type=Path, required=True)
    prepare.add_argument("--persona-file", type=Path, required=True)
    prepare.add_argument("--review-rubric-version", required=True)
    prepare.add_argument("--compiler-file", type=Path, default=ROOT / "Assets/Scripts/ActionLanguage/ActionConfigCompiler.cs")
    prepare.add_argument("--resource-file", type=Path, default=ROOT / "Assets/Scripts/ActionLanguage/ActionResourceCatalog.cs")
    prepare.add_argument("--native-profile-file", type=Path, default=ROOT / "Assets/Scripts/ActionLanguage/YukikazeActionCatalog.cs")
    prepare.add_argument("--ffmpeg", type=Path)
    validate = commands.add_parser("validate", help="Recheck a frozen data snapshot without training.")
    validate.add_argument("--snapshot-manifest", type=Path, required=True)
    validate.add_argument("--report", type=Path)
    train = commands.add_parser("train", help="Explicitly start v0.2 training into a new directory.")
    train.add_argument("--snapshot-manifest", type=Path, required=True)
    train.add_argument("--out-dir", type=Path, required=True)
    train.add_argument("--epochs", type=int, default=20)
    train.add_argument("--batch-size", type=int, default=32)
    train.add_argument("--unfreeze-layers", type=int, default=2)
    train.add_argument("--threads", type=int, choices=range(1, 17), default=2)
    evaluation = commands.add_parser("evaluate", help="Write a separate v0.2 diagnostic report; never promotes a checkpoint.")
    evaluation.add_argument("--checkpoint-dir", type=Path, required=True)
    datasets = evaluation.add_mutually_exclusive_group(required=True)
    datasets.add_argument("--snapshot-manifest", type=Path)
    datasets.add_argument("--dataset", type=Path, help="Explicit diagnostic-only dataset; does not confer training admission.")
    evaluation.add_argument("--split", choices=["val", "test"], default="test",
                            help="Select this split whenever row labels exist; unlabelled input is diagnostic-only.")
    evaluation.add_argument("--report", type=Path, required=True)
    evaluation.add_argument("--threads", type=int, choices=range(1, 17), default=2)
    return parser


def main(argv: list[str] | None = None):
    args = build_parser().parse_args(argv)
    if args.command == "prepare":
        from review_evidence import export_snapshot
        ensure_new_output_dir(args.out_dir)
        manifest_path = export_snapshot(args.records, args.out_dir, persona_file=args.persona_file,
            rubric_version=args.review_rubric_version, compiler_file=args.compiler_file,
            resource_file=args.resource_file, native_profile_file=args.native_profile_file,
            ffmpeg_path=args.ffmpeg)
        print(json.dumps({"stage": "frozen_data", "manifest": str(manifest_path), "training_started": False}, ensure_ascii=False))
    elif args.command == "validate":
        rows, manifest = load_snapshot(args.snapshot_manifest)
        report = {"stage": "validated_frozen_data", "manifest_sha256": file_sha256(args.snapshot_manifest),
                  **dataset_summary(rows), "training_started": False}
        if args.report:
            write_report(args.report, report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif args.command == "train":
        subprocess.run(train_command(args), check=True)
    else:
        report = evaluate(args)
        write_report(args.report, report)
        print(json.dumps({"report": str(args.report.resolve()), "metrics": report["metrics"],
                          "release_approved": False, "training_started": False}, ensure_ascii=False))


if __name__ == "__main__":
    main()
