using System;
using System.IO;
using System.Text;
using Live2D.Cubism.Core;
using Live2D.Cubism.Framework;
using Live2D.Cubism.Framework.LookAt;
using Live2D.Cubism.Framework.Motion;
using Live2D.Cubism.Framework.Physics;
using UnityEditor;
using UnityEditor.Media;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace PetLive2d.ActionLanguage.Editor
{
    /// <summary>
    /// Manages an isolated DontSave clone of the scene Yukikaze instance, dedicated preview camera/RT,
    /// deterministic clock, and cancellation/release lifecycle for ActionReviewWindow.
    /// </summary>
    public sealed class PreviewSession : IDisposable
    {
        public PreviewPlayState State { get; private set; } = PreviewPlayState.Idle;
        public string StatusDetail { get; private set; } = "未初始化";
        public RenderTexture PreviewTexture { get; private set; }
        public GameObject PreviewRoot { get; private set; }
        public Live2DActionAdapter Adapter { get; private set; }
        public ActionPlanReceiver Receiver { get; private set; }
        public CapabilityProfile Profile { get; private set; }

        public bool IsReady => PreviewRoot != null && Adapter != null && Adapter.IsBound && Receiver != null;
        public int RequestGeneration { get; private set; }
        public bool LastCaptureSucceeded { get; private set; }
        public string LastEvidencePath { get; private set; }
        public bool IsRecording => _isCapturingVideo;

        private CubismModel _sourceModel;
        private CubismModel _previewModel;
        private CubismUpdateController _updateController;
        private Camera _previewCamera;
        private Scene _previewScene;
        private ActionCardCandidate _activeCandidate;
        private Action<ActionCardCandidate> _onPlaybackCompleted;
        private Action<ActionCardCandidate, bool, bool> _onCompileOutcome;
        private double _simClockMs;
        private double _lastEditorTime;
        private bool _wasPlaying;
        private ulong _startedCompletionVersion, _startedInterruptionVersion;
        private bool _pendingReplayAfterRelease;
        private ActionCardCandidate _queuedAfterReleaseCandidate;

        private const int CaptureFps = 30;
        private const int PreviewWidth = 720, PreviewHeight = 840;
        private MediaEncoder _mediaEncoder;
        private Texture2D _captureTex;
        private bool _isCapturingVideo;
        private string _snapshotRoot;
        private double _recordingStartMs;
        private PreviewRecordingEvidence _evidence;

        public void Initialize(
            CubismModel sourceModel,
            Action<ActionCardCandidate> onPlaybackCompleted,
            Action<ActionCardCandidate, bool, bool> onCompileOutcome = null,
            string snapshotRoot = null)
        {
            Dispose();
            if (sourceModel == null)
                throw new ArgumentNullException(nameof(sourceModel));

            _sourceModel = sourceModel;
            _snapshotRoot = Path.GetFullPath(snapshotRoot ?? Path.Combine(Directory.GetCurrentDirectory(), "Dataset", "ActionCards", "snapshots"));
            _onPlaybackCompleted = onPlaybackCompleted;
            _onCompileOutcome = onCompileOutcome;
            Profile = YukikazeActionCatalog.CreateProfile();

            // A spatial offset alone is not isolation: multiple review/batch sessions
            // occupy that same location. Give each camera its own editor preview scene.
            _previewScene = EditorSceneManager.NewPreviewScene();
            PreviewRoot = new GameObject("__YukikazeReviewPreviewRoot")
            {
                hideFlags = HideFlags.HideAndDontSave
            };
            SceneManager.MoveGameObjectToScene(PreviewRoot, _previewScene);
            PreviewRoot.transform.position = new Vector3(1000f, 0f, 0f);

            var clone = UnityEngine.Object.Instantiate(sourceModel.gameObject, PreviewRoot.transform);
            clone.name = "__YukikazePreviewModel";
            SetHideFlagsRecursive(clone, HideFlags.HideAndDontSave);
            clone.transform.localPosition = Vector3.zero;
            clone.transform.localRotation = Quaternion.identity;
            clone.transform.localScale = sourceModel.transform.localScale;

            DisableCompetingControllers(clone);

            _previewModel = clone.GetComponent<CubismModel>();
            _updateController = clone.GetComponent<CubismUpdateController>();

            Adapter = clone.GetComponent<Live2DActionAdapter>() ?? clone.AddComponent<Live2DActionAdapter>();
            Receiver = clone.GetComponent<ActionPlanReceiver>() ?? clone.AddComponent<ActionPlanReceiver>();

            _simClockMs = 0.0;
            _lastEditorTime = EditorApplication.timeSinceStartup;
            Adapter.SetClockProvider(() => _simClockMs);

            if (!Adapter.TryBind(Profile, "review-session-" + Guid.NewGuid().ToString("N").Substring(0, 8), out var bindErr))
            {
                State = PreviewPlayState.Failed;
                StatusDetail = $"绑定失败: {bindErr?.Code} - {bindErr?.Message}";
                return;
            }

            ResetModelToReferencePose();

            Receiver.Configure(YukikazeActionCatalog.CreateMotionMap());
            Receiver.ConfigureCatalog(ActionResourceCatalog.CreateYukikazeV02());
            _updateController?.Refresh();

            SetupPreviewCamera(clone);
            RenderPreviewFrame();

            State = PreviewPlayState.Idle;
            StatusDetail = $"已绑定隔离实例（源自 {sourceModel.name}）";
        }

        public int NextGeneration()
        {
            RequestGeneration++;
            return RequestGeneration;
        }

        public void CancelCurrentAndReset(string reason = "cancelled")
        {
            StopVideoCapture(false, reason);
            _pendingReplayAfterRelease = false;
            _queuedAfterReleaseCandidate = null;
            _wasPlaying = false;
            Receiver?.CancelPending();
            if (Adapter != null && Adapter.IsBound)
            {
                Adapter.CancelCurrentAction();
            }
            State = PreviewPlayState.Cancelled;
            StatusDetail = reason;
        }

        public bool TryPlayCandidate(ActionCardCandidate candidate, out string errorMessage)
        {
            errorMessage = null;
            if (!IsReady)
            {
                errorMessage = "预览实例未就绪，请先选择场景中的 Yukikaze。";
                return false;
            }
            if (candidate == null)
            {
                errorMessage = "候选为空。";
                return false;
            }
            if (string.IsNullOrWhiteSpace(candidate.candidate_id) ||
                candidate.candidate_id.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 ||
                candidate.candidate_id == "." || candidate.candidate_id == "..")
            {
                errorMessage = "invalid_candidate_id";
                return false;
            }
            if (candidate.decision == "execute" && Directory.Exists(GetSnapshotDir(candidate.candidate_id)))
            {
                errorMessage = "immutable_snapshot: 请创建新 candidate_id 重播，旧视频不会被覆盖。";
                return false;
            }
            if (candidate.decision == "execute" && EditorApplication.isPlaying)
            {
                errorMessage = "完整证据录制需要 Edit Mode；请退出 Play Mode 后重播。";
                return false;
            }

            if (candidate.decision == "none" || candidate.decision == "unsupported" || candidate.decision == "ambiguous")
            {
                CancelCurrentAndReset($"非执行结果: {candidate.decision}");
                _activeCandidate = candidate;
                bool isV02NonExec = !string.IsNullOrEmpty(candidate.plan_json) && candidate.plan_json.Contains("\"action-config.v0.2\"");
                if (isV02NonExec)
                    Receiver.ConfigureCatalog(ActionResourceCatalog.CreateYukikazeV02());
                ActionValidationError nonExecErr;
                bool nonExecOk = isV02NonExec
                    ? Receiver.TryQueueConfigJson(candidate.plan_json, HostExecutionMode.PreviewCandidate, out _, out nonExecErr)
                    : Receiver.TryQueuePlanJson(candidate.plan_json, out _, out nonExecErr);
                if (!nonExecOk)
                {
                    candidate.compile_ok = false;
                    candidate.compile_error_code = nonExecErr?.Code ?? "invalid_non_execute";
                    candidate.compile_error_message = nonExecErr?.Message ?? "Invalid non-execute plan.";
                    candidate.playback_status = "compile_failed";
                    State = PreviewPlayState.Failed;
                    errorMessage = $"{candidate.compile_error_code}: {candidate.compile_error_message}";
                    StatusDetail = "非执行结构校验失败: " + errorMessage;
                    _onCompileOutcome?.Invoke(candidate, false, true);
                    return false;
                }
                candidate.compile_ok = true;
                candidate.compile_error_code = string.Empty;
                candidate.compile_error_message = string.Empty;
                candidate.playback_status = "non_execute_ready";
                State = PreviewPlayState.NonExecuteReady;
                StatusDetail = $"非执行判定 ({candidate.decision})，已清理旧动作且不触发动画。";
                _onCompileOutcome?.Invoke(candidate, true, true);
                return true;
            }

            // If currently playing or releasing, cancel and queue after release/reset.
            if (IsTrackBusy())
            {
                StopVideoCapture(false, "superseded_by_new_candidate");
                _wasPlaying = false;
                Receiver.CancelPending();
                Adapter.CancelCurrentAction();
                _pendingReplayAfterRelease = true;
                _queuedAfterReleaseCandidate = candidate;
                State = PreviewPlayState.Releasing;
                StatusDetail = "正在取消旧动作并等待释放回参考姿态...";
                return true;
            }

            return StartCandidateImmediate(candidate, out errorMessage);
        }

        private bool StartCandidateImmediate(ActionCardCandidate candidate, out string errorMessage)
        {
            errorMessage = null;
            _activeCandidate = candidate;
            _wasPlaying = false;
            ResetModelToReferencePose();

            YukikazeMotionTuning tuning = null;
            if (!string.IsNullOrEmpty(candidate.motion_tuning_json))
            {
                try { tuning = JsonUtility.FromJson<YukikazeMotionTuning>(candidate.motion_tuning_json); }
                catch { tuning = new YukikazeMotionTuning(); }
            }

            var map = YukikazeActionCatalog.CreateMotionMap(tuning);
            Receiver.Configure(map);
            Receiver.ConfigureCatalog(ActionResourceCatalog.CreateYukikazeV02());

            State = PreviewPlayState.Validating;
            bool isV02Config = !string.IsNullOrEmpty(candidate.plan_json) && candidate.plan_json.Contains("\"action-config.v0.2\"");
            ActionPlanCompilation compilation;
            ActionValidationError valErr;
            bool queued = isV02Config
                ? Receiver.TryQueueConfigJson(candidate.plan_json, HostExecutionMode.PreviewCandidate, out compilation, out valErr)
                : Receiver.TryQueuePlanJson(candidate.plan_json, out compilation, out valErr);
            if (!queued)
            {
                candidate.compile_ok = false;
                candidate.compile_error_code = valErr?.Code ?? "compile_failed";
                candidate.compile_error_message = valErr?.Message ?? "Compilation failed.";
                candidate.playback_status = "compile_failed";
                State = PreviewPlayState.Failed;
                errorMessage = $"{candidate.compile_error_code}: {candidate.compile_error_message}";
                StatusDetail = "编译/校验失败: " + errorMessage;
                _onCompileOutcome?.Invoke(candidate, false, false);
                return false;
            }

            candidate.compile_ok = true;
            candidate.compile_error_code = string.Empty;
            candidate.compile_error_message = string.Empty;
            candidate.native_json = compilation.NativeJson;
            _onCompileOutcome?.Invoke(candidate, true, false);

            State = PreviewPlayState.Queued;
            if (!Receiver.TryCommitPending(out var commitErr))
            {
                candidate.playback_status = "commit_failed";
                State = PreviewPlayState.Failed;
                errorMessage = $"{commitErr?.Code}: {commitErr?.Message}";
                StatusDetail = "提交失败: " + errorMessage;
                return false;
            }

            candidate.playback_status = "submitted";
            State = PreviewPlayState.Submitted;
            StatusDetail = "已提交，正在播放...";

            // Commit the pending action at this exact clock before recording frame zero.
            StepEditModeCubismPipeline();
            _wasPlaying = Adapter.Player.HasActiveForeground;
            _startedCompletionVersion = Adapter.Player.NaturalCompletionVersion;
            _startedInterruptionVersion = Adapter.Player.InterruptionVersion;
            if (!_wasPlaying)
            {
                errorMessage = "playback_did_not_start";
                State = PreviewPlayState.Failed;
                return false;
            }
            if (!StartVideoCapture(candidate, out errorMessage))
            {
                Adapter.CancelCurrentAction();
                _wasPlaying = false;
                State = PreviewPlayState.Failed;
                candidate.playback_status = "recording_failed";
                return false;
            }
            return true;
        }

        public void Tick()
        {
            double now = EditorApplication.timeSinceStartup;
            // During capture one simulation step produces one video frame, independent
            // of editor wall-clock stalls. The trajectory records the exact player time.
            double dtMs = _isCapturingVideo ? 1000.0 / CaptureFps : Math.Max(0.0, Math.Min(50.0, (now - _lastEditorTime) * 1000.0));
            _lastEditorTime = now;
            _simClockMs += dtMs;

            if (!IsReady) return;

            if (!EditorApplication.isPlaying && PreviewRoot != null)
            {
                StepEditModeCubismPipeline();
            }

            var player = Adapter.Player;
            bool anyReleasing = AnyChannelReleasing(player);

            if (player.HasActiveForeground)
            {
                _wasPlaying = true;
                State = PreviewPlayState.Playing;
                if (_activeCandidate != null) _activeCandidate.playback_status = "playing";
                StatusDetail = "播放中...";
            }
            else if (anyReleasing)
            {
                State = PreviewPlayState.Releasing;
                StatusDetail = "动作结束，释放回基线中...";
            }
            else
            {
                if (_pendingReplayAfterRelease && _queuedAfterReleaseCandidate != null)
                {
                    var next = _queuedAfterReleaseCandidate;
                    _pendingReplayAfterRelease = false;
                    _queuedAfterReleaseCandidate = null;
                    StartCandidateImmediate(next, out _);
                    return;
                }
                else if (_wasPlaying)
                {
                    _wasPlaying = false;
                    if (player.NaturalCompletionVersion != _startedCompletionVersion + 1 ||
                        player.InterruptionVersion != _startedInterruptionVersion)
                    {
                        State = PreviewPlayState.Failed;
                        StatusDetail = "播放被外部取消、替换或中断，录像证据无效";
                        StopVideoCapture(false, "playback_interrupted");
                        if (_activeCandidate != null)
                        {
                            var interrupted = _activeCandidate;
                            interrupted.playback_status = "interrupted";
                            interrupted.playback_completed = false;
                            WriteSnapshotMeta(interrupted);
                            _activeCandidate = null;
                            _onPlaybackCompleted?.Invoke(interrupted);
                        }
                        return;
                    }
                    State = PreviewPlayState.Completed;
                    StatusDetail = "完整播放完成";
                    if (_activeCandidate != null)
                    {
                        _activeCandidate.playback_status = "completed";
                        _activeCandidate.playback_completed = true;
                    }
                }
            }

            RenderPreviewFrame();

            if (_isCapturingVideo)
            {
                AppendVideoFrame();
            }
            if (State == PreviewPlayState.Completed && _activeCandidate != null)
            {
                var completed = _activeCandidate;
                // The completion callback may start/dispose another session. Finalize
                // the final return-to-baseline frame, encoder and files before invoking it.
                StopVideoCapture(true);
                WriteSnapshotMeta(completed);
                _activeCandidate = null;
                _onPlaybackCompleted?.Invoke(completed);
            }
        }

        private void StepEditModeCubismPipeline()
        {
            if (_previewModel == null) return;
            var updatables = _previewModel.GetComponents<ICubismUpdatable>();
            Array.Sort(updatables, (a, b) => a.ExecutionOrder.CompareTo(b.ExecutionOrder));
            bool forcedModelUpdate = false;
            for (int i = 0; i < updatables.Length; i++)
            {
                var u = updatables[i];
                if (u is Behaviour b && !b.enabled) continue;
                bool isActionComponent = u is ActionPlanReceiver || u is Live2DActionAdapter;
                if (!u.NeedsUpdateOnEditing && !isActionComponent) continue;

                // Ensure CubismModel pushes updated parameter values to drawable meshes before rendering.
                if (!forcedModelUpdate && u.ExecutionOrder > Live2DActionAdapter.AdapterExecutionOrder)
                {
                    _previewModel.ForceUpdateNow();
                    forcedModelUpdate = true;
                }

                u.OnLateUpdate();
            }
            if (!forcedModelUpdate)
            {
                _previewModel.ForceUpdateNow();
            }
        }

        private bool IsTrackBusy()
        {
            if (Adapter == null || !Adapter.IsBound) return false;
            var p = Adapter.Player;
            if (p.HasPendingSubmission || p.HasActiveForeground) return true;
            return AnyChannelReleasing(p);
        }

        private bool AnyChannelReleasing(ActionPlayer player)
        {
            for (int i = 0; i < Profile.Parameters.Count; i++)
            {
                if (player.IsChannelReleasing(i)) return true;
            }
            return false;
        }

        private void ResetModelToReferencePose()
        {
            if (_previewModel == null || _previewModel.Parameters == null) return;
            foreach (var p in _previewModel.Parameters)
            {
                if (p != null) p.Value = p.DefaultValue;
            }
        }

        private void SetupPreviewCamera(GameObject clone)
        {
            var camGo = new GameObject("__YukikazePreviewCamera")
            {
                hideFlags = HideFlags.HideAndDontSave
            };
            camGo.transform.SetParent(PreviewRoot.transform, false);

            Vector3 focusWorld = clone.transform.position + new Vector3(0f, 0.08f, 0f);
            float orthoSize = 0.72f;
            var renderers = clone.GetComponentsInChildren<Renderer>(true);
            bool hasBounds = false;
            Bounds combined = default;
            foreach (var r in renderers)
            {
                if (r == null || !r.enabled) continue;
                if (!hasBounds) { combined = r.bounds; hasBounds = true; }
                else combined.Encapsulate(r.bounds);
            }
            if (hasBounds && combined.size.y > 0.01f)
            {
                // Evidence must show hands and the return pose, not a cropped bust.
                // Keep a fixed camera with room for motion; never track the animation.
                focusWorld = combined.center;
                float aspect = (float)PreviewWidth / PreviewHeight;
                orthoSize = Mathf.Max(0.25f, Mathf.Max(combined.extents.y, combined.extents.x / aspect) * 1.15f);
            }

            camGo.transform.position = new Vector3(focusWorld.x, focusWorld.y, focusWorld.z - 10f);
            camGo.transform.rotation = Quaternion.identity;

            _previewCamera = camGo.AddComponent<Camera>();
            _previewCamera.scene = _previewScene;
            _previewCamera.orthographic = true;
            _previewCamera.orthographicSize = orthoSize;
            _previewCamera.nearClipPlane = 0.1f;
            _previewCamera.farClipPlane = 50f;
            _previewCamera.clearFlags = CameraClearFlags.SolidColor;
            _previewCamera.backgroundColor = new Color(0.11f, 0.12f, 0.16f, 1f);
            _previewCamera.enabled = false;

            PreviewTexture = new RenderTexture(PreviewWidth, PreviewHeight, 16, RenderTextureFormat.ARGB32)
            {
                hideFlags = HideFlags.HideAndDontSave
            };
            PreviewTexture.Create();
            _previewCamera.targetTexture = PreviewTexture;
        }

        private void RenderPreviewFrame()
        {
            if (_previewCamera != null && PreviewTexture != null)
            {
                _previewCamera.Render();
            }
        }

        private string GetSnapshotDir(string candidateId)
        {
            return Path.Combine(_snapshotRoot, candidateId);
        }

        private void WriteSnapshotMeta(ActionCardCandidate candidate)
        {
            if (candidate == null || string.IsNullOrEmpty(candidate.candidate_id)) return;
            try
            {
                string dir = GetSnapshotDir(candidate.candidate_id);
                Directory.CreateDirectory(dir);
                string meta = JsonUtility.ToJson(candidate, true);
                File.WriteAllText(Path.Combine(dir, "meta.json"), meta, new UTF8Encoding(false));
            }
            catch (Exception ex)
            {
                Debug.LogWarning("[PreviewSession] Failed to write snapshot meta: " + ex.Message);
            }
        }

        private bool StartVideoCapture(ActionCardCandidate candidate, out string error)
        {
            error = null;
            StopVideoCapture(false, "superseded");
            LastCaptureSucceeded = false;
            LastEvidencePath = null;
            if (candidate == null || string.IsNullOrEmpty(candidate.candidate_id) || PreviewTexture == null)
            { error = "capture_not_ready"; return false; }
            try
            {
                string dir = GetSnapshotDir(candidate.candidate_id);
                if (Directory.Exists(dir)) throw new IOException("immutable_snapshot: " + dir);
                Directory.CreateDirectory(dir);
                WriteSnapshotMeta(candidate);
                _evidence = new PreviewRecordingEvidence(dir, candidate, _sourceModel, CaptureFps);
                LastEvidencePath = Path.Combine(dir, "evidence.json");

                var videoAttr = new VideoTrackAttributes
                {
                    bitRateMode = VideoBitrateMode.Medium,
                    frameRate = new MediaRational(CaptureFps, 1),
                    width = (uint)PreviewTexture.width,
                    height = (uint)PreviewTexture.height,
                    includeAlpha = false
                };
                string mp4Path = Path.Combine(dir, "preview.mp4");
                _mediaEncoder = new MediaEncoder(mp4Path, videoAttr);
                _captureTex = new Texture2D(PreviewTexture.width, PreviewTexture.height, TextureFormat.RGBA32, false);
                _recordingStartMs = _simClockMs;
                _isCapturingVideo = true;
                RenderPreviewFrame();
                AppendVideoFrame();
                if (!_isCapturingVideo) error = "recording_initial_frame_failed";
                return _isCapturingVideo;
            }
            catch (Exception ex)
            {
                Debug.LogWarning("[PreviewSession] Failed to start MP4 capture: " + ex.Message);
                error = "recording_start_failed: " + ex.Message;
                StopVideoCapture(false, error);
                return false;
            }
        }

        private void AppendVideoFrame()
        {
            if (!_isCapturingVideo || _mediaEncoder == null || _captureTex == null || PreviewTexture == null) return;
            RenderTexture prevActive = RenderTexture.active;
            try
            {
                RenderTexture.active = PreviewTexture;
                _captureTex.ReadPixels(new Rect(0, 0, PreviewTexture.width, PreviewTexture.height), 0, 0);
                _captureTex.Apply();
                _mediaEncoder.AddFrame(_captureTex);
                _evidence.Append(_previewModel, _simClockMs - _recordingStartMs, State.ToString());
            }
            catch (Exception ex)
            {
                Debug.LogWarning("[PreviewSession] Failed to append MP4 frame: " + ex.Message);
                StopVideoCapture(false, "recording_frame_failed: " + ex.Message);
            }
            finally
            {
                RenderTexture.active = prevActive;
            }
        }

        private void StopVideoCapture(bool completed = false, string error = null)
        {
            _isCapturingVideo = false;
            bool closed = false;
            if (_mediaEncoder != null)
            {
                try { _mediaEncoder.Dispose(); closed = true; }
                catch (Exception ex) { error = "encoder_close_failed: " + ex.Message; }
                _mediaEncoder = null;
            }
            if (_evidence != null)
            {
                try
                {
                    _evidence.Finish(completed, closed, error);
                    LastCaptureSucceeded = _evidence.IsComplete;
                }
                catch (Exception ex)
                {
                    LastCaptureSucceeded = false;
                    Debug.LogWarning("[PreviewSession] Evidence finalization failed: " + ex.Message);
                }
                _evidence = null;
            }
            if (_captureTex != null)
            {
                UnityEngine.Object.DestroyImmediate(_captureTex);
                _captureTex = null;
            }
        }

        private static void DisableCompetingControllers(GameObject clone)
        {
            DisableComponent<CubismAutoEyeBlinkInput>(clone);
            DisableComponent<CubismEyeBlinkController>(clone);
            DisableComponent<CubismLookController>(clone);
            DisableComponent<Animator>(clone);
            // Keep CubismPhysicsController, CubismPoseController, CubismUpdateController, CubismRenderController.
        }

        private static void DisableComponent<T>(GameObject go) where T : Behaviour
        {
            var comp = go.GetComponent<T>();
            if (comp != null) comp.enabled = false;
        }

        private static void SetHideFlagsRecursive(GameObject go, HideFlags flags)
        {
            go.hideFlags = flags;
            foreach (Transform child in go.transform)
            {
                SetHideFlagsRecursive(child.gameObject, flags);
            }
        }

        public void Dispose()
        {
            StopVideoCapture();
            _pendingReplayAfterRelease = false;
            _queuedAfterReleaseCandidate = null;
            _activeCandidate = null;

            if (_previewCamera != null)
            {
                _previewCamera.targetTexture = null;
                _previewCamera = null;
            }
            if (PreviewTexture != null)
            {
                PreviewTexture.Release();
                UnityEngine.Object.DestroyImmediate(PreviewTexture);
                PreviewTexture = null;
            }
            if (PreviewRoot != null)
            {
                UnityEngine.Object.DestroyImmediate(PreviewRoot);
                PreviewRoot = null;
            }
            if (_previewScene.IsValid())
            {
                EditorSceneManager.ClosePreviewScene(_previewScene);
                _previewScene = default;
            }
            Adapter = null;
            Receiver = null;
            _previewModel = null;
            _updateController = null;
        }
    }
}
