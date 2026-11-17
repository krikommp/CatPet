using System;

namespace PetLive2d.ActionLanguage
{
    public sealed class ActionPlayer
    {
        private struct ReleaseChannelState
        {
            public bool IsActive;
            public float StartValue;
            public double StartTimeMs;
        }

        private readonly struct PendingSubmission
        {
            public CompiledActionPacket Packet { get; }
            public ActionRequestContext RequestContext { get; }

            public PendingSubmission(CompiledActionPacket packet, ActionRequestContext requestContext)
            {
                Packet = packet;
                RequestContext = requestContext;
            }
        }

        private sealed class ActiveActionState
        {
            public CompiledActionPacket Packet { get; }
            public double StartTimeMs { get; }
            public float[] InitialValues { get; }

            public ActiveActionState(CompiledActionPacket packet, double startTimeMs, float[] initialValues)
            {
                Packet = packet;
                StartTimeMs = startTimeMs;
                InitialValues = initialValues;
            }
        }

        private CapabilityProfile _profile;
        private HostSessionState _hostState;
        private int _slotCount;

        private PendingSubmission? _pendingSubmission;
        private ActiveActionState _activeAction;
        private ReleaseChannelState[] _releasing;
        private bool[] _activeMaskScratch;

        private float[] _lastAppliedCompositeValues;
        private bool _hasSynthesizedHistory;

        private bool _isPaused;
        private double _pauseStartRawMs;
        private double _accumulatedPausedMs;

        public string CurrentSubtitle { get; private set; }
        public bool HasActiveForeground => _activeAction != null;
        public bool HasPendingSubmission => _pendingSubmission.HasValue;
        public bool IsPaused => _isPaused;
        public CapabilityProfile Profile => _profile;
        public HostSessionState HostState => _hostState;

        public event Action<string> OnSubtitleChanged;

        public ActionPlayer(CapabilityProfile profile, HostSessionState hostState)
        {
            Bind(profile, hostState);
        }

        public void Bind(CapabilityProfile profile, HostSessionState hostState)
        {
            _profile = profile ?? throw new ArgumentNullException(nameof(profile));
            _hostState = hostState ?? throw new ArgumentNullException(nameof(hostState));
            _slotCount = _profile.Parameters.Count;

            _pendingSubmission = null;
            _activeAction = null;
            _releasing = new ReleaseChannelState[_slotCount];
            _activeMaskScratch = new bool[_slotCount];
            _lastAppliedCompositeValues = new float[_slotCount];
            _hasSynthesizedHistory = false;

            _isPaused = false;
            _pauseStartRawMs = 0.0;
            _accumulatedPausedMs = 0.0;

            SetSubtitle(null);
        }

        public void SwitchModel(CapabilityProfile newProfile, string newCharacterInstanceId)
        {
            if (newProfile == null) throw new ArgumentNullException(nameof(newProfile));
            _hostState.RebindCharacter(newCharacterInstanceId, newProfile.ProfileId);
            Bind(newProfile, _hostState);
        }

        public bool Submit(
            string json,
            in ActionRequestContext requestContext,
            double nowMs,
            out ActionValidationError error)
        {
            if (!ActionContract.TryValidateAndCompile(
                json,
                _profile,
                in requestContext,
                _hostState,
                nowMs,
                out var compiledPacket,
                out error))
            {
                // Validation failure must NOT interrupt current action or subtitle.
                return false;
            }

            _pendingSubmission = new PendingSubmission(compiledPacket, requestContext);
            error = null;
            return true;
        }

        public void Cancel(double nowMs)
        {
            _pendingSubmission = null;

            // Idempotent when no active foreground action: do NOT reset in-progress release timers.
            if (_activeAction == null)
            {
                return;
            }

            double effectiveNowMs = GetEffectiveTimeMs(nowMs);
            var curves = _activeAction.Packet.Curves;
            for (int i = 0; i < curves.Length; i++)
            {
                int slot = curves[i].ProfileSlotIndex;
                float releaseStartVal = _hasSynthesizedHistory
                    ? _lastAppliedCompositeValues[slot]
                    : _activeAction.InitialValues[i];

                _releasing[slot] = new ReleaseChannelState
                {
                    IsActive = true,
                    StartValue = releaseStartVal,
                    StartTimeMs = effectiveNowMs
                };
            }

            _activeAction = null;
            SetSubtitle(null);
        }

        public void Pause(double nowMs)
        {
            if (_isPaused) return;
            _isPaused = true;
            _pauseStartRawMs = nowMs;
        }

        public void Resume(double nowMs)
        {
            if (!_isPaused) return;
            if (nowMs > _pauseStartRawMs)
            {
                _accumulatedPausedMs += (nowMs - _pauseStartRawMs);
            }
            _isPaused = false;
        }

        public double GetEffectiveTimeMs(double rawNowMs)
        {
            double referenceRaw = _isPaused ? _pauseStartRawMs : rawNowMs;
            return referenceRaw - _accumulatedPausedMs;
        }

        public bool IsChannelReleasing(int slotIndex)
        {
            if (slotIndex < 0 || slotIndex >= _slotCount) return false;
            return _releasing[slotIndex].IsActive;
        }

        public void EvaluateFrame(double rawNowMs, float[] baselineValues, float[] outputValues)
        {
            if (baselineValues == null) throw new ArgumentNullException(nameof(baselineValues));
            if (outputValues == null) throw new ArgumentNullException(nameof(outputValues));
            if (baselineValues.Length < _slotCount || outputValues.Length < _slotCount)
            {
                throw new ArgumentException($"Baseline and output arrays must have length >= {_slotCount}.");
            }

            for (int i = 0; i < _slotCount; i++)
            {
                outputValues[i] = baselineValues[i];
            }

            try
            {
                double effectiveNowMs = GetEffectiveTimeMs(rawNowMs);

                // 1. Check if existing active action naturally completed at or before effectiveNowMs
                if (_activeAction != null)
                {
                    double activeEndMs = _activeAction.StartTimeMs + _activeAction.Packet.DurationMs;
                    if (effectiveNowMs >= activeEndMs)
                    {
                        TransitionCompletedActionToRelease(_activeAction, activeEndMs);
                        _activeAction = null;
                        SetSubtitle(null);
                    }
                }

                // 2. Atomically commit pending submission if present and still valid
                if (_pendingSubmission.HasValue)
                {
                    var pending = _pendingSubmission.Value;
                    _pendingSubmission = null;

                    var reqCtx = pending.RequestContext;
                    if (ActionContract.ValidateRequestContext(in reqCtx, _hostState, rawNowMs, out _) &&
                        string.Equals(pending.Packet.ProfileId, _hostState.ActiveProfileId, StringComparison.Ordinal) &&
                        string.Equals(pending.Packet.ProfileId, _profile.ProfileId, StringComparison.Ordinal))
                    {
                        _hostState.MarkRequestCommitted(pending.RequestContext.RequestId);
                        CommitNewAction(pending.Packet, effectiveNowMs, baselineValues);
                    }
                }

                // 3. Evaluate active action curves
                if (_activeAction != null)
                {
                    double elapsedMs = effectiveNowMs - _activeAction.StartTimeMs;
                    var curves = _activeAction.Packet.Curves;
                    for (int i = 0; i < curves.Length; i++)
                    {
                        var curve = curves[i];
                        int slot = curve.ProfileSlotIndex;
                        float rawVal = EvaluateCurve(curve, _activeAction.InitialValues[i], elapsedMs);
                        outputValues[slot] = SanitizeAndClamp(rawVal, curve.MinValue, curve.MaxValue, baselineValues[slot]);
                    }
                }

                // 4. Evaluate releasing channels
                double releaseDurationMs = _profile.ReleaseMs;
                for (int slot = 0; slot < _slotCount; slot++)
                {
                    if (!_releasing[slot].IsActive) continue;

                    double releaseElapsedMs = effectiveNowMs - _releasing[slot].StartTimeMs;
                    if (releaseElapsedMs >= releaseDurationMs)
                    {
                        _releasing[slot].IsActive = false;
                        outputValues[slot] = baselineValues[slot];
                    }
                    else
                    {
                        double progress = Clamp01(releaseElapsedMs / releaseDurationMs);
                        double s = SmoothStep01(progress);
                        float startP = _releasing[slot].StartValue;
                        float baseB = baselineValues[slot];
                        float blended = (float)(startP + (baseB - startP) * s);
                        var paramDef = _profile.Parameters[slot];
                        outputValues[slot] = SanitizeAndClamp(blended, paramDef.Min, paramDef.Max, baseB);
                    }
                }

                // 5. Record pre-physics composite values for future continuity
                for (int i = 0; i < _slotCount; i++)
                {
                    _lastAppliedCompositeValues[i] = outputValues[i];
                }
                _hasSynthesizedHistory = true;
            }
            catch
            {
                // Section 6 safety fallback: on internal exception, revoke foreground control and revert to baseline
                _pendingSubmission = null;
                _activeAction = null;
                for (int i = 0; i < _slotCount; i++)
                {
                    _releasing[i].IsActive = false;
                    outputValues[i] = baselineValues[i];
                    _lastAppliedCompositeValues[i] = baselineValues[i];
                }
                SetSubtitle(null);
            }
        }

        private void TransitionCompletedActionToRelease(ActiveActionState completedAction, double exactEndTimeMs)
        {
            var curves = completedAction.Packet.Curves;
            for (int i = 0; i < curves.Length; i++)
            {
                var curve = curves[i];
                int slot = curve.ProfileSlotIndex;
                var keyframes = curve.Keyframes;
                float endpointValue = keyframes[keyframes.Length - 1].TargetValue;

                _releasing[slot] = new ReleaseChannelState
                {
                    IsActive = true,
                    StartValue = endpointValue,
                    StartTimeMs = exactEndTimeMs
                };
            }
        }

        private void CommitNewAction(CompiledActionPacket newPacket, double effectiveNowMs, float[] currentBaseline)
        {
            Array.Clear(_activeMaskScratch, 0, _slotCount);
            var newCurves = newPacket.Curves;
            var initialValues = new float[newCurves.Length];

            for (int i = 0; i < newCurves.Length; i++)
            {
                int slot = newCurves[i].ProfileSlotIndex;
                _activeMaskScratch[slot] = true;
                initialValues[i] = _hasSynthesizedHistory
                    ? _lastAppliedCompositeValues[slot]
                    : currentBaseline[slot];
            }

            // If replacing an active action, its exclusive channels begin releasing from current composite value
            if (_activeAction != null)
            {
                var oldCurves = _activeAction.Packet.Curves;
                for (int i = 0; i < oldCurves.Length; i++)
                {
                    int oldSlot = oldCurves[i].ProfileSlotIndex;
                    if (!_activeMaskScratch[oldSlot])
                    {
                        float startP = _hasSynthesizedHistory
                            ? _lastAppliedCompositeValues[oldSlot]
                            : _activeAction.InitialValues[i];
                        _releasing[oldSlot] = new ReleaseChannelState
                        {
                            IsActive = true,
                            StartValue = startP,
                            StartTimeMs = effectiveNowMs
                        };
                    }
                }
            }

            // Channels taken over by the new packet stop any in-progress release;
            // channels already releasing and NOT in the new packet keep their existing release timer untouched.
            for (int i = 0; i < newCurves.Length; i++)
            {
                int slot = newCurves[i].ProfileSlotIndex;
                _releasing[slot].IsActive = false;
            }

            _activeAction = new ActiveActionState(newPacket, effectiveNowMs, initialValues);
            SetSubtitle(newPacket.Subtitle);
        }

        private static float EvaluateCurve(CompiledParameterCurve curve, float initialValue, double elapsedMs)
        {
            var keyframes = curve.Keyframes;
            if (keyframes == null || keyframes.Length == 0)
            {
                return initialValue;
            }

            if (elapsedMs <= 0.0)
            {
                return initialValue;
            }

            double t0 = 0.0;
            float v0 = initialValue;

            for (int i = 0; i < keyframes.Length; i++)
            {
                double t1 = keyframes[i].AtMs;
                float v1 = keyframes[i].TargetValue;

                if (elapsedMs <= t1)
                {
                    double span = t1 - t0;
                    if (span <= 0.0) return v1;
                    double u = Clamp01((elapsedMs - t0) / span);
                    double s = SmoothStep01(u);
                    return (float)(v0 + (v1 - v0) * s);
                }

                t0 = t1;
                v0 = v1;
            }

            // After the last explicit keyframe, hold the last target value until duration_ms
            return keyframes[keyframes.Length - 1].TargetValue;
        }

        private static double Clamp01(double value)
        {
            if (value < 0.0) return 0.0;
            if (value > 1.0) return 1.0;
            return value;
        }

        private static double SmoothStep01(double u)
        {
            return u * u * (3.0 - 2.0 * u);
        }

        private static float SanitizeAndClamp(float value, float min, float max, float fallback)
        {
            if (float.IsNaN(value) || float.IsInfinity(value))
            {
                return fallback;
            }
            if (value < min) return min;
            if (value > max) return max;
            return value;
        }

        private void SetSubtitle(string subtitle)
        {
            string normalized = string.IsNullOrEmpty(subtitle) ? null : subtitle;
            if (!string.Equals(CurrentSubtitle, normalized, StringComparison.Ordinal))
            {
                CurrentSubtitle = normalized;
                OnSubtitleChanged?.Invoke(CurrentSubtitle);
            }
        }
    }
}
