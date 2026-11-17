"""Contract tests only. Fabricated acceptance belongs exclusively to labelled fixtures.

No fixture is a real AI review or part of a training corpus.
"""
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"Tools/ActionEncoder"))
import review_evidence as ev


def make_semantic_fixture(root, splits=("train","val","test")):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    binding_paths={}
    for name in ("persona_file","compiler_file","resource_file","native_profile_file"):
        p=root/(name+".txt");p.write_text("TEST FIXTURE ONLY: "+name,encoding="utf-8");binding_paths[name]=p
    expected={"persona_sha256":ev.file_hash(binding_paths["persona_file"]),"compiler_sha256":ev.file_hash(binding_paths["compiler_file"]),
              "resource_sha256":ev.file_hash(binding_paths["resource_file"]),"native_profile_sha256":ev.file_hash(binding_paths["native_profile_file"])}
    rows=[]
    for i,split in enumerate(splits):
        cfg={"version":"action-config.v0.2","decision":("none","unsupported","ambiguous")[i%3],"steps":[]}
        rows.append({"candidate_id":f"fixture-{split}","parent_candidate_id":"","raw_text":f"测试夹具 {split}，不是实际训练语料。","test_fixture":True,
                     "config":cfg,"input_role":"dialogue","group_id":f"fixture-group-{i}","semantic_family_id":f"fixture-family-{i}",
                     "split":split,"source_type":"ai_semantic_reviewed","provenance":{"test_fixture":True,"original_split":split},
                     "generation":{"provider":"fixture","model":"fixture-generator","context_id":f"fixture-generation-{i}","prompt_version":"fixture.v1"},
                     "review":{"reviewer_type":"AI","provider":"fixture","model":"fixture-reviewer","context_id":f"fixture-review-{i}",
                               "prompt_version":"fixture.v1","status":"accepted","rubric_version":"fixture-rubric.v1",
                               "reviewed_at":"2026-11-17T12:00:00Z","semantic_match":True,"scores":{"semantic":1},
                               "rationale":"Constructed unit-test fixture, never an actual AI evaluation.",
                               "config_sha256":ev.canonical_hash(cfg),"candidate_id":f"fixture-{split}","parent_candidate_id":"","input_role":"dialogue",
                               "raw_text_sha256":ev.text_hash(f"测试夹具 {split}，不是实际训练语料。"),**expected}})
    records=root/"fixture-records.jsonl";write_rows(records,rows)
    return records,{**binding_paths,"rubric_version":"fixture-rubric.v1"}


def write_rows(path,rows):
    Path(path).write_text("".join(ev.canonical_json(r)+"\n" for r in rows),encoding="utf-8")


def read_rows(path):return [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines()]


def video_fixture(root):
    records,options=make_semantic_fixture(root,splits=("train",))
    row=read_rows(records)[0];row["source_type"]="ai_video_reviewed"
    row["input_role"]="instruction";row["raw_text"]="眨眼一次，每次600毫秒"
    row["config"]={"version":"action-config.v0.2","decision":"execute","steps":[{"actions":[{"resource_id":"blink.full","cycles":[{"duration_ms":600,"controls":{"hold_ratio":.2}}]}]}]}
    video=Path(root)/"preview.mp4";video.write_bytes(b"TEST FIXTURE VIDEO (decoder mocked in unit tests)")
    trajectory=Path(root)/"trajectory.jsonl"
    write_rows(trajectory,[{"frame_index":i,"video_time_ms":i*100,"player_time_ms":i*100,"state":"fixture",
                            "parameters":[{"id":"ParamEyeLOpen","value":1.0}]} for i in range(7)])
    observation=Path(root)/"observation.txt";observation.write_text("TEST FIXTURE: constructed observation, not AI evidence.",encoding="utf-8")
    native=ev.canonical_json({"version":"0.1","profile":"yukikaze.v1","duration_ms":600,"frames":[]})
    plan=json.dumps(row["config"],ensure_ascii=False,indent=2)
    review=row["review"];review["config_sha256"]=ev.canonical_hash(row["config"]);review["scores"]["naturalness"]=.8
    review["raw_text_sha256"]=ev.text_hash(row["raw_text"]);review["input_role"]=row["input_role"]
    evidence={"schema_version":"preview-evidence.v1","candidate_id":row["candidate_id"],"parent_candidate_id":"","input_role":"instruction",
              "compile_ok":True,"playback_completed":True,"encoder_closed":True,"capture_error":"","source_hashes_unchanged":True,"asset_hashes_unchanged":True,
              "started_utc":"2026-11-17T11:59:00Z","completed_utc":"2026-11-17T11:59:01Z","raw_text_sha256":ev.text_hash(row["raw_text"]),
              "config_json":plan,"config_sha256":ev.text_hash(plan),"config_hash_encoding":"exact_utf8_plan_json",
              "native_json":native,"native_sha256":ev.text_hash(native),"native_duration_ms":600,
              "resource_catalog_sha256":review["resource_sha256"],"compiler_sha256":review["compiler_sha256"],"profile_sha256":review["native_profile_sha256"],
              "persona_sha256":review["persona_sha256"],"compiled_assembly_sha256":"a"*64,"character_asset_sha256":"b"*64,
              "resource_catalog_version":"fixture-resource.v1","parameter_schema_version":"action-config.v0.2",
              "video_file":"preview.mp4","video_sha256":ev.file_hash(video),"trajectory_file":"trajectory.jsonl","trajectory_sha256":ev.file_hash(trajectory),
              "frame_count":7,"fps":10,"last_player_time_ms":600}
    evidence_path=Path(root)/"evidence.json";evidence_path.write_text(ev.canonical_json(evidence),encoding="utf-8")
    row["evidence_path"]=str(evidence_path);review["evidence_sha256"]=ev.file_hash(evidence_path);review["video_sha256"]=ev.file_hash(video)
    review["observation"]={"method":"timestamped_frames_and_trajectory","full_clip_observed":True,"limitations":[],"artifact_paths":[str(observation)]}
    (Path(root)/"meta.json").write_text(ev.canonical_json({"candidate_id":row["candidate_id"],"parent_candidate_id":"","raw_text":row["raw_text"],
        "input_role":row["input_role"],"plan_json":plan,"compile_ok":True,"playback_completed":True}),encoding="utf-8")
    write_rows(records,[row]);return records,options,evidence_path


class ReviewEvidenceTests(unittest.TestCase):
    def setUp(self):self.temp=tempfile.TemporaryDirectory(prefix="review-evidence-fixture-");self.root=Path(self.temp.name)
    def tearDown(self):self.temp.cleanup()
    def semantic(self):return make_semantic_fixture(self.root/"input")
    def export(self,records,options):return ev.export_snapshot(records,self.root/"snapshot",**options)
    def mutate_row(self,records,callback):
        rows=read_rows(records);callback(rows[0]);write_rows(records,rows)
    def test_semantic_ai_requires_no_human_keep_or_video(self):
        records,options=self.semantic();manifest=self.export(records,options);rows,m=ev.validate_frozen_snapshot(manifest)
        self.assertEqual(len(rows),3);self.assertTrue(m["test_fixture"]);self.assertFalse(m["ready"])
        self.assertTrue(rows[0]["training_eligible"]);self.assertFalse(rows[-1]["training_eligible"])
        self.assertFalse(any("human" in r["provenance"] for r in rows))
    def test_original_files_can_disappear_after_freeze(self):
        records,options=self.semantic();manifest=self.export(records,options);shutil.rmtree(records.parent)
        self.assertEqual(len(ev.validate_frozen_snapshot(manifest)[0]),3)
    def test_existing_snapshot_not_overwritten(self):
        records,options=self.semantic();self.export(records,options)
        with self.assertRaises(ev.EvidenceError):self.export(records,options)
    def test_dataset_tampering_rejected(self):
        records,options=self.semantic();manifest=self.export(records,options);(manifest.parent/"dataset.jsonl").write_text("{}\n",encoding="utf-8")
        with self.assertRaises(ev.EvidenceError):ev.validate_frozen_snapshot(manifest)
    def test_rehashed_dataset_cannot_detach_review(self):
        records,options=self.semantic();manifest=self.export(records,options);m=json.loads(manifest.read_text(encoding="utf-8"));dataset=manifest.parent/m["dataset"]["path"]
        rows=read_rows(dataset);rows[0]["raw_text"]="改过的标签";write_rows(dataset,rows);m["dataset"]["sha256"]=ev.file_hash(dataset);manifest.write_text(ev.canonical_json(m),encoding="utf-8")
        with self.assertRaises(ev.EvidenceError):ev.validate_frozen_snapshot(manifest)
    def test_persona_artifact_tampering_rejected(self):
        records,options=self.semantic();manifest=self.export(records,options);m=json.loads(manifest.read_text(encoding="utf-8"));(manifest.parent/m["persona"]["path"]).write_text("altered",encoding="utf-8")
        with self.assertRaises(ev.EvidenceError):ev.validate_frozen_snapshot(manifest)
    def test_same_context_rejected(self):
        records,options=self.semantic();self.mutate_row(records,lambda r:r["review"].update(context_id=r["generation"]["context_id"]))
        with self.assertRaises(ev.EvidenceError):self.export(records,options)
    def test_ai_rejection_never_exported(self):
        records,options=self.semantic();self.mutate_row(records,lambda r:r["review"].update(status="rejected"))
        with self.assertRaises(ev.EvidenceError):self.export(records,options)
    def test_changed_config_review_hash_rejected(self):
        records,options=self.semantic();self.mutate_row(records,lambda r:r["config"].update(decision="unsupported"))
        with self.assertRaises(ev.EvidenceError):self.export(records,options)
    def test_changed_text_cannot_reuse_config_review(self):
        records,options=self.semantic();self.mutate_row(records,lambda r:r.update(raw_text="另一个不同语义的请求"))
        with self.assertRaises(ev.EvidenceError):self.export(records,options)
    def test_changed_input_role_cannot_reuse_review(self):
        records,options=self.semantic();self.mutate_row(records,lambda r:r.update(input_role="instruction"))
        with self.assertRaises(ev.EvidenceError):self.export(records,options)
    def test_test_to_train_rejected(self):
        records,options=self.semantic();self.mutate_row(records,lambda r:r["provenance"].update(original_split="test"))
        with self.assertRaises(ev.EvidenceError):self.export(records,options)
    def test_cross_family_split_rejected(self):
        records,options=self.semantic();rows=read_rows(records);rows[1]["semantic_family_id"]=rows[0]["semantic_family_id"];write_rows(records,rows)
        with self.assertRaises(ev.EvidenceError):self.export(records,options)
    def test_parent_split_leak_rejected(self):
        records,options=self.semantic();rows=read_rows(records);rows[0]["parent_candidate_id"]=rows[1]["candidate_id"];write_rows(records,rows)
        with self.assertRaises(ev.EvidenceError):self.export(records,options)
    def test_execute_cannot_use_semantic_only_review(self):
        records,options,evidence=video_fixture(self.root/"input");self.mutate_row(records,lambda r:r.update(source_type="ai_semantic_reviewed"))
        with self.assertRaises(ev.EvidenceError):self.export(records,options)
    def test_historical_cold_does_not_require_ai_or_video(self):
        records,options=self.semantic();rows=read_rows(records);original=self.root/"input/source.jsonl";write_rows(original,rows)
        for i,row in enumerate(rows,1):
            row["source_type"]="historical_synthetic";row.pop("review");row.pop("generation")
            row["provenance"].update(source_file=str(original),source_sha256=ev.file_hash(original),source_line=i,
                persona_sha256=ev.file_hash(options["persona_file"]),label_policy_review_rubric_version=options["rubric_version"],
                label_policy_review_status="accepted",label_policy_review_source="fixture-only policy check")
        write_rows(records,rows);manifest=self.export(records,options)
        self.assertEqual(ev.validate_frozen_snapshot(manifest)[1]["source_counts"]["historical_synthetic"],3)
    def test_historical_source_test_split_cannot_be_hidden(self):
        records,options=self.semantic();rows=read_rows(records);row=rows[0]
        source=self.root/"input/source.jsonl";original=copy.deepcopy(row);original["split"]="test";write_rows(source,[original])
        row["source_type"]="historical_synthetic";row.pop("review");row.pop("generation")
        row["provenance"].update(source_file=str(source),source_sha256=ev.file_hash(source),source_line=1,
            persona_sha256=ev.file_hash(options["persona_file"]),label_policy_review_rubric_version=options["rubric_version"],
            label_policy_review_status="accepted",label_policy_review_source="fixture-only policy check")
        write_rows(records,rows)
        with self.assertRaises(ev.EvidenceError):self.export(records,options)
    def test_pending_row_cannot_be_promoted(self):
        records,options=self.semantic();self.mutate_row(records,lambda r:r.update(admission_status="pending_persona"))
        with self.assertRaises(ev.EvidenceError):self.export(records,options)
    def test_explicit_training_ineligible_not_overridden(self):
        records,options=self.semantic();self.mutate_row(records,lambda r:r.update(training_eligible=False))
        with self.assertRaises(ev.EvidenceError):self.export(records,options)
    def test_raw_history_without_binding_rejected(self):
        p=ROOT/"Experiments/teacher_video_20261117_01/input/Dataset/ActionCards/llm_v02_corpus.jsonl"
        if not p.exists():self.skipTest("history snapshot not available")
        records,options=self.semantic();records.write_text(p.read_text(encoding="utf-8").splitlines()[0]+"\n",encoding="utf-8")
        with self.assertRaises(ev.EvidenceError):self.export(records,options)
    def mock_decoder(self,path,ffmpeg):return {"decoded_frames":7,"decoded_duration_ms":700,"video_sha256":ev.file_hash(path),"full_decode":True}
    def test_complete_video_fixture_admitted_and_revalidated(self):
        records,options,evidence=video_fixture(self.root/"input")
        with patch.object(ev,"find_ffmpeg",return_value=Path(sys.executable)),patch.object(ev,"decode_video",side_effect=self.mock_decoder):
            manifest=self.export(records,options);rows,m=ev.validate_frozen_snapshot(manifest)
        self.assertEqual(rows[0]["provenance"]["decoded_frames"],7);self.assertTrue(m["test_fixture"])
    def test_capture_only_does_not_invent_ai_acceptance(self):
        records,options,p=video_fixture(self.root/"input")
        options.pop("rubric_version")
        with patch.object(ev,"find_ffmpeg",return_value=Path(sys.executable)),patch.object(ev,"decode_video",side_effect=self.mock_decoder):
            result=ev.validate_capture_only(p,**options)
        self.assertTrue(result["valid"]);self.assertFalse(result["ai_reviewed"]);self.assertFalse(result["training_eligible"])
    def video_rejection(self,field,value):
        records,options,p=video_fixture(self.root/"input");e=json.loads(p.read_text(encoding="utf-8"));e[field]=value;p.write_text(ev.canonical_json(e),encoding="utf-8")
        self.mutate_row(records,lambda r:r["review"].update(evidence_sha256=ev.file_hash(p)))
        with patch.object(ev,"find_ffmpeg",return_value=Path(sys.executable)),patch.object(ev,"decode_video",side_effect=self.mock_decoder):
            with self.assertRaises(ev.EvidenceError):self.export(records,options)
    def test_incomplete_playback_rejected(self):self.video_rejection("playback_completed",False)
    def test_unclosed_encoder_rejected(self):self.video_rejection("encoder_closed",False)
    def test_stale_source_binding_rejected(self):self.video_rejection("source_hashes_unchanged",False)
    def test_truncated_frame_count_rejected(self):self.video_rejection("frame_count",8)
    def test_short_trajectory_rejected(self):self.video_rejection("last_player_time_ms",599)
    def test_encoder_error_rejected(self):self.video_rejection("capture_error","disk full")
    def test_wrong_parent_video_rejected(self):self.video_rejection("parent_candidate_id","wrong-parent")
    def test_wrong_config_video_rejected(self):self.video_rejection("config_sha256","0"*64)
    def test_trajectory_missing_start_rejected(self):
        records,options,p=video_fixture(self.root/"input");trajectory=p.parent/"trajectory.jsonl";frames=read_rows(trajectory)
        for f in frames:f["player_time_ms"]+=300
        write_rows(trajectory,frames);e=json.loads(p.read_text(encoding="utf-8"));e["trajectory_sha256"]=ev.file_hash(trajectory);p.write_text(ev.canonical_json(e),encoding="utf-8")
        self.mutate_row(records,lambda r:r["review"].update(evidence_sha256=ev.file_hash(p)))
        with patch.object(ev,"find_ffmpeg",return_value=Path(sys.executable)),patch.object(ev,"decode_video",side_effect=self.mock_decoder):
            with self.assertRaises(ev.EvidenceError):self.export(records,options)
    def test_trajectory_skipped_interval_rejected(self):
        records,options,p=video_fixture(self.root/"input");trajectory=p.parent/"trajectory.jsonl";frames=read_rows(trajectory)
        for f in frames[3:]:f["player_time_ms"]+=300
        write_rows(trajectory,frames);e=json.loads(p.read_text(encoding="utf-8"));e["trajectory_sha256"]=ev.file_hash(trajectory);p.write_text(ev.canonical_json(e),encoding="utf-8")
        self.mutate_row(records,lambda r:r["review"].update(evidence_sha256=ev.file_hash(p)))
        with patch.object(ev,"find_ffmpeg",return_value=Path(sys.executable)),patch.object(ev,"decode_video",side_effect=self.mock_decoder):
            with self.assertRaises(ev.EvidenceError):self.export(records,options)
    def test_decode_failure_never_admitted(self):
        records,options,p=video_fixture(self.root/"input")
        with patch.object(ev,"find_ffmpeg",return_value=Path(sys.executable)),patch.object(ev,"decode_video",side_effect=ev.EvidenceError("corrupt video")):
            with self.assertRaises(ev.EvidenceError):self.export(records,options)
    def test_real_full_decode_when_ffmpeg_configured(self):
        ff=os.environ.get("REVIEW_EVIDENCE_TEST_FFMPEG")
        if not ff:self.skipTest("set REVIEW_EVIDENCE_TEST_FFMPEG for real decoder integration")
        path=self.root/"fixture-video.mp4"
        subprocess.run([ff,"-v","error","-f","lavfi","-i","color=c=black:s=64x64:r=10:d=0.7","-an","-c:v","libx264","-y",str(path)],check=True,capture_output=True)
        result=ev.decode_video(path,Path(ff));self.assertEqual(result["decoded_frames"],7);self.assertTrue(result["full_decode"])
    def test_real_video_fixture_full_export_roundtrip(self):
        ff=os.environ.get("REVIEW_EVIDENCE_TEST_FFMPEG")
        if not ff:self.skipTest("set REVIEW_EVIDENCE_TEST_FFMPEG for real export integration")
        records,options,p=video_fixture(self.root/"input");video=p.parent/"preview.mp4"
        subprocess.run([ff,"-v","error","-f","lavfi","-i","color=c=black:s=64x64:r=10:d=0.7","-an","-c:v","libx264","-y",str(video)],check=True,capture_output=True)
        sidecar=json.loads(p.read_text(encoding="utf-8"));sidecar["video_sha256"]=ev.file_hash(video);p.write_text(ev.canonical_json(sidecar),encoding="utf-8")
        self.mutate_row(records,lambda r:r["review"].update(video_sha256=ev.file_hash(video),evidence_sha256=ev.file_hash(p)))
        manifest=ev.export_snapshot(records,self.root/"snapshot",ffmpeg_path=Path(ff),**options)
        rows,m=ev.validate_frozen_snapshot(manifest)
        self.assertTrue(m["test_fixture"]);self.assertEqual(rows[0]["provenance"]["decoded_frames"],7)


if __name__=="__main__":unittest.main()
