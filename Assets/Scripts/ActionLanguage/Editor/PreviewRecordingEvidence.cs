using System;
using System.Collections.Generic;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using Live2D.Cubism.Core;
using UnityEditor;
using UnityEngine;

namespace PetLive2d.ActionLanguage.Editor
{
    [Serializable]
    public sealed class PreviewEvidenceRecord
    {
        public string schema_version = "preview-evidence.v1";
        public string candidate_id, parent_candidate_id, input_role, raw_text_sha256;
        public string config_json, config_sha256, native_json, native_sha256;
        public string config_hash_encoding = "exact_utf8_plan_json";
        public string video_file = "preview.mp4", trajectory_file = "trajectory.jsonl";
        public string video_sha256, trajectory_sha256;
        public string resource_catalog_sha256, compiler_sha256, profile_sha256, compiled_assembly_sha256;
        public string resource_catalog_version = ActionResourceCatalog.DefaultCatalogVersion;
        public string parameter_schema_version = ActionConfigCompiler.SupportedVersion;
        public string persona_path, persona_sha256, character_asset_sha256;
        public string started_utc, completed_utc, capture_error;
        public string clock_mode = "fixed_step_edit_mode";
        public string resource_status = "preview_candidate_not_formal_calibration";
        public int fps, frame_count, native_duration_ms;
        public double last_player_time_ms;
        public bool compile_ok, playback_completed, encoder_closed;
        public bool source_hashes_unchanged, asset_hashes_unchanged;
        public string[] character_asset_paths;
    }

    [Serializable]
    internal sealed class PreviewParameterSample { public string id; public float value; }
    [Serializable]
    internal sealed class PreviewFrameSample
    {
        public int frame_index;
        public double video_time_ms, player_time_ms;
        public string state;
        public List<PreviewParameterSample> parameters = new List<PreviewParameterSample>();
    }

    /// <summary>Evidence only. Never writes an AI acceptance or fabricates historical versions.</summary>
    public sealed class PreviewRecordingEvidence : IDisposable
    {
        [Serializable] private sealed class NativeHeader { public int duration_ms; }
        public PreviewEvidenceRecord Record { get; }
        public string DirectoryPath { get; }
        private StreamWriter _trajectory;
        private readonly Dictionary<string, string> _sourceHashes = new Dictionary<string, string>();
        private readonly Dictionary<string, string> _assetHashes = new Dictionary<string, string>();
        private bool _finished;

        public PreviewRecordingEvidence(string directory, ActionCardCandidate candidate, CubismModel source, int fps)
        {
            DirectoryPath = directory;
            Directory.CreateDirectory(directory);
            Record = new PreviewEvidenceRecord {
                candidate_id = candidate.candidate_id, parent_candidate_id = candidate.parent_candidate_id,
                input_role = candidate.input_role, raw_text_sha256 = HashText(candidate.raw_text),
                config_json = candidate.plan_json, config_sha256 = HashText(candidate.plan_json),
                native_json = candidate.native_json, native_sha256 = HashText(candidate.native_json),
                compile_ok = candidate.compile_ok, fps = fps, started_utc = DateTime.UtcNow.ToString("o"),
                compiler_sha256 = BindSource("Assets/Scripts/ActionLanguage/ActionConfigCompiler.cs"),
                resource_catalog_sha256 = BindSource("Assets/Scripts/ActionLanguage/ActionResourceCatalog.cs"),
                profile_sha256 = BindSource("Assets/Scripts/ActionLanguage/YukikazeActionCatalog.cs"),
                compiled_assembly_sha256 = BindSource(typeof(ActionConfigCompiler).Assembly.Location),
                persona_path = "Docs/ActionLanguage/personas/gemini-cyber-cat.md"
            };
            BindSource("Assets/Scripts/ActionLanguage/ActionContract.cs");
            BindSource("Assets/Scripts/ActionLanguage/ActionPlayer.cs");
            BindSource("Assets/Scripts/ActionLanguage/Live2DActionAdapter.cs");
            BindSource("Assets/Scripts/ActionLanguage/Editor/PreviewSession.cs");
            BindSource(typeof(PreviewSession).Assembly.Location);
            Record.persona_sha256 = BindSource(Record.persona_path);
            Record.native_duration_ms = JsonUtility.FromJson<NativeHeader>(candidate.native_json).duration_ms;

            var paths = new SortedSet<string>(StringComparer.Ordinal);
            var prefab = PrefabUtility.GetCorrespondingObjectFromOriginalSource(source.gameObject);
            string assetPath = prefab != null ? AssetDatabase.GetAssetPath(prefab) : AssetDatabase.GetAssetPath(source.Moc);
            if (!string.IsNullOrEmpty(assetPath))
                foreach (string path in AssetDatabase.GetDependencies(assetPath, true))
                    if (File.Exists(path)) paths.Add(path);
            // Include live renderer assets even when the source has scene material overrides.
            foreach (var renderer in source.GetComponentsInChildren<Renderer>(true))
                foreach (var material in renderer.sharedMaterials)
                    if (material != null && !string.IsNullOrEmpty(AssetDatabase.GetAssetPath(material)))
                        foreach (string path in AssetDatabase.GetDependencies(AssetDatabase.GetAssetPath(material), true))
                            if (File.Exists(path)) paths.Add(path);
            foreach (string path in paths) _assetHashes[path] = HashFile(path);
            Record.character_asset_paths = new List<string>(paths).ToArray();
            Record.character_asset_sha256 = HashBindings(_assetHashes);
            if (paths.Count == 0) Record.capture_error = "character_asset_binding_missing";
            if (EditorApplication.isCompiling || EditorApplication.isUpdating) Record.capture_error = "editor_sources_not_stable";
            _trajectory = new StreamWriter(new FileStream(Path.Combine(directory, Record.trajectory_file), FileMode.CreateNew, FileAccess.Write), new UTF8Encoding(false));
            Save();
        }

        private string BindSource(string path)
        {
            string hash = HashFile(path);
            _sourceHashes[path] = hash;
            return hash;
        }

        public void Append(CubismModel model, double playerTimeMs, string state)
        {
            if (_finished) throw new InvalidOperationException("Recording is already closed.");
            var frame = new PreviewFrameSample { frame_index = Record.frame_count,
                video_time_ms = Record.frame_count * 1000.0 / Record.fps, player_time_ms = playerTimeMs, state = state };
            foreach (var parameter in model.Parameters)
                if (parameter != null) frame.parameters.Add(new PreviewParameterSample { id = parameter.Id, value = parameter.Value });
            _trajectory.WriteLine(JsonUtility.ToJson(frame));
            Record.frame_count++;
            Record.last_player_time_ms = playerTimeMs;
        }

        public void Finish(bool completed, bool encoderClosed, string error)
        {
            if (_finished) return;
            _finished = true;
            _trajectory?.Dispose();
            _trajectory = null;
            Record.playback_completed = completed;
            Record.encoder_closed = encoderClosed;
            if (!string.IsNullOrEmpty(error)) Record.capture_error = error;
            Record.source_hashes_unchanged = BindingsUnchanged(_sourceHashes) && !EditorApplication.isCompiling && !EditorApplication.isUpdating;
            Record.asset_hashes_unchanged = _assetHashes.Count > 0 && BindingsUnchanged(_assetHashes);
            Record.video_sha256 = HashFile(Path.Combine(DirectoryPath, Record.video_file));
            Record.trajectory_sha256 = HashFile(Path.Combine(DirectoryPath, Record.trajectory_file));
            Record.completed_utc = DateTime.UtcNow.ToString("o");
            Save();
        }

        public bool IsComplete => _finished && Record.playback_completed && Record.encoder_closed &&
            string.IsNullOrEmpty(Record.capture_error) && Record.frame_count > 1 &&
            Record.last_player_time_ms >= Record.native_duration_ms &&
            Record.source_hashes_unchanged && Record.asset_hashes_unchanged && !string.IsNullOrEmpty(Record.video_sha256);

        private void Save() => File.WriteAllText(Path.Combine(DirectoryPath, "evidence.json"), JsonUtility.ToJson(Record, true), new UTF8Encoding(false));
        private static bool BindingsUnchanged(Dictionary<string, string> bindings)
        {
            foreach (var pair in bindings) if (string.IsNullOrEmpty(pair.Value) || HashFile(pair.Key) != pair.Value) return false;
            return true;
        }
        private static string HashBindings(Dictionary<string, string> bindings)
        {
            var lines = new List<string>();
            foreach (var pair in bindings) lines.Add(pair.Key.Replace('\\', '/') + ":" + pair.Value);
            lines.Sort(StringComparer.Ordinal);
            return HashText(string.Join("\n", lines));
        }
        public static string HashText(string value)
        {
            using (var hash = SHA256.Create()) return BitConverter.ToString(hash.ComputeHash(Encoding.UTF8.GetBytes(value ?? ""))).Replace("-", "").ToLowerInvariant();
        }
        public static string HashFile(string path)
        {
            if (string.IsNullOrEmpty(path) || !File.Exists(path)) return "";
            using (var stream = File.OpenRead(path))
            using (var hash = SHA256.Create()) return BitConverter.ToString(hash.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
        }
        public void Dispose() { if (!_finished) Finish(false, false, "recording_disposed_before_completion"); }
    }
}
