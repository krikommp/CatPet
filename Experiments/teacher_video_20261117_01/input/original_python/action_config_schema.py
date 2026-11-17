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


def decode_config(disc: dict[str, torch.Tensor], params: torch.Tensor) -> dict[str, Any]:
    """Decodes single-sample discrete + continuous predictions into an action-config.v0.2 dict."""
    dec_id = int(disc["decision"][0].argmax().item())
    decision = DECISIONS[dec_id]
    if decision != "execute":
        return {"version": CONFIG_VERSION, "decision": decision, "steps": []}

    stages: dict[int, list[dict[str, Any]]] = {0: [], 1: []}
    used_channels_by_stage: dict[int, set[str]] = {0: set(), 1: set()}
    for a_idx in range(MAX_ACTIONS):
        logits = disc["resource_id"][0, a_idx]
        r_id = int(logits.argmax().item())
        if r_id == 0:
            continue
        st_id = int(disc["stage"][0, a_idx, :2].argmax().item())
        rid = RESOURCE_IDS[r_id]
        if used_channels_by_stage[st_id] & RESOURCE_CHANNELS[rid]:
            # Pick highest-scoring non-conflicting resource in this stage to prevent parallel channel conflict
            ranked = logits.argsort(descending=True).tolist()
            chosen = None
            for cand_id in ranked:
                if cand_id == 0:
                    continue
                cand_rid = RESOURCE_IDS[cand_id]
                if not (used_channels_by_stage[st_id] & RESOURCE_CHANNELS[cand_rid]):
                    chosen = cand_rid
                    break
            if chosen is None:
                continue
            rid = chosen
        used_channels_by_stage[st_id] |= RESOURCE_CHANNELS[rid]
        spec = RESOURCE_SPECS[rid]
        cyc_cnt = int(disc["cycle_count"][0, a_idx, 1:].argmax().item()) + 1

        cycles = []
        for c_idx in range(cyc_cnt):
            p_dur, p_amp, p_hold = [float(x) for x in params[0, a_idx, c_idx].tolist()]
            dur_ms = denorm_log_duration(p_dur, spec)
            ctrls: dict[str, float] = {}
            if spec["supports_amp"]:
                ctrls["amplitude_scale"] = denorm_linear(p_amp, spec["min_amp"], spec["max_amp"])
            if spec["supports_hold"]:
                ctrls["hold_ratio"] = denorm_linear(p_hold, spec["min_hold"], spec["max_hold"])
            cycles.append({"duration_ms": dur_ms, "controls": ctrls})

        stages[st_id].append({"resource_id": rid, "cycles": cycles})

    steps = []
    for st in (0, 1):
        if stages[st]:
            stages[st].sort(key=lambda a: RESOURCE_TO_ID.get(a["resource_id"], 999))
            steps.append({"actions": stages[st]})

    if not steps:
        return {"version": CONFIG_VERSION, "decision": "none", "steps": []}

    return {"version": CONFIG_VERSION, "decision": "execute", "steps": steps}
