"""Shared schema, canonical slot encoding/decoding, and MLP action head for MiniRBT."""
from __future__ import annotations

from typing import Any

import torch
import torch.nn as nn

LABEL_POLICY_VERSION = "action-labels.v1"
CAPABILITY_PROFILE = "yukikaze.v1"
MOTION_MAP_VERSION = "yukikaze-motion.v1"
PLAN_VERSION = "action-plan.v0.1"

DECISIONS = ["execute", "none", "unsupported", "ambiguous"]
ACTION_TYPES = [
    "PAD", "blink", "nod", "shake_head", "tilt_head", "look_around",
    "smile", "angry", "shy", "surprise", "wave", "cheer", "bow",
]
AMPLITUDES = ["PAD", "small", "normal", "full"]
SPEEDS = ["PAD", "slow", "normal", "fast"]
COUNTS = [0, 1, 2, 3]  # 0 = PAD
STAGES = [0, 1, 2]     # 0 = stage0, 1 = stage1, 2 = PAD

MAX_SLOTS = 4
CANONICAL_TYPE_ORDER = {t: idx for idx, t in enumerate(ACTION_TYPES[1:])}

DECISION_TO_ID = {v: i for i, v in enumerate(DECISIONS)}
TYPE_TO_ID = {v: i for i, v in enumerate(ACTION_TYPES)}
AMP_TO_ID = {v: i for i, v in enumerate(AMPLITUDES)}
SPEED_TO_ID = {v: i for i, v in enumerate(SPEEDS)}


def canonicalize_plan(plan: dict[str, Any]) -> dict[str, Any]:
    """Converts an action-plan.v0.1 dict into fixed canonical slot targets with loss masks."""
    decision = plan.get("decision")
    if decision not in DECISION_TO_ID:
        raise ValueError(f"Unsupported decision: {decision}")

    slots = []
    if decision == "execute":
        steps = plan.get("steps") or []
        if not 1 <= len(steps) <= 2:
            raise ValueError("v1 training supports 1 to 2 steps.")
        for stage_idx, step in enumerate(steps):
            actions = sorted(
                step.get("actions") or [],
                key=lambda a: CANONICAL_TYPE_ORDER.get(a.get("type", ""), 99),
            )
            for item in actions:
                atype = item.get("type")
                count = item.get("count")
                amp = item.get("amplitude")
                speed = item.get("speed")
                if atype not in CANONICAL_TYPE_ORDER:
                    raise ValueError(f"Unsupported action type for v1: {atype}")
                if type(count) is not int or not 1 <= count <= 3:
                    raise ValueError(f"Out of v1 count range (1..3): {count}")
                if atype == "blink":
                    amp = "full"
                elif amp not in ("small", "normal"):
                    raise ValueError(f"Unsupported amplitude '{amp}' for {atype}")
                if speed not in ("slow", "normal", "fast"):
                    raise ValueError(f"Unsupported speed: {speed}")
                slots.append({
                    "type": TYPE_TO_ID[atype],
                    "stage": stage_idx,
                    "count": count,
                    "amplitude": AMP_TO_ID[amp],
                    "speed": SPEED_TO_ID[speed],
                })
        if not 1 <= len(slots) <= 2:
            raise ValueError("v1 training supports 1 to 2 active action items.")

    while len(slots) < MAX_SLOTS:
        slots.append({"type": 0, "stage": 2, "count": 0, "amplitude": 0, "speed": 0})

    return {
        "decision": DECISION_TO_ID[decision],
        "type": [s["type"] for s in slots],
        "stage": [s["stage"] for s in slots],
        "count": [s["count"] for s in slots],
        "amplitude": [s["amplitude"] for s in slots],
        "speed": [s["speed"] for s in slots],
    }


def decode_slots_to_plan(decision_id: int, slot_logits: dict[str, torch.Tensor]) -> dict[str, Any]:
    """Decodes predicted logits for a single sample into a valid action-plan.v0.1 dict."""
    decision = DECISIONS[decision_id]
    if decision != "execute":
        return {"version": PLAN_VERSION, "decision": decision, "steps": []}

    stages: dict[int, list[dict[str, Any]]] = {0: [], 1: []}
    for slot_idx in range(MAX_SLOTS):
        type_id = int(slot_logits["type"][slot_idx].argmax().item())
        if type_id == 0:  # PAD
            continue
        atype = ACTION_TYPES[type_id]
        stage_id = int(slot_logits["stage"][slot_idx][:2].argmax().item())
        count_val = int(slot_logits["count"][slot_idx][1:4].argmax().item()) + 1
        speed_val = SPEEDS[int(slot_logits["speed"][slot_idx][1:].argmax().item()) + 1]
        if atype == "blink":
            amp_val = "full"
        else:
            amp_idx = int(slot_logits["amplitude"][slot_idx][1:3].argmax().item()) + 1
            amp_val = AMPLITUDES[amp_idx]

        stages[stage_id].append({
            "type": atype,
            "count": count_val,
            "amplitude": amp_val,
            "speed": speed_val,
        })

    steps = []
    for st in (0, 1):
        if stages[st]:
            stages[st].sort(key=lambda a: CANONICAL_TYPE_ORDER.get(a["type"], 99))
            steps.append({"actions": stages[st]})

    if not steps:
        return {"version": PLAN_VERSION, "decision": "none", "steps": []}

    return {"version": PLAN_VERSION, "decision": "execute", "steps": steps}


class ActionHeadModel(nn.Module):
    """Lightweight MLP + multi-head classifier over 256-dim MiniRBT pooled features."""

    def __init__(self, hidden_size: int = 256, mlp_dim: int = 256, dropout: float = 0.1):
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
        self.type_head = nn.Linear(mlp_dim, MAX_SLOTS * len(ACTION_TYPES))
        self.stage_head = nn.Linear(mlp_dim, MAX_SLOTS * len(STAGES))
        self.count_head = nn.Linear(mlp_dim, MAX_SLOTS * len(COUNTS))
        self.amplitude_head = nn.Linear(mlp_dim, MAX_SLOTS * len(AMPLITUDES))
        self.speed_head = nn.Linear(mlp_dim, MAX_SLOTS * len(SPEEDS))

    def forward(self, pooled: torch.Tensor) -> dict[str, torch.Tensor]:
        h = self.trunk(pooled)
        bsz = h.size(0)
        return {
            "decision": self.decision_head(h),
            "type": self.type_head(h).view(bsz, MAX_SLOTS, len(ACTION_TYPES)),
            "stage": self.stage_head(h).view(bsz, MAX_SLOTS, len(STAGES)),
            "count": self.count_head(h).view(bsz, MAX_SLOTS, len(COUNTS)),
            "amplitude": self.amplitude_head(h).view(bsz, MAX_SLOTS, len(AMPLITUDES)),
            "speed": self.speed_head(h).view(bsz, MAX_SLOTS, len(SPEEDS)),
        }
