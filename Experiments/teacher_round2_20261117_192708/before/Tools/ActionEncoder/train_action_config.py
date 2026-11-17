"""Train MiniRBT v0.2 from a reviewed, frozen snapshot into an explicit new directory.

This command never promotes a checkpoint, changes a running service, or resplits data.
Use retrain_and_eval.py prepare/validate to build and inspect the snapshot first.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import torch
import torch.nn.functional as F
from transformers import BertModel, BertTokenizer

from action_config_schema import (
    CAPABILITY_PROFILE, CONFIG_VERSION, DECISIONS, INPUT_POLICY_VERSION,
    DECODER_POLICY_VERSION, LABEL_POLICY_VERSION, MAX_ACTIONS, MAX_CYCLES,
    RESOURCE_CATALOG_VERSION, RESOURCE_IDS, ActionConfigV02Model, ModelOutputError,
    decode_config,
)
from encoder import DEFAULT_MODEL_DIR, MODEL_ID, MODEL_REVISION, verify_model
from input_constraints import validate_instruction_constraints
from training_data import (build_samples, check_snapshot_unchanged, dataset_summary,
                           ensure_new_output_dir, file_sha256, load_snapshot, split_by_group)


def structure(config: dict) -> tuple:
    return (config["decision"], tuple(tuple(sorted((a["resource_id"], len(a["cycles"]))
             for a in step["actions"])) for step in config["steps"]))


def prediction_metrics(model: ActionConfigV02Model, features: torch.Tensor, samples: list[dict]) -> tuple[dict, list[dict]]:
    discrete = model.forward_discrete(features)
    predicted_resources = discrete["resource_id"].argmax(dim=-1)
    params = model.forward_params(discrete["h"], predicted_resources)
    counts = Counter()
    per_class = {decision: Counter() for decision in DECISIONS}
    predictions = []
    for index, sample in enumerate(samples):
        gold = sample["config"]
        decision = gold["decision"]
        counts["total"] += 1
        per_class[decision]["total"] += 1
        counts["execute_total" if decision == "execute" else "nonexecute_total"] += 1
        try:
            predicted = decode_config({key: value[index:index + 1] for key, value in discrete.items()}, params[index:index + 1])
            if sample.get("input_role", "instruction") == "instruction":
                audit = validate_instruction_constraints(sample["text"], predicted)
                if audit["violations"] or audit["unresolved"]:
                    failure = ModelOutputError("Prediction violates explicit instruction constraints or has unresolved numeric scope.")
                    failure.raw_config = predicted
                    failure.constraint_audit = audit
                    raise failure
            correct_decision = predicted["decision"] == decision
            correct_structure = structure(predicted) == structure(gold)
            counts["decision_correct"] += int(correct_decision)
            per_class[decision]["correct"] += int(correct_decision)
            counts["structure_correct"] += int(correct_structure)
            counts["execute_structure_correct"] += int(decision == "execute" and correct_structure)
            counts["false_execution"] += int(decision != "execute" and predicted["decision"] == "execute")
            predictions.append({"raw_text": sample["text"], "input_role": sample["input_role"],
                                "group_id": sample["group_id"], "gold": gold, "predicted": predicted})
        except ModelOutputError as exc:
            counts["technical_errors"] += 1
            record = {"raw_text": sample["text"], "input_role": sample["input_role"],
                      "group_id": sample["group_id"], "gold": gold, "technical_error": str(exc)}
            if hasattr(exc, "raw_config"):
                record.update(raw_prediction_before_guard=exc.raw_config, instruction_constraint_audit=exc.constraint_audit)
            predictions.append(record)
    macro = sum(c["correct"] / c["total"] for c in per_class.values() if c["total"]) / max(1, sum(bool(c["total"]) for c in per_class.values()))
    execute_accuracy = counts["execute_structure_correct"] / max(1, counts["execute_total"])
    nonexecute_specificity = 1 - counts["false_execution"] / max(1, counts["nonexecute_total"])
    error_rate = counts["technical_errors"] / max(1, counts["total"])
    score = (macro + execute_accuracy + nonexecute_specificity) / 3 - error_rate
    return {**counts, "per_decision": {d: dict(c) for d, c in per_class.items()},
            "macro_decision_accuracy": macro, "execute_structure_accuracy": execute_accuracy,
            "nonexecute_specificity": nonexecute_specificity, "technical_error_rate": error_rate,
            "selection_score": score,
            "selection_rule": "mean(macro_decision_accuracy, execute_structure_accuracy, nonexecute_specificity) - technical_error_rate"}, predictions


def write_epoch_predictions(out_dir: Path, epoch: int, predictions: list[dict]) -> Path:
    path = out_dir / f"epoch_{epoch}_validation_predictions.jsonl"
    with path.open("x", encoding="utf-8") as stream:
        for prediction in predictions:
            stream.write(json.dumps(prediction, ensure_ascii=False) + "\n")
    return path


def make_batch_tensors(items: list[dict]) -> dict[str, torch.Tensor]:
    return {
        "decision": torch.tensor([x["targets"]["decision"] for x in items], dtype=torch.long),
        "resource_id": torch.tensor([x["targets"]["resource_id"] for x in items], dtype=torch.long),
        "stage": torch.tensor([x["targets"]["stage"] for x in items], dtype=torch.long),
        "cycle_count": torch.tensor([x["targets"]["cycle_count"] for x in items], dtype=torch.long),
        "dur_norm": torch.tensor([x["targets"]["dur_norm"] for x in items], dtype=torch.float32),
        "amp_norm": torch.tensor([x["targets"]["amp_norm"] for x in items], dtype=torch.float32),
        "hold_norm": torch.tensor([x["targets"]["hold_norm"] for x in items], dtype=torch.float32),
        "amp_mask": torch.tensor([x["targets"]["amp_mask"] for x in items], dtype=torch.float32),
        "cyc_mask": torch.tensor([x["targets"]["cyc_mask"] for x in items], dtype=torch.float32),
    }


def compute_loss(model: ActionConfigV02Model, feats: torch.Tensor, batch: dict[str, torch.Tensor]) -> torch.Tensor:
    disc = model.forward_discrete(feats)
    dec_t = batch["decision"]
    loss = F.cross_entropy(disc["decision"], dec_t)

    exec_mask = dec_t == 0
    if exec_mask.any():
        loss = loss + F.cross_entropy(
            disc["resource_id"][exec_mask].reshape(-1, len(RESOURCE_IDS)),
            batch["resource_id"][exec_mask].reshape(-1),
        )
        act_mask = exec_mask.unsqueeze(1) & (batch["resource_id"] > 0)
        if act_mask.any():
            loss = loss + F.cross_entropy(disc["stage"][act_mask], batch["stage"][act_mask])
            loss = loss + F.cross_entropy(disc["cycle_count"][act_mask], batch["cycle_count"][act_mask])

        # Condition continuous param head on gold resource_id during training
        params_pred = model.forward_params(disc["h"], batch["resource_id"])
        cm = batch["cyc_mask"] * exec_mask.unsqueeze(1).unsqueeze(2).float()
        am = batch["amp_mask"] * exec_mask.unsqueeze(1).unsqueeze(2).float()
        if cm.sum() > 0:
            dur_err = F.smooth_l1_loss(params_pred[..., 0], batch["dur_norm"], reduction="none") * cm
            hold_err = F.smooth_l1_loss(params_pred[..., 2], batch["hold_norm"], reduction="none") * cm
            loss = loss + 2.0 * (dur_err.sum() + hold_err.sum()) / cm.sum()
        if am.sum() > 0:
            amp_err = F.smooth_l1_loss(params_pred[..., 1], batch["amp_norm"], reduction="none") * am
            loss = loss + 2.0 * amp_err.sum() / am.sum()

    return loss


def pool_backbone(backbone: BertModel, inputs: dict[str, torch.Tensor]) -> torch.Tensor:
    hidden = backbone(**inputs).last_hidden_state
    mask = inputs["attention_mask"].unsqueeze(-1).to(hidden.dtype)
    return (hidden * mask).sum(1) / mask.sum(1).clamp(min=1)


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot-manifest", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, help="Required for training; must not already exist.")
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--backbone-lr", type=float, default=8e-5)
    parser.add_argument("--unfreeze-layers", type=int, default=2)
    parser.add_argument("--threads", type=int, default=2)
    parser.add_argument("--status", choices=["experimental"], default="experimental")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args(argv)
    if min(args.epochs, args.batch_size, args.threads) < 1 or args.max_length < 8:
        parser.error("epochs, batch-size, threads must be positive; max-length must be >=8.")
    if not 0 <= args.unfreeze_layers <= 6:
        parser.error("unfreeze-layers must be 0..6.")
    if args.out_dir is None and not args.validate_only:
        parser.error("--out-dir is required; the current/default checkpoint is never overwritten.")
    out_dir = ensure_new_output_dir(args.out_dir) if args.out_dir else None
    source_paths = [Path(__file__).with_name(name) for name in (
        "train_action_config.py", "training_data.py", "review_evidence.py", "input_constraints.py", "action_config_schema.py", "encoder.py")]
    source_hashes = {path.name: file_sha256(path) for path in source_paths}
    snapshot_hash = file_sha256(args.snapshot_manifest)
    rows, frozen_manifest = load_snapshot(args.snapshot_manifest)
    if not args.validate_only and (frozen_manifest.get("test_fixture") is True or any(row.get("test_fixture") is True for row in rows)):
        raise ValueError("Test fixtures cannot be used for actual training; use --validate-only for regression checks.")
    summary = dataset_summary(rows)
    torch.set_num_threads(args.threads)
    torch.manual_seed(1337)
    verify_model(args.model_dir)
    tokenizer = BertTokenizer.from_pretrained(str(args.model_dir), local_files_only=True)
    samples = build_samples(rows, tokenizer, args.max_length)
    train_s, val_s, test_s = split_by_group(samples)
    print(json.dumps({"snapshot": str(args.snapshot_manifest.resolve()), **summary}, ensure_ascii=False), flush=True)
    if args.validate_only:
        print("Validated only. No training started or output directory created.", flush=True)
        return

    backbone = BertModel.from_pretrained(str(args.model_dir), local_files_only=True,
                                        use_safetensors=True, add_pooling_layer=False)
    for parameter in backbone.parameters():
        parameter.requires_grad = False
    if args.unfreeze_layers:
        for layer in backbone.encoder.layer[-args.unfreeze_layers:]:
            for parameter in layer.parameters():
                parameter.requires_grad = True
    model = ActionConfigV02Model(hidden_size=256)
    train_t = make_batch_tensors(train_s)
    val_t = make_batch_tensors(val_s)
    groups = [{"params": model.parameters(), "lr": args.lr}]
    backbone_parameters = [parameter for parameter in backbone.parameters() if parameter.requires_grad]
    if backbone_parameters:
        groups.append({"params": backbone_parameters, "lr": args.backbone_lr})
    optimizer = torch.optim.AdamW(groups, weight_decay=1e-2)
    check_snapshot_unchanged(args.snapshot_manifest, snapshot_hash)
    # Exclusive creation also protects against another trainer claiming the same path.
    out_dir.mkdir(parents=True, exist_ok=False)
    (out_dir / "training_request.json").write_text(json.dumps({
        "snapshot_manifest": str(args.snapshot_manifest.resolve()), "snapshot_manifest_sha256": snapshot_hash,
        "frozen_data_manifest": frozen_manifest, "dataset_summary": summary,
        "training_source_sha256": source_hashes,
        "arguments": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
        "status": "training", "release_approved": False}, ensure_ascii=False, indent=2), encoding="utf-8")
    best_key = None
    best_epoch = None
    best_model_state = best_backbone_state = None
    best_metrics = best_predictions = None
    best_val_loss = None
    for epoch in range(1, args.epochs + 1):
        model.train()
        backbone.train(args.unfreeze_layers > 0)
        permutation = torch.randperm(len(train_s)).tolist()
        total_loss = batches = 0
        for start in range(0, len(train_s), args.batch_size):
            indexes = permutation[start:start + args.batch_size]
            targets = {key: tensor[indexes] for key, tensor in train_t.items()}
            inputs = tokenizer([train_s[index]["model_text"] for index in indexes],
                               padding=True, truncation=False, return_tensors="pt")
            optimizer.zero_grad()
            features = pool_backbone(backbone, inputs)
            loss = compute_loss(model, features, targets)
            loss.backward()
            optimizer.step()
            total_loss += float(loss.item())
            batches += 1
        model.eval()
        backbone.eval()
        with torch.inference_mode():
            validation_inputs = tokenizer([sample["model_text"] for sample in val_s],
                                          padding=True, truncation=False, return_tensors="pt")
            validation_features = pool_backbone(backbone, validation_inputs)
            val_loss = float(compute_loss(model, validation_features, val_t).item())
            metrics, predictions = prediction_metrics(model, validation_features, val_s)
        key = (metrics["selection_score"], -metrics["technical_error_rate"], -val_loss)
        record = {"epoch": epoch, "train_loss": total_loss / max(1, batches),
                  "gold_conditioned_val_loss": val_loss, "predicted_resource_validation": metrics}
        prediction_path = write_epoch_predictions(out_dir, epoch, predictions)
        record["validation_predictions"] = {"path": prediction_path.name, "sha256": file_sha256(prediction_path)}
        with (out_dir / "epoch_metrics.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(json.dumps(record, ensure_ascii=False), flush=True)
        if best_key is None or key > best_key:
            best_key, best_epoch, best_val_loss = key, epoch, val_loss
            best_metrics, best_predictions = metrics, predictions
            best_model_state = {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
            best_backbone_state = {key: value.detach().cpu().clone() for key, value in backbone.state_dict().items()} if args.unfreeze_layers else None
    # Fail closed if data, review evidence, persona or source bindings changed mid-run.
    check_snapshot_unchanged(args.snapshot_manifest, snapshot_hash)
    if any(file_sha256(path) != source_hashes[path.name] for path in source_paths):
        raise ValueError("Training/inference source changed during this run; refusing to publish inconsistent checkpoint provenance.")
    checkpoint = out_dir / "config_head.pt"
    torch.save(best_model_state, checkpoint)
    if best_backbone_state is not None:
        torch.save(best_backbone_state, out_dir / "backbone_state.pt")
    checkpoint_id = file_sha256(checkpoint)[:12]
    for name, split_rows in (("train", train_s), ("val", val_s), ("test", test_s)):
        (out_dir / f"{name}_split.jsonl").write_text("\n".join(json.dumps({
            key: value for key, value in row.items() if key not in {"targets", "text", "model_text"}},
            ensure_ascii=False) for row in split_rows) + "\n", encoding="utf-8")
    (out_dir / "best_validation_predictions.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in best_predictions) + "\n", encoding="utf-8")
    supported_resources = sorted({action["resource_id"] for row in train_s
                                  for step in row["config"]["steps"] for action in step["actions"]},
                                 key=RESOURCE_IDS.index)
    manifest = {
        "model_id": MODEL_ID, "model_revision": MODEL_REVISION,
        "checkpoint_id": checkpoint_id, "model_version": f"minirbt-config-v02-{checkpoint_id}",
        "status": "experimental", "release_approved": False, "can_generate_configs": True,
        "parameter_schema_version": CONFIG_VERSION, "capability_profile": CAPABILITY_PROFILE,
        "resource_catalog_version": RESOURCE_CATALOG_VERSION, "label_policy_version": LABEL_POLICY_VERSION,
        "input_policy": INPUT_POLICY_VERSION, "decoder_policy": DECODER_POLICY_VERSION,
        "max_length": args.max_length, "unfrozen_layers": args.unfreeze_layers,
        "supported_resources": supported_resources, "max_actions": MAX_ACTIONS, "max_cycles": MAX_CYCLES,
        "decisions": DECISIONS, "train_count": len(train_s), "val_count": len(val_s), "test_count": len(test_s),
        "best_epoch": best_epoch, "selected_epoch_gold_conditioned_val_loss": best_val_loss,
        "best_validation_prediction_metrics": best_metrics, "data_summary": summary,
        "snapshot_manifest_path": str(args.snapshot_manifest.resolve()), "snapshot_manifest_sha256": snapshot_hash,
        "frozen_data_manifest": frozen_manifest,
        "training_source_sha256": source_hashes,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved experimental checkpoint to {out_dir}; no service or release status changed.", flush=True)


if __name__ == "__main__":
    main()
