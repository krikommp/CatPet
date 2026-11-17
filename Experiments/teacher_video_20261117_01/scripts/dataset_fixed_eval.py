"""Freeze new objective-only challenges; no video/persona approval is implied."""
import hashlib
import json
from pathlib import Path

from dataset_constraints import validate_instruction_constraints
from dataset_prepare import RUN, family_key, prescribed_split, write_jsonl


def action(rid, durations, amplitudes=None, hold=.2):
    return {"resource_id":rid, "cycles":[{"duration_ms":d,"controls":{
        "hold_ratio":hold, **({"amplitude_scale":amplitudes[i] if amplitudes else .8} if rid != "blink.full" else {})
    }} for i,d in enumerate(durations)]}


def config(*steps, decision="execute"):
    return {"version":"action-config.v0.2","decision":decision,"steps":[{"actions":s} for s in steps]}


def main():
    cases = []
    def add(text,cfg,focus): cases.append((text,cfg,focus))
    add("请完成摇头一次，完整周期用800毫秒。",config([action("shake_head.basic",[800])]),"exact_duration")
    add("请摇头两次，第一次用0.8秒，第二次用1.2秒。",config([action("shake_head.basic",[800,1200])]),"cycle_duration_binding")
    add("请摇头三次，每次用900毫秒。",config([action("shake_head.basic",[900]*3)]),"count_and_exact_duration")
    add("摇头两次，第二次比前一次更慢。",config([action("shake_head.basic",[800,1400])]),"relative_duration")
    add("摇头两次，第二次幅度更小。",config([action("shake_head.basic",[1000,1000],[1.0,.6])]),"relative_amplitude")
    add("连续摇头三次，幅度越来越大。",config([action("shake_head.basic",[1000]*3,[.5,.8,1.1])]),"gradual_amplitude")
    add("连续摇头三次，节奏越来越快。",config([action("shake_head.basic",[1600,1200,800])]),"gradual_duration")
    add("请四处张望一次，完整周期用1200毫秒。",config([action("look_around.basic",[1200],hold=0)]),"exact_duration")
    add("四处张望两次，第二次比前一次更慢。",config([action("look_around.basic",[1000,1600],hold=0)]),"relative_duration")
    add("先眨眼两次，再点头一次。",config([action("blink.full",[600,600])],[action("nod.basic",[1000])]),"sequence_count")
    add("先眨眼一次，周期用600毫秒，再点头一次，周期用1000毫秒。",config([action("blink.full",[600])],[action("nod.basic",[1000])]),"sequence_numeric_scope_probe")
    add("先眨眼三次，然后点头两次。",config([action("blink.full",[600]*3)],[action("nod.basic",[1000]*2)]),"sequence_count")
    add("同时开始眨眼两次和挥手一次。",config([action("blink.full",[600,600]),action("wave.basic",[1200])]),"parallel_count")
    add("眨眼一次，同时挥手两次。",config([action("blink.full",[800]),action("wave.basic",[1000,1000])]),"parallel_count")
    for text,focus in [
        ("请准确执行摇头四次。","unsupported_count"),
        ("请连续眨眼五次，不要减少次数。","unsupported_count"),
        ("请张嘴打一个哈欠。","unsupported_action"),
        ("先打哈欠，再点头一次。","unsupported_component"),
        ("请眨眼一次，完整周期只用50毫秒。","unsupported_exact_duration"),
        ("请点头一次，完整周期用5秒。","unsupported_exact_duration"),
    ]: add(text,config(decision="unsupported"),focus)
    for text,focus in [
        ("这一轮不要摇头。","negation"),("请别晃脑袋，保持当前姿势。","negation"),
        ("请解释一下这段Python代码。","non_animation_instruction"),("把本轮日志保存到桌面。","non_animation_instruction"),
    ]: add(text,config(decision="none"),focus)
    for text in ["请把刚才那个动作再来一遍。","照上一轮的动作做，但再慢一些。","接着刚才的动作继续吧。","还是那个动作，这次轻一点。"]:
        add(text,config(decision="ambiguous"),"missing_prior_context")
    manifest_path = RUN / "data/family_splits.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    existing = {key:f for f in manifest["families"] for key in f["keys"]}
    frozen_input = [json.loads(x) for x in (RUN/"input/Dataset/ActionCards/llm_v02_corpus.jsonl").read_text(encoding="utf-8").splitlines()]
    source_texts = {r["raw_text"] for r in frozen_input}
    records = []
    for i,(text,cfg,focus) in enumerate(cases,1):
        row = {"raw_text":text,"config":cfg}; key=family_key(row)
        f = existing.get(key)
        if f is None:
            f={"semantic_family_id":"sf-"+hashlib.sha256(key.encode()).hexdigest()[:16],"keys":[key],"split":prescribed_split(key),"source_group_ids":[],"source_rows":0}
            existing[key]=f; manifest["families"].append(f)
        assert f["split"] == "test", (text,key,f)
        assert text not in source_texts, "Challenge text must not repeat frozen source text"
        records.append({"candidate_id":f"objective-eval-{i:03d}","raw_text":text,"config":cfg,
                        "input_role":"instruction","group_id":f["semantic_family_id"],"semantic_family_id":f["semantic_family_id"],
                        "semantic_family_key":key,"split":"test","eval_focus":focus,
                        "source_type":"teacher_objective_challenge","training_eligible":False,
                        "admission_status":"evaluation_only_pending_independent_review",
                        "evaluation_scope":"decision_structure_and_explicit_constraints_only",
                        "metric_exclusions":["unconstrained_parameter_mae","visual_quality","persona_fit"],
                        "provenance":{"reviewer_type":"AI","generation_source":"Codex dataset_audit independent task context",
                                      "generation_prompt_version":"objective-challenge.v1","video_review_status":"not_reviewed",
                                      "persona_sha256":None,"review_rubric_version":None,"baseline_semantic_family_seen":"possible; baseline already trained on historical source families"},
                        "objective_constraint_checks":validate_instruction_constraints(text,cfg)})
    write_jsonl(RUN/"data/fixed_eval.jsonl",records)
    manifest["families"].sort(key=lambda x:x["semantic_family_id"])
    manifest_path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    (RUN/"reports/dataset_fixed_eval.json").write_text(json.dumps({"count":len(records),"sha256":hashlib.sha256((RUN/"data/fixed_eval.jsonl").read_bytes()).hexdigest(),
        "new_texts":True,"new_semantic_families_for_baseline":False,"future_train_family_overlap":0,
        "note":"Objective challenge pool, not a video-reviewed golden set. Fixed before any new experiment trains. Independent review and exact-duration parsing coverage remain explicit.",
        "unresolved_constraint_cases":[r["candidate_id"] for r in records if r["objective_constraint_checks"]["unresolved"]]},ensure_ascii=False,indent=2),encoding="utf-8")
    print(f"Frozen {len(records)} objective-only test challenges")


if __name__ == "__main__": main()
