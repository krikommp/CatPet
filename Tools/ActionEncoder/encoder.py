"""Local, offline MiniRBT text backbone. No trained action head is installed."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import time

from action_config_schema import ModelOutputError, INPUT_POLICY_VERSION, DECODER_POLICY_VERSION, format_input_text

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MODEL_DIR = ROOT / ".cache" / "action-encoder" / "model"
DEFAULT_ACTION_HEAD_DIR = Path(__file__).resolve().parent / "checkpoints" / "latest"
DEFAULT_CONFIG_HEAD_DIR = Path(__file__).resolve().parent / "checkpoints" / "v02_latest"
MODEL_ID = "hfl/minirbt-h256"
MODEL_REVISION = "446e1b4012b10946f479563005700c54c9db3f7c"
ACTION_HEAD = {"status": "not_trained", "can_generate_actions": False}
CONFIG_HEAD = {"status": "not_trained", "can_generate_configs": False}


class ActionHeadNotTrainedError(RuntimeError):
    pass


class ConfigHeadNotTrainedError(RuntimeError):
    pass


class InputTooLongError(ValueError):
    pass


class VersionMismatchError(ValueError):
    pass


def validate_request(data: object) -> tuple[list[str], int]:
    if not isinstance(data, dict) or set(data) - {"texts", "max_length"}:
        raise ValueError("Expected an object with only texts and optional max_length.")
    texts = data.get("texts")
    if not isinstance(texts, list) or not 1 <= len(texts) <= 8:
        raise ValueError("texts must contain 1 to 8 strings.")
    if any(not isinstance(s, str) or not s.strip() or len(s) > 2048 for s in texts):
        raise ValueError("Each text must be non-empty and at most 2048 characters.")
    length = data.get("max_length", 128)
    if type(length) is not int or not 8 <= length <= 512:
        raise ValueError("max_length must be an integer between 8 and 512.")
    return texts, length


def verify_model(model_dir: Path) -> dict:
    manifest = json.loads((model_dir / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("model_id") != MODEL_ID or manifest.get("revision") != MODEL_REVISION:
        raise ValueError("Expected a pinned hfl/minirbt-h256 manifest.")
    required = {"config.json", "vocab.txt", "model.safetensors"}
    seen = set()
    for entry in manifest["files"]:
        path = (model_dir / entry["path"]).resolve()
        if not path.is_relative_to(model_dir.resolve()):
            raise ValueError("Manifest path escapes the model directory.")
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != entry["sha256"] or path.stat().st_size != entry["size_bytes"]:
            raise ValueError(f"Model integrity check failed: {entry['path']}")
        seen.add(entry["path"])
    if not required <= seen:
        raise ValueError("Manifest must cover config, vocabulary, and safetensors weights.")
    return manifest


class LocalEncoder:
    def __init__(
        self,
        model_dir: Path = DEFAULT_MODEL_DIR,
        threads: int = 2,
        action_head_dir: Path | None = None,
        config_head_dir: Path | None = None,
    ):
        # Inference has no download fallback, remote code, cloud API, or credential use.
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        self.model_dir = model_dir.resolve()
        self.manifest = verify_model(self.model_dir)
        import torch
        from transformers import BertModel, BertTokenizer

        self.torch = torch
        torch.set_num_threads(threads)
        torch.manual_seed(1337)
        self.tokenizer = BertTokenizer.from_pretrained(str(model_dir), local_files_only=True)
        self.model, loading = BertModel.from_pretrained(
            str(model_dir), local_files_only=True, use_safetensors=True,
            add_pooling_layer=False, attn_implementation="eager",
            output_loading_info=True,
        )
        if any(loading.get(key) for key in ("missing_keys", "unexpected_keys", "mismatched_keys", "error_msgs")):
            raise ValueError("Checkpoint did not load exactly; refusing partial or randomly initialized weights.")
        self.model.to("cpu").eval()
        if self.model.config.hidden_size != 256 or self.model.config.num_hidden_layers != 6:
            raise ValueError("Unexpected model architecture; expected MiniRBT H256 with 6 layers.")
        self.parameter_count = sum(p.numel() for p in self.model.parameters())

        self.action_head = None
        self.action_head_manifest = None
        self.plan_backbone = None
        self.action_head_info = dict(ACTION_HEAD)
        if action_head_dir is not None and (action_head_dir / "checkpoint.pt").exists() and (action_head_dir / "manifest.json").exists():
            self._load_action_head(action_head_dir.resolve())

        self.config_head = None
        self.config_head_manifest = None
        self.config_backbone = None
        self.config_head_info = dict(CONFIG_HEAD)
        if config_head_dir is not None and (config_head_dir / "config_head.pt").exists() and (config_head_dir / "manifest.json").exists():
            self._load_config_head(config_head_dir.resolve())

    def _load_action_head(self, head_dir: Path) -> None:
        from transformers import BertModel
        from action_schema import ActionHeadModel
        head_manifest = json.loads((head_dir / "manifest.json").read_text(encoding="utf-8"))
        if head_manifest.get("model_id") != MODEL_ID or head_manifest.get("model_revision") != self.manifest["revision"]:
            raise ValueError("Action head manifest does not match MiniRBT backbone revision.")
        head = ActionHeadModel(hidden_size=256)
        head.load_state_dict(self.torch.load(head_dir / "checkpoint.pt", map_location="cpu"))
        head.eval()

        backbone_state_path = head_dir / "backbone_state.pt"
        if backbone_state_path.exists():
            plan_bb = BertModel.from_pretrained(
                str(self.model_dir), local_files_only=True, use_safetensors=True, add_pooling_layer=False, attn_implementation="eager"
            )
            plan_bb.load_state_dict(self.torch.load(backbone_state_path, map_location="cpu"))
            plan_bb.to("cpu").eval()
            self.plan_backbone = plan_bb
        else:
            self.plan_backbone = self.model

        self.action_head = head
        self.action_head_manifest = head_manifest
        self.action_head_info = {
            "status": head_manifest.get("status", "experimental"),
            "can_generate_actions": True,
            "model_version": head_manifest.get("model_version", "unknown"),
            "checkpoint_id": head_manifest.get("checkpoint_id", "unknown"),
            "capability_profile": head_manifest.get("capability_profile"),
            "motion_map_version": head_manifest.get("motion_map_version"),
            "label_policy_version": head_manifest.get("label_policy_version"),
            "max_length": head_manifest.get("max_length", 128),
            "supported_actions": head_manifest.get("supported_actions", []),
        }

    def _load_config_head(self, head_dir: Path) -> None:
        from transformers import BertModel
        from config_prediction import create_config_head, validate_head_manifest, architecture_policies
        head_manifest = json.loads((head_dir / "manifest.json").read_text(encoding="utf-8"))
        if head_manifest.get("model_id") != MODEL_ID or head_manifest.get("model_revision") != self.manifest["revision"]:
            raise ValueError("Config head manifest does not match MiniRBT backbone revision.")
        architecture = validate_head_manifest(head_manifest)
        head = create_config_head(architecture, hidden_size=256)
        head.load_state_dict(self.torch.load(head_dir / "config_head.pt", map_location="cpu"), strict=True)
        head.eval()

        backbone_state_path = head_dir / "backbone_state.pt"
        if backbone_state_path.exists():
            cfg_bb = BertModel.from_pretrained(
                str(self.model_dir), local_files_only=True, use_safetensors=True, add_pooling_layer=False, attn_implementation="eager"
            )
            cfg_bb.load_state_dict(self.torch.load(backbone_state_path, map_location="cpu"))
            cfg_bb.to("cpu").eval()
            self.config_backbone = cfg_bb
        else:
            self.config_backbone = self.model

        self.config_head = head
        self.config_head_manifest = head_manifest
        self.config_head_info = {
            "status": head_manifest.get("status", "experimental"),
            "can_generate_configs": True,
            "model_version": head_manifest.get("model_version", "unknown"),
            "checkpoint_id": head_manifest.get("checkpoint_id", "unknown"),
            "parameter_schema_version": head_manifest.get("parameter_schema_version"),
            "capability_profile": head_manifest.get("capability_profile"),
            "resource_catalog_version": head_manifest.get("resource_catalog_version"),
            "label_policy_version": head_manifest.get("label_policy_version"),
            "max_length": head_manifest.get("max_length", 128),
            "supported_resources": head_manifest.get("supported_resources", []),
            "input_policy": head_manifest.get("input_policy", "legacy-unprefixed"),
            **architecture_policies(architecture),
        }

    def health(self) -> dict:
        return {
            "status": "ok", "schema_version": "1.0", "model_id": MODEL_ID,
            "model_revision": self.manifest["revision"], "hidden_size": 256,
            "device": "cpu", "offline": True, "parameter_count": self.parameter_count,
            "action_head": dict(self.action_head_info),
            "action_config_head": dict(self.config_head_info),
        }

    def configure(self, data: object) -> dict:
        if self.config_head is None or self.config_head_manifest is None:
            raise ConfigHeadNotTrainedError("No trained action-config.v0.2 head is installed.")
        if not isinstance(data, dict):
            raise ValueError("Expected JSON object.")
        text = data.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string.")
        request_id = data.get("request_id") or ""
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id is required.")

        expected_profile = self.config_head_manifest.get("capability_profile")
        expected_catalog = self.config_head_manifest.get("resource_catalog_version")
        expected_schema = self.config_head_manifest.get("parameter_schema_version")
        expected_policy = self.config_head_manifest.get("label_policy_version")
        if data.get("capability_profile") != expected_profile:
            raise VersionMismatchError(f"Unsupported capability_profile; expected {expected_profile}.")
        if data.get("resource_catalog_version") != expected_catalog:
            raise VersionMismatchError(f"Unsupported resource_catalog_version; expected {expected_catalog}.")
        if data.get("parameter_schema_version") != expected_schema:
            raise VersionMismatchError(f"Unsupported parameter_schema_version; expected {expected_schema}.")
        if data.get("label_policy_version") != expected_policy:
            raise VersionMismatchError(f"Unsupported label_policy_version; expected {expected_policy}.")

        input_role = data.get("input_role", "instruction")
        if input_role not in ("instruction", "dialogue"):
            raise ValueError("input_role must be instruction or dialogue.")
        input_policy = self.config_head_manifest.get("input_policy")
        if input_policy not in (None, INPUT_POLICY_VERSION):
            raise VersionMismatchError(f"Unsupported model input_policy: {input_policy}.")
        model_text = format_input_text(text, input_role) if input_policy == INPUT_POLICY_VERSION else text.strip()
        max_length = int(self.config_head_manifest.get("max_length", 128))
        full_tokens = self.tokenizer.encode(model_text, add_special_tokens=True, truncation=False)
        if len(full_tokens) > max_length:
            raise InputTooLongError(f"Input exceeds max_length={max_length} ({len(full_tokens)} tokens); refusing truncated execution.")

        from config_prediction import predict_config, validate_head_manifest, architecture_policies
        architecture = validate_head_manifest(self.config_head_manifest)
        start = time.perf_counter()
        inputs = self.tokenizer([model_text], padding=True, truncation=False, return_tensors="pt")
        bb = self.config_backbone or self.model
        with self.torch.inference_mode():
            hidden = bb(**inputs).last_hidden_state
            mask = inputs["attention_mask"].unsqueeze(-1).to(hidden.dtype)
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1)
            disc = self.config_head.forward_discrete(pooled)
            pred_rids = disc["resource_id"].argmax(dim=-1)
            params = self.config_head.forward_params(disc["h"], pred_rids)
            config_obj, prediction_audit = predict_config(disc, params, text.strip(), input_role, architecture)

        return {
            "request_id": request_id,
            "source": "local_minirbt_v02",
            "input_role": input_role,
            "input_policy": input_policy or "legacy-unprefixed",
            **architecture_policies(architecture),
            **prediction_audit,
            "model_version": self.config_head_manifest.get("model_version", "unknown"),
            "capability_profile": expected_profile,
            "resource_catalog_version": expected_catalog,
            "parameter_schema_version": expected_schema,
            "label_policy_version": expected_policy,
            "inference_ms": round((time.perf_counter() - start) * 1000, 3),
            "config": config_obj,
        }

    def plan(self, data: object) -> dict:
        if self.action_head is None or self.action_head_manifest is None:
            raise ActionHeadNotTrainedError("Only text features are available; no trained action head is installed.")
        if not isinstance(data, dict):
            raise ValueError("Expected JSON object.")
        text = data.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError("text must be a non-empty string.")
        request_id = data.get("request_id") or ""
        if not isinstance(request_id, str) or not request_id.strip():
            raise ValueError("request_id is required.")

        expected_profile = self.action_head_manifest.get("capability_profile")
        expected_policy = self.action_head_manifest.get("label_policy_version")
        if data.get("capability_profile") != expected_profile:
            raise VersionMismatchError(f"Unsupported capability_profile; expected {expected_profile}.")
        if data.get("label_policy_version") != expected_policy:
            raise VersionMismatchError(f"Unsupported label_policy_version; expected {expected_policy}.")

        max_length = int(self.action_head_manifest.get("max_length", 128))
        full_tokens = self.tokenizer.encode(text.strip(), add_special_tokens=True, truncation=False)
        if len(full_tokens) > max_length:
            raise InputTooLongError(f"Input exceeds max_length={max_length} ({len(full_tokens)} tokens); refusing truncated execution.")

        from action_schema import decode_slots_to_plan
        start = time.perf_counter()
        inputs = self.tokenizer([text.strip()], padding=True, truncation=False, return_tensors="pt")
        bb = self.plan_backbone or self.model
        with self.torch.inference_mode():
            hidden = bb(**inputs).last_hidden_state
            mask = inputs["attention_mask"].unsqueeze(-1).to(hidden.dtype)
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1)
            logits = self.action_head(pooled)
            dec_id = int(logits["decision"][0].argmax().item())
            plan_obj = decode_slots_to_plan(dec_id, {k: v[0] for k, v in logits.items() if k != "decision"})

        return {
            "request_id": request_id,
            "source": "local_minirbt",
            "model_version": self.action_head_manifest.get("model_version", "unknown"),
            "capability_profile": expected_profile,
            "motion_map_version": data.get("motion_map_version") or self.action_head_manifest.get("motion_map_version"),
            "label_policy_version": expected_policy,
            "inference_ms": round((time.perf_counter() - start) * 1000, 3),
            "plan": plan_obj,
        }

    def encode(self, data: object) -> dict:
        texts, max_length = validate_request(data)
        start = time.perf_counter()
        full_counts = [len(self.tokenizer.encode(s, add_special_tokens=True, truncation=False)) for s in texts]
        inputs = self.tokenizer(texts, padding=True, truncation=True,
                                max_length=max_length, return_tensors="pt")
        with self.torch.inference_mode():
            hidden = self.model(**inputs).last_hidden_state
            mask = inputs["attention_mask"].unsqueeze(-1).to(hidden.dtype)
            # Includes CLS/SEP; ignores padding. This is a feature vector, not a calibrated similarity score.
            pooled = (hidden * mask).sum(1) / mask.sum(1).clamp(min=1)
            if not self.torch.isfinite(pooled).all():
                raise RuntimeError("Encoder produced non-finite features.")
        result = self.health()
        result.update({
            "embedding_kind": "attention_masked_mean_last_hidden_state",
            "embeddings": [{"values": row} for row in pooled.tolist()],
            "token_counts": inputs["attention_mask"].sum(1).tolist(),
            "original_token_counts": full_counts,
            "truncated": [n > max_length for n in full_counts],
            "inference_ms": round((time.perf_counter() - start) * 1000, 3),
        })
        return result
