using System;
using System.Diagnostics;
using Live2D.Cubism.Core;
using Live2D.Cubism.Framework;
using UnityEngine;

namespace PetLive2d.ActionLanguage
{
    [DisallowMultipleComponent]
    public sealed class Live2DActionAdapter : MonoBehaviour, ICubismUpdatable
    {
        public const int AdapterExecutionOrder = 750;

        [SerializeField]
        private bool _showSubtitleOverlay = true;

        private CubismModel _model;
        private CubismUpdateController _updateController;
        private CubismParameterStore _parameterStore;

        private CapabilityProfile _profile;
        private HostSessionState _hostState;
        private ActionPlayer _player;

        private CubismParameter[] _boundParameters;
        private bool[] _isForegroundSlot;
        private float[] _baselineBuffer;
        private float[] _outputBuffer;

        private Func<double> _clockProviderMs;
        private int _nextAutoRequestSeq = 1;

        public int ExecutionOrder => AdapterExecutionOrder;
        public bool NeedsUpdateOnEditing => false;

        [HideInInspector]
        public bool HasUpdateController { get; set; }

        public bool IsBound => _player != null && _boundParameters != null;
        public ActionPlayer Player => _player;
        public CapabilityProfile Profile => _profile;
        public HostSessionState HostState => _hostState;
        public string CurrentSubtitle => _player?.CurrentSubtitle;

        public event Action<string> OnSubtitleChanged;

        public void SetClockProvider(Func<double> clockProviderMs)
        {
            _clockProviderMs = clockProviderMs ?? GetMonotonicTimeMs;
        }

        public double GetCurrentTimeMs()
        {
            if (_clockProviderMs == null)
            {
                _clockProviderMs = GetMonotonicTimeMs;
            }
            return _clockProviderMs();
        }

        public static double GetMonotonicTimeMs()
        {
            return Stopwatch.GetTimestamp() * 1000.0 / Stopwatch.Frequency;
        }

        public bool TryBind(
            CapabilityProfile profile,
            string sessionId,
            out ActionValidationError error)
        {
            error = null;
            if (profile == null)
            {
                error = new ActionValidationError("missing_profile", "$", "CapabilityProfile cannot be null.");
                return false;
            }

            _model = this.FindCubismModel();
            if (_model == null)
            {
                _model = GetComponent<CubismModel>();
            }

            if (_model == null)
            {
                error = new ActionValidationError("missing_cubism_model", "$", "CubismModel component was not found on this GameObject.");
                return false;
            }

            var modelParams = _model.Parameters;
            if (modelParams == null || modelParams.Length == 0)
            {
                error = new ActionValidationError("empty_model_parameters", "$", "CubismModel.Parameters is empty or not initialized.");
                return false;
            }

            int slotCount = profile.Parameters.Count;
            var boundParams = new CubismParameter[slotCount];
            var fgMask = new bool[slotCount];

            for (int slot = 0; slot < slotCount; slot++)
            {
                var def = profile.Parameters[slot];
                if (profile.IsPhysicsOutput(def.Id))
                {
                    error = new ActionValidationError("invalid_profile_physics_overlap", $"$.parameters.{def.Id}", $"Parameter '{def.Id}' is marked as physics output.");
                    return false;
                }

                CubismParameter found = null;
                for (int j = 0; j < modelParams.Length; j++)
                {
                    if (modelParams[j] != null && string.Equals(modelParams[j].Id, def.Id, StringComparison.Ordinal))
                    {
                        found = modelParams[j];
                        break;
                    }
                }

                if (found == null)
                {
                    error = new ActionValidationError("missing_model_parameter", $"$.parameters.{def.Id}", $"Parameter '{def.Id}' does not exist on CubismModel '{_model.name}'.");
                    return false;
                }

                if (Mathf.Abs(found.MinimumValue - def.Min) > 1e-3f ||
                    Mathf.Abs(found.MaximumValue - def.Max) > 1e-3f ||
                    Mathf.Abs(found.DefaultValue - def.DefaultValue) > 1e-3f)
                {
                    error = new ActionValidationError(
                        "profile_metadata_mismatch",
                        $"$.parameters.{def.Id}",
                        $"Profile range/default [{def.Min}, {def.Max}, default={def.DefaultValue}] does not match CubismParameter [{found.MinimumValue}, {found.MaximumValue}, default={found.DefaultValue}].");
                    return false;
                }

                boundParams[slot] = found;
                fgMask[slot] = (def.Owner == ParameterOwner.Foreground);
            }

            // Ensure CubismParameterStore is present & enabled so pre-200 baseline is saved/restored cleanly without double-restoring
            _parameterStore = _model.GetComponent<CubismParameterStore>();
            if (_parameterStore == null)
            {
                _parameterStore = _model.gameObject.AddComponent<CubismParameterStore>();
            }
            if (!_parameterStore.enabled)
            {
                _parameterStore.enabled = true;
            }
            _parameterStore.Refresh();

            _profile = profile;
            _boundParameters = boundParams;
            _isForegroundSlot = fgMask;
            _baselineBuffer = new float[slotCount];
            _outputBuffer = new float[slotCount];

            string instanceId = _model.GetInstanceID().ToString();
            if (_hostState == null)
            {
                _hostState = new HostSessionState(sessionId ?? "default-session", instanceId, profile.ProfileId, 1);
            }
            else
            {
                _hostState.RebindCharacter(instanceId, profile.ProfileId);
            }

            if (_player != null)
            {
                _player.OnSubtitleChanged -= HandleSubtitleChanged;
            }

            _player = new ActionPlayer(_profile, _hostState);
            _player.OnSubtitleChanged += HandleSubtitleChanged;

            if (_clockProviderMs == null)
            {
                _clockProviderMs = GetMonotonicTimeMs;
            }

            _updateController = _model.GetComponent<CubismUpdateController>();
            if (_updateController != null)
            {
                HasUpdateController = true;
                _updateController.Refresh();
            }

            return true;
        }

        public bool SubmitActionJson(string actionJson, out ActionValidationError error, string requestId = null, double? expiresAtMs = null)
        {
            if (!IsBound)
            {
                error = new ActionValidationError("adapter_not_bound", "$", "Live2DActionAdapter is not bound to a profile and model.");
                return false;
            }

            string reqId = string.IsNullOrEmpty(requestId)
                ? $"req-{_hostState.Generation}-{_nextAutoRequestSeq++}"
                : requestId;

            var ctx = _hostState.CreateRequestContext(reqId, expiresAtMs);
            return _player.Submit(actionJson, in ctx, GetCurrentTimeMs(), out error);
        }

        public bool SubmitActionJsonWithContext(string actionJson, in ActionRequestContext context, out ActionValidationError error)
        {
            if (!IsBound)
            {
                error = new ActionValidationError("adapter_not_bound", "$", "Live2DActionAdapter is not bound to a profile and model.");
                return false;
            }

            return _player.Submit(actionJson, in context, GetCurrentTimeMs(), out error);
        }

        public void CancelCurrentAction()
        {
            if (!IsBound) return;
            _player.Cancel(GetCurrentTimeMs());
        }

        public void PauseActionClock()
        {
            if (!IsBound) return;
            _player.Pause(GetCurrentTimeMs());
        }

        public void ResumeActionClock()
        {
            if (!IsBound) return;
            _player.Resume(GetCurrentTimeMs());
        }

        public float ReadCurrentParameterValue(string parameterId)
        {
            if (!IsBound || !_profile.TryGetParameter(parameterId, out var def))
            {
                return float.NaN;
            }
            return _boundParameters[def.SlotIndex].Value;
        }

        public void OnLateUpdate()
        {
            if (!HasUpdateController || !IsBound)
            {
                return;
            }

            StepSynthesis(GetCurrentTimeMs());
        }

        public void StepSynthesis(double nowMs)
        {
            if (!IsBound) return;

            int count = _boundParameters.Length;
            for (int i = 0; i < count; i++)
            {
                _baselineBuffer[i] = _boundParameters[i].Value;
            }

            _player.EvaluateFrame(nowMs, _baselineBuffer, _outputBuffer);

            for (int i = 0; i < count; i++)
            {
                if (_isForegroundSlot[i])
                {
                    _boundParameters[i].Value = _outputBuffer[i];
                }
            }
        }

        private void OnEnable()
        {
            if (_model == null)
            {
                _model = this.FindCubismModel();
            }
            if (_model != null)
            {
                _updateController = _model.GetComponent<CubismUpdateController>();
                if (_updateController != null)
                {
                    HasUpdateController = true;
                    _updateController.Refresh();
                }
            }
        }

        private void OnDestroy()
        {
            if (_player != null)
            {
                _player.OnSubtitleChanged -= HandleSubtitleChanged;
            }
        }

        private void HandleSubtitleChanged(string subtitle)
        {
            OnSubtitleChanged?.Invoke(subtitle);
        }

        private void OnGUI()
        {
            if (!_showSubtitleOverlay || !IsBound) return;
            string sub = _player.CurrentSubtitle;
            if (string.IsNullOrEmpty(sub)) return;

            var style = new GUIStyle(GUI.skin.box)
            {
                fontSize = 22,
                alignment = TextAnchor.MiddleCenter,
                wordWrap = true
            };
            style.normal.textColor = Color.white;

            float width = Mathf.Min(Screen.width - 80f, 640f);
            float height = 56f;
            float x = (Screen.width - width) * 0.5f;
            float y = Screen.height - height - 40f;

            GUI.Box(new Rect(x, y, width, height), sub, style);
        }
    }
}
