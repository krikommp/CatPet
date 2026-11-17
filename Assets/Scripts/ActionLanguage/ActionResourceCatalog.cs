using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;

namespace PetLive2d.ActionLanguage
{
    public enum ResourceCalibrationStatus
    {
        Candidate,
        Calibrated
    }

    public readonly struct PhaseChannelPoint
    {
        public string Phase { get; } // "enter" | "hold" | "return"
        public double LocalFraction { get; } // 0..1 within phase
        public float BaseValue { get; }

        public PhaseChannelPoint(string phase, double localFraction, float baseValue)
        {
            Phase = phase;
            LocalFraction = localFraction;
            BaseValue = baseValue;
        }
    }

    public sealed class ActionResourceChannel
    {
        public string ParameterId { get; }
        public float ReferenceValue { get; }
        public float StartTolerance { get; }
        public bool Scalable { get; }
        public IReadOnlyList<PhaseChannelPoint> Points { get; }

        public ActionResourceChannel(
            string parameterId,
            float referenceValue,
            float startTolerance,
            bool scalable,
            params PhaseChannelPoint[] points)
        {
            ParameterId = parameterId;
            ReferenceValue = referenceValue;
            StartTolerance = startTolerance;
            Scalable = scalable;
            Points = Array.AsReadOnly((PhaseChannelPoint[])(points ?? Array.Empty<PhaseChannelPoint>()).Clone());
        }
    }

    public sealed class ActionResourceDefinition
    {
        public string ResourceId { get; }
        public string Description { get; }
        public ResourceCalibrationStatus Status { get; }
        public int MinDurationMs { get; }
        public int MaxDurationMs { get; }
        public int DefaultDurationMs { get; }
        public bool SupportsAmplitudeScale { get; }
        public float MinAmplitudeScale { get; }
        public float MaxAmplitudeScale { get; }
        public float DefaultAmplitudeScale { get; }
        public bool SupportsHoldRatio { get; }
        public float MinHoldRatio { get; }
        public float MaxHoldRatio { get; }
        public float DefaultHoldRatio { get; }
        public double EnterReturnAlpha { get; }
        public IReadOnlyList<ActionResourceChannel> Channels { get; }

        public ActionResourceDefinition(
            string resourceId,
            string description,
            ResourceCalibrationStatus status,
            int minDurationMs,
            int maxDurationMs,
            int defaultDurationMs,
            bool supportsAmplitudeScale,
            float minAmpScale,
            float maxAmpScale,
            float defaultAmpScale,
            bool supportsHoldRatio,
            float minHoldRatio,
            float maxHoldRatio,
            float defaultHoldRatio,
            double enterReturnAlpha,
            params ActionResourceChannel[] channels)
        {
            ResourceId = resourceId;
            Description = description;
            Status = status;
            MinDurationMs = minDurationMs;
            MaxDurationMs = maxDurationMs;
            DefaultDurationMs = defaultDurationMs;
            SupportsAmplitudeScale = supportsAmplitudeScale;
            MinAmplitudeScale = minAmpScale;
            MaxAmplitudeScale = maxAmpScale;
            DefaultAmplitudeScale = defaultAmpScale;
            SupportsHoldRatio = supportsHoldRatio;
            MinHoldRatio = minHoldRatio;
            MaxHoldRatio = maxHoldRatio;
            DefaultHoldRatio = defaultHoldRatio;
            EnterReturnAlpha = enterReturnAlpha;
            Channels = Array.AsReadOnly((ActionResourceChannel[])(channels ?? Array.Empty<ActionResourceChannel>()).Clone());
        }
    }

    /// <summary>
    /// Unified versioned parametric action resource catalog for Yukikaze (action-config.v0.2).
    /// </summary>
    public sealed class ActionResourceCatalog
    {
        public const string DefaultCatalogVersion = "yukikaze-resources.v0.2";
        public string Version { get; }
        public string ProfileId { get; }

        private readonly Dictionary<string, ActionResourceDefinition> _byId = new Dictionary<string, ActionResourceDefinition>(StringComparer.Ordinal);
        private readonly List<ActionResourceDefinition> _ordered = new List<ActionResourceDefinition>();

        public IReadOnlyList<ActionResourceDefinition> Resources => _ordered;

        public ActionResourceCatalog(string version, string profileId, params ActionResourceDefinition[] resources)
        {
            Version = version ?? throw new ArgumentNullException(nameof(version));
            ProfileId = profileId ?? throw new ArgumentNullException(nameof(profileId));
            foreach (var r in resources ?? Array.Empty<ActionResourceDefinition>())
            {
                if (r == null) continue;
                _byId.Add(r.ResourceId, r);
                _ordered.Add(r);
            }
        }

        public bool TryGetResource(string resourceId, out ActionResourceDefinition def) =>
            _byId.TryGetValue(resourceId ?? string.Empty, out def);

        public static ActionResourceCatalog CreateYukikazeV02()
        {
            return new ActionResourceCatalog(
                DefaultCatalogVersion,
                YukikazeActionCatalog.ProfileId,
                // 1. blink.full (amplitude_scale disabled; hold_ratio supported)
                new ActionResourceDefinition(
                    "blink.full", "双眼完整眨眼", ResourceCalibrationStatus.Calibrated,
                    300, 1800, 600,
                    false, 1f, 1f, 1f,
                    true, 0.0f, 0.5f, 0.25f, 0.5,
                    new ActionResourceChannel("ParamEyeLOpen", 1f, 0.05f, false,
                        new PhaseChannelPoint("enter", 1.0, 0f),
                        new PhaseChannelPoint("hold", 1.0, 0f),
                        new PhaseChannelPoint("return", 1.0, 1f)),
                    new ActionResourceChannel("ParamEyeROpen", 1f, 0.05f, false,
                        new PhaseChannelPoint("enter", 1.0, 0f),
                        new PhaseChannelPoint("hold", 1.0, 0f),
                        new PhaseChannelPoint("return", 1.0, 1f))),

                // 2. nod.basic
                new ActionResourceDefinition(
                    "nod.basic", "点头", ResourceCalibrationStatus.Candidate,
                    420, 2200, 760,
                    true, 0.35f, 1.35f, 1.0f,
                    true, 0.0f, 0.45f, 0.20f, 0.5,
                    new ActionResourceChannel("ParamAngleY", 0f, 3f, true,
                        new PhaseChannelPoint("enter", 1.0, -18f),
                        new PhaseChannelPoint("hold", 1.0, -18f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("ParamBodyAngleY", 0f, 1.5f, true,
                        new PhaseChannelPoint("enter", 1.0, -4.5f),
                        new PhaseChannelPoint("hold", 1.0, -4.5f),
                        new PhaseChannelPoint("return", 1.0, 0f))),

                // 3. shake_head.basic (multi-swing inside enter/hold/return)
                new ActionResourceDefinition(
                    "shake_head.basic", "摇头", ResourceCalibrationStatus.Candidate,
                    480, 2400, 840,
                    true, 0.35f, 1.35f, 1.0f,
                    true, 0.0f, 0.30f, 0.10f, 0.5,
                    new ActionResourceChannel("ParamAngleX", 0f, 3f, true,
                        new PhaseChannelPoint("enter", 0.5, -18f),
                        new PhaseChannelPoint("enter", 1.0, 18f),
                        new PhaseChannelPoint("hold", 1.0, 18f),
                        new PhaseChannelPoint("return", 1.0, 0f))),

                // 4. tilt_head.basic
                new ActionResourceDefinition(
                    "tilt_head.basic", "歪头", ResourceCalibrationStatus.Candidate,
                    480, 2400, 880,
                    true, 0.35f, 1.35f, 1.0f,
                    true, 0.0f, 0.50f, 0.25f, 0.5,
                    new ActionResourceChannel("ParamAngleZ", 0f, 3f, true,
                        new PhaseChannelPoint("enter", 1.0, 20f),
                        new PhaseChannelPoint("hold", 1.0, 20f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("ParamBodyAngleZ", 0f, 1.5f, true,
                        new PhaseChannelPoint("enter", 1.0, 5f),
                        new PhaseChannelPoint("hold", 1.0, 5f),
                        new PhaseChannelPoint("return", 1.0, 0f))),

                // 5. look_around.basic
                new ActionResourceDefinition(
                    "look_around.basic", "四处张望", ResourceCalibrationStatus.Candidate,
                    600, 2600, 1100,
                    true, 0.40f, 1.25f, 1.0f,
                    true, 0.0f, 0.30f, 0.10f, 0.5,
                    new ActionResourceChannel("ParamEyeBallX", 0f, 0.2f, true,
                        new PhaseChannelPoint("enter", 0.5, -0.8f),
                        new PhaseChannelPoint("enter", 1.0, 0.8f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("ParamAngleX", 0f, 3f, true,
                        new PhaseChannelPoint("enter", 0.5, -14f),
                        new PhaseChannelPoint("enter", 1.0, 14f),
                        new PhaseChannelPoint("return", 1.0, 0f))),

                // 6. smile.basic
                new ActionResourceDefinition(
                    "smile.basic", "微笑", ResourceCalibrationStatus.Candidate,
                    550, 2600, 1100,
                    true, 0.40f, 1.15f, 1.0f,
                    true, 0.0f, 0.55f, 0.35f, 0.5,
                    new ActionResourceChannel("PARAM_Smile_eye", 0f, 0.2f, false,
                        new PhaseChannelPoint("enter", 1.0, 1.0f),
                        new PhaseChannelPoint("hold", 1.0, 1.0f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("ParamEyeLOpen", 1f, 0.05f, false,
                        new PhaseChannelPoint("enter", 1.0, 0f),
                        new PhaseChannelPoint("hold", 1.0, 0f),
                        new PhaseChannelPoint("return", 1.0, 1f)),
                    new ActionResourceChannel("ParamEyeROpen", 1f, 0.05f, false,
                        new PhaseChannelPoint("enter", 1.0, 0f),
                        new PhaseChannelPoint("hold", 1.0, 0f),
                        new PhaseChannelPoint("return", 1.0, 1f)),
                    new ActionResourceChannel("ParamMouthForm", 0f, 0.2f, true,
                        new PhaseChannelPoint("enter", 1.0, 0.95f),
                        new PhaseChannelPoint("hold", 1.0, 0.95f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("ParamMouthOpenY", 0f, 0.2f, true,
                        new PhaseChannelPoint("enter", 1.0, 0.50f),
                        new PhaseChannelPoint("hold", 1.0, 0.50f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("ParamBrowLY", 0f, 0.2f, true,
                        new PhaseChannelPoint("enter", 1.0, 0.60f),
                        new PhaseChannelPoint("hold", 1.0, 0.60f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("ParamBrowRY", 0f, 0.2f, true,
                        new PhaseChannelPoint("enter", 1.0, 0.60f),
                        new PhaseChannelPoint("hold", 1.0, 0.60f),
                        new PhaseChannelPoint("return", 1.0, 0f))),

                // 7. angry.basic
                new ActionResourceDefinition(
                    "angry.basic", "生气傲娇", ResourceCalibrationStatus.Candidate,
                    550, 2600, 1100,
                    true, 0.40f, 1.15f, 1.0f,
                    true, 0.0f, 0.55f, 0.35f, 0.5,
                    new ActionResourceChannel("PARAM_Angry_eye", 0f, 0.2f, false,
                        new PhaseChannelPoint("enter", 1.0, 1.0f),
                        new PhaseChannelPoint("hold", 1.0, 1.0f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("ParamBrowLY", 0f, 0.2f, true,
                        new PhaseChannelPoint("enter", 1.0, -0.90f),
                        new PhaseChannelPoint("hold", 1.0, -0.90f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("ParamBrowRY", 0f, 0.2f, true,
                        new PhaseChannelPoint("enter", 1.0, -0.90f),
                        new PhaseChannelPoint("hold", 1.0, -0.90f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("ParamBrowLX", 0f, 0.2f, true,
                        new PhaseChannelPoint("enter", 1.0, -0.60f),
                        new PhaseChannelPoint("hold", 1.0, -0.60f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("ParamBrowRX", 0f, 0.2f, true,
                        new PhaseChannelPoint("enter", 1.0, -0.60f),
                        new PhaseChannelPoint("hold", 1.0, -0.60f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("PARAM_mouth", 1f, 0.1f, false,
                        new PhaseChannelPoint("enter", 1.0, 0f),
                        new PhaseChannelPoint("hold", 1.0, 0f),
                        new PhaseChannelPoint("return", 1.0, 1f)),
                    new ActionResourceChannel("PARAM_FXmouth1", 0f, 0.1f, false,
                        new PhaseChannelPoint("enter", 1.0, 1f),
                        new PhaseChannelPoint("hold", 1.0, 1f),
                        new PhaseChannelPoint("return", 1.0, 0f))),

                // 8. shy.basic
                new ActionResourceDefinition(
                    "shy.basic", "害羞", ResourceCalibrationStatus.Candidate,
                    650, 2600, 1200,
                    true, 0.40f, 1.25f, 1.0f,
                    true, 0.0f, 0.55f, 0.35f, 0.5,
                    new ActionResourceChannel("ParamAngleZ", 0f, 3f, true,
                        new PhaseChannelPoint("enter", 1.0, -18f),
                        new PhaseChannelPoint("hold", 1.0, -18f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("ParamEyeBallX", 0f, 0.2f, true,
                        new PhaseChannelPoint("enter", 1.0, 0.80f),
                        new PhaseChannelPoint("hold", 1.0, 0.80f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("ParamEyeBallY", 0f, 0.2f, true,
                        new PhaseChannelPoint("enter", 1.0, -0.45f),
                        new PhaseChannelPoint("hold", 1.0, -0.45f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("ParamBrowLY", 0f, 0.2f, true,
                        new PhaseChannelPoint("enter", 1.0, -0.40f),
                        new PhaseChannelPoint("hold", 1.0, -0.40f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("ParamBrowRY", 0f, 0.2f, true,
                        new PhaseChannelPoint("enter", 1.0, -0.40f),
                        new PhaseChannelPoint("hold", 1.0, -0.40f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("PARAM_mouth", 1f, 0.1f, false,
                        new PhaseChannelPoint("enter", 1.0, 0f),
                        new PhaseChannelPoint("hold", 1.0, 0f),
                        new PhaseChannelPoint("return", 1.0, 1f)),
                    new ActionResourceChannel("PARAM_FXmouth2", 0f, 0.1f, false,
                        new PhaseChannelPoint("enter", 1.0, 1f),
                        new PhaseChannelPoint("hold", 1.0, 1f),
                        new PhaseChannelPoint("return", 1.0, 0f))),

                // 9. surprise.basic
                new ActionResourceDefinition(
                    "surprise.basic", "惊讶", ResourceCalibrationStatus.Candidate,
                    500, 2400, 950,
                    true, 0.40f, 1.20f, 1.0f,
                    true, 0.0f, 0.50f, 0.30f, 0.4,
                    new ActionResourceChannel("PARAM_FXeye", 0f, 0.2f, false,
                        new PhaseChannelPoint("enter", 1.0, 1.0f),
                        new PhaseChannelPoint("hold", 1.0, 1.0f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("ParamBrowLY", 0f, 0.2f, true,
                        new PhaseChannelPoint("enter", 1.0, 0.80f),
                        new PhaseChannelPoint("hold", 1.0, 0.80f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("ParamBrowRY", 0f, 0.2f, true,
                        new PhaseChannelPoint("enter", 1.0, 0.80f),
                        new PhaseChannelPoint("hold", 1.0, 0.80f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("PARAM_mouth", 1f, 0.1f, false,
                        new PhaseChannelPoint("enter", 1.0, 0f),
                        new PhaseChannelPoint("hold", 1.0, 0f),
                        new PhaseChannelPoint("return", 1.0, 1f)),
                    new ActionResourceChannel("PARAM_FXmouth3", 0f, 0.1f, false,
                        new PhaseChannelPoint("enter", 1.0, 1f),
                        new PhaseChannelPoint("hold", 1.0, 1f),
                        new PhaseChannelPoint("return", 1.0, 0f))),

                // 10. wave.basic
                new ActionResourceDefinition(
                    "wave.basic", "挥手", ResourceCalibrationStatus.Candidate,
                    550, 2500, 1050,
                    true, 0.40f, 1.20f, 1.0f,
                    true, 0.0f, 0.50f, 0.30f, 0.5,
                    new ActionResourceChannel("PARAM_Arm_RT_Angle", 0f, 0.5f, true,
                        new PhaseChannelPoint("enter", 1.0, 8.0f),
                        new PhaseChannelPoint("hold", 1.0, 8.0f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("PARAM_Arm_R_hand", 0f, 0.2f, true,
                        new PhaseChannelPoint("enter", 1.0, 0.9f),
                        new PhaseChannelPoint("hold", 1.0, 0.9f),
                        new PhaseChannelPoint("return", 1.0, 0f))),

                // 11. cheer.basic
                new ActionResourceDefinition(
                    "cheer.basic", "举手欢呼", ResourceCalibrationStatus.Candidate,
                    550, 2500, 1100,
                    true, 0.40f, 1.20f, 1.0f,
                    true, 0.0f, 0.50f, 0.30f, 0.5,
                    new ActionResourceChannel("PARAM_Arm_LT_Angle", 0f, 0.5f, true,
                        new PhaseChannelPoint("enter", 1.0, 8.5f),
                        new PhaseChannelPoint("hold", 1.0, 8.5f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("PARAM_Arm_RT_Angle", 0f, 0.5f, true,
                        new PhaseChannelPoint("enter", 1.0, 8.5f),
                        new PhaseChannelPoint("hold", 1.0, 8.5f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("PARAM_shangxia", 0f, 0.2f, true,
                        new PhaseChannelPoint("enter", 1.0, 0.85f),
                        new PhaseChannelPoint("hold", 1.0, 0.85f),
                        new PhaseChannelPoint("return", 1.0, 0f))),

                // 12. bow.basic
                new ActionResourceDefinition(
                    "bow.basic", "鞠躬", ResourceCalibrationStatus.Candidate,
                    600, 2600, 1200,
                    true, 0.40f, 1.25f, 1.0f,
                    true, 0.0f, 0.50f, 0.30f, 0.5,
                    new ActionResourceChannel("ParamBodyAngleY", 0f, 1.5f, true,
                        new PhaseChannelPoint("enter", 1.0, -8.5f),
                        new PhaseChannelPoint("hold", 1.0, -8.5f),
                        new PhaseChannelPoint("return", 1.0, 0f)),
                    new ActionResourceChannel("ParamAngleY", 0f, 3f, true,
                        new PhaseChannelPoint("enter", 1.0, -20f),
                        new PhaseChannelPoint("hold", 1.0, -20f),
                        new PhaseChannelPoint("return", 1.0, 0f)))
            );
        }
    }
}
