"""Mechanical recording verification only; never creates AI acceptance records."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"Tools/ActionEncoder"))
from review_evidence import validate_capture_only, file_hash, text_hash


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--snapshots",type=Path,required=True)
    p.add_argument("--out",type=Path,required=True)
    p.add_argument("--ffmpeg",type=Path,required=True)
    p.add_argument("--expect-rejected",action="append",default=[])
    args=p.parse_args()
    results=[]
    for evidence_path in sorted(args.snapshots.glob("*/evidence.json")):
        try:
            result=validate_capture_only(evidence_path,ffmpeg_path=args.ffmpeg,
                compiler_file=ROOT/"Assets/Scripts/ActionLanguage/ActionConfigCompiler.cs",
                resource_file=ROOT/"Assets/Scripts/ActionLanguage/ActionResourceCatalog.cs",
                native_profile_file=ROOT/"Assets/Scripts/ActionLanguage/YukikazeActionCatalog.cs",
                persona_file=ROOT/"Docs/ActionLanguage/personas/gemini-cyber-cat.md")
            evidence=json.loads(evidence_path.read_text(encoding="utf-8-sig"))
            paths=evidence["character_asset_paths"]
            current_asset_hash=text_hash("\n".join(sorted(path.replace("\\","/")+":"+file_hash(ROOT/path) for path in paths)))
            result["character_asset_count"]=len(paths)
            result["current_character_asset_sha256"]=current_asset_hash
            result["current_character_assets_match_recording"]=current_asset_hash==evidence["character_asset_sha256"]
            if not result["current_character_assets_match_recording"]:
                result["valid"]=False;result["error"]="Current character assets differ from recorded dependency digest"
            assembly=ROOT/"Library/ScriptAssemblies/Assembly-CSharp.dll"
            result["recorded_compiled_assembly_sha256"]=evidence["compiled_assembly_sha256"]
            result["current_compiled_assembly_sha256"]=file_hash(assembly) if assembly.exists() else None
            result["current_assembly_matches_recording"]=result["current_compiled_assembly_sha256"]==result["recorded_compiled_assembly_sha256"]
        except Exception as exc:
            result={"valid":False,"candidate_id":evidence_path.parent.name,"error":str(exc),"ai_reviewed":False,"training_eligible":False}
        results.append(result)
        result["expected_rejection"]=result["candidate_id"] in args.expect_rejected
        result["expected_outcome_observed"]=not result["valid"] if result["expected_rejection"] else result["valid"]
    report={"stage":"physical_recording_evidence_check","recording_count":len(results),"passed":sum(r["valid"] for r in results),
            "expected_rejected":sum(r["expected_rejection"] and not r["valid"] for r in results),
            "regression_passed":bool(results) and all(r["expected_outcome_observed"] for r in results),
            "ai_accepted_created":0,"training_started":False,"release_approved":False,"rows":results,
            "limits":["No visual semantic or naturalness review was performed by this validator.",
                      "Assembly current-hash comparison is reported separately; later recompilation does not rewrite historical evidence.",
                      "Candidate resources remain uncalibrated; physical validity grants no training admission."]}
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k!="rows"},ensure_ascii=False))
    for r in results:print(json.dumps({k:r.get(k) for k in ("candidate_id","valid","decoded_frames","decoded_duration_ms","native_duration_ms","first_player_time_ms","last_player_time_ms","current_character_assets_match_recording","current_assembly_matches_recording","error")},ensure_ascii=False))
    return 0 if report["regression_passed"] else 1


if __name__=="__main__":sys.exit(main())
