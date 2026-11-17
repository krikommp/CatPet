"""Targeted objective-constraint, quarantine, source-association and split checks."""
import copy
import hashlib
import json
from pathlib import Path

from dataset_constraints import validate_instruction_constraints
from dataset_fixed_eval import action, config
from dataset_prepare import RUN, norm_text, validate_config


def main():
    results=[]
    def check(name, condition):
        results.append({"name":name,"passed":bool(condition)})
        assert condition, name
    def audit(text,cfg): return validate_instruction_constraints(text,cfg)
    cfg=config([action("blink.full",[600,1200])])
    before=copy.deepcopy(cfg)
    a=audit("眨眼两次，第一次用0.6秒，第二次用1.2秒",cfg)
    check("exact_units_and_cycle_binding",not a["violations"] and len([x for x in a["checks"] if x["kind"]=="exact_duration_ms"])==2)
    check("validator_does_not_rewrite_config",cfg==before)
    wrong=copy.deepcopy(cfg); wrong["steps"][0]["actions"][0]["cycles"].reverse()
    check("swapped_cycle_durations_rejected",len(audit("眨眼两次，第一次用0.6秒，第二次用1.2秒",wrong)["violations"])==2)
    a=audit("眨眼两次，每次600毫秒",config([action("blink.full",[600,600])]))
    check("each_duration_broadcast_only_when_explicit",not a["violations"] and len([x for x in a["checks"] if x["kind"]=="exact_duration_ms"])==2)
    a=audit("眨眼两次，用600毫秒",cfg)
    check("unscoped_number_not_broadcast",bool(a["unresolved"]) and not any(x["kind"]=="exact_duration_ms" for x in a["checks"]))
    check("count_mismatch_rejected",bool(audit("眨眼三次",cfg)["violations"]))
    check("infix_chinese_count",bool(audit("眨三次眼",cfg)["violations"]))
    check("arabic_count",bool(audit("眨眼3次",cfg)["violations"]))
    check("second_slower_pass",not audit("眨眼两次，第二次更慢",cfg)["violations"])
    check("second_slower_fail",bool(audit("眨眼两次，第二次更慢",wrong)["violations"]))
    check("second_faster_pass",not audit("眨眼两次，第二次更快",wrong)["violations"])
    check("equal_relative_values_rejected",bool(audit("摇头两次，第二次更轻",config([action("shake_head.basic",[1000,1000],[.8,.8])]))["violations"]))
    check("strict_gradual_amplitude",bool(audit("摇头三次，幅度越来越大",config([action("shake_head.basic",[1000]*3,[.6,.8,.8])]))["violations"]))
    check("gradual_tempo",not audit("摇头三次，越来越快",config([action("shake_head.basic",[1400,1000,800])]))["violations"])
    a=audit("眨眼一次同时点头一次，第二次慢一点",config([action("blink.full",[600]),action("nod.basic",[1000])]))
    check("multi_action_relative_scope_unresolved",bool(a["unresolved"]))
    check("nonexecute_not_invented_numeric_checks",not audit("点头四次",config(decision="unsupported"))["execution_constraints_applicable"])
    a=audit("眨眼两次，第二次闭眼保持600毫秒",cfg)
    check("hold_duration_not_misread_cycle_duration",bool(a["unresolved"]) and not any(x["kind"]=="exact_duration_ms" for x in a["checks"]))
    a=audit("先快速点头一下，接着慢慢再点一下",config([action("nod.basic",[800,1400])]))
    check("per_clause_one_not_wrong_total_count",not a["violations"] and bool(a["unresolved"]))
    check("no_scope_inference_from_single_predicted_action",bool(audit("第二次用600毫秒",cfg)["unresolved"]))
    check("infix_count_missing_resource_reported",bool(audit("眨两次眼",config([action("nod.basic",[1000,1000])]))["unresolved"]))
    a=audit("眨眼两次，用600毫秒",config([action("blink.full",[600])]))
    check("wrong_predicted_cycle_count_not_used_to_resolve_duration",bool(a["unresolved"]) and not any(x["kind"]=="exact_duration_ms" for x in a["checks"]))
    a=audit("眨眼两次，每次600毫秒",config([action("blink.full",[600])]))
    check("each_explicit_duration_detects_missing_cycle",any(x["kind"]=="exact_duration_ms" and x["cycle_index"]==1 and not x["passed"] for x in a["checks"]))
    check("gradual_relation_cannot_pass_with_one_predicted_cycle",bool(audit("点头三次，越来越慢",config([action("nod.basic",[1000])]))["violations"]))
    check("twelve_not_partial_two",any(x.get("expected")==12 and not x["passed"] for x in audit("点头十二次",config([action("nod.basic",[1000,1000])]))["checks"]))
    check("fractional_count_not_truncated",any(x["kind"]=="fractional_count" for x in audit("点头1.5次",config([action("nod.basic",[1000])]))["violations"]))
    for name,text in (("half_second","眨眼一次，用半秒"),("chinese_decimal","眨眼一次，用零点六秒"),("seconds_suffix","眨眼一次，用一秒钟")):
        a=audit(text,config([action("blink.full",[600])]))
        check(name+"_unresolved_not_false_pass",bool(a["unresolved"]) and not any(x["kind"]=="exact_duration_ms" for x in a["checks"]))
    check("600ms_no_action_context_unresolved",bool(audit("第二次600ms",cfg)["unresolved"]))
    triple=config([action("nod.basic",[700,1200,900],[.5,1.0,.7])])
    a=audit("点头三次，第三次比第一次慢",triple)
    check("explicit_relative_reference_first_not_previous",any(x["kind"]=="relative" and x["reference_cycle_index"]==0 and x["passed"] for x in a["checks"]))
    a=audit("点头三次，第三次比第二次轻",triple)
    check("explicit_relative_amplitude_reference",any(x["kind"]=="relative" and x["reference_cycle_index"]==1 and x["passed"] for x in a["checks"]))
    for ref in ("前一次","上一次"):
        a=audit("点头两次，第二次比"+ref+"更慢",config([action("nod.basic",[700,1200])]))
        check("previous_reference_consumed_"+ref,not a["violations"] and not a["unresolved"] and any(x["kind"]=="relative" for x in a["checks"]))
    a=audit("点头两次，第二次不要比第一次更重",config([action("nod.basic",[1000,1000],[.5,1.0])]))
    check("negated_relative_not_inverted_or_accepted",bool(a["unresolved"]) and not any(x["kind"]=="relative" for x in a["checks"]))
    for name,text in (("amplitude_number","点头两次，第二次幅度为0.5"),("half_amplitude","点头两次，第二次用第一下的一半幅度"),("chinese_hundreds","眨眼一次，持续六百毫秒")):
        check(name+"_fails_closed_unresolved",bool(audit(text,config([action("nod.basic",[1000,1000])]))["unresolved"]))
    bad_multi=config([action("nod.basic",[1000,1000]),action("wave.basic",[600,900])])
    a=audit("点头一次，同时挥手两次，第二次挥手更慢",bad_multi)
    check("unrelated_ordinal_never_waives_first_action_count",any(x["kind"]=="cycle_count" and not x["passed"] for x in a["checks"]))
    a=audit("只点头一次，第二次不要做",config([action("nod.basic",[1000,1000])]))
    check("only_once_not_waived_by_negated_second_cycle",bool(a["violations"]))
    for name,text in (("negative_duration","点头一次，用-0.6秒"),("fractional_ordinal","点头两次，第1.5次用0.6秒"),("zero_ordinal","点头两次，第0次用0.6秒"),("later_invalid_ordinal","点头两次，第1次600ms，第1.5次600ms")):
        a=audit(text,config([action("nod.basic",[600,600])]))
        check(name+"_not_silently_coerced",bool(a["unresolved"]) and not any(x["kind"]=="exact_duration_ms" for x in a["checks"]))
    specs=json.loads((RUN/"input/Docs/ActionLanguage/profiles/yukikaze-resources.v0.2.json").read_text(encoding="utf-8"))["resources"]
    check("positive_short_hold_rejected",any("hold_below" in x for x in validate_config(config([action("blink.full",[600],hold=.05)]),specs)))
    check("zero_hold_preserved",not validate_config(config([action("blink.full",[600],hold=0)]),specs))
    check("look_positive_hold_rejected","missing_hold_phase" in validate_config(config([action("look_around.basic",[1200],hold=.1)]),specs))
    check("look_zero_hold_valid",not validate_config(config([action("look_around.basic",[1200],hold=0)]),specs))
    check("parallel_conflict_rejected","parallel_channel_conflict" in validate_config(config([action("blink.full",[1000]),action("smile.basic",[1000])]),specs))
    rows=[json.loads(x) for x in (RUN/"data/cold_start.jsonl").read_text(encoding="utf-8").splitlines()]
    challenges=[json.loads(x) for x in (RUN/"data/fixed_eval.jsonl").read_text(encoding="utf-8").splitlines()]
    for field in ("group_id","semantic_family_id"):
        owners={}
        for r in rows+challenges: owners.setdefault(r[field],set()).add(r["split"])
        check("zero_cross_split_"+field,all(len(x)==1 for x in owners.values()))
    owners={}
    for r in rows+challenges: owners.setdefault(norm_text(r["raw_text"]),set()).add(r["split"])
    check("zero_cross_split_normalized_text",all(len(x)==1 for x in owners.values()))
    check("no_same_text_param_variants_in_kept_pool",len(rows)==len({norm_text(r['raw_text']) for r in rows}))
    comp={x["row"]:x for x in map(json.loads,(RUN/"reports/compiler_patched_corpus.jsonl").read_text(encoding="utf-8").splitlines())}
    check("all_kept_rows_pass_actual_csharp_patch",all(comp[r["provenance"]["source_line"]]["compile_ok"] for r in rows))
    check("kept_rows_no_claimed_video_review",all(r["provenance"]["video_review_status"]=="not_reviewed" for r in rows))
    check("all_kept_rows_quarantined_from_training",all(not r["training_eligible"] and r["provenance"]["persona_sha256"] is None for r in rows))
    train_families={r["semantic_family_id"] for r in rows if r["split"]=="train"}
    check("fixed_challenge_families_reserved",not train_families&{r["semantic_family_id"] for r in challenges})
    check("fixed_challenges_exclude_unconstrained_parameter_metrics",all("unconstrained_parameter_mae" in r["metric_exclusions"] for r in challenges))
    report={"passed":sum(x["passed"] for x in results),"total":len(results),"checks":results,
            "cold_start_sha256":hashlib.sha256((RUN/"data/cold_start.jsonl").read_bytes()).hexdigest(),
            "fixed_eval_sha256":hashlib.sha256((RUN/"data/fixed_eval.jsonl").read_bytes()).hexdigest(),
            "limits":"Partial grammar validator, not general semantic NLU or perceptual sufficiency test."}
    (RUN/"reports/dataset_verification.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=="__main__": main()
