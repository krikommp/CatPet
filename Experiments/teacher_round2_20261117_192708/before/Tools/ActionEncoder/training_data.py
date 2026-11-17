"""Fixed-split, provenance-checked v0.2 training input. No human-review prerequisite."""
from __future__ import annotations

from collections import Counter
import hashlib
import json
from pathlib import Path
import unicodedata

ROOT = Path(__file__).resolve().parents[2]
SPLITS = ("train", "val", "test")


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalized_text(text: str) -> str:
    return "".join(char for char in unicodedata.normalize("NFKC", text).casefold()
                   if not char.isspace() and not unicodedata.category(char).startswith("P"))


def split_by_group(samples: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Honor the global semantic-family assignment; never resample by decision."""
    groups = {split: [] for split in SPLITS}
    memberships = {}
    for row in samples:
        split = row.get("split")
        if split not in groups:
            raise ValueError("Every row must explicitly declare split=train|val|test.")
        if not row.get("group_id") or not row.get("semantic_family_id"):
            raise ValueError("Every row needs group_id and global semantic_family_id.")
        text = row.get("raw_text", row.get("text"))
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Every row needs non-empty raw_text.")
        identities = (("group_id", row["group_id"]), ("semantic_family_id", row["semantic_family_id"]),
                      ("normalized_text", normalized_text(text)))
        for key in identities:
            if key in memberships and memberships[key] != split:
                raise ValueError(f"Cross-split leakage: {key} appears in {memberships[key]} and {split}.")
            memberships[key] = split
        provenance = row.get("provenance") or {}
        if split == "train":
            if row.get("training_eligible") is not True:
                raise ValueError("Training rows require explicit training_eligible=true; AI approval is sufficient.")
            if any(provenance.get(field) in {"val", "test"} for field in ("original_split", "source_split")):
                raise ValueError("A held-out source cannot return to training.")
            if row.get("source_type") in {"teacher_fixed_eval", "teacher_objective_challenge"}:
                raise ValueError("Fixed evaluation samples cannot enter training.")
        groups[split].append(row)
    if not all(groups.values()):
        raise ValueError("Fixed train, validation and test splits must all be non-empty.")
    return tuple(groups[split] for split in SPLITS)


def ensure_new_output_dir(path: Path) -> Path:
    """Validate without writing; mkdir(exist_ok=False) claims it immediately before training."""
    target = path.resolve()
    protected = [ROOT / "Tools/ActionEncoder/checkpoints/latest",
                 ROOT / "Tools/ActionEncoder/checkpoints/v02_latest"]
    if any(target == item.resolve() or target.is_relative_to(item.resolve()) for item in protected):
        raise ValueError("Training must use a new experiment directory, never latest/v02_latest.")
    if target.exists():
        raise FileExistsError(f"Refusing to overwrite an existing output directory: {target}")
    return target


def load_snapshot(manifest_path: Path) -> tuple[list[dict], dict]:
    from review_evidence import validate_frozen_snapshot
    rows, manifest = validate_frozen_snapshot(manifest_path.resolve())
    split_by_group(rows)
    return rows, manifest


def build_samples(rows: list[dict], tokenizer, max_length: int) -> list[dict]:
    from action_config_schema import canonicalize_config, format_input_text
    from input_constraints import validate_instruction_constraints
    samples = []
    for index, row in enumerate(rows, 1):
        try:
            text = row["raw_text"].strip()
            role = row["input_role"]
            model_text = format_input_text(text, role)
            token_ids = tokenizer.encode(model_text, add_special_tokens=True, truncation=False)
            if len(token_ids) > max_length:
                raise ValueError(f"Input has {len(token_ids)} tokens, exceeds {max_length}; no truncation is allowed.")
            config = row["config"]
            targets = canonicalize_config(config)
            if role == "instruction":
                checked = validate_instruction_constraints(text, config)
                if checked["violations"] or checked["unresolved"]:
                    raise ValueError(f"Explicit instruction constraint failed/unresolved: {checked}")
            samples.append({**row, "text": text, "model_text": model_text, "targets": targets})
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError(f"Frozen dataset row {index}: {exc}") from exc
    split_by_group(samples)
    return samples


def dataset_summary(rows: list[dict]) -> dict:
    train, val, test = split_by_group(rows)
    decisions = ("execute", "none", "unsupported", "ambiguous")
    return {
        "split_counts": dict(zip(SPLITS, map(len, (train, val, test)))),
        "source_counts_by_split": {name: dict(Counter(row["source_type"] for row in split_rows))
                                   for name, split_rows in zip(SPLITS, (train, val, test))},
        "decision_counts_by_split": {name: dict(Counter(row["config"]["decision"] for row in split_rows))
                                     for name, split_rows in zip(SPLITS, (train, val, test))},
        "missing_train_decisions": [decision for decision in decisions
                                    if not any(row["config"]["decision"] == decision for row in train)],
        "release_approved": False,
    }


def check_snapshot_unchanged(manifest_path: Path, manifest_hash: str) -> tuple[list[dict], dict]:
    if file_sha256(manifest_path) != manifest_hash:
        raise ValueError("Frozen manifest changed during this operation.")
    # Re-read and re-hash all referenced artifacts; no stale validation cache.
    return load_snapshot(manifest_path)
