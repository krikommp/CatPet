"""Versioned feasible parameter head for the pinned Yukikaze v0.2 catalog.

The legacy head/decoder are deliberately unchanged. Positive holds are positions
in a resource/duration-conditioned legal 0.001 ratio grid, with a separate learned
zero/positive gate. The grid is the output space, not a repair of decoded values.
"""
from __future__ import annotations

from bisect import bisect_left
from functools import lru_cache
import math
import struct
from typing import Any

import torch
import torch.nn as nn
import torch.nn.functional as F

from action_config_schema import (
    ActionConfigV02Model, CONFIG_VERSION, DECISIONS, MAX_ACTIONS, MAX_CYCLES,
    ModelOutputError, RESOURCE_CHANNELS, RESOURCE_IDS, RESOURCE_SPECS,
    RESOURCE_TO_ID, canonicalize_config, denorm_log_duration,
    validate_training_config,
)

MODEL_ARCHITECTURE = "action-config-head.feasible-v1"
PARAMETERIZATION_VERSION = "resource-feasible-hold-gate.v1"
DECODER_POLICY_VERSION = "strict-predicted-resource.feasible-v1"
MIN_SEGMENT_MS = 80
RATIO_GRID_SCALE = 1000

# (parameter, reference, peak, native_min, native_max). Only scalable channels
# from ActionResourceCatalog.CreateYukikazeV02 participate. In particular the
# smile/angry eye switches and all expression toggles are NOT amplitude-scaled.
# Native limits are from YukikazeActionCatalog.CreateProfile.
NATIVE_SCALABLE_CHANNELS = {
    "blink.full": (),
    "nod.basic": (("ParamAngleY", 0, -18, -30, 30), ("ParamBodyAngleY", 0, -4.5, -10, 10)),
    "shake_head.basic": (("ParamAngleX", 0, -18, -30, 30), ("ParamAngleX", 0, 18, -30, 30)),
    "tilt_head.basic": (("ParamAngleZ", 0, 20, -30, 30), ("ParamBodyAngleZ", 0, 5, -10, 10)),
    "look_around.basic": (("ParamEyeBallX", 0, -.8, -1, 1), ("ParamEyeBallX", 0, .8, -1, 1),
                          ("ParamAngleX", 0, -14, -30, 30), ("ParamAngleX", 0, 14, -30, 30)),
    "smile.basic": (("ParamMouthForm", 0, .95, -1, 1), ("ParamMouthOpenY", 0, .5, 0, 1),
                    ("ParamBrowLY", 0, .6, -1, 1), ("ParamBrowRY", 0, .6, -1, 1)),
    "angry.basic": (("ParamBrowLY", 0, -.9, -1, 1), ("ParamBrowRY", 0, -.9, -1, 1),
                    ("ParamBrowLX", 0, -.6, -1, 1), ("ParamBrowRX", 0, -.6, -1, 1)),
    "shy.basic": (("ParamAngleZ", 0, -18, -30, 30), ("ParamEyeBallX", 0, .8, -1, 1),
                  ("ParamEyeBallY", 0, -.45, -1, 1), ("ParamBrowLY", 0, -.4, -1, 1),
                  ("ParamBrowRY", 0, -.4, -1, 1)),
    "surprise.basic": (("ParamBrowLY", 0, .8, -1, 1), ("ParamBrowRY", 0, .8, -1, 1)),
    "wave.basic": (("PARAM_Arm_RT_Angle", 0, 8, 0, 10), ("PARAM_Arm_R_hand", 0, .9, 0, 1)),
    "cheer.basic": (("PARAM_Arm_LT_Angle", 0, 8.5, 0, 10), ("PARAM_Arm_RT_Angle", 0, 8.5, 0, 10),
                    ("PARAM_shangxia", 0, .85, 0, 1)),
    "bow.basic": (("ParamBodyAngleY", 0, -8.5, -10, 10), ("ParamAngleY", 0, -20, -30, 30)),
}


def feasible_amplitude_bounds(resource_id: str) -> tuple[float, float]:
    """Catalog/native intersection, with inward rounding to output precision."""
    spec = RESOURCE_SPECS[resource_id]
    low, high = spec["min_amp"], spec["max_amp"]
    for _, reference, peak, native_low, native_high in NATIVE_SCALABLE_CHANNELS[resource_id]:
        delta = peak - reference
        if delta:
            left, right = sorted(((native_low - reference) / delta, (native_high - reference) / delta))
            low, high = max(low, left), min(high, right)
    return math.ceil(low * 1000) / 1000, math.floor(high * 1000) / 1000


def _float32(value: float) -> float:
    return struct.unpack("f", struct.pack("f", value))[0]


def _segment_times(resource_id: str, duration_ms: int, hold: float, native_float: bool) -> list[int]:
    # C#: int * float is rounded to float BEFORE assignment to double holdMs.
    hold_ms = _float32(duration_ms * _float32(hold)) if native_float else duration_ms * hold
    enter = (duration_ms - hold_ms) * (0.4 if resource_id == "surprise.basic" else 0.5)
    times = [0, math.floor(enter + 0.5), duration_ms]
    if resource_id in {"shake_head.basic", "look_around.basic"}:
        times.append(math.floor(enter * 0.5 + 0.5))
    if hold > 0:
        times.append(math.floor(enter + hold_ms + 0.5))
    return sorted(times)


def _hold_is_feasible(resource_id: str, duration_ms: int, hold: float) -> bool:
    if resource_id == "look_around.basic" and hold != 0:
        return False
    return all(
        all(right - left >= MIN_SEGMENT_MS for left, right in zip(times, times[1:]))
        for times in (_segment_times(resource_id, duration_ms, hold, False),
                      _segment_times(resource_id, duration_ms, hold, True))
    )


@lru_cache(maxsize=4096)
def legal_positive_holds(resource_id: str, duration_ms: int) -> tuple[float, ...]:
    """Exact legal positive ratio grid under Python and pinned native arithmetic."""
    spec = RESOURCE_SPECS[resource_id]
    if type(duration_ms) is not int or not spec["min_dur"] <= duration_ms <= spec["max_dur"]:
        raise ValueError(f"Invalid duration for {resource_id}: {duration_ms}.")
    if resource_id == "look_around.basic":
        return ()
    return tuple(tick / RATIO_GRID_SCALE
                 for tick in range(1, math.floor(spec["max_hold"] * RATIO_GRID_SCALE) + 1)
                 if _hold_is_feasible(resource_id, duration_ms, tick / RATIO_GRID_SCALE))


def _hold_position(grid: tuple[float, ...], hold: float) -> float:
    """Inverse grid coordinate; never edits the source label or chooses zero."""
    if not grid or not grid[0] <= hold <= grid[-1]:
        raise ValueError(f"Gold hold {hold} is outside the representable positive hold grid.")
    if len(grid) == 1:
        return 0.5
    index = bisect_left(grid, hold)
    if index == 0 or grid[index] == hold:
        return index / (len(grid) - 1)
    fraction = (hold - grid[index - 1]) / (grid[index] - grid[index - 1])
    return (index - 1 + fraction) / (len(grid) - 1)


class FeasibleActionConfigModel(ActionConfigV02Model):
    """Same pooled MiniRBT features and discrete heads; additional learned gate."""

    def __init__(self, hidden_size: int = 256, mlp_dim: int = 256, cond_dim: int = 64, dropout: float = 0.1):
        super().__init__(hidden_size, mlp_dim, cond_dim, dropout)
        self.hold_gate = nn.Sequential(
            nn.Linear(mlp_dim + cond_dim * 3, 96), nn.GELU(), nn.Linear(96, 1))

    def forward_params(self, h: torch.Tensor, resource_ids: torch.Tensor) -> dict[str, torch.Tensor]:
        values, gates = [], []
        batch_size = h.size(0)
        for action in range(MAX_ACTIONS):
            resource = self.resource_emb(resource_ids[:, action])
            action_emb = self.action_slot_emb(torch.full((batch_size,), action, dtype=torch.long, device=h.device))
            cycle_values, cycle_gates = [], []
            for cycle in range(MAX_CYCLES):
                cycle_emb = self.cycle_idx_emb(torch.full((batch_size,), cycle, dtype=torch.long, device=h.device))
                conditioned = torch.cat((h, resource, action_emb, cycle_emb), dim=-1)
                cycle_values.append(torch.sigmoid(self.param_mlp(conditioned)))
                cycle_gates.append(self.hold_gate(conditioned).squeeze(-1))
            values.append(torch.stack(cycle_values, dim=1))
            gates.append(torch.stack(cycle_gates, dim=1))
        return {"values": torch.stack(values, dim=1), "hold_logits": torch.stack(gates, dim=1)}


def make_feasible_batch(items: list[dict[str, Any]]) -> dict[str, torch.Tensor]:
    """Create targets from reviewed configs, not legacy normalized target caches."""
    if not items:
        raise ValueError("A feasible target batch must contain at least one item.")
    targets = []
    for item in items:
        config = item["config"]
        target = canonicalize_config(config)
        target.pop("hold_norm")
        for key in ("hold_on", "hold_mask", "positive_hold_mask", "hold_position", "gold_hold_ratio"):
            target[key] = [[0.0] * MAX_CYCLES for _ in range(MAX_ACTIONS)]
        actions = [action for step in config["steps"] for action in
                   sorted(step["actions"], key=lambda value: RESOURCE_TO_ID[value["resource_id"]])]
        for action_index, action in enumerate(actions):
            rid = action["resource_id"]
            amp_low, amp_high = feasible_amplitude_bounds(rid)
            for cycle_index, cycle in enumerate(action["cycles"]):
                controls = cycle["controls"]
                hold = float(controls["hold_ratio"])
                if not _hold_is_feasible(rid, cycle["duration_ms"], hold):
                    raise ValueError(f"Gold hold is not natively representable for {rid}.")
                target["gold_hold_ratio"][action_index][cycle_index] = hold
                target["hold_on"][action_index][cycle_index] = float(hold > 0)
                target["hold_mask"][action_index][cycle_index] = float(rid != "look_around.basic")
                if hold > 0:
                    target["positive_hold_mask"][action_index][cycle_index] = 1.0
                    target["hold_position"][action_index][cycle_index] = _hold_position(
                        legal_positive_holds(rid, cycle["duration_ms"]), hold)
                if RESOURCE_SPECS[rid]["supports_amp"]:
                    amp = float(controls["amplitude_scale"])
                    if not amp_low <= amp <= amp_high:
                        raise ValueError(f"Gold amplitude {amp} is outside feasible output bounds for {rid}.")
                    target["amp_norm"][action_index][cycle_index] = (amp - amp_low) / (amp_high - amp_low)
        targets.append(target)
    discrete_keys = {"decision", "resource_id", "stage", "cycle_count"}
    return {key: torch.tensor([row[key] for row in targets],
                              dtype=torch.long if key in discrete_keys else torch.float32)
            for key in targets[0]}


def compute_feasible_loss(model: FeasibleActionConfigModel, feats: torch.Tensor,
                          batch: dict[str, torch.Tensor]) -> torch.Tensor:
    discrete = model.forward_discrete(feats)
    decision_target = batch["decision"]
    loss = F.cross_entropy(discrete["decision"], decision_target)
    execute = decision_target == 0
    if not execute.any():
        return loss
    loss = loss + F.cross_entropy(discrete["resource_id"][execute].reshape(-1, len(RESOURCE_IDS)),
                                  batch["resource_id"][execute].reshape(-1))
    active = execute.unsqueeze(1) & (batch["resource_id"] > 0)
    if active.any():
        loss = loss + F.cross_entropy(discrete["stage"][active], batch["stage"][active])
        loss = loss + F.cross_entropy(discrete["cycle_count"][active], batch["cycle_count"][active])
    params = model.forward_params(discrete["h"], batch["resource_id"])
    mask = execute[:, None, None].float()
    for channel, target_key, mask_key in ((0, "dur_norm", "cyc_mask"),
                                          (1, "amp_norm", "amp_mask"),
                                          (2, "hold_position", "positive_hold_mask")):
        weights = batch[mask_key] * mask
        error = F.smooth_l1_loss(params["values"][..., channel], batch[target_key], reduction="none")
        loss = loss + 2.0 * (error * weights).sum() / weights.sum().clamp_min(1)
    gate_weights = batch["hold_mask"] * mask
    gate_error = F.binary_cross_entropy_with_logits(params["hold_logits"], batch["hold_on"], reduction="none")
    return loss + (gate_error * gate_weights).sum() / gate_weights.sum().clamp_min(1)


def decode_feasible_config(discrete: dict[str, torch.Tensor], params: dict[str, torch.Tensor],
                           duration_overrides: dict[tuple[int, int], int] | None = None) -> dict[str, Any]:
    """Decode predicted structure unchanged, then construct feasible cycle values.

    Overrides are explicit-input durations keyed by canonical flattened action
    index (stage, then RESOURCE_IDS order), cycle index. They are applied before
    selecting a positive hold grid. Unknown/out-of-range overrides are errors.
    """
    for key, shape in (("decision", (1, len(DECISIONS))),
                       ("resource_id", (1, MAX_ACTIONS, len(RESOURCE_IDS))),
                       ("stage", (1, MAX_ACTIONS, 3)),
                       ("cycle_count", (1, MAX_ACTIONS, MAX_CYCLES + 1))):
        value = discrete.get(key)
        if not isinstance(value, torch.Tensor) or tuple(value.shape) != shape or not torch.isfinite(value).all():
            raise ModelOutputError(f"Invalid/non-finite discrete prediction: {key}.")
    for key, shape in (("values", (1, MAX_ACTIONS, MAX_CYCLES, 3)),
                       ("hold_logits", (1, MAX_ACTIONS, MAX_CYCLES))):
        value = params.get(key)
        if not isinstance(value, torch.Tensor) or tuple(value.shape) != shape or not torch.isfinite(value).all():
            raise ModelOutputError(f"Invalid/non-finite parameter prediction: {key}.")
    if ((params["values"] < 0) | (params["values"] > 1)).any():
        raise ModelOutputError("Out-of-bound predicted parameters.")
    overrides = {} if duration_overrides is None else dict(duration_overrides)
    decision = DECISIONS[int(discrete["decision"][0].argmax().item())]
    if decision != "execute":
        if overrides:
            raise ModelOutputError("Duration overrides cannot target a non-execution prediction.")
        result = {"version": CONFIG_VERSION, "decision": decision, "steps": []}
        validate_training_config(result)
        return result
    active, used = [], {0: set(), 1: set()}
    for slot in range(MAX_ACTIONS):
        resource_index = int(discrete["resource_id"][0, slot].argmax().item())
        if resource_index == 0:
            continue
        stage = int(discrete["stage"][0, slot].argmax().item())
        count = int(discrete["cycle_count"][0, slot].argmax().item())
        if stage not in used or not 1 <= count <= MAX_CYCLES:
            raise ModelOutputError(f"Invalid active slot {slot}: stage={stage}, cycle_count={count}.")
        rid = RESOURCE_IDS[resource_index]
        overlap = used[stage] & RESOURCE_CHANNELS[rid]
        if overlap:
            raise ModelOutputError(f"Parallel resource conflict at slot {slot}: {rid}, channels={sorted(overlap)}.")
        used[stage] |= RESOURCE_CHANNELS[rid]
        active.append((stage, resource_index, slot, count))
    if not active:
        raise ModelOutputError("execute prediction has no active resource.")
    active.sort()
    if active[0][0] != 0:
        raise ModelOutputError("execute prediction starts at stage 1 with no stage 0.")
    valid_override_keys = {(action, cycle) for action, entry in enumerate(active) for cycle in range(entry[3])}
    for key, value in overrides.items():
        if (type(key) is not tuple or len(key) != 2 or any(type(index) is not int for index in key)
                or key not in valid_override_keys or type(value) is not int):
            raise ModelOutputError(f"Invalid duration override: {key!r} -> {value!r}.")
    stages = {0: [], 1: []}
    for action_index, (stage, resource_index, slot, count) in enumerate(active):
        rid = RESOURCE_IDS[resource_index]
        spec = RESOURCE_SPECS[rid]
        amp_low, amp_high = feasible_amplitude_bounds(rid)
        cycles = []
        for cycle_index in range(count):
            duration_position, amp_position, hold_position = params["values"][0, slot, cycle_index].tolist()
            duration_ms = overrides.get((action_index, cycle_index), denorm_log_duration(duration_position, spec))
            if not spec["min_dur"] <= duration_ms <= spec["max_dur"]:
                raise ModelOutputError(f"Explicit duration {duration_ms} is outside bounds for {rid}.")
            hold = 0.0
            if rid != "look_around.basic" and params["hold_logits"][0, slot, cycle_index].item() > 0:
                grid = legal_positive_holds(rid, duration_ms)
                if not grid:
                    raise ModelOutputError(f"No positive hold is representable for {rid} at {duration_ms}ms.")
                hold = grid[math.floor(hold_position * (len(grid) - 1) + 0.5)]
            controls = {"hold_ratio": hold}
            if spec["supports_amp"]:
                controls["amplitude_scale"] = round(amp_low + amp_position * (amp_high - amp_low), 3)
            cycles.append({"duration_ms": duration_ms, "controls": controls})
        stages[stage].append({"resource_id": rid, "cycles": cycles})
    result = {"version": CONFIG_VERSION, "decision": decision,
              "steps": [{"actions": stages[stage]} for stage in (0, 1) if stages[stage]]}
    try:
        validate_training_config(result)
    except ValueError as exc:
        raise ModelOutputError(str(exc)) from exc
    return result
