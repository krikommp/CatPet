"""One-click merge (seed + qualified human reviews), archive previous checkpoint, retrain, evaluate, or rollback."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = Path(__file__).resolve().parent
SEED_PATH = ROOT / "Dataset" / "ActionCards" / "seed_corpus.jsonl"
QUALIFIED_PATH = ROOT / "Dataset" / "ActionCards" / "qualified_semantic.jsonl"
MERGED_PATH = ROOT / "Dataset" / "ActionCards" / "merged_train_corpus.jsonl"
CKPT_DIR = TOOLS_DIR / "checkpoints" / "latest"
HISTORY_DIR = TOOLS_DIR / "checkpoints" / "history"


def archive_current_checkpoint() -> None:
    manifest_path = CKPT_DIR / "manifest.json"
    if not manifest_path.exists():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    ver = manifest.get("model_version") or "unknown"
    dest = HISTORY_DIR / ver
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(CKPT_DIR, dest)
        print(f"Archived previous checkpoint {ver} -> {dest}", flush=True)


def rollback(version: str) -> None:
    src = HISTORY_DIR / version
    if not src.exists():
        raise FileNotFoundError(f"Archived checkpoint not found: {src}")
    if CKPT_DIR.exists():
        shutil.rmtree(CKPT_DIR)
    shutil.copytree(src, CKPT_DIR)
    print(f"Rolled back latest checkpoint to {version}.", flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rollback", type=str, default=None, help="Restore an archived model_version from checkpoints/history/")
    args = parser.parse_args()

    if args.rollback:
        rollback(args.rollback)
        return

    merged_lines = []
    if SEED_PATH.exists():
        merged_lines.extend(
            line for line in SEED_PATH.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    if QUALIFIED_PATH.exists():
        human_lines = [
            line for line in QUALIFIED_PATH.read_text(encoding="utf-8").splitlines() if line.strip()
        ]
        merged_lines.extend(human_lines * 3)
        print(f"Merged {len(human_lines)} human-verified samples (3x) with seed corpus.", flush=True)

    if not merged_lines:
        raise RuntimeError("No training samples found.")

    archive_current_checkpoint()

    MERGED_PATH.parent.mkdir(parents=True, exist_ok=True)
    MERGED_PATH.write_text("\n".join(merged_lines) + "\n", encoding="utf-8")

    subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "train_action_head.py"),
            "--dataset", str(MERGED_PATH),
            "--out-dir", str(CKPT_DIR),
            "--epochs", "12",
            "--batch-size", "64",
            "--lr", "1e-3",
            "--backbone-lr", "8e-5",
            "--unfreeze-layers", "2",
        ],
        check=True,
    )
    subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "eval_action_head.py"),
            "--checkpoint-dir", str(CKPT_DIR),
        ],
        check=True,
    )

    report = json.loads((CKPT_DIR / "eval_report.json").read_text(encoding="utf-8"))
    manifest_path = CKPT_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if report.get("release_gate_passed"):
        manifest["status"] = "ready"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        print("Release gate PASSED! Promoted manifest status to 'ready'.", flush=True)
    else:
        print("Release gate not passed; kept manifest status as 'experimental'.", flush=True)


if __name__ == "__main__":
    main()
