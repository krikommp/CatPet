"""Reproducible pre-review pool; never claims training-ready before persona/rubric binding.

Reads ONLY the frozen run/input corpus and resources. It does not rewrite labels,
touch the shared corpus, download data, or train. Rerunning produces identical data.
"""
from __future__ import annotations

import collections
import hashlib
import json
import math
import random
import re
import unicodedata
from pathlib import Path

from dataset_constraints import mentioned_resources, validate_instruction_constraints

RUN = Path(__file__).resolve().parents[1]
INPUT = RUN / "input/Dataset/ActionCards/llm_v02_corpus.jsonl"
CATALOG = RUN / "input/Docs/ActionLanguage/profiles/yukikaze-resources.v0.2.json"
SOURCE = RUN / "input/Assets/Scripts/ActionLanguage/ActionResourceCatalog.cs"
COMPILER = RUN / "input/Assets/Scripts/ActionLanguage/ActionConfigCompiler.cs"
OUT = RUN / "data"
POLICY = "objective-preclean.v1"


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def norm_text(text):
    return re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", text)).lower()


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(x, ensure_ascii=False, sort_keys=True) + "\n" for x in rows), encoding="utf-8")


def family_key(row):
    """Conservative known-paraphrase family; all counts and parameter variants merge.

    No semantic-perfect claim: keys are reviewed deterministic heuristics; source
    group and normalized-text connected components are also unioned globally.
    """
    cfg = row["config"]; dec = cfg["decision"]; text = row["raw_text"]
    if dec == "execute":
        topology = ">".join("+".join(sorted(a["resource_id"] for a in s["actions"])) for s in cfg["steps"])
        return "execute:" + topology
    named = mentioned_resources(text)
    if dec == "none":
        if named: return "none:negated:" + "+".join(sorted(named))
        if re.search(r"代码|Python|训练|过拟合|配置|测试|端口|日志|服务|显存|公式|梯度|排序|翻译|总结|润色|写一首", text):
            return "none:non_animation_task"
        if re.search(r"别动|不动|静止|停下来|动作|乱动|安静|表情|取消", text): return "none:static_cancel"
        return "none:social_chat"
    if dec == "ambiguous":
        if re.search(r"刚|上次|之前|前|旧|老样|继续|接着|延续|重复|再来|再做|重新|再放|再加|这次", text):
            return "ambiguous:missing_prior_context"
        if re.search(r"快|慢|轻|重|幅度|节奏|久|调整|参数|用力|明显|夸张|收敛|保持|停顿|定格|微调", text):
            return "ambiguous:missing_target_for_parameter"
        return "ambiguous:unspecified_action"
    if "哈欠" in text: return "unsupported:yawn"
    if re.search(r"单眼|wink|媚眼", text, re.I): return "unsupported:single_eye"
    if re.search(r"[四五六七八九十456789][次下遍]|眨[四五六七八九十456789][次下遍]眼|歪[四五六七八九十456789]下", text):
        return "unsupported:count_exceeds_three"
    if re.search(r"秒|毫秒", text): return "unsupported:explicit_duration_out_of_bounds"
    if len(named) >= 3: return "unsupported:too_many_actions"
    if len(named) >= 2: return "unsupported:resource_channel_conflict"
    if re.search(r"哭|泪", text): return "unsupported:tears"
    if re.search(r"舞|转|跳|蹦|跑|走|迈|退|踏|跟头|空翻|蹲|坐|躺|捡", text):
        return "unsupported:whole_body_locomotion"
    if re.search(r"唱|说话|口哨|吹|吐舌|鬼脸|亲亲", text): return "unsupported:unavailable_face_voice"
    return "unsupported:unavailable_hands_props"


def prescribed_split(key):
    test = {
        "execute:shake_head.basic", "execute:look_around.basic",
        "execute:blink.full>nod.basic", "execute:blink.full+wave.basic",
        "none:negated:shake_head.basic", "none:non_animation_task",
        "unsupported:yawn", "unsupported:count_exceeds_three",
        "unsupported:explicit_duration_out_of_bounds", "ambiguous:missing_prior_context",
    }
    val = {"execute:bow.basic", "execute:smile.basic>wave.basic",
           "none:negated:bow.basic", "unsupported:single_eye", "ambiguous:unspecified_action"}
    if key in test: return "test"
    if key in val: return "val"
    # Additional independent pair topologies only; all remaining singles stay train.
    if key.startswith("execute:") and (">" in key or "+" in key):
        k = int(hashlib.sha256(("frozen-family-v1|" + key).encode()).hexdigest()[:8], 16) % 10
        return "test" if k == 0 else "val" if k == 1 else "train"
    return "train"


def validate_config(cfg, specs):
    issues = []
    if set(cfg) != {"version", "decision", "steps"}: issues.append("unknown_or_missing_config_field")
    if cfg.get("version") != "action-config.v0.2": issues.append("wrong_version")
    if cfg.get("decision") not in ("execute", "none", "unsupported", "ambiguous"):
        return issues + ["invalid_decision"]
    steps = cfg.get("steps")
    if not isinstance(steps, list): return issues + ["steps_not_list"]
    if cfg["decision"] != "execute": return issues + (["nonexec_has_actions"] if steps else [])
    if not 1 <= len(steps) <= 2: issues.append("step_count")
    count = 0; total_ms = 0; channels_all = set(); native_times = set()
    for step in steps:
        if set(step) != {"actions"}: issues.append("unknown_or_missing_step_field")
        used = set(); durations = []
        for a in step.get("actions", []):
            count += 1
            if set(a) != {"resource_id", "cycles"}: issues.append("unknown_or_missing_action_field")
            rid = a.get("resource_id")
            if rid not in specs: issues.append("unknown_resource"); continue
            s = specs[rid]; channels = set(s["channels"])
            if channels & used: issues.append("parallel_channel_conflict")
            used |= channels; channels_all |= channels
            cycles = a.get("cycles", [])
            if not 1 <= len(cycles) <= 3: issues.append("cycle_count")
            cyc_start = total_ms
            for c in cycles:
                if set(c) != {"duration_ms", "controls"}: issues.append("unknown_or_missing_cycle_field")
                d = c.get("duration_ms"); ctrls = c.get("controls", {})
                if type(d) is not int or not s["duration_ms"][0] <= d <= s["duration_ms"][1]:
                    issues.append("duration_range_or_type"); continue
                fields = {"hold_ratio"} | ({"amplitude_scale"} if s["supports_amplitude_scale"] else set())
                if set(ctrls) != fields: issues.append("control_fields")
                for f in fields:
                    v = ctrls.get(f)
                    if type(v) not in (int, float) or not math.isfinite(v) or not s[f][0] <= v <= s[f][1]:
                        issues.append(f + "_range_or_type")
                hold = ctrls.get("hold_ratio")
                if not isinstance(hold, (int, float)): continue
                hold_ms = d * hold; move_ms = d - hold_ms
                alpha = 0.4 if rid == "surprise.basic" else 0.5
                enter_ms = move_ms * alpha; ret_ms = move_ms * (1 - alpha)
                if 0 < hold_ms < 80: issues.append("positive_hold_below_80ms_silently_changed_by_original_compiler")
                if move_ms < 160: issues.append("insufficient_move_time_silently_changed_by_original_compiler")
                if rid == "look_around.basic" and hold > 0: issues.append("missing_hold_phase")
                # Rounded endpoint gap, not merely duration*ratio, controls final native legality.
                offsets = [enter_ms, enter_ms + hold_ms, d] if hold > 0 else [enter_ms, d]
                if rid in ("shake_head.basic", "look_around.basic"): offsets.insert(0, enter_ms / 2)
                rounded = sorted(set(int(math.floor(t + 0.5)) for t in offsets))
                if any(b - a < 80 for a, b in zip([0] + rounded, rounded)):
                    issues.append("native_parameter_segment_below_80ms")
                native_times.update(cyc_start + t for t in rounded)
                cyc_start += d
            durations.append(cyc_start - total_ms)
        total_ms += max(durations, default=0)
    if not 1 <= count <= 2: issues.append("action_count")
    if total_ms > 10000: issues.append("total_duration_exceeds_10s")
    if len(channels_all) > 16: issues.append("channel_count_exceeds_16")
    if len(native_times) > 32: issues.append("keyframe_count_exceeds_32")
    return sorted(set(issues))


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    rows = [json.loads(x) for x in INPUT.read_text(encoding="utf-8").splitlines() if x.strip()]
    specs = json.loads(CATALOG.read_text(encoding="utf-8"))["resources"]
    compiler_report_path = RUN / "reports/compiler_patched_corpus.jsonl"
    compiler_results = {x["row"]:x for x in (json.loads(line) for line in compiler_report_path.read_text(encoding="utf-8").splitlines() if line.strip())}
    assert len(compiler_results) == len(rows), "Compiler report must cover the exact frozen corpus"
    for i, row in enumerate(rows, 1):
        assert compiler_results[i]["raw_text"] == row["raw_text"] and compiler_results[i]["group_id"] == row["group_id"], "Compiler report row association mismatch"
    hashes = {"source_sha256":sha(INPUT), "resource_catalog_sha256":sha(CATALOG), "resource_implementation_sha256":sha(SOURCE),
              "original_compiler_snapshot_sha256":sha(COMPILER),
              "compiler_snapshot_sha256":sha(RUN/"source/csharp/ActionConfigCompiler.cs"),
              "patched_csharp_compile_report_sha256":sha(compiler_report_path)}
    excluded = []; kept = []; constraint_summary = collections.Counter()
    group_params = collections.defaultdict(set)
    for row in rows: group_params[norm_text(row["raw_text"])].add(json.dumps(row["config"], sort_keys=True))
    duplicate_variants = {k for k, v in group_params.items() if len(v) > 1}

    # Union known semantic family, source group and same normalized text BEFORE
    # filtering: excluded relatives cannot hide a cross-split ancestry link.
    parent = list(range(len(rows)))
    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    def union(a, b): parent[find(a)] = find(b)
    seen = {}
    for i, row in enumerate(rows):
        for key in ("family|" + family_key(row), "source|" + row["group_id"], "text|" + norm_text(row["raw_text"])):
            if key in seen: union(i, seen[key])
            else: seen[key] = i
    components = collections.defaultdict(list)
    for i in range(len(rows)): components[find(i)].append(i)
    family_by_index = {}; split_by_index = {}; split_manifest = []
    for indexes in components.values():
        keys = sorted({family_key(rows[i]) for i in indexes})
        fid = "sf-" + hashlib.sha256("|".join(keys).encode()).hexdigest()[:16]
        proposals = {prescribed_split(k) for k in keys}
        split = "test" if "test" in proposals else "val" if "val" in proposals else "train"
        split_manifest.append({"semantic_family_id": fid, "keys": keys, "split": split,
                               "source_group_ids": sorted({rows[i]["group_id"] for i in indexes}),
                               "source_rows": len(indexes)})
        for i in indexes: family_by_index[i] = fid; split_by_index[i] = split

    seen_text = set()
    for i, row in enumerate(rows):
        reasons = []
        g = row["group_id"]; text = row["raw_text"]; cfg = row["config"]
        if not re.match(r"llm-(single-|bare-|percycle-|seq-|par-|nonexec-)", g):
            reasons.append("dialogue_roleplay_or_unclassified_input_role")
        if re.search(r"哈欠", text) and cfg["decision"] == "execute": reasons.append("unsupported_action_silently_approximated")
        if cfg["decision"] == "ambiguous" and re.search(r"可爱|卖.*萌|开心|元气|停一下|保持住|别动太快", text):
            reasons.append("ambiguous_semantics_needs_persona_or_context_policy")
        reasons += validate_config(cfg, specs)
        if not compiler_results[i+1]["compile_ok"]:
            reasons.append("patched_csharp:" + compiler_results[i+1]["error"])
        checks = validate_instruction_constraints(text, cfg)
        if checks["violations"]: reasons.append("explicit_count_or_relative_constraint_mismatch")
        if checks["unresolved"]: reasons.append("explicit_numeric_scope_unresolved")
        constraint_summary["checked_constraints"] += len(checks["checks"])
        constraint_summary["violations"] += len(checks["violations"])
        constraint_summary["unresolved"] += len(checks["unresolved"])
        norm = norm_text(text)
        if norm in duplicate_variants: reasons.append("same_text_different_continuous_labels_pending_adjudication")
        elif norm in seen_text: reasons.append("duplicate_normalized_text")
        if reasons:
            excluded.append({"source_line": i + 1, "raw_text": text, "source_group_id": g,
                             "semantic_family_id": family_by_index[i], "split": split_by_index[i],
                             "reasons": sorted(set(reasons)), "constraint_checks": checks})
            continue
        seen_text.add(norm)
        kept.append({
            "raw_text": text, "group_id": family_by_index[i], "semantic_family_id": family_by_index[i],
            "semantic_family_key": family_key(row), "input_role": "instruction", "split": split_by_index[i],
            "config": cfg, "source_type": "historical_synthetic", "source": "cold_start_synthetic_unreviewed",
            "admission_status": "pending_persona", "training_eligible": False,
            "provenance": {"source_file": str(INPUT.relative_to(RUN)), **hashes,
                           "source_line": i + 1, "source_group_id": g,
                           "original_generation_source": row.get("source", "historical_generator_unspecified"),
                           "video_review_status": "not_reviewed", "persona_sha256": None,
                           "label_policy_review_rubric_version": None, "objective_preclean_policy": POLICY,
                           "compile_verified_in_unity": False, "compiled_with_isolated_csharp_patch": True,
                           "compile_report_row": i+1,
                           "resource_status": "experimental_candidate_except_blink"},
            "objective_constraint_checks": checks,
        })
    write_jsonl(OUT / "cold_start.jsonl", kept)
    write_jsonl(OUT / "quarantined.jsonl", excluded)
    split_manifest.sort(key=lambda x: x["semantic_family_id"])
    (OUT / "family_splits.json").write_text(json.dumps({"policy": "conservative-topology-union.v1", "immutable_for_this_round": True,
        "precedence": "test > val > train across merged source ancestry", "families": split_manifest}, ensure_ascii=False, indent=2), encoding="utf-8")
    split_counts = collections.Counter(r["split"] for r in kept)
    reasons = collections.Counter(x for r in excluded for x in r["reasons"])
    # Reproduce the baseline trainer's original group shuffle to audit known leakage.
    buckets = collections.defaultdict(lambda:collections.defaultdict(list))
    for row in rows: buckets[row["config"]["decision"]][row["group_id"]].append(row)
    rng = random.Random(1337); old_splits = {k:[] for k in ("train", "val", "test")}
    for dec in ("execute", "none", "unsupported", "ambiguous"):
        groups = buckets[dec]; keys = sorted(groups); rng.shuffle(keys); n = len(keys)
        nv = max(1, int(round(n*.1))); nt = max(1, int(round(n*.1))); ntr = max(1, n - nv - nt)
        for split, selected in (("train",keys[:ntr]),("val",keys[ntr:ntr+nv]),("test",keys[ntr+nv:])):
            for key in selected: old_splits[split].extend(groups[key])
    old_text = {s:{x["raw_text"] for x in rr} for s,rr in old_splits.items()}
    old_overlap = {a+"/"+b:len(old_text[a]&old_text[b]) for a,b in (("train","test"),("train","val"),("val","test"))}
    # Count structural differences separately from continuous-label variants.
    def sig(cfg):
        return (cfg["decision"],tuple(tuple(sorted((a["resource_id"],len(a["cycles"])) for a in s["actions"])) for s in cfg["steps"]))
    sigs = collections.defaultdict(set)
    for r in rows: sigs[r["raw_text"]].add(sig(r["config"]))
    report = {"input_sha256": sha(INPUT), "input_rows": len(rows), "unique_raw_text": len({r['raw_text'] for r in rows}),
              "source_group_count": len({r['group_id'] for r in rows}), "kept_prereview": len(kept),
              "quarantined": len(excluded), "split_counts": dict(split_counts), "rejection_reason_counts": dict(reasons),
              "kept_decisions_by_split": {s:dict(collections.Counter(r["config"]["decision"] for r in kept if r["split"]==s)) for s in ("train","val","test")},
              "semantic_components": len(split_manifest), "constraint_summary":dict(constraint_summary),
              "same_text_continuous_variant_sets_quarantined": len(duplicate_variants),
              "duplicate_raw_text_structural_conflict_sets":sum(len(x)>1 for x in sigs.values()),
              "original_split_counts_reproduced":{s:len(rr) for s,rr in old_splits.items()}, "original_split_exact_text_overlap":old_overlap,
              "csharp_patch_compile_report_sha256":hashes["patched_csharp_compile_report_sha256"],
              "train_missing_decision_classes":sorted(set(("execute","none","unsupported","ambiguous"))-{r["config"]["decision"] for r in kept if r["split"]=="train"}),
              "training_ready": False,
              "blocking_dependency": "Persona now observed; label-policy/rubric review, independent visual evidence and missing training class must be resolved before admission",
              "persona_observed_sha256":sha(OUT/"persona_observed.md") if (OUT/"persona_observed.md").exists() else None,
              "persona_observed_does_not_approve_existing_labels":True,
              "limits": ["No historical video review evidence manufactured.", "Isolated C# compiler checks do not replace Unity playback or resource visual calibration.",
                         "Conservative semantic family heuristics are not a proof of all paraphrase equivalence.", "Current baseline trained on historical rows; this split is only independent for future experiments.",
                         "All non-blink resources remain experimental candidates; no formal calibration claimed."]}
    (RUN / "reports/dataset_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
