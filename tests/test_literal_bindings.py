"""Adversarial exact-duration binding contracts; all inputs are test fixtures."""
from __future__ import annotations

import copy
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "Tools/ActionEncoder"))

from action_config_schema import CONFIG_VERSION, ModelOutputError, RESOURCE_SPECS
from input_constraints import validate_instruction_constraints
from literal_bindings import BINDING_POLICY_VERSION, extract_exact_duration_bindings


def action(rid="nod.basic", durations=(800,), amplitudes=None):
    amplitudes = amplitudes or [1.0] * len(durations)
    return {"resource_id": rid, "cycles": [
        {"duration_ms": duration, "controls": {"hold_ratio": 0.0,
         **({"amplitude_scale": amplitudes[index]} if RESOURCE_SPECS[rid]["supports_amp"] else {})}}
        for index, duration in enumerate(durations)]}


def config(*steps, decision="execute"):
    return {"version": CONFIG_VERSION, "decision": decision,
            "steps": [{"actions": list(step)} for step in steps]}


NONEXACT_OR_UNRELATED_FIXTURES = (
    "不需要点头一次，每次1秒", "无需点头一次，每次1秒",
    "点头一次，每次不满1秒", "点头一次，每次不超1秒",
    "点头一次，每次1秒也不用", "点头一次，每次不一定是1秒",
    "点头一次，背景音乐1秒", "点头一次，后台接口超时1秒",
    "点头一次，每次预计1秒", "点头一次，每次1秒也未必",
    "点头一次，声音长度为1秒", "也许点头一次，每次1秒",
    "如果需要点头一次，每次1秒", "点头一次不是必须，每次1秒",
    "点头一次，背景音乐，时长1秒", "点头一次，不必，每次1秒",
    "点头一次，先1秒", "点头一次，每次1秒而已",
)


class LiteralBindingTests(unittest.TestCase):
    def assert_rejected(self, text, prediction, kind=None):
        before = copy.deepcopy(prediction)
        with self.assertRaises(ModelOutputError) as raised:
            extract_exact_duration_bindings(text, prediction)
        self.assertEqual(prediction, before)
        audit = raised.exception.binding_audit
        self.assertFalse(audit["accepted"])
        self.assertTrue(audit["no_silent_repair"])
        self.assertEqual(audit["policy"], BINDING_POLICY_VERSION)
        if kind:
            self.assertEqual(audit["rejections"][-1]["kind"], kind)
        return audit

    def test_single_exact_with_audit_and_no_mutation(self):
        prediction = config([action()])
        before = copy.deepcopy(prediction)
        text = "  点头一次，用时1.2秒。"
        overrides, audit = extract_exact_duration_bindings(text, prediction)
        self.assertEqual(overrides, {(0, 0): 1200})
        self.assertEqual(prediction, before)
        binding = audit["bindings"][0]
        self.assertEqual(binding["previous_predicted_ms"], 800)
        self.assertEqual(binding["exact_duration_ms"], 1200)
        self.assertEqual(binding["resource_id"], "nod.basic")
        for source in binding["sources"]:
            self.assertEqual(text[source["start"]:source["end"]], "1.2秒")
            self.assertEqual(text[source["scope_start"]:source["scope_end"]], source["scope_text"])
        self.assertEqual(audit["input_role"], "instruction")
        self.assertEqual(audit["unchanged_structural_fields"]["actions"][0]["cycle_count"], 1)

    def test_equivalent_decimal_seconds_and_milliseconds(self):
        for literal in ("1.2秒", "1200毫秒", "1200ms", "1.2s", "一点二秒"):
            with self.subTest(literal=literal):
                actual, _ = extract_exact_duration_bindings("点头一次，用时" + literal, config([action()]))
                self.assertEqual(actual, {(0, 0): 1200})

    def test_positive_grammar_retains_declared_exact_forms(self):
        for text in (
            "点头一次，用时为1秒", "请先点头一次，时长是1秒",
            "点头一次，第一次点头用时1秒", "点头第一次1秒",
        ):
            with self.subTest(text=text):
                overrides, _ = extract_exact_duration_bindings(text, config([action()]))
                self.assertEqual(overrides, {(0, 0): 1000})
        overrides, _ = extract_exact_duration_bindings(
            "点头两次，每次耗时为1秒", config([action(durations=(800, 900))]))
        self.assertEqual(overrides, {(0, 0): 1000, (0, 1): 1000})

    def test_positive_grammar_rejects_unknown_qualifiers_and_unrelated_context(self):
        for text in NONEXACT_OR_UNRELATED_FIXTURES:
            with self.subTest(text=text):
                audit = self.assert_rejected(text, config([action()]))
                self.assertEqual(audit["bindings"], [])

    def test_positive_grammar_does_not_apply_to_duration_free_instructions(self):
        for text in ("请轻轻点头一次", "后台接口已经超时，请点头一次", "别紧张，慢慢点头一次"):
            with self.subTest(text=text):
                prediction = config([action()])
                before = copy.deepcopy(prediction)
                overrides, audit = extract_exact_duration_bindings(text, prediction)
                self.assertEqual(overrides, {})
                self.assertEqual(audit["bindings"], [])
                self.assertEqual(prediction, before)

    def test_shared_prediction_rejects_unsafe_bindings_without_changing_raw_structure(self):
        from config_prediction import FEASIBLE_MODEL_ARCHITECTURE, predict_config
        from feasible_config import decode_feasible_config
        from test_feasible_integration import logits, parameters

        for text in NONEXACT_OR_UNRELATED_FIXTURES:
            with self.subTest(text=text):
                discrete, params = logits(("nod.basic", 0, 1)), parameters()
                before = decode_feasible_config(discrete, params)
                with self.assertRaises(ModelOutputError) as raised:
                    predict_config(discrete, params, text, architecture=FEASIBLE_MODEL_ARCHITECTURE)
                failure = raised.exception
                self.assertEqual(failure.raw_config, before)
                self.assertEqual(failure.raw_prediction["decision"], "execute")
                self.assertEqual(failure.raw_prediction["resource_ids"], ["nod.basic", "PAD"])
                self.assertEqual(failure.raw_prediction["stages"], [0, 2])
                self.assertEqual(failure.raw_prediction["cycle_counts"], [1, 0])
                self.assertFalse(failure.binding_audit["accepted"])
                self.assertEqual(failure.binding_audit["bindings"], [])

    def test_shared_prediction_accepts_positive_exact_scope_and_final_guard(self):
        from config_prediction import FEASIBLE_MODEL_ARCHITECTURE, predict_config
        from test_feasible_integration import logits, parameters

        prediction, audit = predict_config(
            logits(("nod.basic", 0, 2)), parameters(),
            "请点头两次，第一次1秒，第二次1.2秒", architecture=FEASIBLE_MODEL_ARCHITECTURE)
        self.assertEqual([cycle["duration_ms"] for cycle in prediction["steps"][0]["actions"][0]["cycles"]],
                         [1000, 1200])
        self.assertTrue(audit["binding_audit"]["accepted"])
        self.assertTrue(audit["constraint_audit"]["passed_checked_constraints"])

    def test_all_cycles_and_per_cycle_exact(self):
        prediction = config([action(durations=(800, 850, 900))])
        overrides, _ = extract_exact_duration_bindings("点头三次，每次1秒", prediction)
        self.assertEqual(overrides, {(0, 0): 1000, (0, 1): 1000, (0, 2): 1000})
        overrides, _ = extract_exact_duration_bindings("点头三次，第一次600毫秒，第二次1秒，第三次1.2秒", prediction)
        self.assertEqual(overrides, {(0, 0): 600, (0, 1): 1000, (0, 2): 1200})

    def test_first_event_is_not_invented_total_count(self):
        prediction = config([action(durations=(800, 900))])
        overrides, _ = extract_exact_duration_bindings("先点头一次，第二次1.2秒", prediction)
        self.assertEqual(overrides, {(0, 1): 1200})

    def test_parallel_action_order_uses_resource_catalog(self):
        prediction = config([action("wave.basic"), action("nod.basic")])
        overrides, audit = extract_exact_duration_bindings("挥手一次每次1.5秒，点头一次每次1.2秒", prediction)
        self.assertEqual(overrides, {(0, 0): 1200, (1, 0): 1500})
        self.assertEqual({entry["resource_id"]: entry["exact_duration_ms"] for entry in audit["bindings"]},
                         {"wave.basic": 1500, "nod.basic": 1200})

    def test_stage_precedes_resource_catalog_order(self):
        prediction = config([action("wave.basic")], [action("nod.basic")])
        overrides, _ = extract_exact_duration_bindings("挥手一次每次1.5秒，然后点头一次每次1.2秒", prediction)
        self.assertEqual(overrides, {(0, 0): 1500, (1, 0): 1200})

    def test_different_resources_never_share_duration(self):
        prediction = config([action("wave.basic")], [action("nod.basic")])
        overrides, _ = extract_exact_duration_bindings("挥手一次，点头一次每次1.2秒", prediction)
        self.assertEqual(overrides, {(1, 0): 1200})

    def test_scope_cannot_be_guessed_from_model_cycle_count(self):
        for text in ("点头1秒", "点头两次，1秒", "点头两次，挥手一次，每次1秒", "点头一次和挥手一次每次1秒"):
            with self.subTest(text=text):
                self.assert_rejected(text, config([action(), action("wave.basic")]))

    def test_repeated_resource_scope_rejects(self):
        self.assert_rejected("点头一次每次1秒，然后点头一次每次1.2秒",
                             config([action()], [action()]))
        self.assert_rejected("点头一次每次1秒，然后点头一次每次1.2秒", config([action()]))

    def test_contradictory_literals_reject(self):
        self.assert_rejected("点头一次，第一次1秒，第一次1.2秒", config([action()]),
                             "contradictory_exact_durations")
        self.assert_rejected("点头两次，每次1秒，第二次1.2秒", config([action(durations=(800, 900))]),
                             "contradictory_exact_durations")

    def test_repeated_equal_literals_have_exact_provenance(self):
        text = "点头一次，第一次1秒，第一次1000毫秒"
        overrides, audit = extract_exact_duration_bindings(text, config([action()]))
        self.assertEqual(overrides, {(0, 0): 1000})
        self.assertEqual({s["text"] for s in audit["bindings"][0]["sources"]}, {"1秒", "1000毫秒"})

    def test_ranges_approximations_negations_and_other_duration_fields_reject(self):
        for text in (
            "点头一次，大约1秒", "点头一次，约1秒", "点头一次，1秒左右",
            "点头一次，1到2秒", "点头一次，1秒或2秒", "点头一次，至少1秒",
            "点头一次，不要用时1秒", "不要点头一次每次1秒", "点头一次，每次-1秒",
            "点头一次，保持1秒", "点头一次，总共1秒", "点头一次，每次1秒半",
            "点头一次，每次0.8001秒", "点头一次，每次0秒",
        ):
            with self.subTest(text=text):
                self.assert_rejected(text, config([action()]))

    def test_relative_deadline_and_unrecognized_ordinal_are_not_exact_durations(self):
        for text, durations in (
            ("点头两次，第二次比第一次慢1秒", (800, 900)),
            ("点头两次，第二次慢1秒", (800, 900)),
            ("点头三次，第二次和第三次1秒", (800, 900, 1000)),
            ("点头一次，第二轮1秒", (800,)),
            ("点头一次，1秒后开始", (800,)),
            ("点头一次，1秒内完成", (800,)),
            ("点头一次，每次小于1秒", (800,)),
            ("点头一次，每次不短于1秒", (800,)),
            ("点头一次，每次接近1秒", (800,)),
            ("点头一次，每次不是1秒", (800,)),
            ("点头一次，每次1秒是不行的", (800,)),
        ):
            with self.subTest(text=text):
                self.assert_rejected(text, config([action(durations=durations)]))

    def test_separate_ordinal_literal_pairs_in_one_clause_are_unambiguous(self):
        overrides, _ = extract_exact_duration_bindings(
            "点头两次，第一次1秒第二次1.2秒", config([action(durations=(800, 900))]))
        self.assertEqual(overrides, {(0, 0): 1000, (0, 1): 1200})

    def test_direct_scoped_negation_is_rejected_but_generic_negation_is_not(self):
        self.assert_rejected("不要点头，点头一次每次1秒", config([action()]),
                             "explicitly_negated_predicted_action")
        for text in ("别紧张，点头一次每次1秒", "不要摇头，点头一次每次1秒"):
            overrides, _ = extract_exact_duration_bindings(text, config([action()]))
            self.assertEqual(overrides, {(0, 0): 1000})

    def test_wrong_resource_extra_resource_and_count_reject(self):
        self.assert_rejected("点头一次，每次1秒", config([action("wave.basic")]))
        self.assert_rejected("点头一次，每次1秒", config([action(), action("wave.basic")]),
                             "unmentioned_predicted_resource")
        self.assert_rejected("点头两次，每次1秒", config([action()]))
        self.assert_rejected("点头一次，每次1秒", config([action(durations=(800, 900))]))

    def test_missing_cycle_reference_is_not_created(self):
        self.assert_rejected("点头一次，第二次1秒", config([action()]), "missing_predicted_cycle")
        self.assert_rejected("点头一次每次1秒，第二次再来", config([action()]),
                             "non_binding_constraint_violation")

    def test_bounds_are_resource_specific(self):
        for literal in ("100毫秒", "3000毫秒"):
            self.assert_rejected("点头一次，每次" + literal, config([action()]), "duration_out_of_resource_bounds")
        overrides, _ = extract_exact_duration_bindings("点头一次，每次420毫秒", config([action()]))
        self.assertEqual(overrides, {(0, 0): 420})

    def test_duration_relative_checks_defer_and_final_guard_still_required(self):
        prediction = config([action(durations=(900, 700))])
        text = "点头两次，第一次800毫秒，第二次1.2秒，第二次比第一次慢"
        overrides, audit = extract_exact_duration_bindings(text, prediction)
        self.assertEqual(overrides, {(0, 0): 800, (0, 1): 1200})
        self.assertTrue(audit["final_instruction_guard_required"])
        self.assertEqual(len(audit["deferred_duration_constraints"]), 1)
        bound = copy.deepcopy(prediction)
        for (ai, ci), duration in overrides.items():
            bound["steps"][0]["actions"][ai]["cycles"][ci]["duration_ms"] = duration
        self.assertTrue(validate_instruction_constraints(text, bound)["passed_checked_constraints"])
        contradictory = "点头两次，第一次1.2秒，第二次800毫秒，第二次比第一次慢"
        overrides, _ = extract_exact_duration_bindings(contradictory, prediction)
        for (ai, ci), duration in overrides.items():
            bound["steps"][0]["actions"][ai]["cycles"][ci]["duration_ms"] = duration
        self.assertFalse(validate_instruction_constraints(contradictory, bound)["passed_checked_constraints"])

    def test_amplitude_violation_cannot_be_repaired_by_duration_binding(self):
        prediction = config([action(durations=(800, 900), amplitudes=(1.0, 0.8))])
        self.assert_rejected("点头两次，每次1秒，第二次比第一次重", prediction,
                             "non_binding_constraint_violation")

    def test_no_exact_request_means_no_numeric_repair(self):
        prediction = config([action(durations=(800, 1000))])
        overrides, audit = extract_exact_duration_bindings("点头两次，第二次更慢", prediction)
        self.assertEqual(overrides, {})
        self.assertEqual(audit["bindings"], [])
        self.assert_rejected("点头两次，第二次更慢", config([action(durations=(1000, 800))]),
                             "non_binding_constraint_violation")

    def test_dialogue_and_nonexecution_never_gain_bindings(self):
        prediction = config([action()])
        for text in ("点头一次每次1秒", "版本1.2已上线，余额1200元", "不要点头一次每次1秒"):
            overrides, audit = extract_exact_duration_bindings(text, prediction, input_role="dialogue")
            self.assertEqual(overrides, {})
            self.assertEqual(audit["bindings"], [])
            self.assertFalse(audit["execution_constraints_applicable"])
        for decision in ("none", "unsupported", "ambiguous"):
            prediction = config(decision=decision)
            overrides, audit = extract_exact_duration_bindings("点头一次每次1秒", prediction)
            self.assertEqual(overrides, {})
            self.assertEqual(audit["unchanged_structural_fields"]["decision"], decision)

    def test_non_duration_decimals_never_become_bindings(self):
        audit = self.assert_rejected("版本1.2，点头一次", config([action()]))
        self.assertEqual(audit["bindings"], [])
        self.assertTrue(any(issue["kind"] == "uncovered_explicit_quantity"
                            for issue in audit["constraint_audit"]["unresolved"]))

    def test_invalid_role_is_not_a_bypass(self):
        with self.assertRaises(ValueError):
            extract_exact_duration_bindings("点头一次每次1秒", config([action()]), input_role="unknown")


if __name__ == "__main__":
    unittest.main()
