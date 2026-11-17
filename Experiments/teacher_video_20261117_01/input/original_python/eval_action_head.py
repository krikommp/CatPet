"""Independent offline evaluation for the MiniRBT action prediction head."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

import torch
from transformers import BertModel, BertTokenizer

from action_schema import ActionHeadModel, CANONICAL_TYPE_ORDER, DECISIONS, decode_slots_to_plan
from encoder import DEFAULT_MODEL_DIR, verify_model


def canonical_plan_key(plan: dict) -> str:
    norm = {
        "version": plan.get("version", "action-plan.v0.1"),
        "decision": plan.get("decision"),
        "steps": [],
    }
    if norm["decision"] == "execute":
        for step in plan.get("steps") or []:
            actions = sorted(
                step.get("actions") or [],
                key=lambda a: CANONICAL_TYPE_ORDER.get(a.get("type", ""), 99),
            )
            norm["steps"].append({"actions": actions})
    return json.dumps(norm, sort_keys=True, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--test-file", type=Path, default=None)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    args = parser.parse_args()

    manifest = json.loads((args.checkpoint_dir / "manifest.json").read_text(encoding="utf-8"))
    test_file = args.test_file or (args.checkpoint_dir / "test_split.jsonl")
    if not test_file.exists():
        raise FileNotFoundError(f"Test split not found: {test_file}")

    verify_model(args.model_dir)
    tokenizer = BertTokenizer.from_pretrained(str(args.model_dir), local_files_only=True)
    backbone = BertModel.from_pretrained(
        str(args.model_dir), local_files_only=True, use_safetensors=True, add_pooling_layer=False
    )
    backbone_state_path = args.checkpoint_dir / "backbone_state.pt"
    if backbone_state_path.exists():
        backbone.load_state_dict(torch.load(backbone_state_path, map_location="cpu"))
    backbone.eval()

    head = ActionHeadModel(hidden_size=256)
    head.load_state_dict(torch.load(args.checkpoint_dir / "checkpoint.pt", map_location="cpu"))
    head.eval()

    rows = [json.loads(line) for line in test_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    max_length = int(manifest.get("max_length", 128))

    exact_match = 0
    decision_match = 0
    exec_total = 0
    exec_exact = 0
    non_exec_total = 0
    non_exec_match = 0
    negation_total = 0
    negation_false_exec = 0
    unsupported_total = 0
    unsupported_false_exec = 0
    order_parallel_confusion = 0
    latencies_ms = []

    for row in rows:
        text = row["raw_text"]
        gold = row["plan"] if isinstance(row.get("plan"), dict) else json.loads(row["plan_json"])
        t0 = time.perf_counter()
        inputs = tokenizer([text], padding=True, truncation=False, return_tensors="pt")
        with torch.inference_mode():
            hidden = backbone(**inputs).last_hidden_state
            mask = inputs["attention_mask"].unsqueeze(-1).to(hidden.dtype)
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1)
            logits = head(pooled)
            dec_id = int(logits["decision"][0].argmax().item())
            pred = decode_slots_to_plan(dec_id, {k: v[0] for k, v in logits.items() if k != "decision"})
        latencies_ms.append((time.perf_counter() - t0) * 1000.0)

        if pred["decision"] == gold["decision"]:
            decision_match += 1
        matched = canonical_plan_key(pred) == canonical_plan_key(gold)
        if matched:
            exact_match += 1

        if gold["decision"] == "execute":
            exec_total += 1
            if matched:
                exec_exact += 1
            if pred["decision"] == "execute":
                if len(gold.get("steps", [])) != len(pred.get("steps", [])):
                    order_parallel_confusion += 1
        else:
            non_exec_total += 1
            if pred["decision"] == gold["decision"]:
                non_exec_match += 1

        if gold["decision"] == "none":
            negation_total += 1
            if pred["decision"] == "execute":
                negation_false_exec += 1
        if gold["decision"] == "unsupported":
            unsupported_total += 1
            if pred["decision"] == "execute":
                unsupported_false_exec += 1

    total = max(1, len(rows))
    exact_rate = exact_match / total
    avg_latency = sum(latencies_ms) / max(1, len(latencies_ms))
    gate_passed = (exact_rate >= 0.90) and (negation_false_exec == 0) and (unsupported_false_exec == 0)

    report = {
        "total_samples": len(rows),
        "exact_match_count": exact_match,
        "exact_match_rate": round(exact_rate, 4),
        "decision_accuracy": round(decision_match / total, 4),
        "execute_total": exec_total,
        "execute_exact_match_rate": round(exec_exact / max(1, exec_total), 4) if exec_total else None,
        "non_execute_total": non_exec_total,
        "non_execute_accuracy": round(non_exec_match / max(1, non_exec_total), 4) if non_exec_total else None,
        "order_parallel_confusion": order_parallel_confusion,
        "negation_total": negation_total,
        "negation_false_execute": negation_false_exec,
        "unsupported_total": unsupported_total,
        "unsupported_false_execute": unsupported_false_exec,
        "avg_latency_ms": round(avg_latency, 2),
        "release_gate_passed": gate_passed,
    }
    (args.checkpoint_dir / "eval_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
