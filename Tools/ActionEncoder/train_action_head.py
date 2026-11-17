"""Train the MiniRBT action prediction head (supports freezing or unfreezing top backbone layers)."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random

import torch
import torch.nn.functional as F
from transformers import BertModel, BertTokenizer

from action_schema import (
    ACTION_TYPES,
    CAPABILITY_PROFILE,
    DECISIONS,
    LABEL_POLICY_VERSION,
    MAX_SLOTS,
    MOTION_MAP_VERSION,
    ActionHeadModel,
    canonicalize_plan,
)
from encoder import DEFAULT_MODEL_DIR, MODEL_ID, MODEL_REVISION, verify_model

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "Dataset" / "ActionCards" / "qualified_semantic.jsonl"
DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "checkpoints" / "latest"


def load_samples(dataset_path: Path, tokenizer: BertTokenizer, max_length: int) -> list[dict]:
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")
    samples = []
    for line_no, raw in enumerate(dataset_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        row = json.loads(raw)
        text = (row.get("raw_text") or "").strip()
        if not text:
            raise ValueError(f"Line {line_no}: empty raw_text.")
        token_ids = tokenizer.encode(text, add_special_tokens=True, truncation=False)
        if len(token_ids) > max_length:
            raise ValueError(f"Line {line_no}: text exceeds max_length={max_length} ({len(token_ids)} tokens); refusing truncated training.")
        plan_obj = row.get("plan") if isinstance(row.get("plan"), dict) else json.loads(row["plan_json"])
        targets = canonicalize_plan(plan_obj)
        samples.append({
            "group_id": row.get("group_id") or text,
            "text": text,
            "plan": plan_obj,
            "targets": targets,
        })
    return samples


def split_by_group(samples: list[dict], seed: int = 1337) -> tuple[list[dict], list[dict], list[dict]]:
    # Stratified group split by decision category so val/test always include non-execute denominators when present.
    buckets: dict[int, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for s in samples:
        dec = s["targets"]["decision"]
        buckets[dec][s["group_id"]].append(s)

    rng = random.Random(seed)
    train, val, test = [], [], []
    for dec in sorted(buckets.keys()):
        groups = buckets[dec]
        keys = sorted(groups.keys())
        rng.shuffle(keys)
        n = len(keys)
        if n >= 3:
            n_val = max(1, int(round(n * 0.1)))
            n_test = max(1, int(round(n * 0.1)))
            n_train = max(1, n - n_val - n_test)
        else:
            n_train = max(1, int(round(n * 0.8)))
            n_val = max(0, n - n_train)
        for k in keys[:n_train]:
            train.extend(groups[k])
        for k in keys[n_train : n_train + n_val]:
            val.extend(groups[k])
        for k in keys[n_train + n_val :]:
            test.extend(groups[k])
    return train, val, test


def compute_loss(logits: dict[str, torch.Tensor], batch: dict[str, torch.Tensor]) -> torch.Tensor:
    decision_t = batch["decision"]
    loss = F.cross_entropy(logits["decision"], decision_t)

    exec_mask = decision_t == 0
    if exec_mask.any():
        type_logits = logits["type"][exec_mask].reshape(-1, len(ACTION_TYPES))
        type_t = batch["type"][exec_mask].reshape(-1)
        loss = loss + F.cross_entropy(type_logits, type_t)

        active_mask = exec_mask.unsqueeze(1) & (batch["type"] > 0)
        if active_mask.any():
            for key in ("stage", "count", "speed"):
                k_logits = logits[key][active_mask]
                k_t = batch[key][active_mask]
                loss = loss + F.cross_entropy(k_logits, k_t)

            non_blink_mask = active_mask & (batch["type"] != 1)
            if non_blink_mask.any():
                amp_logits = logits["amplitude"][non_blink_mask]
                amp_t = batch["amplitude"][non_blink_mask]
                loss = loss + F.cross_entropy(amp_logits, amp_t)

    return loss


def pool_backbone(backbone: BertModel, inputs: dict[str, torch.Tensor]) -> torch.Tensor:
    hidden = backbone(**inputs).last_hidden_state
    mask = inputs["attention_mask"].unsqueeze(-1).to(hidden.dtype)
    return (hidden * mask).sum(1) / mask.sum(1).clamp(min=1)


def make_target_tensors(items: list[dict]) -> dict[str, torch.Tensor]:
    return {
        "decision": torch.tensor([x["targets"]["decision"] for x in items], dtype=torch.long),
        "type": torch.tensor([x["targets"]["type"] for x in items], dtype=torch.long),
        "stage": torch.tensor([x["targets"]["stage"] for x in items], dtype=torch.long),
        "count": torch.tensor([x["targets"]["count"] for x in items], dtype=torch.long),
        "amplitude": torch.tensor([x["targets"]["amplitude"] for x in items], dtype=torch.long),
        "speed": torch.tensor([x["targets"]["speed"] for x in items], dtype=torch.long),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--max-length", type=int, default=128)
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=32)
    parser.add_argument("--lr", type=float, default=8e-4)
    parser.add_argument("--backbone-lr", type=float, default=5e-5)
    parser.add_argument("--unfreeze-layers", type=int, default=0)
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--status", choices=["experimental", "ready"], default="experimental")
    args = parser.parse_args()

    torch.set_num_threads(args.threads)
    torch.manual_seed(1337)

    verify_model(args.model_dir)
    tokenizer = BertTokenizer.from_pretrained(str(args.model_dir), local_files_only=True)
    backbone = BertModel.from_pretrained(
        str(args.model_dir), local_files_only=True, use_safetensors=True, add_pooling_layer=False
    )

    for p in backbone.parameters():
        p.requires_grad = False
    if args.unfreeze_layers > 0:
        layers = backbone.encoder.layer
        for layer in layers[-args.unfreeze_layers :]:
            for p in layer.parameters():
                p.requires_grad = True

    samples = load_samples(args.dataset, tokenizer, args.max_length)
    train_s, val_s, test_s = split_by_group(samples)
    print(f"Loaded {len(samples)} samples -> train={len(train_s)}, val={len(val_s)}, test={len(test_s)} (unfreeze_layers={args.unfreeze_layers})", flush=True)

    head = ActionHeadModel(hidden_size=256)

    if args.unfreeze_layers == 0:
        # Fast frozen feature caching path
        backbone.eval()
        with torch.no_grad():
            tr_in = tokenizer([s["text"] for s in train_s], padding=True, truncation=False, return_tensors="pt")
            train_feat = pool_backbone(backbone, tr_in)
            val_feat = None
            if val_s:
                va_in = tokenizer([s["text"] for s in val_s], padding=True, truncation=False, return_tensors="pt")
                val_feat = pool_backbone(backbone, va_in)
        train_t = make_target_tensors(train_s)
        val_t = make_target_tensors(val_s) if val_s else None
        opt = torch.optim.AdamW(head.parameters(), lr=args.lr, weight_decay=1e-2)
    else:
        train_t = make_target_tensors(train_s)
        val_t = make_target_tensors(val_s) if val_s else None
        backbone_params = [p for p in backbone.parameters() if p.requires_grad]
        opt = torch.optim.AdamW([
            {"params": head.parameters(), "lr": args.lr},
            {"params": backbone_params, "lr": args.backbone_lr},
        ], weight_decay=1e-2)

    best_val = float("inf")
    best_head_state = None
    best_backbone_state = None

    for epoch in range(1, args.epochs + 1):
        head.train()
        if args.unfreeze_layers > 0:
            backbone.train()
        perm = torch.randperm(len(train_s)).tolist()
        total_loss = 0.0
        steps = 0

        for start in range(0, len(train_s), args.batch_size):
            idx = perm[start : start + args.batch_size]
            sub_t = {k: v[idx] for k, v in train_t.items()}
            opt.zero_grad()
            if args.unfreeze_layers == 0:
                feats = train_feat[idx]
            else:
                batch_texts = [train_s[i]["text"] for i in idx]
                inputs = tokenizer(batch_texts, padding=True, truncation=False, return_tensors="pt")
                feats = pool_backbone(backbone, inputs)
            loss = compute_loss(head(feats), sub_t)
            loss.backward()
            opt.step()
            total_loss += float(loss.item())
            steps += 1

        val_loss = total_loss / max(1, steps)
        if val_t is not None:
            head.eval()
            backbone.eval()
            with torch.no_grad():
                if args.unfreeze_layers == 0:
                    v_feats = val_feat
                else:
                    v_in = tokenizer([s["text"] for s in val_s], padding=True, truncation=False, return_tensors="pt")
                    v_feats = pool_backbone(backbone, v_in)
                val_loss = float(compute_loss(head(v_feats), val_t).item())

        if val_loss <= best_val:
            best_val = val_loss
            best_head_state = {k: v.detach().cpu().clone() for k, v in head.state_dict().items()}
            if args.unfreeze_layers > 0:
                best_backbone_state = {k: v.detach().cpu().clone() for k, v in backbone.state_dict().items()}

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = args.out_dir / "checkpoint.pt"
    torch.save(best_head_state or head.state_dict(), ckpt_path)
    if best_backbone_state is not None:
        torch.save(best_backbone_state, args.out_dir / "backbone_state.pt")
    elif (args.out_dir / "backbone_state.pt").exists():
        (args.out_dir / "backbone_state.pt").unlink()

    ckpt_hash = hashlib.sha256(ckpt_path.read_bytes()).hexdigest()[:12]

    if test_s:
        (args.out_dir / "test_split.jsonl").write_text(
            "\n".join(json.dumps({"raw_text": s["text"], "plan": s["plan"], "group_id": s["group_id"]}, ensure_ascii=False) for s in test_s) + "\n",
            encoding="utf-8",
        )

    manifest = {
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "checkpoint_id": ckpt_hash,
        "model_version": f"minirbt-head-{ckpt_hash}",
        "status": args.status,
        "can_generate_actions": True,
        "capability_profile": CAPABILITY_PROFILE,
        "motion_map_version": MOTION_MAP_VERSION,
        "label_policy_version": LABEL_POLICY_VERSION,
        "max_length": args.max_length,
        "unfrozen_layers": args.unfreeze_layers,
        "has_finetuned_backbone": best_backbone_state is not None,
        "pooling": "attention_masked_mean_last_hidden_state",
        "supported_actions": ACTION_TYPES[1:],
        "max_slots": MAX_SLOTS,
        "decisions": DECISIONS,
        "train_count": len(train_s),
        "val_count": len(val_s),
        "test_count": len(test_s),
        "best_val_loss": round(best_val, 6),
    }
    (args.out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved checkpoint & manifest to {args.out_dir} (best_val_loss={best_val:.4f})", flush=True)


if __name__ == "__main__":
    main()
