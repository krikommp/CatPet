"""Train the resource-conditioned per-cycle MiniRBT model for action-config.v0.2."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import unicodedata
from collections import Counter
from functools import lru_cache

import torch
import torch.nn.functional as F
from transformers import BertModel, BertTokenizer

from action_config_schema import (
    CAPABILITY_PROFILE,
    CONFIG_VERSION,
    INPUT_POLICY_VERSION,
    DECODER_POLICY_VERSION,
    ModelOutputError,
    format_input_text,
    DECISIONS,
    LABEL_POLICY_VERSION,
    MAX_ACTIONS,
    MAX_CYCLES,
    RESOURCE_CATALOG_VERSION,
    RESOURCE_IDS,
    ActionConfigV02Model,
    canonicalize_config,
    decode_config,
)
from encoder import DEFAULT_MODEL_DIR, MODEL_ID, MODEL_REVISION, ROOT, verify_model

RUN_ROOT = Path(__file__).resolve().parent.parent
from input_constraints import validate_instruction_constraints
DEFAULT_DATASET = RUN_ROOT / "data" / "training_snapshot.jsonl"
DEFAULT_OUT_DIR = RUN_ROOT / "checkpoints" / "teacher_round_001"


def json_line(raw: str) -> dict:
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError(f"Duplicate JSON key: {key}")
            obj[key] = value
        return obj
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(f"Non-finite JSON: {value}")))


def training_binding(persona_file: Path, rubric_version: str) -> dict:
    if not persona_file.is_file() or not persona_file.read_bytes().strip():
        raise ValueError("A real, non-empty Gemini persona file is required before training.")
    if not isinstance(rubric_version, str) or not rubric_version.strip():
        raise ValueError("An explicit review rubric version is required.")
    return {"persona_file": str(persona_file.resolve()),
            "persona_sha256": hashlib.sha256(persona_file.read_bytes()).hexdigest(),
            "review_rubric_version": rubric_version.strip(),
            "compiler_sha256": hashlib.sha256((RUN_ROOT / "source/csharp/ActionConfigCompiler.cs").read_bytes()).hexdigest(),
            "resource_sha256": hashlib.sha256((RUN_ROOT / "source/csharp/ActionResourceCatalog.cs").read_bytes()).hexdigest(),
            "native_profile_sha256": hashlib.sha256((RUN_ROOT / "source/csharp/YukikazeActionCatalog.cs").read_bytes()).hexdigest()}


@lru_cache(maxsize=8)
def checked_evidence(path: str, expected_sha256: str) -> tuple[dict, ...]:
    source = (RUN_ROOT / path).resolve()
    if not source.is_relative_to(RUN_ROOT.resolve()) or not source.is_file():
        raise ValueError("Compilation evidence must be a file inside the experiment snapshot.")
    data = source.read_bytes()
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("Compilation evidence/source hash mismatch.")
    return tuple(json_line(line) for line in data.decode("utf-8-sig").splitlines() if line.strip())


def validate_compile_evidence(row: dict, binding: dict) -> None:
    provenance = row["provenance"]
    if provenance.get("compiler_snapshot_sha256") != binding["compiler_sha256"]:
        raise ValueError("Compilation evidence is not bound to the isolated compiler snapshot.")
    if provenance.get("resource_implementation_sha256") != binding["resource_sha256"]:
        raise ValueError("Compilation evidence is not bound to the isolated resource snapshot.")
    report = checked_evidence(provenance.get("compile_report_path", "reports/compiler_patched_corpus.jsonl"),
                              provenance.get("patched_csharp_compile_report_sha256", ""))
    index = provenance.get("compile_report_row")
    if type(index) is not int or not 1 <= index <= len(report):
        raise ValueError("Invalid compilation report row.")
    result = report[index - 1]
    if not result.get("compile_ok") or result.get("raw_text") != row["raw_text"]:
        raise ValueError("Compilation report failed or belongs to another input.")
    original_rows = checked_evidence(provenance.get("source_file", ""), provenance.get("source_sha256", ""))
    source_index = provenance.get("source_line")
    if type(source_index) is not int or not 1 <= source_index <= len(original_rows):
        raise ValueError("Invalid source row for compilation evidence.")
    original = original_rows[source_index - 1]
    original_config = original.get("config") if isinstance(original.get("config"), dict) else json_line(original["config_json"])
    if original_config != row["config"]:
        raise ValueError("Training label differs from the configuration actually compiled.")


def validate_provenance(row: dict, binding: dict) -> None:
    provenance = row.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("Every row needs provenance with a real persona/rubric binding.")
    if provenance.get("persona_sha256") != binding["persona_sha256"]:
        raise ValueError("Dataset persona hash differs from the training persona.")
    if row.get("split") == "train" and row.get("training_eligible") is not True:
        raise ValueError("Training row must explicitly declare training_eligible=true.")
    source_type = row.get("source_type") or provenance.get("source_type")
    if source_type not in {"historical_synthetic", "ai_video_reviewed", "ai_semantic_reviewed", "teacher_fixed_eval"}:
        raise ValueError(f"Unsupported or missing source_type: {source_type}.")
    rubric_key = "label_policy_review_rubric_version" if source_type == "historical_synthetic" else "review_rubric_version"
    if provenance.get(rubric_key) != binding["review_rubric_version"]:
        raise ValueError(f"Dataset {rubric_key} differs from this run.")
    if row["config"]["decision"] == "execute":
        validate_compile_evidence(row, binding)
    if source_type in {"ai_video_reviewed", "ai_semantic_reviewed"}:
        if provenance.get("reviewer_type") != "AI" or provenance.get("review_status") != "accepted":
            raise ValueError("AI-reviewed rows require an accepted AI review.")
    if source_type == "ai_video_reviewed":
        for key in ("candidate_id", "config_sha256", "video_sha256", "resource_sha256", "compiler_sha256"):
            if not provenance.get(key):
                raise ValueError(f"AI video provenance is missing {key}.")
        canonical_hash = hashlib.sha256(json.dumps(row["config"], sort_keys=True, ensure_ascii=False,
                                                  separators=(",", ":")).encode("utf-8")).hexdigest()
        if provenance["config_sha256"] != canonical_hash:
            raise ValueError("AI video config hash does not match its training label.")


def load_samples(dataset_path: Path, tokenizer: BertTokenizer, max_length: int,
                 binding: dict | None = None) -> list[dict]:
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")
    samples = []
    for line_no, raw in enumerate(dataset_path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json_line(raw)
            text = (row.get("raw_text") or "").strip()
            role = row.get("input_role")
            model_text = format_input_text(text, role)
            token_ids = tokenizer.encode(model_text, add_special_tokens=True, truncation=False)
            if len(token_ids) > max_length:
                raise ValueError(f"exceeds max_length={max_length} ({len(token_ids)} tokens).")
            cfg = row.get("config") if isinstance(row.get("config"), dict) else json_line(row["config_json"])
            targets = canonicalize_config(cfg)
            if role == "instruction":
                constraints = validate_instruction_constraints(text, cfg)
                if constraints["violations"] or constraints["unresolved"]:
                    raise ValueError(f"Instruction constraint mismatch/unresolved scope: {constraints}")
            if row.get("split") not in {"train", "val", "test"} or not row.get("group_id"):
                raise ValueError("Every row needs an explicit split and global group_id.")
            if binding is not None:
                validate_provenance({**row, "config": cfg}, binding)
            samples.append({**row, "text": text, "model_text": model_text,
                            "config": cfg, "targets": targets})
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"{dataset_path}:{line_no}: {exc}") from exc
    if not samples:
        raise ValueError("Dataset is empty.")
    return samples


def normalized_text(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKC", text).casefold()
                   if not c.isspace() and not unicodedata.category(c).startswith("P"))


def split_by_group(samples: list[dict], seed: int = 1337) -> tuple[list[dict], list[dict], list[dict]]:
    # No resampling: the predeclared global semantic-family assignment is authoritative.
    memberships = {}
    split_rows = {name: [] for name in ("train", "val", "test")}
    for sample in samples:
        split = sample.get("split")
        if split not in split_rows:
            raise ValueError("Every sample must declare train, val or test.")
        group = sample.get("group_id")
        if not group:
            raise ValueError("Every sample must declare a global group_id.")
        identities = [("group_id", group), ("raw_text", normalized_text(sample["text"]))]
        if sample.get("semantic_family_id"):
            identities.append(("semantic_family_id", sample["semantic_family_id"]))
        for identity in identities:
            if identity in memberships and memberships[identity] != split:
                raise ValueError(f"Cross-split leakage: {identity} belongs to {memberships[identity]} and {split}.")
            memberships[identity] = split
        split_rows[split].append(sample)
    if not all(split_rows.values()):
        raise ValueError("Fixed train, validation and test splits must all be non-empty.")
    return tuple(split_rows[name] for name in ("train", "val", "test"))


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
            predictions.append({"raw_text": sample["text"], "group_id": sample["group_id"], "gold": gold, "predicted": predicted})
        except ModelOutputError as exc:
            counts["technical_errors"] += 1
            record = {"raw_text": sample["text"], "group_id": sample["group_id"], "gold": gold, "technical_error": str(exc)}
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--backbone-lr", type=float, default=8e-5)
    parser.add_argument("--unfreeze-layers", type=int, default=2)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--status", choices=["experimental"], default="experimental")
    parser.add_argument("--persona-file", type=Path, required=True)
    parser.add_argument("--review-rubric-version", required=True)
    parser.add_argument("--validate-only", action="store_true", help="Validate data/provenance without creating a checkpoint.")
    args = parser.parse_args()

    if args.epochs < 1 or args.batch_size < 1 or args.threads < 1:
        raise ValueError("epochs, batch-size and threads must be positive.")
    binding = training_binding(args.persona_file, args.review_rubric_version)
    if args.out_dir.exists() and any(args.out_dir.iterdir()):
        raise ValueError("Refusing to overwrite a non-empty checkpoint directory.")
    if not args.out_dir.resolve().is_relative_to(RUN_ROOT.resolve()):
        raise ValueError("This isolated trainer only writes below its experiment run directory.")
    torch.set_num_threads(args.threads)
    torch.manual_seed(1337)
    verify_model(args.model_dir)

    tokenizer = BertTokenizer.from_pretrained(str(args.model_dir), local_files_only=True)
    samples = load_samples(args.dataset, tokenizer, args.max_length, binding)
    train_s, val_s, test_s = split_by_group(samples)
    print(f"Loaded {len(samples)} v0.2 samples -> train={len(train_s)}, val={len(val_s)}, test={len(test_s)}", flush=True)
    if args.validate_only:
        print("Validated only; no training started and no checkpoint created.", flush=True)
        return
    backbone = BertModel.from_pretrained(
        str(args.model_dir), local_files_only=True, use_safetensors=True, add_pooling_layer=False
    )
    for p in backbone.parameters():
        p.requires_grad = False
    if args.unfreeze_layers > 0:
        for layer in backbone.encoder.layer[-args.unfreeze_layers :]:
            for p in layer.parameters():
                p.requires_grad = True

    model = ActionConfigV02Model(hidden_size=256)
    train_t = make_batch_tensors(train_s)
    val_t = make_batch_tensors(val_s) if val_s else None

    bb_params = [p for p in backbone.parameters() if p.requires_grad]
    opt_groups = [{"params": model.parameters(), "lr": args.lr}]
    if bb_params:
        opt_groups.append({"params": bb_params, "lr": args.backbone_lr})
    opt = torch.optim.AdamW(opt_groups, weight_decay=1e-2)

    best_val = float("inf")
    best_key = None
    best_epoch = None
    best_predictions = []
    best_metrics = {}
    args.out_dir.mkdir(parents=True, exist_ok=True)
    history = []
    best_model_state = None
    best_bb_state = None

    for epoch in range(1, args.epochs + 1):
        model.train()
        if args.unfreeze_layers > 0:
            backbone.train()
        else:
            backbone.eval()
        perm = torch.randperm(len(train_s)).tolist()
        total_loss = 0.0
        steps = 0
        for start in range(0, len(train_s), args.batch_size):
            idx = perm[start : start + args.batch_size]
            sub = {k: v[idx] for k, v in train_t.items()}
            opt.zero_grad()
            inputs = tokenizer([train_s[i]["model_text"] for i in idx], padding=True, truncation=False, return_tensors="pt")
            feats = pool_backbone(backbone, inputs)
            loss = compute_loss(model, feats, sub)
            loss.backward()
            opt.step()
            total_loss += float(loss.item())
            steps += 1

        val_loss = total_loss / max(1, steps)
        if val_t is not None:
            model.eval()
            backbone.eval()
            with torch.no_grad():
                v_in = tokenizer([s["model_text"] for s in val_s], padding=True, truncation=False, return_tensors="pt")
                v_feats = pool_backbone(backbone, v_in)
                val_loss = float(compute_loss(model, v_feats, val_t).item())
                metrics, predictions = prediction_metrics(model, v_feats, val_s)
        selection_key = (metrics["selection_score"], -metrics["technical_error_rate"], -val_loss)
        history.append({"epoch": epoch, "train_loss": total_loss / max(1, steps), "gold_conditioned_val_loss": val_loss,
                        "predicted_resource_validation": metrics})
        with (args.out_dir / "epoch_metrics.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(history[-1], ensure_ascii=False) + "\n")
        print(json.dumps(history[-1], ensure_ascii=False), flush=True)
        if best_key is None or selection_key > best_key:
            best_key = selection_key
            best_epoch = epoch
            best_predictions = predictions
            best_metrics = metrics
            best_val = val_loss
            best_model_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            if args.unfreeze_layers > 0:
                best_bb_state = {k: v.detach().cpu().clone() for k, v in backbone.state_dict().items()}

    (args.out_dir / "best_validation_predictions.jsonl").write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in best_predictions) + "\n", encoding="utf-8")
    ckpt_path = args.out_dir / "config_head.pt"
    torch.save(best_model_state or model.state_dict(), ckpt_path)
    if best_bb_state is not None:
        torch.save(best_bb_state, args.out_dir / "backbone_state.pt")
    elif (args.out_dir / "backbone_state.pt").exists():
        (args.out_dir / "backbone_state.pt").unlink()

    ckpt_hash = hashlib.sha256(ckpt_path.read_bytes()).hexdigest()[:12]
    if test_s:
        (args.out_dir / "test_split.jsonl").write_text(
            "\n".join(json.dumps({k: v for k, v in s.items() if k not in {"text", "model_text", "targets"}}, ensure_ascii=False) for s in test_s) + "\n",
            encoding="utf-8",
        )

    manifest = {
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "checkpoint_id": ckpt_hash,
        "model_version": f"minirbt-config-v02-{ckpt_hash}",
        "status": "experimental",
        "release_approved": False,
        "input_policy": INPUT_POLICY_VERSION,
        "decoder_policy": DECODER_POLICY_VERSION,
        "persona_binding": binding,
        "dataset_sha256": hashlib.sha256(args.dataset.read_bytes()).hexdigest(),
        "dataset_path": str(args.dataset.resolve()),
        "training_source_counts": dict(Counter(s.get("source_type") or s["provenance"]["source_type"] for s in train_s)),
        "train_decision_counts": dict(Counter(s["config"]["decision"] for s in train_s)),
        "val_decision_counts": dict(Counter(s["config"]["decision"] for s in val_s)),
        "missing_train_decisions": [decision for decision in DECISIONS if not any(s["config"]["decision"] == decision for s in train_s)],
        "split_group_ids": {name: sorted({s["group_id"] for s in rows}) for name, rows in (("train", train_s), ("val", val_s), ("test", test_s))},
        "training_arguments": {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()},
        "best_epoch": best_epoch,
        "best_validation_prediction_metrics": best_metrics,
        "can_generate_configs": True,
        "parameter_schema_version": CONFIG_VERSION,
        "capability_profile": CAPABILITY_PROFILE,
        "resource_catalog_version": RESOURCE_CATALOG_VERSION,
        "label_policy_version": LABEL_POLICY_VERSION,
        "max_length": args.max_length,
        "unfrozen_layers": args.unfreeze_layers,
        "supported_resources": RESOURCE_IDS[1:],
        "max_actions": MAX_ACTIONS,
        "max_cycles": MAX_CYCLES,
        "decisions": DECISIONS,
        "train_count": len(train_s),
        "val_count": len(val_s),
        "test_count": len(test_s),
        "selected_epoch_gold_conditioned_val_loss": round(best_val, 6),
    }
    (args.out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved v0.2 checkpoint & manifest to {args.out_dir} (best_val_loss={best_val:.4f})", flush=True)


if __name__ == "__main__":
    main()
