"""Feasible-head contract tests; constructed configs are never training data."""
import copy
import math
from pathlib import Path
import re
import struct
import sys
import unittest

import torch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools/ActionEncoder"))
from action_config_schema import (
    ActionConfigV02Model, CONFIG_VERSION, DECISIONS, ModelOutputError,
    RESOURCE_IDS, RESOURCE_SPECS, RESOURCE_TO_ID, decode_config,
    validate_training_config,
)
from feasible_config import (
    FeasibleActionConfigModel, NATIVE_SCALABLE_CHANNELS, compute_feasible_loss,
    decode_feasible_config, feasible_amplitude_bounds, legal_positive_holds,
    make_feasible_batch,
)


def discrete(resources=("blink.full", "PAD"), stages=(0, 2), counts=(1, 0), decision="execute"):
    def logits(indexes, classes):
        return torch.nn.functional.one_hot(torch.tensor(indexes), classes).float() * 20 - 10
    return {"decision": logits([DECISIONS.index(decision)], len(DECISIONS)),
            "resource_id": logits([[RESOURCE_TO_ID[r] for r in resources]], len(RESOURCE_IDS)),
            "stage": logits([list(stages)], 3), "cycle_count": logits([list(counts)], 4)}


def parameters(duration=.5, amplitude=.5, position=.5, gate=10.):
    values = torch.tensor([duration, amplitude, position]).reshape(1, 1, 1, 3).expand(1, 2, 3, 3).clone()
    return {"values": values, "hold_logits": torch.full((1, 2, 3), float(gate))}


def config(resource="blink.full", duration=600, hold=.2, amplitude=.9):
    controls = {"hold_ratio": hold}
    if RESOURCE_SPECS[resource]["supports_amp"]:
        controls["amplitude_scale"] = amplitude
    return {"version": CONFIG_VERSION, "decision": "execute", "steps": [
        {"actions": [{"resource_id": resource, "cycles": [{"duration_ms": duration, "controls": controls}]}]}]}


def f32(value):
    return struct.unpack("f", struct.pack("f", value))[0]


def native_times(resource, duration, hold):
    """Independent literal mirror of C# float multiplication and phase topology."""
    held = f32(duration * f32(hold))
    enter = (duration - held) * (.4 if resource == "surprise.basic" else .5)
    round_ms = lambda value: math.floor(value + .5)
    times = [0, round_ms(enter), duration]
    if resource in {"shake_head.basic", "look_around.basic"}:
        times.append(round_ms(enter * .5))
    if hold > 0:
        times.append(round_ms(enter + held))
    return sorted(times)


class FeasibleConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        torch.set_num_threads(2)

    def test_all_resource_duration_and_parameter_boundaries_are_native_feasible(self):
        for resource, spec in RESOURCE_SPECS.items():
            for duration in (spec["min_dur"], spec["min_dur"] + 1,
                             (spec["min_dur"] + spec["max_dur"]) // 2, spec["max_dur"]):
                for position in (0., .5, 1.):
                    for gate in (-1., 0., 1e-20):
                        with self.subTest(resource=resource, duration=duration, position=position, gate=gate):
                            result = decode_feasible_config(discrete((resource, "PAD")),
                                parameters(position=position, amplitude=1., gate=gate), {(0, 0): duration})
                            validate_training_config(result)
                            cycle = result["steps"][0]["actions"][0]["cycles"][0]
                            self.assertEqual(cycle["duration_ms"], duration)
                            hold = cycle["controls"]["hold_ratio"]
                            if gate <= 0 or resource == "look_around.basic":
                                self.assertEqual(hold, 0.)
                            else:
                                self.assertGreater(hold, 0.)
                            times = native_times(resource, duration, hold)
                            self.assertTrue(all(b - a >= 80 for a, b in zip(times, times[1:])), times)
                            amp = cycle["controls"].get("amplitude_scale", 1.)
                            for name, reference, peak, low, high in NATIVE_SCALABLE_CHANNELS[resource]:
                                actual = f32(f32(reference) + f32(f32(amp) * f32(f32(peak) - f32(reference))))
                                self.assertLessEqual(actual, high, (resource, name, actual))
                                self.assertGreaterEqual(actual, low, (resource, name, actual))

    def test_grid_excludes_float_rounding_holes(self):
        # The full generated grid, including edge ratios, must survive native
        # arithmetic, not merely pass the double-precision Python validator.
        for resource, spec in RESOURCE_SPECS.items():
            for duration in (spec["min_dur"], spec["min_dur"] + 7, spec["max_dur"]):
                grid = legal_positive_holds(resource, duration)
                self.assertEqual(bool(grid), resource != "look_around.basic")
                for hold in grid:
                    times = native_times(resource, duration, hold)
                    self.assertTrue(all(b - a >= 80 for a, b in zip(times, times[1:])))

    def test_amplitude_table_matches_scalable_catalog_channels_and_native_profile(self):
        catalog = (ROOT / "Assets/Scripts/ActionLanguage/ActionResourceCatalog.cs").read_text(encoding="utf-8")
        profile = (ROOT / "Assets/Scripts/ActionLanguage/YukikazeActionCatalog.cs").read_text(encoding="utf-8")
        number = r"(-?\d+(?:\.\d+)?)[fF]?"
        native_ranges = {match[0]: (float(match[1]), float(match[2])) for match in re.findall(
            r'new ParameterDefinition\("([^"]+)",\s*\d+,\s*' + number + r",\s*" + number, profile)}
        parsed = {}
        for block in catalog.split("new ActionResourceDefinition(")[1:]:
            resource = re.search(r'"([^"]+)"', block).group(1)
            points = []
            for channel in block.split("new ActionResourceChannel(")[1:]:
                match = re.match(r'"([^"]+)",\s*' + number + r",\s*" + number + r",\s*(true|false)", channel)
                name, reference, _, scalable = match.groups()
                if scalable != "true":
                    continue
                peaks = set(float(value) for value in re.findall(
                    r'new PhaseChannelPoint\("[^"]+",\s*[\d.]+,\s*' + number, channel))
                peaks.discard(float(reference))
                for peak in peaks:
                    points.append((name, float(reference), peak, *native_ranges[name]))
            parsed[resource] = sorted(points)
        self.assertEqual(parsed, {resource: sorted(points) for resource, points in NATIVE_SCALABLE_CHANNELS.items()})
        self.assertEqual(feasible_amplitude_bounds("smile.basic"), (.4, 1.052))
        self.assertEqual(feasible_amplitude_bounds("angry.basic"), (.4, 1.111))
        self.assertEqual(feasible_amplitude_bounds("wave.basic"), (.4, 1.111))
        self.assertEqual(feasible_amplitude_bounds("cheer.basic"), (.4, 1.176))
        self.assertEqual(feasible_amplitude_bounds("bow.basic"), (.4, 1.176))

    def test_exact_duration_is_applied_before_positive_hold_selection(self):
        prediction = parameters(duration=1., position=0.)
        original = decode_feasible_config(discrete(), prediction)
        exact = decode_feasible_config(discrete(), prediction, {(0, 0): 300})
        original_cycle = original["steps"][0]["actions"][0]["cycles"][0]
        exact_cycle = exact["steps"][0]["actions"][0]["cycles"][0]
        self.assertEqual(original_cycle["duration_ms"], 1800)
        self.assertEqual(exact_cycle["duration_ms"], 300)
        self.assertGreater(exact_cycle["controls"]["hold_ratio"], original_cycle["controls"]["hold_ratio"])
        validate_training_config(exact)

    def test_override_action_indexes_are_canonical_not_model_slot_indexes(self):
        for stages, ordered_resources in (((0, 0), ["blink.full", "wave.basic"]),
                                           ((0, 1), ["wave.basic", "blink.full"])):
            disc = discrete(("wave.basic", "blink.full"), stages, (2, 3))
            overrides = {(0, 0): 800, (1, 0): 900}
            result = decode_feasible_config(disc, parameters(), overrides)
            actions = [action for step in result["steps"] for action in step["actions"]]
            self.assertEqual([action["resource_id"] for action in actions], ordered_resources)
            self.assertEqual([action["cycles"][0]["duration_ms"] for action in actions], [800, 900])
            self.assertEqual({a["resource_id"]: len(a["cycles"]) for a in actions}, {"wave.basic": 2, "blink.full": 3})
        # Stage order takes priority even when the earlier stage has a larger ID.
        result = decode_feasible_config(discrete(("blink.full", "wave.basic"), (1, 0), (1, 1)),
                                        parameters(), {(0, 0): 1200, (1, 0): 600})
        self.assertEqual(result["steps"][0]["actions"][0]["resource_id"], "wave.basic")
        self.assertEqual(result["steps"][0]["actions"][0]["cycles"][0]["duration_ms"], 1200)

    def test_conflicts_and_invalid_counts_are_rejected_without_mutation(self):
        cases = [discrete(("PAD", "PAD")), discrete(counts=(0, 0)),
                 discrete(stages=(2, 2)), discrete(stages=(1, 2)),
                 discrete(("blink.full", "smile.basic"), (0, 0), (1, 1))]
        for disc in cases:
            before = {key: value.clone() for key, value in disc.items()}
            with self.assertRaises(ModelOutputError):
                decode_feasible_config(disc, parameters())
            self.assertTrue(all(torch.equal(before[key], disc[key]) for key in before))

    def test_nonexecution_decision_preserved(self):
        for decision in DECISIONS[1:]:
            result = decode_feasible_config(discrete(decision=decision), parameters())
            self.assertEqual(result, {"version": CONFIG_VERSION, "decision": decision, "steps": []})

    def test_invalid_overrides_and_nonfinite_outputs_reject(self):
        for overrides in ({(0, 0): 299}, {(0, 0): 1801}, {(0, 1): 600},
                          {(1, 0): 600}, {(0, 0): 600.0}, {(True, 0): 600}):
            with self.assertRaises(ModelOutputError):
                decode_feasible_config(discrete(), parameters(), overrides)
        for key in ("values", "hold_logits"):
            for bad in (float("nan"), float("inf")):
                params = parameters()
                params[key].flatten()[0] = bad
                with self.assertRaises(ModelOutputError):
                    decode_feasible_config(discrete(), params)
        for key in discrete():
            disc = discrete()
            disc[key].flatten()[0] = float("nan")
            with self.assertRaises(ModelOutputError):
                decode_feasible_config(disc, parameters())
        with self.assertRaises(ModelOutputError):
            decode_feasible_config(discrete(), parameters(position=1.01))
        with self.assertRaises(ModelOutputError):
            decode_feasible_config(discrete(decision="none"), parameters(), {(0, 0): 600})

    def test_targets_use_actual_config_preserve_zero_and_ignore_legacy_targets(self):
        source = [{"config": config(hold=0.)}, {"config": config(hold=.345678)},
                  {"config": config("look_around.basic", 1000, 0.)},
                  {"config": config("smile.basic", 1000, .4, 1.02)}]
        source[0]["targets"] = {"hold_norm": "deliberately unusable legacy cache"}
        before = copy.deepcopy(source)
        batch = make_feasible_batch(source)
        self.assertEqual(source, before)
        self.assertEqual(batch["hold_on"][:, 0, 0].tolist(), [0., 1., 0., 1.])
        self.assertEqual(batch["hold_mask"][:, 0, 0].tolist(), [1., 1., 0., 1.])
        self.assertEqual(batch["positive_hold_mask"][:, 0, 0].tolist(), [0., 1., 0., 1.])
        self.assertAlmostEqual(batch["gold_hold_ratio"][1, 0, 0].item(), .345678, places=7)
        self.assertTrue(torch.all((batch["hold_position"] >= 0) & (batch["hold_position"] <= 1)))
        invalid = [{"config": config("smile.basic", 1000, .4, 1.15)}]
        with self.assertRaises(ValueError):
            make_feasible_batch(invalid)
        self.assertEqual(invalid[0]["config"]["steps"][0]["actions"][0]["cycles"][0]["controls"]["amplitude_scale"], 1.15)

    def test_forward_loss_and_backprop_are_finite_with_learned_gate(self):
        torch.manual_seed(77)
        model = FeasibleActionConfigModel(hidden_size=8, mlp_dim=12, cond_dim=4, dropout=0.)
        items = [{"config": config(hold=0.)}, {"config": config(hold=.25)},
                 {"config": config("smile.basic", 1000, .4)},
                 {"config": {"version": CONFIG_VERSION, "decision": "none", "steps": []}}]
        batch = make_feasible_batch(items)
        features = torch.randn(4, 8, requires_grad=True)
        disc = model.forward_discrete(features)
        params = model.forward_params(disc["h"], batch["resource_id"])
        self.assertEqual(tuple(params["values"].shape), (4, 2, 3, 3))
        self.assertEqual(tuple(params["hold_logits"].shape), (4, 2, 3))
        loss = compute_feasible_loss(model, features, batch)
        self.assertTrue(torch.isfinite(loss))
        loss.backward()
        self.assertTrue(torch.isfinite(features.grad).all())
        self.assertTrue(all(parameter.grad is None or torch.isfinite(parameter.grad).all() for parameter in model.parameters()))
        self.assertGreater(sum(p.grad.abs().sum().item() for p in model.hold_gate.parameters()), 0.)
        # All non-execution batches retain a differentiable decision objective.
        negative = make_feasible_batch([items[-1]])
        negative_loss = compute_feasible_loss(model, torch.randn(1, 8), negative)
        self.assertTrue(torch.isfinite(negative_loss))

    def test_legacy_state_loading_and_decoder_remain_unchanged(self):
        kwargs = {"hidden_size": 8, "mlp_dim": 12, "cond_dim": 4, "dropout": 0.}
        torch.manual_seed(19)
        legacy = ActionConfigV02Model(**kwargs).eval()
        saved = copy.deepcopy(legacy.state_dict())
        loaded = ActionConfigV02Model(**kwargs).eval()
        loaded.load_state_dict(saved, strict=True)
        feats = torch.randn(1, 8)
        ids = torch.tensor([[RESOURCE_TO_ID["blink.full"], 0]])
        old_params = legacy.forward_params(legacy.forward_discrete(feats)["h"], ids)
        self.assertIsInstance(old_params, torch.Tensor)
        self.assertTrue(torch.equal(old_params, loaded.forward_params(loaded.forward_discrete(feats)["h"], ids)))
        self.assertFalse(any(key.startswith("hold_gate") for key in saved))
        with self.assertRaises(RuntimeError):
            FeasibleActionConfigModel(**kwargs).load_state_dict(saved, strict=True)
        # Legacy's small-positive hold failure is preserved for existing versions.
        with self.assertRaises(ModelOutputError):
            decode_config(discrete(), parameters(position=.001)["values"])
        self.assertEqual(decode_feasible_config(discrete(), parameters(position=.001, gate=-1.))
                         ["steps"][0]["actions"][0]["cycles"][0]["controls"]["hold_ratio"], 0.)


if __name__ == "__main__":
    unittest.main()
