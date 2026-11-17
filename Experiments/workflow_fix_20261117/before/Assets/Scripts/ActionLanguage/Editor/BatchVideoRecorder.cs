using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using Live2D.Cubism.Core;
using UnityEditor;
using UnityEngine;

namespace PetLive2d.ActionLanguage.Editor
{
    /// <summary>
    /// Headless Editor batch runner that plays queued action-config.v0.2 candidates in PreviewSession
    /// and records 12fps preview.mp4 + meta.json for VLM/LLM visual feedback loops.
    /// </summary>
    public static class BatchVideoRecorder
    {
        [Serializable]
        private sealed class QueueItem
        {
            public string candidate_id;
            public string raw_text;
            public string plan_json;
            public string decision = "execute";
        }

        [Serializable]
        private sealed class DoneItem
        {
            public string candidate_id;
            public string raw_text;
            public bool ok;
            public string error;
            public string video_path;
        }

        [Serializable]
        private sealed class DoneReport
        {
            public int total;
            public int completed;
            public int failed;
            public List<DoneItem> items = new List<DoneItem>();
        }

        private static readonly string QueuePath = Path.Combine("Dataset", "ActionCards", "video_eval_queue.jsonl");
        private static readonly string DonePath = Path.Combine("Dataset", "ActionCards", "video_eval_done.json");

        private static PreviewSession _session;
        private static List<QueueItem> _queue;
        private static int _index;
        private static DoneReport _report;
        private static bool _running;
        private static double _itemStartTime;

        [MenuItem("Tools/PetLive2d/动作模型/批量录制评测视频")]
        [MenuItem("Tools/PetLive2d/BatchVideoEval")]
        public static void RunBatchFromMenu()
        {
            if (_running)
            {
                Debug.LogWarning("[BatchVideoRecorder] Already running.");
                return;
            }
            if (!File.Exists(QueuePath))
            {
                Debug.LogError($"[BatchVideoRecorder] Queue file not found: {QueuePath}");
                return;
            }

            var model = UnityEngine.Object.FindObjectOfType<CubismModel>();
            if (model == null)
            {
                Debug.LogError("[BatchVideoRecorder] No CubismModel found in the active scene.");
                return;
            }

            _queue = new List<QueueItem>();
            foreach (string raw in File.ReadAllLines(QueuePath, Encoding.UTF8))
            {
                if (string.IsNullOrWhiteSpace(raw)) continue;
                var item = JsonUtility.FromJson<QueueItem>(raw);
                if (item != null && !string.IsNullOrWhiteSpace(item.candidate_id) && !string.IsNullOrWhiteSpace(item.plan_json))
                {
                    _queue.Add(item);
                }
            }

            if (_queue.Count == 0)
            {
                Debug.LogWarning("[BatchVideoRecorder] Queue is empty.");
                return;
            }

            if (File.Exists(DonePath)) File.Delete(DonePath);

            _report = new DoneReport { total = _queue.Count };
            _index = 0;
            _session = new PreviewSession();
            _session.Initialize(model, OnPlaybackCompleted, OnCompileOutcome);
            _running = true;
            EditorApplication.update += OnEditorUpdate;
            StartNext();
        }

        private static void StartNext()
        {
            while (_index < _queue.Count)
            {
                var q = _queue[_index];
                var cand = new ActionCardCandidate
                {
                    session_id = "batch-video-eval",
                    candidate_id = q.candidate_id,
                    raw_text = q.raw_text ?? "",
                    decision = string.IsNullOrWhiteSpace(q.decision) ? "execute" : q.decision,
                    plan_json = q.plan_json,
                    provider_kind = "batch_video_eval",
                    provider_version = "v0.2",
                    model_version = "batch",
                };
                _itemStartTime = EditorApplication.timeSinceStartup;
                if (_session.TryPlayCandidate(cand, out string err))
                {
                    return;
                }
                _report.failed++;
                _report.items.Add(new DoneItem
                {
                    candidate_id = q.candidate_id,
                    raw_text = q.raw_text,
                    ok = false,
                    error = err ?? "compile_failed",
                    video_path = ""
                });
                _index++;
            }
            FinishBatch();
        }

        private static void OnCompileOutcome(ActionCardCandidate cand, bool compileOk, bool isNonExec)
        {
            if (isNonExec)
            {
                RecordDone(cand, compileOk, compileOk ? "" : cand.compile_error_message);
                _index++;
                StartNext();
            }
        }

        private static void OnPlaybackCompleted(ActionCardCandidate cand)
        {
            RecordDone(cand, true, "");
            _index++;
            StartNext();
        }

        private static void RecordDone(ActionCardCandidate cand, bool ok, string err)
        {
            string vid = Path.Combine(Directory.GetCurrentDirectory(), "Dataset", "ActionCards", "snapshots", cand.candidate_id, "preview.mp4");
            if (ok) _report.completed++;
            else _report.failed++;
            _report.items.Add(new DoneItem
            {
                candidate_id = cand.candidate_id,
                raw_text = cand.raw_text,
                ok = ok,
                error = err ?? "",
                video_path = File.Exists(vid) ? vid : ""
            });
        }

        private static void OnEditorUpdate()
        {
            if (!_running || _session == null) return;
            _session.Tick();
            if (EditorApplication.timeSinceStartup - _itemStartTime > 15.0)
            {
                var q = _index < _queue.Count ? _queue[_index] : null;
                _report.failed++;
                _report.items.Add(new DoneItem
                {
                    candidate_id = q?.candidate_id ?? "unknown",
                    raw_text = q?.raw_text ?? "",
                    ok = false,
                    error = "timeout_15s",
                    video_path = ""
                });
                _index++;
                StartNext();
            }
        }

        private static void FinishBatch()
        {
            _running = false;
            EditorApplication.update -= OnEditorUpdate;
            _session?.Dispose();
            _session = null;
            Directory.CreateDirectory(Path.GetDirectoryName(DonePath));
            File.WriteAllText(DonePath, JsonUtility.ToJson(_report, true), new UTF8Encoding(false));
            Debug.Log($"[BatchVideoRecorder] Done: {_report.completed}/{_report.total} succeeded, {_report.failed} failed -> {DonePath}");
        }
    }
}
