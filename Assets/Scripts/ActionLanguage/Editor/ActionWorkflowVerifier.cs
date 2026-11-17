using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Live2D.Cubism.Core;
using UnityEditor;
using UnityEngine;

namespace PetLive2d.ActionLanguage.Editor
{
    /// <summary>Small real-editor regression: compile, record, complete, preserve evidence.</summary>
    public static class ActionWorkflowVerifier
    {
        [Serializable] private sealed class QueueRow { public string candidate_id, parent_candidate_id, raw_text, input_role = "instruction", decision = "execute", plan_json; }
        [Serializable] private sealed class BatchResult { public int total, completed, failed; public bool finished; }
        [Serializable] private sealed class Result
        {
            public bool passed;
            public string run_directory, error;
            public int recorded, non_execute, expected_compile_rejections;
            public bool overwrite_rejected, all_completed_meta, all_encoder_closed, all_hashes_stable, actual_eye_motion_measured;
            public bool external_cancel_rejected, input_role_preserved;
            public List<string> evidence_paths = new List<string>();
        }
        private static string _run, _queue, _done, _snapshots;
        private static double _started;
        private static readonly string ReportPath = "Experiments/workflow_fix_20261117/reports/unity_workflow_check.json";
        private static string Cycle(string resource, int duration = 600, string hold = "0.2") =>
            "{\"resource_id\":\"" + resource + "\",\"cycles\":[{\"duration_ms\":" + duration + ",\"controls\":{\"hold_ratio\":" + hold + (resource == "blink.full" ? "" : ",\"amplitude_scale\":1.0") + "}}]}";
        private static string Step(params string[] actions) => "{\"actions\":[" + string.Join(",", actions) + "]}";
        private static string Config(params string[] steps) => "{\"version\":\"action-config.v0.2\",\"decision\":\"execute\",\"steps\":[" + string.Join(",", steps) + "]}";

        [MenuItem("Tools/PetLive2d/动作模型/验证训练回放流程")]
        public static void Run()
        {
            if (BatchVideoRecorder.IsRunning) throw new InvalidOperationException("Another recording batch is running.");
            _run = Path.GetFullPath(Path.Combine("Experiments/workflow_fix_20261117", "recording-" + Guid.NewGuid().ToString("N").Substring(0, 12)));
            Directory.CreateDirectory(_run);
            _queue = Path.Combine(_run, "queue.jsonl"); _done = Path.Combine(_run, "done.json"); _snapshots = Path.Combine(_run, "snapshots");
            var rows = new[] {
                new QueueRow {candidate_id="flow-blink",raw_text="眨眼一次，每次600毫秒。",plan_json=Config(Step(Cycle("blink.full")))},
                new QueueRow {candidate_id="flow-sequence",raw_text="先眨眼一次，再点头一次。",plan_json=Config(Step(Cycle("blink.full")),Step(Cycle("nod.basic",800)))},
                new QueueRow {candidate_id="flow-parallel",raw_text="同时眨眼一次和挥手一次。",plan_json=Config(Step(Cycle("blink.full"),Cycle("wave.basic",800)))},
                new QueueRow {candidate_id="flow-none",raw_text="保持原姿态，不执行动作。",decision="none",plan_json="{\"version\":\"action-config.v0.2\",\"decision\":\"none\",\"steps\":[]}"},
                new QueueRow {candidate_id="flow-short-hold",raw_text="编译拒绝用例",plan_json=Config(Step(Cycle("blink.full",600,"0.01")))}
            };
            var lines = new List<string>(); foreach (var row in rows) lines.Add(JsonUtility.ToJson(row));
            File.WriteAllLines(_queue, lines, new UTF8Encoding(false));
            if (!BatchVideoRecorder.RunBatch(_queue, _done, _snapshots, out string error)) throw new InvalidOperationException(error);
            _started = EditorApplication.timeSinceStartup;
            EditorApplication.update -= Poll;
            EditorApplication.update += Poll;
            Debug.Log("[ActionWorkflowVerifier] Started -> " + _run);
        }

        private static void Poll()
        {
            if (BatchVideoRecorder.IsRunning)
            {
                if (EditorApplication.timeSinceStartup - _started < 180) return;
                EditorApplication.update -= Poll;
                Save(new Result {run_directory=_run,error="verification_timeout"});
                return;
            }
            EditorApplication.update -= Poll;
            var result = new Result {run_directory=_run,all_completed_meta=true,all_encoder_closed=true,all_hashes_stable=true};
            try
            {
                var batch = JsonUtility.FromJson<BatchResult>(File.ReadAllText(_done));
                if (!batch.finished || batch.completed != 4 || batch.failed != 1) throw new InvalidOperationException("Unexpected batch result: " + File.ReadAllText(_done));
                foreach (var id in new[] {"flow-blink","flow-sequence","flow-parallel"})
                {
                    string dir=Path.Combine(_snapshots,id), evidencePath=Path.Combine(dir,"evidence.json");
                    var evidence=JsonUtility.FromJson<PreviewEvidenceRecord>(File.ReadAllText(evidencePath));
                    var meta=JsonUtility.FromJson<ActionCardCandidate>(File.ReadAllText(Path.Combine(dir,"meta.json")));
                    result.all_completed_meta &= meta.playback_completed && evidence.playback_completed;
                    result.all_encoder_closed &= evidence.encoder_closed && string.IsNullOrEmpty(evidence.capture_error);
                    result.all_hashes_stable &= evidence.source_hashes_unchanged && evidence.asset_hashes_unchanged &&
                        evidence.video_sha256==PreviewRecordingEvidence.HashFile(Path.Combine(dir,"preview.mp4"));
                    string[] trajectory=File.ReadAllLines(Path.Combine(dir,"trajectory.jsonl"));
                    if (trajectory.Length != evidence.frame_count || evidence.last_player_time_ms < evidence.native_duration_ms) throw new InvalidOperationException("Truncated trajectory");
                    if(id=="flow-blink")
                    {
                        float min=1,max=0;
                        foreach(string line in trajectory)
                            foreach(var sample in JsonUtility.FromJson<PreviewFrameSample>(line).parameters)
                                if(sample.id=="ParamEyeLOpen") {min=Mathf.Min(min,sample.value);max=Mathf.Max(max,sample.value);}
                        result.actual_eye_motion_measured=min<0.1f&&max>0.9f;
                    }
                    result.evidence_paths.Add(evidencePath); result.recorded++;
                }
                result.non_execute=1;result.expected_compile_rejections=1;
                result.overwrite_rejected=!BatchVideoRecorder.RunBatch(_queue,_done,_snapshots,out _);
                // A direct adapter cancellation near the endpoint must never be
                // mistaken for a natural completion after the release interval.
                CubismModel model=null;
                foreach(var candidate in UnityEngine.Object.FindObjectsOfType<CubismModel>())
                    if((candidate.gameObject.hideFlags&HideFlags.DontSave)==0&&!candidate.name.StartsWith("__",StringComparison.Ordinal)) {model=candidate;break;}
                var cancelled=new ActionCardCandidate {candidate_id="flow-external-cancel",raw_text="眨眼一次",input_role="instruction",decision="execute",plan_json=Config(Step(Cycle("blink.full")))};
                using(var session=new PreviewSession())
                {
                    session.Initialize(model,_=>{},null,_snapshots);
                    if(!session.TryPlayCandidate(cancelled,out string cancelError)) throw new InvalidOperationException(cancelError);
                    for(int i=0;i<15;i++) session.Tick();
                    session.Adapter.CancelCurrentAction();
                    for(int i=0;i<20;i++) session.Tick();
                    var rejected=JsonUtility.FromJson<PreviewEvidenceRecord>(File.ReadAllText(Path.Combine(_snapshots,cancelled.candidate_id,"evidence.json")));
                    result.external_cancel_rejected=!cancelled.playback_completed&&!session.LastCaptureSucceeded&&!rejected.playback_completed&&rejected.capture_error=="playback_interrupted";
                }
                var roleCandidate=JsonUtility.FromJson<ActionCardCandidate>("{\"input_role\":\"dialogue\"}");
                result.input_role_preserved=roleCandidate.input_role=="dialogue"&&string.IsNullOrEmpty(JsonUtility.FromJson<ActionCardCandidate>("{}").input_role);
                result.passed=result.recorded==3&&result.overwrite_rejected&&result.all_completed_meta&&result.all_encoder_closed&&result.all_hashes_stable&&result.actual_eye_motion_measured&&result.external_cancel_rejected&&result.input_role_preserved;
            }
            catch(Exception ex) {result.error=ex.ToString();}
            Save(result);
        }
        private static void Save(Result result)
        {
            Directory.CreateDirectory(Path.GetDirectoryName(ReportPath));
            File.WriteAllText(ReportPath,JsonUtility.ToJson(result,true),new UTF8Encoding(false));
            if(result.passed) Debug.Log("[ActionWorkflowVerifier] PASSED -> "+ReportPath);
            else Debug.LogError("[ActionWorkflowVerifier] FAILED -> "+ReportPath+" "+result.error);
        }
    }
}
