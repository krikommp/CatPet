using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;

namespace PetLive2d.ActionLanguage
{
    /// <summary>
    /// Append-only, idempotent JSONL store for immutable action candidates, evaluation events,
    /// and qualified training sample exports under Dataset/ActionCards/.
    /// </summary>
    public sealed class ReviewStore
    {
        public string RootDirectory { get; }
        public string CandidatesPath => Path.Combine(RootDirectory, "candidates.jsonl");
        public string EvaluationsPath => Path.Combine(RootDirectory, "evaluations.jsonl");
        public string QualifiedExportPath => Path.Combine(RootDirectory, "qualified_semantic.jsonl");
        public string QualifiedV02ExportPath => Path.Combine(RootDirectory, "qualified_action_config.jsonl");

        private readonly Dictionary<string, ActionCardCandidate> _candidatesById = new Dictionary<string, ActionCardCandidate>(StringComparer.Ordinal);
        private readonly List<ActionCardCandidate> _candidates = new List<ActionCardCandidate>();
        private readonly List<ActionCardEvaluationEvent> _evaluations = new List<ActionCardEvaluationEvent>();
        private readonly HashSet<string> _exportedCandidateIds = new HashSet<string>(StringComparer.Ordinal);

        public IReadOnlyList<ActionCardCandidate> Candidates => _candidates;
        public IReadOnlyList<ActionCardEvaluationEvent> Evaluations => _evaluations;
        public int ExportedQualifiedCount => _exportedCandidateIds.Count;

        public ReviewStore(string rootDirectory = null)
        {
            RootDirectory = string.IsNullOrWhiteSpace(rootDirectory)
                ? Path.GetFullPath(Path.Combine(Application.dataPath, "..", "Dataset", "ActionCards"))
                : Path.GetFullPath(rootDirectory);
            Reload();
        }

        public void Reload()
        {
            _candidatesById.Clear();
            _candidates.Clear();
            _evaluations.Clear();
            _exportedCandidateIds.Clear();

            if (!Directory.Exists(RootDirectory))
                return;

            if (File.Exists(CandidatesPath))
            {
                foreach (string line in File.ReadAllLines(CandidatesPath, Encoding.UTF8))
                {
                    if (string.IsNullOrWhiteSpace(line)) continue;
                    var item = JsonUtility.FromJson<ActionCardCandidate>(line);
                    if (item != null && !string.IsNullOrEmpty(item.candidate_id) && !_candidatesById.ContainsKey(item.candidate_id))
                    {
                        _candidatesById.Add(item.candidate_id, item);
                        _candidates.Add(item);
                    }
                }
            }

            if (File.Exists(EvaluationsPath))
            {
                foreach (string line in File.ReadAllLines(EvaluationsPath, Encoding.UTF8))
                {
                    if (string.IsNullOrWhiteSpace(line)) continue;
                    var ev = JsonUtility.FromJson<ActionCardEvaluationEvent>(line);
                    if (ev != null && !string.IsNullOrEmpty(ev.candidate_id))
                    {
                        _evaluations.Add(ev);
                        ApplyLifecycleEvent(ev);
                    }
                }
            }

            if (File.Exists(QualifiedExportPath))
            {
                foreach (string line in File.ReadAllLines(QualifiedExportPath, Encoding.UTF8))
                {
                    if (string.IsNullOrWhiteSpace(line)) continue;
                    var sample = JsonUtility.FromJson<QualifiedSemanticSample>(line);
                    if (sample != null && !string.IsNullOrEmpty(sample.candidate_id))
                    {
                        _exportedCandidateIds.Add(sample.candidate_id);
                    }
                }
            }
        }

        public void AppendCandidate(ActionCardCandidate candidate)
        {
            if (candidate == null || string.IsNullOrEmpty(candidate.candidate_id))
                throw new ArgumentException("Candidate and candidate_id are required.");
            if (_candidatesById.ContainsKey(candidate.candidate_id))
                return;

            Directory.CreateDirectory(RootDirectory);
            string json = JsonUtility.ToJson(candidate);
            File.AppendAllText(CandidatesPath, json + "\n", Encoding.UTF8);
            _candidatesById.Add(candidate.candidate_id, candidate);
            _candidates.Add(candidate);
        }

        public void AppendEvaluation(ActionCardEvaluationEvent ev)
        {
            if (ev == null || string.IsNullOrEmpty(ev.candidate_id))
                throw new ArgumentException("Evaluation event and candidate_id are required.");
            if (string.IsNullOrEmpty(ev.event_id))
                ev.event_id = Guid.NewGuid().ToString("N");
            if (string.IsNullOrEmpty(ev.timestamp_utc))
                ev.timestamp_utc = DateTime.UtcNow.ToString("O");

            Directory.CreateDirectory(RootDirectory);
            string json = JsonUtility.ToJson(ev);
            File.AppendAllText(EvaluationsPath, json + "\n", Encoding.UTF8);
            _evaluations.Add(ev);
        }

        private void ApplyLifecycleEvent(ActionCardEvaluationEvent ev)
        {
            if (!_candidatesById.TryGetValue(ev.candidate_id, out var c)) return;
            switch (ev.event_type)
            {
                case "playback_completed":
                    c.playback_completed = true;
                    c.playback_status = "completed";
                    break;
                case "compile_succeeded":
                    c.compile_ok = true;
                    if (!string.IsNullOrEmpty(ev.native_json)) c.native_json = ev.native_json;
                    c.compile_error_code = string.Empty;
                    c.compile_error_message = string.Empty;
                    break;
                case "non_execute_ready":
                    c.compile_ok = true;
                    c.playback_status = "non_execute_ready";
                    c.compile_error_code = string.Empty;
                    c.compile_error_message = string.Empty;
                    break;
                case "compile_failed":
                    c.compile_ok = false;
                    c.compile_error_code = ev.reason_tags;
                    c.compile_error_message = ev.note;
                    c.playback_status = "compile_failed";
                    break;
            }
        }

        public void RecordCompileOutcome(string candidateId, string sessionId, bool compileOk, string nativeJson, string errCode, string errMsg, bool isNonExecute = false)
        {
            if (string.IsNullOrEmpty(candidateId)) return;
            string evType = isNonExecute ? "non_execute_ready" : (compileOk ? "compile_succeeded" : "compile_failed");
            var ev = new ActionCardEvaluationEvent
            {
                session_id = sessionId,
                candidate_id = candidateId,
                event_type = evType,
                semantic_match = "unconfirmed",
                naturalness_score = 0,
                reason_tags = errCode ?? string.Empty,
                note = errMsg ?? string.Empty,
                native_json = nativeJson ?? string.Empty,
                is_kept = false
            };
            AppendEvaluation(ev);
            ApplyLifecycleEvent(ev);
        }

        public void MarkPlaybackCompleted(string candidateId, string sessionId)
        {
            if (string.IsNullOrEmpty(candidateId)) return;
            if (_candidatesById.TryGetValue(candidateId, out var c))
            {
                c.playback_completed = true;
                c.playback_status = "completed";
            }
            AppendEvaluation(new ActionCardEvaluationEvent
            {
                session_id = sessionId,
                candidate_id = candidateId,
                event_type = "playback_completed",
                semantic_match = "unconfirmed",
                naturalness_score = 0,
                is_kept = false
            });
        }

        public ActionCardEvaluationEvent GetLatestDecisionEvent(string candidateId)
        {
            for (int i = _evaluations.Count - 1; i >= 0; i--)
            {
                var ev = _evaluations[i];
                if (ev.candidate_id == candidateId &&
                    (ev.event_type == "keep" || ev.event_type == "reject" || ev.event_type == "skip" || ev.event_type == "evaluate"))
                {
                    return ev;
                }
            }
            return null;
        }

        public bool IsCandidateQualifiedForExport(ActionCardCandidate candidate, ActionCardEvaluationEvent ev, out string reason)
        {
            if (candidate == null || ev == null)
            {
                reason = "missing_candidate_or_evaluation";
                return false;
            }
            if (!candidate.compile_ok)
            {
                reason = "compile_failed";
                return false;
            }
            if (!ev.is_kept)
            {
                reason = "not_explicitly_kept";
                return false;
            }
            if (ev.semantic_match != "true")
            {
                reason = "semantic_not_confirmed";
                return false;
            }
            bool isNonExecute = candidate.decision == "none" || candidate.decision == "unsupported" || candidate.decision == "ambiguous";
            if (!isNonExecute)
            {
                if (!candidate.playback_completed)
                {
                    reason = "playback_not_completed";
                    return false;
                }
                if (ev.naturalness_score < 4 || ev.naturalness_score > 5)
                {
                    reason = "naturalness_below_4";
                    return false;
                }
            }
            reason = "ok";
            return true;
        }

        /// <summary>
        /// Rebuilds the qualified snapshot from the latest valid evaluation of every candidate
        /// so revoked/rejected samples are excluded and kept samples are deduplicated.
        /// </summary>
        public int ExportQualifiedSamples(out int skippedNotQualified)
        {
            skippedNotQualified = 0;
            _exportedCandidateIds.Clear();
            Directory.CreateDirectory(RootDirectory);

            var sb = new StringBuilder();
            foreach (var candidate in _candidates)
            {
                var latest = GetLatestDecisionEvent(candidate.candidate_id);
                if (!IsCandidateQualifiedForExport(candidate, latest, out _))
                {
                    if (latest != null && latest.is_kept)
                        skippedNotQualified++;
                    continue;
                }

                var sample = new QualifiedSemanticSample
                {
                    sample_id = Guid.NewGuid().ToString("N"),
                    candidate_id = candidate.candidate_id,
                    session_id = candidate.session_id,
                    group_id = candidate.group_id,
                    raw_text = candidate.raw_text,
                    decision = candidate.decision,
                    plan_json = candidate.plan_json,
                    motion_tuning_json = candidate.motion_tuning_json,
                    native_json = candidate.native_json,
                    capability_profile = candidate.capability_profile,
                    motion_map_version = candidate.motion_map_version,
                    label_policy_version = candidate.label_policy_version,
                    semantic_match = latest.semantic_match,
                    naturalness_score = latest.naturalness_score,
                    exported_utc = DateTime.UtcNow.ToString("O")
                };
                sb.AppendLine(JsonUtility.ToJson(sample));
                _exportedCandidateIds.Add(candidate.candidate_id);
            }

            File.WriteAllText(QualifiedExportPath, sb.ToString(), Encoding.UTF8);
            return _exportedCandidateIds.Count;
        }

        /// <summary>
        /// Rebuilds qualified_action_config.jsonl from kept action-config.v0.2 candidates (and non-execute decisions).
        /// </summary>
        public int ExportQualifiedV02Configs(out int skippedNotQualified)
        {
            skippedNotQualified = 0;
            int count = 0;
            Directory.CreateDirectory(RootDirectory);

            var sb = new StringBuilder();
            foreach (var candidate in _candidates)
            {
                bool isV02 = !string.IsNullOrEmpty(candidate.plan_json) && candidate.plan_json.Contains("\"action-config.v0.2\"");
                if (!isV02) continue;

                var latest = GetLatestDecisionEvent(candidate.candidate_id);
                if (!IsCandidateQualifiedForExport(candidate, latest, out _))
                {
                    if (latest != null && latest.is_kept)
                        skippedNotQualified++;
                    continue;
                }

                string line = "{"
                    + "\"sample_id\":\"" + Guid.NewGuid().ToString("N") + "\","
                    + "\"candidate_id\":\"" + candidate.candidate_id + "\","
                    + "\"group_id\":\"" + (candidate.group_id ?? string.Empty) + "\","
                    + "\"raw_text\":" + QuoteJson(candidate.raw_text) + ","
                    + "\"source\":\"human_reviewed_candidate\","
                    + "\"capability_profile\":\"" + candidate.capability_profile + "\","
                    + "\"resource_catalog_version\":\"" + ActionResourceCatalog.DefaultCatalogVersion + "\","
                    + "\"parameter_schema_version\":\"action-config.v0.2\","
                    + "\"config\":" + candidate.plan_json + ","
                    + "\"native_json\":" + (string.IsNullOrEmpty(candidate.native_json) ? "null" : candidate.native_json) + ","
                    + "\"semantic_match\":\"" + latest.semantic_match + "\","
                    + "\"naturalness_score\":" + latest.naturalness_score + ","
                    + "\"exported_utc\":\"" + DateTime.UtcNow.ToString("O") + "\""
                    + "}";
                sb.AppendLine(line);
                count++;
            }

            File.WriteAllText(QualifiedV02ExportPath, sb.ToString(), Encoding.UTF8);
            return count;
        }

        private static string QuoteJson(string s)
        {
            if (s == null) return "\"\"";
            return "\"" + s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "\\r") + "\"";
        }
    }
}
