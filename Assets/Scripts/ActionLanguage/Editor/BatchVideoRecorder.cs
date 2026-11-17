using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Live2D.Cubism.Core;
using UnityEditor;
using UnityEngine;

namespace PetLive2d.ActionLanguage.Editor
{
    /// <summary>Serial recording with isolated outputs and explicit completion evidence.</summary>
    public static class BatchVideoRecorder
    {
        [Serializable] private sealed class QueueItem
        {
            public string candidate_id, parent_candidate_id, raw_text, plan_json, input_role;
            public string decision = "execute";
        }
        [Serializable] private sealed class DoneItem
        {
            public string candidate_id, raw_text, error, video_path, evidence_path;
            public bool ok;
        }
        [Serializable] private sealed class DoneReport
        {
            public int total, completed, failed;
            public string queue_sha256, snapshot_root;
            public bool finished;
            public List<DoneItem> items = new List<DoneItem>();
        }
        private static PreviewSession _session;
        private static List<QueueItem> _queue;
        private static ActionCardCandidate _active;
        private static int _index;
        private static DoneReport _report;
        private static bool _advancePending;
        private static double _itemStartTime;
        private static string _donePath, _snapshotRoot;
        public static bool IsRunning { get; private set; }
        public static string LastReportPath { get; private set; }

        [MenuItem("Tools/PetLive2d/动作模型/批量录制评测视频")]
        [MenuItem("Tools/PetLive2d/BatchVideoEval")]
        public static void RunBatchFromMenu()
        {
            string run = Path.Combine("Dataset", "ActionCards", "runs", DateTime.UtcNow.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N").Substring(0, 8));
            if (!RunBatch(Path.Combine("Dataset", "ActionCards", "video_eval_queue.jsonl"),
                Path.Combine(run, "done.json"), Path.Combine(run, "snapshots"), out string error))
                Debug.LogError("[BatchVideoRecorder] " + error);
        }

        public static bool RunBatch(string queuePath, string donePath, string snapshotRoot, out string error)
        {
            error = null;
            if (IsRunning) { error = "recording_batch_already_running"; return false; }
            if (EditorApplication.isPlaying) { error = "recording_requires_edit_mode"; return false; }
            if (!File.Exists(queuePath)) { error = "queue_not_found: " + queuePath; return false; }
            if (File.Exists(donePath) || Directory.Exists(snapshotRoot))
            { error = "immutable_output: use new report and snapshot paths"; return false; }
            CubismModel model = null;
            foreach (var candidate in UnityEngine.Object.FindObjectsOfType<CubismModel>())
                if ((candidate.gameObject.hideFlags & HideFlags.DontSave) == 0 && !candidate.name.StartsWith("__", StringComparison.Ordinal))
                { model = candidate; break; }
            if (model == null) { error = "missing_cubism_model"; return false; }
            var queue = new List<QueueItem>();
            var ids = new HashSet<string>(StringComparer.Ordinal);
            try
            {
                foreach (string line in File.ReadAllLines(queuePath, Encoding.UTF8))
                {
                    if (string.IsNullOrWhiteSpace(line)) continue;
                    var item = JsonUtility.FromJson<QueueItem>(line);
                    if (item == null || string.IsNullOrWhiteSpace(item.candidate_id) || string.IsNullOrWhiteSpace(item.plan_json) ||
                        item.candidate_id == "." || item.candidate_id == ".." || item.candidate_id.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 ||
                        !ids.Add(item.candidate_id) || (item.input_role != "instruction" && item.input_role != "dialogue"))
                        throw new InvalidDataException("Every queue row requires a unique candidate_id, input_role and plan_json.");
                    queue.Add(item);
                }
                if (queue.Count == 0) throw new InvalidDataException("queue_empty");
                _donePath = Path.GetFullPath(donePath); _snapshotRoot = Path.GetFullPath(snapshotRoot);
                _queue = queue; _index = 0; _active = null; _advancePending = true;
                _report = new DoneReport { total = queue.Count, snapshot_root = _snapshotRoot, queue_sha256 = PreviewRecordingEvidence.HashFile(queuePath) };
                _session = new PreviewSession();
                _session.Initialize(model, OnPlaybackCompleted, null, _snapshotRoot);
                if (!_session.IsReady) throw new InvalidOperationException(_session.StatusDetail);
                IsRunning = true;
                LastReportPath = _donePath;
                EditorApplication.update += OnEditorUpdate;
                AssemblyReloadEvents.beforeAssemblyReload += AbortForReload;
                WriteReport();
                return true;
            }
            catch (Exception ex)
            {
                IsRunning = false;
                EditorApplication.update -= OnEditorUpdate;
                AssemblyReloadEvents.beforeAssemblyReload -= AbortForReload;
                _session?.Dispose(); _session = null; error = ex.Message; return false;
            }
        }

        private static void StartNext()
        {
            _advancePending = false;
            if (_index >= _queue.Count) { FinishBatch(); return; }
            var item = _queue[_index];
            _active = new ActionCardCandidate {
                session_id = "batch-" + Path.GetFileName(Path.GetDirectoryName(_donePath)),
                candidate_id = item.candidate_id, parent_candidate_id = item.parent_candidate_id,
                raw_text = item.raw_text ?? "", input_role = item.input_role,
                decision = item.decision, plan_json = item.plan_json,
                provider_kind = "batch_config_replay", provider_version = "preview-evidence.v1", model_version = "provided_config",
                timestamp_utc = DateTime.UtcNow.ToString("o")
            };
            _itemStartTime = EditorApplication.timeSinceStartup;
            if (!_session.TryPlayCandidate(_active, out string error))
                RecordDone(false, error);
            else if (_active.decision != "execute")
                RecordDone(_active.compile_ok, _active.compile_error_message);
        }

        private static void OnPlaybackCompleted(ActionCardCandidate candidate)
        {
            if (_active == null || candidate.candidate_id != _active.candidate_id) return;
            RecordDone(candidate.playback_completed && _session.LastCaptureSucceeded,
                _session.LastCaptureSucceeded ? "" : "recording_evidence_incomplete");
        }

        private static void RecordDone(bool ok, string error)
        {
            if (_active == null) return;
            string dir = Path.Combine(_snapshotRoot, _active.candidate_id);
            if (ok) _report.completed++; else _report.failed++;
            _report.items.Add(new DoneItem { candidate_id = _active.candidate_id, raw_text = _active.raw_text, ok = ok,
                error = error ?? "", video_path = File.Exists(Path.Combine(dir, "preview.mp4")) ? Path.Combine(dir, "preview.mp4") : "",
                evidence_path = File.Exists(Path.Combine(dir, "evidence.json")) ? Path.Combine(dir, "evidence.json") : "" });
            _active = null; _index++; _advancePending = true;
            WriteReport();
        }

        private static void OnEditorUpdate()
        {
            if (!IsRunning || _session == null) return;
            // Completion callbacks only enqueue; never dispose/restart inside Tick.
            if (_advancePending) { StartNext(); return; }
            _session.Tick();
            if (_active != null && EditorApplication.timeSinceStartup - _itemStartTime > 60.0)
            {
                _session.CancelCurrentAndReset("recording_timeout");
                RecordDone(false, "timeout_60s");
            }
        }
        private static void AbortForReload()
        {
            _session?.CancelCurrentAndReset("assembly_reload");
            if (_active != null) RecordDone(false, "assembly_reload");
            FinishBatch();
        }
        private static void WriteReport()
        {
            Directory.CreateDirectory(Path.GetDirectoryName(_donePath));
            File.WriteAllText(_donePath, JsonUtility.ToJson(_report, true), new UTF8Encoding(false));
        }
        private static void FinishBatch()
        {
            IsRunning = false;
            EditorApplication.update -= OnEditorUpdate;
            AssemblyReloadEvents.beforeAssemblyReload -= AbortForReload;
            _session?.Dispose(); _session = null;
            _report.finished = _index >= _queue.Count;
            WriteReport();
            Debug.Log($"[BatchVideoRecorder] Done: {_report.completed}/{_report.total}, failed={_report.failed} -> {_donePath}");
        }
    }
}
