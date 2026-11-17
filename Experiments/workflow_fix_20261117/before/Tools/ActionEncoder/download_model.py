"""Fetch a pinned MiniRBT snapshot and convert tensor weights to safetensors.

No Hugging Face account, remote Python code, or model API key is required.
Download uses stdlib HTTPS; conversion requires the project encoder environment.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

MODEL_ID = "hfl/minirbt-h256"
REVISION = "446e1b4012b10946f479563005700c54c9db3f7c"
WEIGHT_SHA256 = "6728ca573fd5197f28198eb7e6119a76e4d5dc626f953fca8c0dc5ba2798f9fc"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_DIR = PROJECT_ROOT / ".cache" / "action-encoder" / "model"
# Pinned revision metadata. Small files use Git blob hashes; weight LFS SHA-256
# was cross-checked against the official Hugging Face file page.
SOURCE_FILES = {
    "config.json": (598, "b2b054760aa0bf4f3cb8191d9318e37ffd649ae1"),
    "vocab.txt": (109540, "ca4f9781030019ab9b253c6dcb8c7878b6dc87a5"),
    "README.md": (974, "0e2093d2ffc54d2e945b5ada1f81139f32493c4a"),
    "pytorch_model.bin": (41514155, WEIGHT_SHA256),
}


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify_source(path: Path, name: str) -> bool:
    if not path.is_file():
        return False
    size, expected = SOURCE_FILES[name]
    if path.stat().st_size != size:
        return False
    if name == "pytorch_model.bin":
        return sha256(path) == expected
    data = path.read_bytes()
    return hashlib.sha1(b"blob " + str(len(data)).encode("ascii") + b"\0" + data).hexdigest() == expected


def download(model_dir: Path, endpoint: str, timeout: int) -> dict:
    endpoint = endpoint.rstrip("/")
    if endpoint not in {"https://huggingface.co", "https://hf-mirror.com"}:
        raise ValueError("Endpoint must be https://huggingface.co or https://hf-mirror.com")
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "source").mkdir(exist_ok=True)
    previous_path = model_dir / "source-manifest.json"
    previous = json.loads(previous_path.read_text("utf-8")) if previous_path.is_file() else {}
    previous_files = {item["path"]: item for item in previous.get("source_files", [])}
    entries = []
    for name, (size, _) in SOURCE_FILES.items():
        destination = model_dir / ("source/" + name if name.endswith(".bin") else name)
        official_url = f"https://huggingface.co/{MODEL_ID}/resolve/{REVISION}/{name}"
        actual_url = f"{endpoint}/{MODEL_ID}/resolve/{REVISION}/{name}"
        cached = verify_source(destination, name)
        if not cached:
            temporary = destination.with_suffix(destination.suffix + ".part")
            print(f"Downloading {name} ({size} bytes)", flush=True)
            try:
                request = urllib.request.Request(actual_url, headers={"User-Agent": "PetLive2d-ActionEncoder/1.0"})
                with urllib.request.urlopen(request, timeout=timeout) as response, temporary.open("wb") as target:
                    received = 0
                    while block := response.read(1024 * 1024):
                        received += len(block)
                        if received > size:
                            raise ValueError(f"Unexpected oversized download: {name}")
                        target.write(block)
                if not verify_source(temporary, name):
                    raise ValueError(f"Pinned hash or size mismatch: {name}")
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        relative = destination.relative_to(model_dir).as_posix()
        prior = previous_files.get(relative, {})
        entries.append({
            "path": relative,
            "sha256": sha256(destination), "size_bytes": destination.stat().st_size,
            "official_url": official_url,
            "download_url": prior.get("download_url") if cached else actual_url,
            "downloaded_utc": prior.get("downloaded_utc", previous.get("downloaded_utc")) if cached else datetime.now(timezone.utc).isoformat(),
        })
    config = json.loads((model_dir / "config.json").read_text("utf-8"))
    required = {"model_type": "bert", "hidden_size": 256, "num_hidden_layers": 6,
                "num_attention_heads": 8, "intermediate_size": 1024, "vocab_size": 21128}
    if any(config.get(key) != value for key, value in required.items()):
        raise ValueError("Pinned model configuration disagrees with expected MiniRBT-H256 architecture")
    metadata = {
        "schema_version": "1.0", "model_id": MODEL_ID, "revision": REVISION,
        "verified_utc": datetime.now(timezone.utc).isoformat(),
        "license": "Apache-2.0", "license_source": f"https://huggingface.co/{MODEL_ID}/blob/{REVISION}/README.md",
        "license_text_url": "https://www.apache.org/licenses/LICENSE-2.0.txt",
        "upstream_repository": "https://github.com/iflytek/MiniRBT",
        "source_files": entries, "architecture": required,
    }
    (model_dir / "source-manifest.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return metadata


def convert(model_dir: Path, metadata: dict) -> dict:
    import torch
    from safetensors.torch import save_file

    version = re.match(r"(\d+)\.(\d+)", torch.__version__)
    if version is None or tuple(map(int, version.groups())) < (2, 6):
        raise RuntimeError("Conversion requires patched PyTorch >= 2.6; use bootstrap.ps1's pinned environment")
    source = model_dir / "source" / "pytorch_model.bin"
    if not verify_source(source, "pytorch_model.bin"):
        raise ValueError("Official source weight hash is invalid")
    # Explicit restricted tensor loading. Never use weights_only=False or add
    # pickle globals. The original checkpoint has no custom model code.
    state = torch.load(source, map_location="cpu", weights_only=True)
    if not isinstance(state, dict) or not state or any(
        not isinstance(key, str) or not isinstance(value, torch.Tensor)
        for key, value in state.items()
    ):
        raise ValueError("Expected a plain string-to-tensor state dictionary")
    # Older Transformers serialized this deterministic buffer; the installed
    # version regenerates it as a non-persistent buffer. Validate before omission.
    position_ids = state.get("bert.embeddings.position_ids")
    if position_ids is not None and not torch.equal(position_ids, torch.arange(512).unsqueeze(0)):
        raise ValueError("Unexpected BERT position_ids buffer")
    # Retain only the pretrained BERT encoder, and preserve its exact values.
    # MLM vocabulary decoding is unrelated to action encoding. No new task head
    # or randomly initialized pooler is introduced here.
    encoder = {
        key.removeprefix("bert."): value.detach().contiguous().clone()
        for key, value in state.items()
        if key.startswith("bert.") and not key.startswith("bert.pooler.")
        and key != "bert.embeddings.position_ids"
    }
    if not encoder or "embeddings.word_embeddings.weight" not in encoder:
        raise ValueError("Checkpoint is missing the expected pretrained BERT encoder")
    if any(not torch.isfinite(value).all().item() for value in encoder.values()):
        raise ValueError("Checkpoint contains non-finite tensors")
    destination = model_dir / "model.safetensors"
    temporary = destination.with_suffix(".safetensors.part")
    try:
        save_file(encoder, str(temporary), metadata={"format": "pt", "source_model": MODEL_ID, "source_revision": REVISION})
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)
    manifest = dict(metadata)
    manifest.update({
        "converted_utc": datetime.now(timezone.utc).isoformat(),
        "conversion": {"torch_version": torch.__version__, "weights_only": True,
                       "operation": "retain bert.* encoder parameters, strip bert. prefix; omit MLM head, pooler, and validated deterministic position_ids buffer",
                       "tensor_count": len(encoder),
                       "parameter_count": sum(value.numel() for value in encoder.values()),
                       "remote_code_executed": False},
        "action_head_trained": False,
        "files": [{"path": name, "sha256": sha256(model_dir / name), "size_bytes": (model_dir / name).stat().st_size}
                  for name in ["config.json", "vocab.txt", "README.md", "model.safetensors"]],
    })
    (model_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--endpoint", default="https://huggingface.co")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--download-only", action="store_true", help="Download and verify only; no Torch dependency")
    parser.add_argument("--convert-only", action="store_true", help="Convert verified local sources without network")
    args = parser.parse_args()
    if args.download_only and args.convert_only:
        parser.error("Choose only one of --download-only / --convert-only")
    if not 1 <= args.timeout <= 120:
        parser.error("timeout must be 1..120 seconds")
    model_dir = args.model_dir.resolve()
    if args.convert_only:
        metadata = json.loads((model_dir / "source-manifest.json").read_text("utf-8"))
        if metadata.get("model_id") != MODEL_ID or metadata.get("revision") != REVISION:
            raise ValueError("Source manifest model/revision mismatch")
        if any(not verify_source(model_dir / ("source/" + n if n.endswith(".bin") else n), n) for n in SOURCE_FILES):
            raise ValueError("Source files do not match pinned hashes")
    else:
        metadata = download(model_dir, args.endpoint, args.timeout)
    if not args.download_only:
        metadata = convert(model_dir, metadata)
    print(json.dumps({"model_id": MODEL_ID, "revision": REVISION, "model_dir": str(model_dir),
                      "converted": not args.download_only}, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError, ImportError) as exc:
        print(f"Model setup failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
