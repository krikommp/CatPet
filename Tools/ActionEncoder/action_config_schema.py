"""Schema, canonical target encoder/decoder, and resource-conditioned per-cycle model for action-config.v0.2."""
from __future__ import annotations

import math
from typing import Any

import torch
import torch.nn as nn

CONFIG_VERSION = "action-config.v0.2"
RESOURCE_CATALOG_VERSION = "yukikaze-resources.v0.2"
CAPABILITY_PROFILE = "yukikaze.v1"
LABEL_POLICY_VERSION = "action-config-labels.v0.2"
INPUT_POLICY_VERSION = "action-input-role.v1"
DECODER_POLICY_VERSION = "strict-predicted-resource.v1"


class ModelOutputError(RuntimeError):
    """A technically invalid prediction, never a semantic none/unsupported label."""


def format_input_text(text: str, input_role: str) -> str:
    prefixes = {"instruction": "动作指令：", "dialogue": "角色台词表演："}
    if input_role not in prefixes:
        raise ValueError("input_role must be instruction or dialogue.")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("raw_text must be non-empty.")
    return prefixes[input_role] + text.strip()

DECISIONS = ["execute", "none", "unsupported", "ambiguous"]
DECISION_TO_ID = {v: i for i, v in enumerate(DECISIONS)}

RESOURCE_SPECS: dict[str, dict[str, Any]] = {
    "blink.full": {"min_dur": 300, "max_dur": 1800, "supports_amp": False, "min_amp": 1.0, "max_amp": 1.0, "supports_hold": True, "min_hold": 0.0, "max_hold": 0.50},
    "nod.basic": {"min_dur": 420, "max_dur": 2200, "supports_amp": True, "min_amp": 0.35, "max_amp": 1.35, "supports_hold": True, "min_hold": 0.0, "max_hold": 0.45},
    "shake_head.basic": {"min_dur": 480, "max_dur": 2400, "supports_amp": True, "min_amp": 0.35, "max_amp": 1.35, "supports_hold": True, "min_hold": 0.0, "max_hold": 0.30},
    "tilt_head.basic": {"min_dur": 480, "max_dur": 2400, "supports_amp": True, "min_amp": 0.35, "max_amp": 1.35, "supports_hold": True, "min_hold": 0.0, "max_hold": 0.50},
    "look_around.basic": {"min_dur": 600, "max_dur": 2600, "supports_amp": True, "min_amp": 0.40, "max_amp": 1.25, "supports_hold": True, "min_hold": 0.0, "max_hold": 0.30},
    "smile.basic": {"min_dur": 550, "max_dur": 2600, "supports_amp": True, "min_amp": 0.40, "max_amp": 1.15, "supports_hold": True, "min_hold": 0.0, "max_hold": 0.55},
    "angry.basic": {"min_dur": 550, "max_dur": 2600, "supports_amp": True, "min_amp": 0.40, "max_amp": 1.15, "supports_hold": True, "min_hold": 0.0, "max_hold": 0.55},
    "shy.basic": {"min_dur": 650, "max_dur": 2600, "supports_amp": True, "min_amp": 0.40, "max_amp": 1.25, "supports_hold": True, "min_hold": 0.0, "max_hold": 0.55},
    "surprise.basic": {"min_dur": 500, "max_dur": 2400, "supports_amp": True, "min_amp": 0.40, "max_amp": 1.20, "supports_hold": True, "min_hold": 0.0, "max_hold": 0.50},
    "wave.basic": {"min_dur": 550, "max_dur": 2500, "supports_amp": True, "min_amp": 0.40, "max_amp": 1.20, "supports_hold": True, "min_hold": 0.0, "max_hold": 0.50},
    "cheer.basic": {"min_dur": 550, "max_dur": 2500, "supports_amp": True, "min_amp": 0.40, "max_amp": 1.20, "supports_hold": True, "min_hold": 0.0, "max_hold": 0.50},
    "bow.basic": {"min_dur": 600, "max_dur": 2600, "supports_amp": True, "min_amp": 0.40, "max_amp": 1.25, "supports_hold": True, "min_hold": 0.0, "max_hold": 0.50},
}

RESOURCE_CHANNELS: dict[str, set[str]] = {
    "blink.full": {"ParamEyeLOpen", "ParamEyeROpen"},
    "nod.basic": {"ParamAngleY", "ParamBodyAngleY"},
    "shake_head.basic": {"ParamAngleX"},
    "tilt_head.basic": {"ParamAngleZ", "ParamBodyAngleZ"},
    "look_around.basic": {"ParamEyeBallX", "ParamAngleX"},
    "smile.basic": {"PARAM_Smile_eye", "ParamEyeLOpen", "ParamEyeROpen", "ParamMouthForm", "ParamMouthOpenY", "ParamBrowLY", "ParamBrowRY"},
    "angry.basic": {"PARAM_Angry_eye", "ParamBrowLY", "ParamBrowRY", "ParamBrowLX", "ParamBrowRX", "PARAM_mouth", "PARAM_FXmouth1"},
    "shy.basic": {"ParamAngleZ", "ParamEyeBallX", "ParamEyeBallY", "ParamBrowLY", "ParamBrowRY", "PARAM_mouth", "PARAM_FXmouth2"},
    "surprise.basic": {"PARAM_FXeye", "ParamBrowLY", "ParamBrowRY", "PARAM_mouth", "PARAM_FXmouth3"},
    "wave.basic": {"PARAM_Arm_RT_Angle", "PARAM_Arm_R_hand"},
    "cheer.basic": {"PARAM_Arm_LT_Angle", "PARAM_Arm_RT_Angle", "PARAM_shangxia"},
    "bow.basic": {"ParamBodyAngleY", "ParamAngleY"},
}

RESOURCE_IDS = ["PAD"] + list(RESOURCE_SPECS.keys())
RESOURCE_TO_ID = {r: i for i, r in enumerate(RESOURCE_IDS)}

MAX_ACTIONS = 2
MAX_CYCLES = 3


def norm_log_duration(dur_ms: int, spec: dict[str, Any]) -> float:
    lo = math.log(spec["min_dur"])
    hi = math.log(spec["max_dur"])
    v = (math.log(max(spec["min_dur"], min(spec["max_dur"], dur_ms))) - lo) / max(1e-6, hi - lo)
    return max(0.0, min(1.0, v))


def denorm_log_duration(norm_v: float, spec: dict[str, Any]) -> int:
    lo = math.log(spec["min_dur"])
    hi = math.log(spec["max_dur"])
    ms = int(round(math.exp(lo + max(0.0, min(1.0, norm_v)) * (hi - lo))))
    return max(spec["min_dur"], min(spec["max_dur"], ms))


def norm_linear(val: float, lo: float, hi: float) -> float:
    if hi <= lo:
        return 0.5
    return max(0.0, min(1.0, (val - lo) / (hi - lo)))


def denorm_linear(norm_v: float, lo: float, hi: float) -> float:
    return round(lo + max(0.0, min(1.0, norm_v)) * (hi - lo), 3)


def canonicalize_config(config: dict[str, Any]) -> dict[str, Any]:
    """Encodes an action-config.v0.2 dict into fixed discrete + normalized continuous targets."""
    validate_training_config(config)
    decision = config.get("decision")
    if decision not in DECISION_TO_ID:
        raise ValueError(f"Unsupported decision: {decision}")

    res_ids = [0] * MAX_ACTIONS
    stages = [2] * MAX_ACTIONS  # 2 = PAD
    cyc_counts = [0] * MAX_ACTIONS
    dur_norm = [[0.5] * MAX_CYCLES for _ in range(MAX_ACTIONS)]
    amp_norm = [[0.5] * MAX_CYCLES for _ in range(MAX_ACTIONS)]
    hold_norm = [[0.5] * MAX_CYCLES for _ in range(MAX_ACTIONS)]
    amp_mask = [[0.0] * MAX_CYCLES for _ in range(MAX_ACTIONS)]
    cyc_mask = [[0.0] * MAX_CYCLES for _ in range(MAX_ACTIONS)]

    if decision == "execute":
        steps = config.get("steps") or []
        if not 1 <= len(steps) <= 2:
            raise ValueError("v0.2 execute requires 1 to 2 steps.")
        flat_actions = []
        for s_idx, step in enumerate(steps):
            acts = sorted(
                step.get("actions") or [],
                key=lambda a: RESOURCE_TO_ID.get(a.get("resource_id", ""), 999),
            )
            for a in acts:
                flat_actions.append((s_idx, a))
        if not 1 <= len(flat_actions) <= MAX_ACTIONS:
            raise ValueError("v0.2 supports 1 to 2 actions in total.")

        for a_idx, (s_idx, act) in enumerate(flat_actions):
            rid = act.get("resource_id")
            if rid not in RESOURCE_SPECS:
                raise ValueError(f"Unknown resource_id: {rid}")
            spec = RESOURCE_SPECS[rid]
            cycles = act.get("cycles") or []
            if not 1 <= len(cycles) <= MAX_CYCLES:
                raise ValueError(f"cycles count must be 1..{MAX_CYCLES}")
            res_ids[a_idx] = RESOURCE_TO_ID[rid]
            stages[a_idx] = s_idx
            cyc_counts[a_idx] = len(cycles)

            for c_idx, cyc in enumerate(cycles):
                dur = int(cyc["duration_ms"])
                ctrls = cyc.get("controls") or {}
                dur_norm[a_idx][c_idx] = norm_log_duration(dur, spec)
                cyc_mask[a_idx][c_idx] = 1.0
                if spec["supports_hold"]:
                    hold_norm[a_idx][c_idx] = norm_linear(float(ctrls["hold_ratio"]), spec["min_hold"], spec["max_hold"])
                if spec["supports_amp"]:
                    amp_norm[a_idx][c_idx] = norm_linear(float(ctrls["amplitude_scale"]), spec["min_amp"], spec["max_amp"])
                    amp_mask[a_idx][c_idx] = 1.0

    return {
        "decision": DECISION_TO_ID[decision],
        "resource_id": res_ids,
        "stage": stages,
        "cycle_count": cyc_counts,
        "dur_norm": dur_norm,
        "amp_norm": amp_norm,
        "hold_norm": hold_norm,
        "amp_mask": amp_mask,
        "cyc_mask": cyc_mask,
    }


class ActionConfigV02Model(nn.Module):
    """Resource-conditioned per-cycle continuous parameter predictor on top of MiniRBT pooled features."""

    def __init__(self, hidden_size: int = 256, mlp_dim: int = 256, cond_dim: int = 64, dropout: float = 0.1):
        super().__init__()
        self.trunk = nn.Sequential(
            nn.Linear(hidden_size, mlp_dim),
            nn.GELU(),
            nn.Dropout(dropout),
            nn.Linear(mlp_dim, mlp_dim),
            nn.GELU(),
            nn.Dropout(dropout),
        )
        self.decision_head = nn.Linear(mlp_dim, len(DECISIONS))
        self.resource_head = nn.Linear(mlp_dim, MAX_ACTIONS * len(RESOURCE_IDS))
        self.stage_head = nn.Linear(mlp_dim, MAX_ACTIONS * 3)
        self.cycle_count_head = nn.Linear(mlp_dim, MAX_ACTIONS * (MAX_CYCLES + 1))

        self.resource_emb = nn.Embedding(len(RESOURCE_IDS), cond_dim)
        self.action_slot_emb = nn.Embedding(MAX_ACTIONS, cond_dim)
        self.cycle_idx_emb = nn.Embedding(MAX_CYCLES, cond_dim)

        self.param_mlp = nn.Sequential(
            nn.Linear(mlp_dim + cond_dim * 3, 192),
            nn.GELU(),
            nn.Linear(192, 3),  # [norm_dur, norm_amp, norm_hold]
        )

    def forward_discrete(self, pooled: torch.Tensor) -> dict[str, torch.Tensor]:
        h = self.trunk(pooled)
        bsz = h.size(0)
        return {
            "h": h,
            "decision": self.decision_head(h),
            "resource_id": self.resource_head(h).view(bsz, MAX_ACTIONS, len(RESOURCE_IDS)),
            "stage": self.stage_head(h).view(bsz, MAX_ACTIONS, 3),
            "cycle_count": self.cycle_count_head(h).view(bsz, MAX_ACTIONS, MAX_CYCLES + 1),
        }

    def forward_params(self, h: torch.Tensor, resource_ids: torch.Tensor) -> torch.Tensor:
        """Predicts bounded (0..1) [dur, amp, hold] for shape [B, MAX_ACTIONS, MAX_CYCLES, 3]."""
        bsz = h.size(0)
        device = h.device
        out = []
        for a_idx in range(MAX_ACTIONS):
            r_emb = self.resource_emb(resource_ids[:, a_idx])
            a_emb = self.action_slot_emb(torch.full((bsz,), a_idx, dtype=torch.long, device=device))
            cyc_preds = []
            for c_idx in range(MAX_CYCLES):
                c_emb = self.cycle_idx_emb(torch.full((bsz,), c_idx, dtype=torch.long, device=device))
                feat = torch.cat([h, r_emb, a_emb, c_emb], dim=-1)
                cyc_preds.append(torch.sigmoid(self.param_mlp(feat)))
            out.append(torch.stack(cyc_preds, dim=1))
        return torch.stack(out, dim=1)


def validate_training_config(config: dict[str, Any]) -> None:
    """Reject label corruption instead of normalizing it into another target."""
    if not isinstance(config, dict) or set(config) != {"version", "decision", "steps"}:
        raise ValueError("Config must contain exactly version, decision and steps.")
    if config["version"] != CONFIG_VERSION or config["decision"] not in DECISIONS:
        raise ValueError("Unsupported config version or decision.")
    steps = config["steps"]
    if not isinstance(steps, list):
        raise ValueError("steps must be a list.")
    if config["decision"] != "execute":
        if steps:
            raise ValueError("Non-execution labels must have empty steps.")
        return
    if not 1 <= len(steps) <= 2:
        raise ValueError("Execution labels require 1..2 steps.")
    total_actions = 0
    for step in steps:
        if not isinstance(step, dict) or set(step) != {"actions"}:
            raise ValueError("Each step must contain only actions.")
        actions = step["actions"]
        if not isinstance(actions, list) or not actions:
            raise ValueError("Each step requires actions.")
        used = set()
        for action in actions:
            if not isinstance(action, dict) or set(action) != {"resource_id", "cycles"}:
                raise ValueError("Each action must contain resource_id and cycles.")
            rid = action["resource_id"]
            if rid not in RESOURCE_SPECS:
                raise ValueError(f"Unknown resource {rid}.")
            if used & RESOURCE_CHANNELS[rid]:
                raise ValueError(f"Parallel channel conflict for {rid}.")
            used |= RESOURCE_CHANNELS[rid]
            total_actions += 1
            cycles = action["cycles"]
            if not isinstance(cycles, list) or not 1 <= len(cycles) <= MAX_CYCLES:
                raise ValueError("Cycles require 1..3 entries.")
            spec = RESOURCE_SPECS[rid]
            for cycle in cycles:
                if not isinstance(cycle, dict) or set(cycle) != {"duration_ms", "controls"}:
                    raise ValueError("Each cycle requires duration_ms and controls.")
                dur = cycle["duration_ms"]
                if type(dur) is not int or not spec["min_dur"] <= dur <= spec["max_dur"]:
                    raise ValueError(f"Invalid duration for {rid}: {dur}.")
                controls = cycle["controls"]
                expected = {"hold_ratio"} | ({"amplitude_scale"} if spec["supports_amp"] else set())
                if not isinstance(controls, dict) or set(controls) != expected:
                    raise ValueError(f"Unexpected controls for {rid}.")
                for name, low, high in (("hold_ratio", "min_hold", "max_hold"), ("amplitude_scale", "min_amp", "max_amp")):
                    if name in expected:
                        value = controls[name]
                        if type(value) not in (int, float) or not math.isfinite(value) or not spec[low] <= value <= spec[high]:
                            raise ValueError(f"Invalid {name} for {rid}: {value}.")
                # Mirrors the pinned catalog's phase topology; Unity compilation is still mandatory.
                hold = controls["hold_ratio"]
                if rid == "look_around.basic" and hold > 0:
                    raise ValueError("invalid_hold_mapping: look_around.basic has no hold-phase points.")
                alpha = 0.4 if rid == "surprise.basic" else 0.5
                enter_ms = (dur - dur * hold) * alpha
                hold_end_ms = enter_ms + dur * hold
                if hold > 0 and math.floor(hold_end_ms + 0.5) - math.floor(enter_ms + 0.5) < 80:
                    raise ValueError("hold_segment_too_short: nonzero hold must survive the 80 ms native limit.")
                key_times = [0, math.floor(enter_ms + 0.5)]
                if rid in {"shake_head.basic", "look_around.basic"}:
                    key_times.append(math.floor(enter_ms * 0.5 + 0.5))
                if hold > 0:
                    key_times.append(math.floor(hold_end_ms + 0.5))
                key_times.append(dur)
                key_times.sort()
                if any(b - a < 80 for a, b in zip(key_times, key_times[1:])):
                    raise ValueError("phase_segment_too_short: native channel segment below 80 ms.")
    if not 1 <= total_actions <= MAX_ACTIONS:
        raise ValueError("Execution labels require 1..2 total actions.")


def decode_config(disc: dict[str, torch.Tensor], params: torch.Tensor) -> dict[str, Any]:
    """Decode exactly the predicted resources; impossible structure is a technical failure.

    params must be conditioned on disc['resource_id'].argmax(-1), which is also
    the resource selection used here. No resource substitution occurs.
    """
    if any(not torch.isfinite(disc[name]).all() for name in ("decision", "resource_id", "stage", "cycle_count")):
        raise ModelOutputError("Non-finite discrete prediction.")
    decision = DECISIONS[int(disc["decision"][0].argmax().item())]
    if decision != "execute":
        return {"version": CONFIG_VERSION, "decision": decision, "steps": []}
    stages = {0: [], 1: []}
    used_channels = {0: set(), 1: set()}
    for slot in range(MAX_ACTIONS):
        resource_index = int(disc["resource_id"][0, slot].argmax().item())
        if resource_index == 0:
            continue
        stage = int(disc["stage"][0, slot].argmax().item())
        count = int(disc["cycle_count"][0, slot].argmax().item())
        if stage not in stages or not 1 <= count <= MAX_CYCLES:
            raise ModelOutputError(f"Invalid active slot {slot}: stage={stage}, cycle_count={count}.")
        rid = RESOURCE_IDS[resource_index]
        overlap = used_channels[stage] & RESOURCE_CHANNELS[rid]
        if overlap:
            raise ModelOutputError(f"Parallel resource conflict at slot {slot}: {rid}, channels={sorted(overlap)}.")
        used_channels[stage] |= RESOURCE_CHANNELS[rid]
        spec = RESOURCE_SPECS[rid]
        cycles = []
        for cycle_index in range(count):
            duration, amplitude, hold = [float(x) for x in params[0, slot, cycle_index].tolist()]
            if not all(math.isfinite(x) and 0 <= x <= 1 for x in (duration, amplitude, hold)):
                raise ModelOutputError("Non-finite or out-of-bound predicted parameters.")
            controls = {"hold_ratio": denorm_linear(hold, spec["min_hold"], spec["max_hold"])}
            if spec["supports_amp"]:
                controls["amplitude_scale"] = denorm_linear(amplitude, spec["min_amp"], spec["max_amp"])
            cycles.append({"duration_ms": denorm_log_duration(duration, spec), "controls": controls})
        stages[stage].append({"resource_id": rid, "cycles": cycles})
    if not any(stages.values()):
        raise ModelOutputError("execute prediction has no active resource.")
    if not stages[0] and stages[1]:
        raise ModelOutputError("execute prediction starts at stage 1 with no stage 0.")
    result = {"version": CONFIG_VERSION, "decision": "execute", "steps": [
        {"actions": sorted(stages[stage], key=lambda action: RESOURCE_TO_ID[action["resource_id"]])}
        for stage in (0, 1) if stages[stage]
    ]}
    try:
        validate_training_config(result)
    except ValueError as exc:
        raise ModelOutputError(str(exc)) from exc
    return result
