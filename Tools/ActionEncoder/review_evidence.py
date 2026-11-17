"""Validate supplied review evidence and freeze an experimental data snapshot.

Stages remain separate: prepare candidates -> review -> export/freeze -> train ->
evaluate. This module neither asks for human keep, invents AI acceptance, trains,
nor marks a model ready. It checks evidence integrity/completion, not whether an
AI's subjective judgement is true.

Input JSONL rows have raw_text/config/input_role/group_id/semantic_family_id/split,
candidate_id/parent_candidate_id/source_type and explicit provenance. Supported
source_type: historical_synthetic, ai_video_reviewed, ai_semantic_reviewed.

AI rows also supply generation={provider,model,context_id,prompt_version}, review=
{reviewer_type:'AI',provider,model,context_id,prompt_version,status:'accepted',
 rubric_version,reviewed_at,semantic_match:true,scores:{semantic:1,naturalness:...},
 candidate_id,parent_candidate_id,input_role,raw_text_sha256,
 rationale,config_sha256,persona_sha256,compiler_sha256,resource_sha256,
 native_profile_sha256}. Independent contexts are mandatory; another model is
optional. Video rows additionally bind review.evidence_sha256/video_sha256 and
observation={method:'native_video'|'timestamped_frames_and_trajectory',
 full_clip_observed:true,limitations:[],artifact_paths:[...]}, plus evidence_path
pointing at PreviewSession's completed preview-evidence.v1 sidecar. Semantic AI
rows are non-execute and need no empty video.

Historical rows supply provenance.source_file/source_sha256/source_line,
persona_sha256/label_policy_review_rubric_version and compile_evidence_path for
execute. The latter is a compile-evidence.v1 JSON object containing compile_ok,
config_sha256,raw_text_sha256 and compiler/resource/native_profile SHA256 bindings.
No visual acceptance may be claimed by this source type.

Every row must already have an explicit split. original_split/source_split and
parents cannot move held-out data into train. Export copies all evidence artifacts
and the original records into a new directory and binds their content hashes.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

SNAPSHOT_VERSION = "action-training-snapshot.v1"
SOURCE_TYPES = {"historical_synthetic", "ai_video_reviewed", "ai_semantic_reviewed"}


class EvidenceError(ValueError):
    pass


def canonical_json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def canonical_hash(value):
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def text_hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""): h.update(chunk)
    return h.hexdigest()


def strict_json(text):
    def unique(pairs):
        result = {}
        for k, v in pairs:
            if k in result: raise EvidenceError(f"duplicate JSON key: {k}")
            result[k] = v
        return result
    try:
        return json.loads(text, object_pairs_hook=unique,
                          parse_constant=lambda x: (_ for _ in ()).throw(EvidenceError(f"non-finite JSON: {x}")))
    except (ValueError, TypeError) as e: raise EvidenceError(str(e)) from e


def require(ok, message):
    if not ok: raise EvidenceError(message)


def nonempty(value, name):
    require(isinstance(value, str) and bool(value.strip()), f"missing {name}")
    return value


def sha_value(value, name):
    require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None, f"invalid {name}")
    return value


def utc_time(value, name):
    try:
        parsed = dt.datetime.fromisoformat(nonempty(value, name).replace("Z", "+00:00"))
        require(parsed.tzinfo is not None, f"{name} must include timezone")
        return parsed
    except ValueError as e: raise EvidenceError(f"invalid {name}") from e


class ArtifactResolver:
    def __init__(self, mapping=None):
        self.mapping = mapping
        self.seen = {}

    def resolve(self, path, base):
        original = Path(nonempty(str(path) if isinstance(path, Path) else path, "artifact path"))
        if not original.is_absolute(): original = Path(base) / original
        original = original.resolve()
        key = str(original)
        if self.mapping is None: actual = original
        else:
            require(key in self.mapping, f"artifact not bound in snapshot: {original}")
            actual = self.mapping[key]
        require(actual.is_file(), f"artifact missing: {original}")
        digest = file_hash(actual)
        self.seen[key] = {"source_path": key, "sha256": digest, "bytes": actual.stat().st_size, "actual": actual}
        return original, actual

    def json(self, path, base):
        original, actual = self.resolve(path, base)
        return strict_json(actual.read_text(encoding="utf-8-sig")), original


def split_assignments_sha256(rows):
    assignments = {(r["group_id"], r["semantic_family_id"], r["split"]) for r in rows}
    return canonical_hash([{"group_id": g, "semantic_family_id": f, "split": s} for g, f, s in sorted(assignments)])


def _validate_splits(rows):
    owners = {"group_id": {}, "semantic_family_id": {}, "text": {}, "candidate_id": {}}
    by_candidate = {}
    for row in rows:
        require(isinstance(row,dict),"record must be an object")
        nonempty(row.get("raw_text"),"raw_text")
        split = row.get("split")
        require(split in {"train", "val", "test"}, "explicit train/val/test split required before export")
        for key in ("group_id", "semantic_family_id", "candidate_id"):
            nonempty(row.get(key), key)
        for key in ("original_split", "source_split"):
            old = row.get("provenance", {}).get(key)
            require(old is None or old == split, f"{key} cannot be reassigned during export")
        norm = re.sub(r"[\W_]+", "", unicodedata.normalize("NFKC", row["raw_text"])).lower()
        for key, value in (("group_id", row["group_id"]), ("semantic_family_id", row["semantic_family_id"]),
                           ("text", norm), ("candidate_id", row["candidate_id"])):
            require(value not in owners[key] or owners[key][value] == split, f"cross-split {key}: {value}")
            owners[key][value] = split
        require(row["candidate_id"] not in by_candidate, "duplicate candidate_id")
        by_candidate[row["candidate_id"]] = row
    for row in rows:
        parent = row.get("parent_candidate_id")
        require(parent != row["candidate_id"], "candidate cannot parent itself")
        if parent:
            if parent in by_candidate:
                p = by_candidate[parent]
                require(p["split"] == row["split"] and p["semantic_family_id"] == row["semantic_family_id"], "parent/child family or split changed")
            else:
                provenance = row.get("provenance", {})
                require(provenance.get("parent_split") == row["split"] and provenance.get("parent_semantic_family_id") == row["semantic_family_id"], "external parent needs frozen family/split binding")


def find_ffmpeg(explicit=None):
    if explicit:
        path = Path(explicit).resolve()
        require(path.is_file(), f"ffmpeg not found: {path}")
        return path
    path = shutil.which("ffmpeg")
    if path: return Path(path).resolve()
    try:
        import imageio_ffmpeg
        return Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
    except ImportError as e: raise EvidenceError("Full video decode needs --ffmpeg or installed imageio_ffmpeg; no evidence is fabricated") from e


def decode_video(path, ffmpeg_path):
    """Decode every video frame. A metadata probe or file existence is insufficient."""
    before = file_hash(path)
    proc = subprocess.run([str(ffmpeg_path), "-nostdin", "-hide_banner", "-v", "error", "-xerror",
                           "-err_detect", "explode", "-i", str(path), "-map", "0:v:0", "-vsync", "0",
                           "-progress", "pipe:1", "-nostats", "-f", "null", "-"],
                          capture_output=True, text=True, timeout=120)
    progress = dict(re.findall(r"^(\w+)=(.*)$", proc.stdout, re.M))
    require(proc.returncode == 0 and progress.get("progress") == "end", "video complete decode failed: " + proc.stderr[:240])
    require(not proc.stderr.strip(), "video decoder reported errors: " + proc.stderr[:240])
    require(file_hash(path) == before, "video changed during decode")
    frames = int(progress.get("frame", 0)); duration = int(progress.get("out_time_us", 0)) / 1000
    require(frames > 1 and duration > 0, "video has no complete multi-frame sequence")
    return {"decoded_frames": frames, "decoded_duration_ms": duration, "video_sha256": before, "full_decode": True}


def _schema_check(config):
    # The shared schema is the semantic/parameter source; do not create a second decoder.
    from action_config_schema import validate_training_config
    validate_training_config(config)


def _bindings(compiler_file, resource_file, native_profile_file, persona_file, resolver, base):
    result = {}
    for name, p in (("compiler_sha256",compiler_file),("resource_sha256",resource_file),
                    ("native_profile_sha256",native_profile_file),("persona_sha256",persona_file)):
        _, actual = resolver.resolve(p, base)
        require(actual.stat().st_size > 0, f"empty binding file: {name}")
        result[name] = file_hash(actual)
    return result


def _check_bound(obj, expected, prefix):
    for key, value in expected.items():
        require(obj.get(key) == value, f"{prefix} {key} mismatch or missing")


def _validate_capture(row, resolver, base, expected, ffmpeg_path):
    evidence, original = resolver.json(row.get("evidence_path"), base)
    sidecar_hash = resolver.seen[str(original)]["sha256"]
    require(evidence.get("schema_version") == "preview-evidence.v1", "missing preview-evidence.v1 sidecar")
    for key in ("candidate_id", "parent_candidate_id", "input_role"):
        require(evidence.get(key, "") == row.get(key, ""), f"sidecar {key} mismatch")
    require(evidence.get("compile_ok") is True, "sidecar compilation not successful")
    require(evidence.get("playback_completed") is True and evidence.get("encoder_closed") is True, "playback/encoder completion not proven")
    require(not evidence.get("capture_error"), "sidecar records capture error")
    require(evidence.get("source_hashes_unchanged") is True and evidence.get("asset_hashes_unchanged") is True, "capture resource/source stability not proven")
    start = utc_time(evidence.get("started_utc"), "started_utc")
    end = utc_time(evidence.get("completed_utc"), "completed_utc")
    require(end >= start, "capture timestamps reversed")
    require(evidence.get("raw_text_sha256") == text_hash(row["raw_text"]), "sidecar raw_text binding mismatch")
    plan_json = nonempty(evidence.get("config_json"), "sidecar config_json")
    require(evidence.get("config_hash_encoding") == "exact_utf8_plan_json", "unknown sidecar config hash encoding")
    require(evidence.get("config_sha256") == text_hash(plan_json), "sidecar exact config hash mismatch")
    require(canonical_hash(strict_json(plan_json)) == canonical_hash(row["config"]), "training config differs from actually played config")
    native_json = nonempty(evidence.get("native_json"), "native_json")
    require(evidence.get("native_sha256") == text_hash(native_json), "native packet hash mismatch")
    native = strict_json(native_json); duration = native.get("duration_ms")
    require(type(duration) is int and duration > 0, "invalid native duration")
    require(evidence.get("native_duration_ms") == duration, "native duration binding mismatch")
    require(evidence.get("resource_catalog_sha256") == expected["resource_sha256"], "sidecar resource hash mismatch")
    require(evidence.get("compiler_sha256") == expected["compiler_sha256"], "sidecar compiler hash mismatch")
    require(evidence.get("profile_sha256") == expected["native_profile_sha256"], "sidecar native profile mismatch")
    require(evidence.get("persona_sha256") == expected["persona_sha256"], "sidecar persona mismatch")
    for key in ("compiled_assembly_sha256", "character_asset_sha256"):
        sha_value(evidence.get(key), key)
    for key in ("resource_catalog_version", "parameter_schema_version"):
        nonempty(evidence.get(key), key)
    require(evidence["parameter_schema_version"] == row["config"]["version"], "parameter schema version mismatch")
    _, video = resolver.resolve(evidence.get("video_file", "preview.mp4"), original.parent)
    require(file_hash(video) == evidence.get("video_sha256"), "video hash association mismatch")
    decoded = decode_video(video, ffmpeg_path)
    frames = evidence.get("frame_count"); fps = evidence.get("fps")
    require(type(frames) is int and frames == decoded["decoded_frames"], "captured/decoded frame count mismatch")
    require(type(fps) in (int, float) and math.isfinite(fps) and fps > 0, "invalid capture fps")
    require(abs(decoded["decoded_duration_ms"] - frames * 1000 / fps) <= max(2.0, 1000 / fps), "decoded duration disagrees with captured frames/fps")
    _, trajectory_path = resolver.resolve(evidence.get("trajectory_file", "trajectory.jsonl"), original.parent)
    require(file_hash(trajectory_path) == evidence.get("trajectory_sha256"), "trajectory hash mismatch")
    trajectory = [strict_json(x) for x in trajectory_path.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    require(len(trajectory) == frames, "trajectory/frame count mismatch")
    last_player = -math.inf
    for index, frame in enumerate(trajectory):
        require(frame.get("frame_index") == index, "trajectory frame indexes not contiguous")
        t = frame.get("video_time_ms"); player = frame.get("player_time_ms")
        require(type(t) in (int,float) and math.isfinite(t) and abs(t-index*1000/fps) <= 2, "trajectory video timestamp mismatch")
        require(type(player) in (int,float) and math.isfinite(player) and player >= last_player, "invalid or reversed player time")
        if index == 0:
            require(0 <= player <= 1000/fps + 2, "trajectory misses start of playback")
        else:
            require(player-last_player <= 1000/fps + 2, "trajectory skips playback intervals")
        last_player = player
        parameters = frame.get("parameters")
        require(isinstance(parameters,list) and bool(parameters), "missing actual parameter trajectory")
        for param in parameters:
            nonempty(param.get("id"), "parameter id")
            value = param.get("value")
            require(type(value) in (int,float) and math.isfinite(value), "invalid actual parameter value")
    require(last_player >= duration and evidence.get("last_player_time_ms", -1) >= duration, "trajectory does not cover native playback completion")
    return {**decoded, "evidence_sha256": sidecar_hash, "trajectory_sha256": evidence["trajectory_sha256"],
            "native_sha256": evidence["native_sha256"], "native_duration_ms":duration,
            "first_player_time_ms":trajectory[0]["player_time_ms"], "last_player_time_ms":last_player,
            "capture_completed_utc":evidence["completed_utc"], "fps":fps,
            "resource_status": "candidate_except_blink; no formal calibration asserted"}


def _validate_video(row, review, resolver, base, expected, ffmpeg_path):
    captured = _validate_capture(row,resolver,base,expected,ffmpeg_path)
    require(utc_time(review.get("reviewed_at"), "reviewed_at") >= utc_time(captured["capture_completed_utc"],"completed_utc"), "review predates complete recording")
    require(review.get("video_sha256") == captured["video_sha256"], "review video hash association mismatch")
    require(review.get("evidence_sha256") == captured["evidence_sha256"], "review not bound to final sidecar")
    observation = review.get("observation", {})
    require(observation.get("method") in {"native_video", "timestamped_frames_and_trajectory"}, "AI review needs actual video/frame observation method")
    require(observation.get("full_clip_observed") is True, "AI did not declare whole-clip observation")
    require(observation.get("limitations") == [], "unresolved visual limitations cannot be accepted")
    paths = observation.get("artifact_paths")
    require(isinstance(paths,list) and bool(paths), "missing review observation artifacts")
    for path in paths: resolver.resolve(path, base)
    return captured


def validate_capture_only(evidence_path, *, persona_file, compiler_file, resource_file, native_profile_file,
                          ffmpeg_path=None, metadata_path=None):
    """Verify physical recording evidence without constructing an AI review/acceptance.

    This intentionally returns training_eligible=False even when every mechanical
    check passes. It does not observe visual semantics or score naturalness.
    """
    resolver=ArtifactResolver();evidence_path=Path(evidence_path).resolve()
    metadata_path=Path(metadata_path).resolve() if metadata_path else evidence_path.parent/"meta.json"
    meta,_=resolver.json(metadata_path,Path.cwd())
    config=strict_json(nonempty(meta.get("plan_json"),"metadata plan_json"))
    _schema_check(config)
    require(config["decision"]=="execute","capture-only validator requires an execution recording")
    row={"candidate_id":meta.get("candidate_id"),"parent_candidate_id":meta.get("parent_candidate_id", ""),
         "input_role":meta.get("input_role"),"raw_text":meta.get("raw_text"),"config":config,"evidence_path":str(evidence_path)}
    nonempty(row["raw_text"],"metadata raw_text")
    expected=_bindings(compiler_file,resource_file,native_profile_file,persona_file,resolver,Path.cwd())
    ffmpeg=find_ffmpeg(ffmpeg_path)
    captured=_validate_capture(row,resolver,evidence_path.parent,expected,ffmpeg)
    return {"stage":"capture_evidence_validation","valid":True,"candidate_id":row["candidate_id"],
            "training_eligible":False,"ai_reviewed":False,"release_approved":False,
            "config_sha256":canonical_hash(config),"bindings":expected,"ffmpeg_sha256":file_hash(ffmpeg),**captured,
            "artifacts":[{k:v for k,v in x.items() if k!="actual"} for x in resolver.seen.values()]}


def validate_record(row, resolver, base, expected, rubric_version, ffmpeg_path=None):
    require(isinstance(row,dict), "record must be an object")
    nonempty(row.get("raw_text"), "raw_text")
    require(row.get("input_role") in {"instruction", "dialogue"}, "explicit instruction/dialogue role required")
    require(row.get("source_type") in SOURCE_TYPES, "unsupported/missing source_type; historical data is not AI-video evidence")
    require("parent_candidate_id" in row and isinstance(row["parent_candidate_id"],str), "explicit parent_candidate_id required (empty for root)")
    _schema_check(row.get("config"))
    provenance = row.get("provenance")
    require(isinstance(provenance,dict), "explicit provenance required")
    require(not str(row.get("admission_status", "")).startswith(("pending", "quarantined", "rejected")), "explicit pending/rejected admission cannot be promoted by export")
    if row.get("split") == "train":
        require(row.get("training_eligible") is not False, "explicit training_eligible=false cannot be silently overridden")
    execute = row["config"]["decision"] == "execute"
    result = dict(row)
    if row["source_type"] == "historical_synthetic":
        require(not row.get("review") and not row.get("evidence_path"), "historical synthetic cannot claim AI/video acceptance")
        require(provenance.get("video_review_status") in {None, "not_reviewed"}, "historical source cannot claim visual review")
        require(provenance.get("persona_sha256") == expected["persona_sha256"] and provenance.get("label_policy_review_rubric_version") == rubric_version,
                "historical labels need actual persona/policy review binding, not human keep")
        require(provenance.get("label_policy_review_status") == "accepted", "historical label-policy review is still pending")
        nonempty(provenance.get("label_policy_review_source"), "historical label-policy review source")
        source, actual = resolver.resolve(provenance.get("source_file"), base)
        require(file_hash(actual) == provenance.get("source_sha256"), "historical source hash mismatch")
        lines = [strict_json(x) for x in actual.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
        line = provenance.get("source_line")
        require(type(line) is int and 1 <= line <= len(lines), "invalid historical source row")
        original = lines[line-1]
        require(original.get("raw_text") == row["raw_text"] and canonical_hash(original.get("config")) == canonical_hash(row["config"]), "historical label differs from bound source row")
        for key in ("split", "semantic_family_id", "input_role"):
            if key in original:
                require(original[key] == row.get(key), f"historical source {key} cannot be reassigned during export")
        if execute:
            compile_ev, _ = resolver.json(provenance.get("compile_evidence_path"), base)
            require(compile_ev.get("schema_version") == "compile-evidence.v1" and compile_ev.get("compile_ok") is True, "historical execution needs successful bound compile evidence")
            _check_bound(compile_ev, {k:v for k,v in expected.items() if k!="persona_sha256"}, "compile evidence")
            require(compile_ev.get("config_sha256") == canonical_hash(row["config"]) and compile_ev.get("raw_text_sha256") == text_hash(row["raw_text"]), "compile evidence text/config association mismatch")
        result["provenance"] = {**provenance, "video_review_status":"not_reviewed", "config_sha256":canonical_hash(row["config"])}
    else:
        generation = row.get("generation", {}); review = row.get("review", {})
        for obj, label in ((generation,"generation"),(review,"review")):
            for key in ("provider","model","context_id","prompt_version"): nonempty(obj.get(key), label+"."+key)
        require(review.get("reviewer_type") == "AI" and review.get("status") == "accepted" and review.get("semantic_match") is True, "accepted independent AI semantic review required; no human keep gate")
        require(generation["context_id"] != review["context_id"], "generation/review must use independent contexts")
        require(review.get("rubric_version") == rubric_version, "AI review rubric mismatch")
        for key in ("candidate_id","parent_candidate_id","input_role"):
            require(review.get(key) == row.get(key), f"AI review {key} association mismatch")
        require(review.get("raw_text_sha256") == text_hash(row["raw_text"]), "AI review raw_text association mismatch")
        utc_time(review.get("reviewed_at"),"reviewed_at")
        _check_bound(review,expected,"AI review")
        require(review.get("config_sha256") == canonical_hash(row["config"]), "AI review config hash mismatch")
        nonempty(review.get("rationale"),"review rationale")
        scores=review.get("scores")
        require(isinstance(scores,dict) and "semantic" in scores, "review needs explicit normalized scores")
        for value in scores.values(): require(type(value) in (int,float) and math.isfinite(value) and 0<=value<=1, "review scores must be normalized 0..1")
        require(scores["semantic"] == 1, "accepted semantic score must be 1")
        if row["source_type"] == "ai_video_reviewed":
            require(execute, "non-execute uses semantic review, without empty video")
            require("naturalness" in scores,"video review needs naturalness score")
            video_result = _validate_video(row,review,resolver,base,expected,ffmpeg_path)
        else:
            require(not execute, "execute cannot bypass video review via semantic-only source")
            require(not row.get("evidence_path"), "non-execute does not require an empty recording")
            video_result = {}
        result["provenance"]={**provenance,**expected,**video_result,"reviewer_type":"AI","review_status":"accepted",
                              "review_rubric_version":rubric_version,"config_sha256":canonical_hash(row["config"]),
                              "generation_context_id":generation["context_id"],"review_context_id":review["context_id"]}
    result["training_eligible"] = row.get("split") == "train"
    result["admission_status"] = "accepted_ai_review" if row["source_type"]!="historical_synthetic" else "admitted_historical_cold_start"
    return result


def _validate_input(records_path, *, persona_file, rubric_version, compiler_file, resource_file, native_profile_file, ffmpeg_path=None, resolver=None):
    resolver = resolver or ArtifactResolver()
    original, actual = resolver.resolve(records_path, Path.cwd())
    rows=[strict_json(x) for x in actual.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    require(bool(rows),"input records empty")
    nonempty(rubric_version,"review rubric version")
    # CLI/API binding-file arguments are relative to cwd; references inside each
    # record remain relative to that records file, including after freezing.
    expected=_bindings(compiler_file,resource_file,native_profile_file,persona_file,resolver,Path.cwd())
    _validate_splits(rows)
    ffmpeg = find_ffmpeg(ffmpeg_path) if any(r.get("source_type")=="ai_video_reviewed" for r in rows) else None
    output=[]
    for index,row in enumerate(rows,1):
        try: output.append(validate_record(row,resolver,original.parent,expected,rubric_version,ffmpeg))
        except (ValueError,KeyError,TypeError) as e: raise EvidenceError(f"record {index} ({row.get('candidate_id','?')}): {e}") from e
    return output,resolver,expected,ffmpeg


def export_snapshot(records_path, output_dir, *, persona_file, rubric_version, compiler_file, resource_file, native_profile_file, ffmpeg_path=None):
    output_dir=Path(output_dir).resolve()
    require(not output_dir.exists(),"output directory must be new; existing snapshots are immutable")
    rows,resolver,expected,ffmpeg=_validate_input(records_path,persona_file=persona_file,rubric_version=rubric_version,
        compiler_file=compiler_file,resource_file=resource_file,native_profile_file=native_profile_file,ffmpeg_path=ffmpeg_path)
    output_dir.mkdir(parents=True)
    artifacts=[]
    for item in resolver.seen.values():
        relative=Path("artifacts")/(item["sha256"][:16]+"-"+Path(item["source_path"]).name)
        dest=output_dir/relative;dest.parent.mkdir(exist_ok=True)
        shutil.copyfile(item["actual"],dest)
        require(file_hash(dest)==item["sha256"]==file_hash(item["actual"]),"artifact changed while freezing; snapshot not finalized")
        artifacts.append({k:v for k,v in item.items() if k!="actual"}|{"path":relative.as_posix()})
    dataset=output_dir/"dataset.jsonl"
    dataset.write_text("".join(canonical_json(r)+"\n" for r in rows),encoding="utf-8")
    by_source={a["source_path"]:a for a in artifacts}
    def original_path(p):
        return str(Path(p).resolve())
    persona_source=original_path(persona_file)
    manifest={"schema_version":SNAPSHOT_VERSION,"stage":"frozen_data","status":"experimental","ready":False,
        "test_fixture":any(r.get("test_fixture") is True or r.get("provenance",{}).get("test_fixture") is True for r in rows),
        "dataset":{"path":"dataset.jsonl","sha256":file_hash(dataset)},"split_sha256":split_assignments_sha256(rows),
        "persona":{"path":by_source[persona_source]["path"],"sha256":expected["persona_sha256"]},
        "bindings":{k:v for k,v in expected.items() if k!="persona_sha256"},"review_rubric_version":rubric_version,
        "artifacts":artifacts,"source_counts":{s:sum(r["source_type"]==s for r in rows) for s in sorted(SOURCE_TYPES)},
        "records_source_path":str(Path(records_path).resolve()),"binding_source_paths":{
            "persona_file":persona_source,"compiler_file":original_path(compiler_file),"resource_file":original_path(resource_file),"native_profile_file":original_path(native_profile_file)},
        "ffmpeg_path":str(ffmpeg) if ffmpeg else None,"ffmpeg_sha256":file_hash(ffmpeg) if ffmpeg else None,
        "limitations":["Integrity validation does not prove subjective AI judgement or human preference.","Candidate resource calibration is not upgraded by export.","No model trained or release approved by this stage."]}
    path=output_dir/"manifest.json";path.write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    return path


def validate_frozen_snapshot(manifest_path):
    manifest_path=Path(manifest_path).resolve();root=manifest_path.parent
    manifest=strict_json(manifest_path.read_text(encoding="utf-8-sig"))
    require(manifest.get("schema_version")==SNAPSHOT_VERSION and manifest.get("stage")=="frozen_data", "invalid frozen snapshot stage/schema")
    require(manifest.get("status")=="experimental" and manifest.get("ready") is False,"data snapshot must not claim release ready")
    def bounded(relative):
        p=(root/relative).resolve();require(p.is_relative_to(root) and p.is_file(),"snapshot artifact missing/outside snapshot");return p
    mapping={}
    for item in manifest.get("artifacts",[]):
        actual=bounded(item["path"]);require(file_hash(actual)==item["sha256"],"frozen artifact hash mismatch")
        require(item["source_path"] not in mapping,"duplicate artifact source")
        mapping[item["source_path"]]=actual
    dataset=bounded(manifest["dataset"]["path"]);require(file_hash(dataset)==manifest["dataset"]["sha256"],"dataset hash mismatch")
    frozen_rows=[strict_json(x) for x in dataset.read_text(encoding="utf-8-sig").splitlines() if x.strip()]
    _validate_splits(frozen_rows)
    require(split_assignments_sha256(frozen_rows)==manifest["split_sha256"],"frozen split assignment hash mismatch")
    ffmpeg=manifest.get("ffmpeg_path")
    if ffmpeg:require(file_hash(ffmpeg)==manifest.get("ffmpeg_sha256"),"ffmpeg binary changed/missing")
    rows,resolver,expected,_=_validate_input(manifest["records_source_path"],resolver=ArtifactResolver(mapping),
        rubric_version=manifest["review_rubric_version"],ffmpeg_path=ffmpeg,**manifest["binding_source_paths"])
    require(canonical_json(rows)==canonical_json(frozen_rows),"frozen labels/provenance differ from verified review records")
    require(manifest["bindings"]=={k:v for k,v in expected.items() if k!="persona_sha256"},"manifest bindings mismatch")
    require(file_hash(bounded(manifest["persona"]["path"]))==expected["persona_sha256"]==manifest["persona"]["sha256"],"manifest persona mismatch")
    return frozen_rows,manifest


def main():
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command",choices=["validate","export"])
    parser.add_argument("--manifest",type=Path)
    parser.add_argument("--records",type=Path)
    parser.add_argument("--out-dir",type=Path)
    parser.add_argument("--persona-file",type=Path)
    parser.add_argument("--review-rubric-version")
    parser.add_argument("--compiler-file",type=Path)
    parser.add_argument("--resource-file",type=Path)
    parser.add_argument("--native-profile-file",type=Path)
    parser.add_argument("--ffmpeg",type=Path)
    args=parser.parse_args()
    try:
        if args.manifest:
            require(args.command=="validate","--manifest only supports validate")
            rows,manifest=validate_frozen_snapshot(args.manifest)
            print(json.dumps({"valid":True,"rows":len(rows),"stage":manifest["stage"],"ready":False}));return
        require(all((args.records,args.persona_file,args.review_rubric_version,args.compiler_file,args.resource_file,args.native_profile_file)),"records mode needs all binding files and review rubric")
        options=dict(persona_file=args.persona_file,rubric_version=args.review_rubric_version,compiler_file=args.compiler_file,
                     resource_file=args.resource_file,native_profile_file=args.native_profile_file,ffmpeg_path=args.ffmpeg)
        if args.command=="export":
            require(args.out_dir is not None,"export needs --out-dir")
            path=export_snapshot(args.records,args.out_dir,**options)
            print(json.dumps({"manifest":str(path),"stage":"frozen_data","ready":False}))
        else:
            rows,_,_,_=_validate_input(args.records,**options)
            print(json.dumps({"valid":True,"rows":len(rows),"stage":"evidence_validation","ready":False}))
    except (EvidenceError,OSError,KeyError,TypeError,subprocess.SubprocessError) as e:
        print(json.dumps({"valid":False,"error":str(e),"ready":False},ensure_ascii=False));sys.exit(1)


if __name__=="__main__":main()
