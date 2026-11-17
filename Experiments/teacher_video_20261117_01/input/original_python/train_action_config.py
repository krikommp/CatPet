"""Train the resource-conditioned per-cycle MiniRBT model for action-config.v0.2."""
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

from action_config_schema import (
    CAPABILITY_PROFILE,
    CONFIG_VERSION,
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
from encoder import DEFAULT_MODEL_DIR, MODEL_ID, MODEL_REVISION, verify_model

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET = ROOT / "Dataset" / "ActionCards" / "qualified_action_config.jsonl"
DEFAULT_OUT_DIR = Path(__file__).resolve().parent / "checkpoints" / "v02_latest"


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
            raise ValueError(f"Line {line_no}: exceeds max_length={max_length} ({len(token_ids)} tokens).")
        cfg = row.get("config") if isinstance(row.get("config"), dict) else json.loads(row["config_json"])
        if cfg.get("version") != CONFIG_VERSION:
            raise ValueError(f"Line {line_no}: expected {CONFIG_VERSION}.")
        targets = canonicalize_config(cfg)
        samples.append({
            "group_id": row.get("group_id") or text,
            "text": text,
            "config": cfg,
            "targets": targets,
        })
    return samples


def split_by_group(samples: list[dict], seed: int = 1337) -> tuple[list[dict], list[dict], list[dict]]:
    buckets: dict[int, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for s in samples:
        buckets[s["targets"]["decision"]][s["group_id"]].append(s)
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
        for layer in backbone.encoder.layer[-args.unfreeze_layers :]:
            for p in layer.parameters():
                p.requires_grad = True

    samples = load_samples(args.dataset, tokenizer, args.max_length)
    train_s, val_s, test_s = split_by_group(samples)
    print(f"Loaded {len(samples)} v0.2 samples -> train={len(train_s)}, val={len(val_s)}, test={len(test_s)}", flush=True)

    model = ActionConfigV02Model(hidden_size=256)
    train_t = make_batch_tensors(train_s)
    val_t = make_batch_tensors(val_s) if val_s else None

    bb_params = [p for p in backbone.parameters() if p.requires_grad]
    opt_groups = [{"params": model.parameters(), "lr": args.lr}]
    if bb_params:
        opt_groups.append({"params": bb_params, "lr": args.backbone_lr})
    opt = torch.optim.AdamW(opt_groups, weight_decay=1e-2)

    best_val = float("inf")
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
            inputs = tokenizer([train_s[i]["text"] for i in idx], padding=True, truncation=False, return_tensors="pt")
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
                v_in = tokenizer([s["text"] for s in val_s], padding=True, truncation=False, return_tensors="pt")
                v_feats = pool_backbone(backbone, v_in)
                val_loss = float(compute_loss(model, v_feats, val_t).item())

        if val_loss <= best_val:
            best_val = val_loss
            best_model_state = {k: v.detach().cpu().clone() for k, v in model.state_dict().items()}
            if args.unfreeze_layers > 0:
                best_bb_state = {k: v.detach().cpu().clone() for k, v in backbone.state_dict().items()}

    args.out_dir.mkdir(parents=True, exist_ok=True)
    ckpt_path = args.out_dir / "config_head.pt"
    torch.save(best_model_state or model.state_dict(), ckpt_path)
    if best_bb_state is not None:
        torch.save(best_bb_state, args.out_dir / "backbone_state.pt")
    elif (args.out_dir / "backbone_state.pt").exists():
        (args.out_dir / "backbone_state.pt").unlink()

    ckpt_hash = hashlib.sha256(ckpt_path.read_bytes()).hexdigest()[:12]
    if test_s:
        (args.out_dir / "test_split.jsonl").write_text(
            "\n".join(json.dumps({"raw_text": s["text"], "config": s["config"], "group_id": s["group_id"]}, ensure_ascii=False) for s in test_s) + "\n",
            encoding="utf-8",
        )

    manifest = {
        "model_id": MODEL_ID,
        "model_revision": MODEL_REVISION,
        "checkpoint_id": ckpt_hash,
        "model_version": f"minirbt-config-v02-{ckpt_hash}",
        "status": args.status,
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
        "best_val_loss": round(best_val, 6),
    }
    (args.out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved v0.2 checkpoint & manifest to {args.out_dir} (best_val_loss={best_val:.4f})", flush=True)


if __name__ == "__main__":
    main()
