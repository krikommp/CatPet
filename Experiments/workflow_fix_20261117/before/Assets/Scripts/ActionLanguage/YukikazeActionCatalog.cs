using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace PetLive2d.ActionLanguage
{
    [Serializable]
    public sealed class YukikazeMotionTuning
    {
        public string variantId = "default";
        public float periodScale = 1.0f;
        public float amplitudeScale = 1.0f;
        public float blinkHoldFraction = 1.0f / 3.0f;
    }

    [Serializable]
    public sealed class ActionStepItemSpec
    {
        public string type;
        public int count = 1;
        public string amplitude = "normal";
        public string speed = "normal";
    }

    [Serializable]
    public sealed class ActionStepSpec
    {
        public List<ActionStepItemSpec> actions = new List<ActionStepItemSpec>();
    }

    /// <summary>
    /// Yukikaze capability profile, full-body calibrated/candidate motion map factory, and deterministic plan JSON serializer.
    /// All parameter ranges and defaults were verified directly against live scene object xuefeng.
    /// </summary>
    public static class YukikazeActionCatalog
    {
        public const string ProfileId = "yukikaze.v1";
        public const string MotionMapVersion = "yukikaze-motion.v1";
        public const string LabelPolicyVersion = "action-labels.v1";
        public const string PlanVersion = "action-plan.v0.1";

        public static readonly string[] CanonicalActionOrder =
        {
            "blink", "nod", "shake_head", "tilt_head", "look_around",
            "smile", "angry", "shy", "surprise",
            "wave", "cheer", "bow"
        };

        public static readonly string[] SupportedSpeeds = { "slow", "normal", "fast" };
        public static readonly string[] SupportedDecisions = { "execute", "none", "unsupported", "ambiguous" };

        public static CapabilityProfile CreateProfile()
        {
            var parameters = new[]
            {
                // Head & Body
                new ParameterDefinition("ParamAngleX", 0, -30f, 30f, 0f, ParameterOwner.Foreground, "Head X (Yaw)", "core_metadata_verified"),
                new ParameterDefinition("ParamAngleY", 1, -30f, 30f, 0f, ParameterOwner.Foreground, "Head Y (Pitch)", "core_metadata_verified"),
                new ParameterDefinition("ParamAngleZ", 2, -30f, 30f, 0f, ParameterOwner.Foreground, "Head Z (Roll)", "core_metadata_verified"),
                new ParameterDefinition("ParamBodyAngleX", 3, -10f, 10f, 0f, ParameterOwner.Foreground, "Body X", "core_metadata_verified"),
                new ParameterDefinition("ParamBodyAngleY", 4, -10f, 10f, 0f, ParameterOwner.Foreground, "Body Y", "core_metadata_verified"),
                new ParameterDefinition("ParamBodyAngleZ", 5, -10f, 10f, 0f, ParameterOwner.Foreground, "Body Z", "core_metadata_verified"),
                new ParameterDefinition("PARAM_shangxia", 6, 0f, 1f, 0f, ParameterOwner.Foreground, "Vertical Bounce", "core_metadata_verified"),

                // Eyes & Brows
                new ParameterDefinition("ParamEyeLOpen", 7, 0f, 1f, 1f, ParameterOwner.Foreground, "Left Eye Open", "core_metadata_verified"),
                new ParameterDefinition("ParamEyeROpen", 8, 0f, 1f, 1f, ParameterOwner.Foreground, "Right Eye Open", "core_metadata_verified"),
                new ParameterDefinition("ParamEyeBallX", 9, -1f, 1f, 0f, ParameterOwner.Foreground, "Eyeball X", "core_metadata_verified"),
                new ParameterDefinition("ParamEyeBallY", 10, -1f, 1f, 0f, ParameterOwner.Foreground, "Eyeball Y", "core_metadata_verified"),
                new ParameterDefinition("PARAM_Smile_eye", 11, 0f, 1f, 0f, ParameterOwner.Foreground, "Smile Eye", "core_metadata_verified"),
                new ParameterDefinition("PARAM_Angry_eye", 12, 0f, 1f, 0f, ParameterOwner.Foreground, "Angry Eye", "core_metadata_verified"),
                new ParameterDefinition("PARAM_FXeye", 13, 0f, 1f, 0f, ParameterOwner.Foreground, "Eye FX", "core_metadata_verified"),
                new ParameterDefinition("ParamBrowLY", 14, -1f, 1f, 0f, ParameterOwner.Foreground, "Left Brow Y", "core_metadata_verified"),
                new ParameterDefinition("ParamBrowRY", 15, -1f, 1f, 0f, ParameterOwner.Foreground, "Right Brow Y", "core_metadata_verified"),
                new ParameterDefinition("ParamBrowLX", 32, -1f, 1f, 0f, ParameterOwner.Foreground, "Left Brow X", "motion3_verified"),
                new ParameterDefinition("ParamBrowRX", 33, -1f, 1f, 0f, ParameterOwner.Foreground, "Right Brow X", "motion3_verified"),

                // Mouth & Cheek
                new ParameterDefinition("ParamMouthForm", 16, -1f, 1f, 0f, ParameterOwner.Foreground, "Mouth Form", "core_metadata_verified"),
                new ParameterDefinition("ParamMouthOpenY", 17, 0f, 1f, 0f, ParameterOwner.Foreground, "Mouth Open Y", "core_metadata_verified"),
                new ParameterDefinition("PARAM_mouth", 25, 0f, 1f, 1f, ParameterOwner.Foreground, "Normal Mouth Toggle", "motion3_verified"),
                new ParameterDefinition("PARAM_FXmouth1", 26, 0f, 1f, 0f, ParameterOwner.Foreground, "FX Mouth 1", "motion3_verified"),
                new ParameterDefinition("PARAM_FXmouth2", 27, 0f, 1f, 0f, ParameterOwner.Foreground, "FX Mouth 2", "motion3_verified"),
                new ParameterDefinition("PARAM_FXmouth3", 28, 0f, 1f, 0f, ParameterOwner.Foreground, "FX Mouth 3", "motion3_verified"),
                new ParameterDefinition("PARAM_Mouth", 29, -1f, 1f, 0f, ParameterOwner.Foreground, "Mouth Shape", "motion3_verified"),
                new ParameterDefinition("PARAM_Mouth_Angle", 30, -1f, 1f, 0f, ParameterOwner.Foreground, "Mouth Angle", "motion3_verified"),
                new ParameterDefinition("ParamCheek", 31, 0f, 1f, 1f, ParameterOwner.Foreground, "Cheek Blush", "motion3_verified"),

                // Arms
                new ParameterDefinition("PARAM_Arm_LT_Angle", 18, 0f, 10f, 0f, ParameterOwner.Foreground, "Left Upper Arm", "core_metadata_verified"),
                new ParameterDefinition("PARAM_Arm_RT_Angle", 19, 0f, 10f, 0f, ParameterOwner.Foreground, "Right Upper Arm", "core_metadata_verified"),
                new ParameterDefinition("PARAM_Arm_LB_Agle", 20, 0f, 1f, 0f, ParameterOwner.Foreground, "Left Forearm", "core_metadata_verified"),
                new ParameterDefinition("PARAM_Arm_RB_Agle", 21, 0f, 1f, 0f, ParameterOwner.Foreground, "Right Forearm", "core_metadata_verified"),
                new ParameterDefinition("PARAM_Arm_L_hand", 22, 0f, 1f, 0f, ParameterOwner.Foreground, "Left Hand", "core_metadata_verified"),
                new ParameterDefinition("PARAM_Arm_R_hand", 23, 0f, 1f, 0f, ParameterOwner.Foreground, "Right Hand", "core_metadata_verified"),

                // Local breath (reserved)
                new ParameterDefinition("ParamBreath", 24, 0f, 1f, 0f, ParameterOwner.Local, "Breath", "core_metadata_verified")
            };

            return new CapabilityProfile(
                ProfileId,
                "Yukikaze",
                parameters,
                new[] { "PARAM_Hairfront_vive" });
        }

        public static ActionMotionMap CreateMotionMap(YukikazeMotionTuning tuning = null, bool includeHeadExpansions = true)
        {
            tuning ??= new YukikazeMotionTuning();
            float pScale = Clamp(tuning.periodScale, 0.6f, 1.6f);
            float aScale = Clamp(tuning.amplitudeScale, 0.5f, 1.4f);
            float hold = Clamp(tuning.blinkHoldFraction, 0.1f, 0.6f);
            float closeFrac = (1f - hold) * 0.5f;
            float reopenStart = closeFrac + hold;

            var templates = new List<ActionMotionTemplate>();

            // 1. blink (full)
            var blinkKeys = new[] { new MotionKey(closeFrac, 0f), new MotionKey(reopenStart, 0f), new MotionKey(1.0, 1f) };
            templates.Add(new ActionMotionTemplate(
                "blink", "full",
                ScalePeriod(900, pScale), ScalePeriod(600, pScale), ScalePeriod(300, pScale),
                new MotionChannel("ParamEyeLOpen", 1f, 0.05f, blinkKeys),
                new MotionChannel("ParamEyeROpen", 1f, 0.05f, blinkKeys)));

            if (includeHeadExpansions)
            {
                // 2. nod (ensure phase gaps >= 0.30 so even fast 480ms * 0.30 = 144ms >= 80ms)
                AddNod(templates, "small", ScalePeriod(1000, pScale), ScalePeriod(680, pScale), ScalePeriod(480, pScale), -10f * aScale, -2.5f * aScale);
                AddNod(templates, "normal", ScalePeriod(1100, pScale), ScalePeriod(760, pScale), ScalePeriod(520, pScale), -18f * aScale, -4.5f * aScale);

                // 3. shake_head
                AddShake(templates, "small", ScalePeriod(1100, pScale), ScalePeriod(760, pScale), ScalePeriod(480, pScale), 10f * aScale);
                AddShake(templates, "normal", ScalePeriod(1200, pScale), ScalePeriod(840, pScale), ScalePeriod(540, pScale), 18f * aScale);

                // 4. tilt_head
                AddTilt(templates, "small", ScalePeriod(1100, pScale), ScalePeriod(780, pScale), ScalePeriod(500, pScale), 12f * aScale, 3f * aScale);
                AddTilt(templates, "normal", ScalePeriod(1250, pScale), ScalePeriod(880, pScale), ScalePeriod(560, pScale), 22f * aScale, 5.5f * aScale);

                // 5. look_around
                AddLookAround(templates, "small", ScalePeriod(1400, pScale), ScalePeriod(1000, pScale), ScalePeriod(650, pScale), 0.5f * aScale, 8f * aScale);
                AddLookAround(templates, "normal", ScalePeriod(1600, pScale), ScalePeriod(1150, pScale), ScalePeriod(750, pScale), 0.9f * aScale, 14f * aScale);

                // 6. smile
                AddSmile(templates, "small", ScalePeriod(1400, pScale), ScalePeriod(1000, pScale), ScalePeriod(650, pScale), 0.6f * aScale, 0.5f * aScale);
                AddSmile(templates, "normal", ScalePeriod(1600, pScale), ScalePeriod(1150, pScale), ScalePeriod(750, pScale), 1.0f, 0.9f * aScale);

                // 7. angry
                AddAngry(templates, "small", ScalePeriod(1400, pScale), ScalePeriod(1000, pScale), ScalePeriod(650, pScale), 0.6f * aScale, -0.5f * aScale);
                AddAngry(templates, "normal", ScalePeriod(1600, pScale), ScalePeriod(1150, pScale), ScalePeriod(750, pScale), 1.0f, -0.9f * aScale);

                // 8. shy
                AddShy(templates, "small", ScalePeriod(1500, pScale), ScalePeriod(1100, pScale), ScalePeriod(720, pScale), 10f * aScale, 0.45f * aScale);
                AddShy(templates, "normal", ScalePeriod(1700, pScale), ScalePeriod(1250, pScale), ScalePeriod(820, pScale), 16f * aScale, 0.75f * aScale);

                // 9. surprise
                AddSurprise(templates, "small", ScalePeriod(1200, pScale), ScalePeriod(860, pScale), ScalePeriod(550, pScale), 0.5f * aScale, 0.45f * aScale);
                AddSurprise(templates, "normal", ScalePeriod(1400, pScale), ScalePeriod(980, pScale), ScalePeriod(640, pScale), 0.9f * aScale, 0.85f * aScale);

                // 10. wave
                AddWave(templates, "small", ScalePeriod(1400, pScale), ScalePeriod(960, pScale), ScalePeriod(620, pScale), 5.0f * aScale, 0.6f * aScale);
                AddWave(templates, "normal", ScalePeriod(1600, pScale), ScalePeriod(1100, pScale), ScalePeriod(720, pScale), 8.5f * aScale, 1.0f);

                // 11. cheer
                AddCheer(templates, "small", ScalePeriod(1400, pScale), ScalePeriod(980, pScale), ScalePeriod(640, pScale), 5.5f * aScale, 0.5f * aScale);
                AddCheer(templates, "normal", ScalePeriod(1600, pScale), ScalePeriod(1120, pScale), ScalePeriod(740, pScale), 9.0f * aScale, 0.9f * aScale);

                // 12. bow
                AddBow(templates, "small", ScalePeriod(1500, pScale), ScalePeriod(1050, pScale), ScalePeriod(680, pScale), -5.0f * aScale, -12f * aScale);
                AddBow(templates, "normal", ScalePeriod(1700, pScale), ScalePeriod(1200, pScale), ScalePeriod(780, pScale), -8.5f * aScale, -22f * aScale);
            }

            return new ActionMotionMap(MotionMapVersion, ProfileId, templates.ToArray());
        }

        private static void AddNod(List<ActionMotionTemplate> t, string amp, int s, int n, int f, float headPitch, float bodyPitch)
        {
            t.Add(new ActionMotionTemplate("nod", amp, s, n, f,
                new MotionChannel("ParamAngleY", 0f, 3f, new MotionKey(0.35, headPitch), new MotionKey(0.65, headPitch), new MotionKey(1.0, 0f)),
                new MotionChannel("ParamBodyAngleY", 0f, 1.5f, new MotionKey(0.45, bodyPitch), new MotionKey(1.0, 0f))));
        }

        private static void AddShake(List<ActionMotionTemplate> t, string amp, int s, int n, int f, float yawPeak)
        {
            t.Add(new ActionMotionTemplate("shake_head", amp, s, n, f,
                new MotionChannel("ParamAngleX", 0f, 3f, new MotionKey(0.25, -yawPeak), new MotionKey(0.75, yawPeak), new MotionKey(1.0, 0f))));
        }

        private static void AddTilt(List<ActionMotionTemplate> t, string amp, int s, int n, int f, float rollPeak, float bodyRoll)
        {
            t.Add(new ActionMotionTemplate("tilt_head", amp, s, n, f,
                new MotionChannel("ParamAngleZ", 0f, 3f, new MotionKey(0.35, rollPeak), new MotionKey(0.65, rollPeak), new MotionKey(1.0, 0f)),
                new MotionChannel("ParamBodyAngleZ", 0f, 1.5f, new MotionKey(0.4, bodyRoll), new MotionKey(0.65, bodyRoll), new MotionKey(1.0, 0f))));
        }

        private static void AddLookAround(List<ActionMotionTemplate> t, string amp, int s, int n, int f, float eyeX, float headX)
        {
            t.Add(new ActionMotionTemplate("look_around", amp, s, n, f,
                new MotionChannel("ParamEyeBallX", 0f, 0.2f, new MotionKey(0.25, -eyeX), new MotionKey(0.75, eyeX), new MotionKey(1.0, 0f)),
                new MotionChannel("ParamAngleX", 0f, 3f, new MotionKey(0.25, -headX), new MotionKey(0.75, headX), new MotionKey(1.0, 0f))));
        }

        private static void AddSmile(List<ActionMotionTemplate> t, string amp, int s, int n, int f, float smileEye, float mouthForm)
        {
            float se = Clamp(smileEye, 0f, 1f);
            float mf = Clamp(mouthForm, -1f, 1f);
            t.Add(new ActionMotionTemplate("smile", amp, s, n, f,
                new MotionChannel("PARAM_Smile_eye", 0f, 0.2f, new MotionKey(0.25, se), new MotionKey(0.75, se), new MotionKey(1.0, 0f)),
                new MotionChannel("ParamMouthForm", 0f, 0.2f, new MotionKey(0.25, mf), new MotionKey(0.75, mf), new MotionKey(1.0, 0f))));
        }

        private static void AddAngry(List<ActionMotionTemplate> t, string amp, int s, int n, int f, float angryEye, float browY)
        {
            float ae = Clamp(angryEye, 0f, 1f);
            float by = Clamp(browY, -1f, 1f);
            t.Add(new ActionMotionTemplate("angry", amp, s, n, f,
                new MotionChannel("PARAM_Angry_eye", 0f, 0.2f, new MotionKey(0.25, ae), new MotionKey(0.75, ae), new MotionKey(1.0, 0f)),
                new MotionChannel("ParamBrowLY", 0f, 0.2f, new MotionKey(0.25, by), new MotionKey(0.75, by), new MotionKey(1.0, 0f)),
                new MotionChannel("ParamBrowRY", 0f, 0.2f, new MotionKey(0.25, by), new MotionKey(0.75, by), new MotionKey(1.0, 0f))));
        }

        private static void AddShy(List<ActionMotionTemplate> t, string amp, int s, int n, int f, float tiltDeg, float eyeSide)
        {
            t.Add(new ActionMotionTemplate("shy", amp, s, n, f,
                new MotionChannel("ParamAngleZ", 0f, 3f, new MotionKey(0.3, -tiltDeg), new MotionKey(0.7, -tiltDeg), new MotionKey(1.0, 0f)),
                new MotionChannel("ParamEyeBallX", 0f, 0.2f, new MotionKey(0.3, eyeSide), new MotionKey(0.7, eyeSide), new MotionKey(1.0, 0f)),
                new MotionChannel("ParamEyeLOpen", 1f, 0.1f, new MotionKey(0.3, 0.72f), new MotionKey(0.7, 0.72f), new MotionKey(1.0, 1f)),
                new MotionChannel("ParamEyeROpen", 1f, 0.1f, new MotionKey(0.3, 0.72f), new MotionKey(0.7, 0.72f), new MotionKey(1.0, 1f))));
        }

        private static void AddSurprise(List<ActionMotionTemplate> t, string amp, int s, int n, int f, float mouthOpen, float fxEye)
        {
            float mo = Clamp(mouthOpen, 0f, 1f);
            float fx = Clamp(fxEye, 0f, 1f);
            t.Add(new ActionMotionTemplate("surprise", amp, s, n, f,
                new MotionChannel("ParamMouthOpenY", 0f, 0.2f, new MotionKey(0.25, mo), new MotionKey(0.7, mo), new MotionKey(1.0, 0f)),
                new MotionChannel("PARAM_FXeye", 0f, 0.2f, new MotionKey(0.25, fx), new MotionKey(0.7, fx), new MotionKey(1.0, 0f)),
                new MotionChannel("ParamBrowLY", 0f, 0.2f, new MotionKey(0.25, 0.7f), new MotionKey(0.7, 0.7f), new MotionKey(1.0, 0f)),
                new MotionChannel("ParamBrowRY", 0f, 0.2f, new MotionKey(0.25, 0.7f), new MotionKey(0.7, 0.7f), new MotionKey(1.0, 0f))));
        }

        private static void AddWave(List<ActionMotionTemplate> t, string amp, int s, int n, int f, float armTop, float armSub)
        {
            float top = Clamp(armTop, 0f, 10f);
            float sub = Clamp(armSub, 0f, 1f);
            t.Add(new ActionMotionTemplate("wave", amp, s, n, f,
                new MotionChannel("PARAM_Arm_RT_Angle", 0f, 0.5f, new MotionKey(0.25, top), new MotionKey(0.75, top), new MotionKey(1.0, 0f)),
                new MotionChannel("PARAM_Arm_RB_Agle", 0f, 0.2f, new MotionKey(0.3, sub), new MotionKey(0.55, sub * 0.4f), new MotionKey(0.75, sub), new MotionKey(1.0, 0f)),
                new MotionChannel("PARAM_Arm_R_hand", 0f, 0.2f, new MotionKey(0.25, sub), new MotionKey(0.75, sub), new MotionKey(1.0, 0f))));
        }

        private static void AddCheer(List<ActionMotionTemplate> t, string amp, int s, int n, int f, float armTop, float bounce)
        {
            float top = Clamp(armTop, 0f, 10f);
            float bn = Clamp(bounce, 0f, 1f);
            t.Add(new ActionMotionTemplate("cheer", amp, s, n, f,
                new MotionChannel("PARAM_Arm_LT_Angle", 0f, 0.5f, new MotionKey(0.3, top), new MotionKey(0.7, top), new MotionKey(1.0, 0f)),
                new MotionChannel("PARAM_Arm_RT_Angle", 0f, 0.5f, new MotionKey(0.3, top), new MotionKey(0.7, top), new MotionKey(1.0, 0f)),
                new MotionChannel("PARAM_shangxia", 0f, 0.2f, new MotionKey(0.3, bn), new MotionKey(0.7, bn), new MotionKey(1.0, 0f)),
                new MotionChannel("PARAM_Smile_eye", 0f, 0.2f, new MotionKey(0.3, 1f), new MotionKey(0.7, 1f), new MotionKey(1.0, 0f))));
        }

        private static void AddBow(List<ActionMotionTemplate> t, string amp, int s, int n, int f, float bodyPitch, float headPitch)
        {
            t.Add(new ActionMotionTemplate("bow", amp, s, n, f,
                new MotionChannel("ParamBodyAngleY", 0f, 1.5f, new MotionKey(0.35, bodyPitch), new MotionKey(0.65, bodyPitch), new MotionKey(1.0, 0f)),
                new MotionChannel("ParamAngleY", 0f, 3f, new MotionKey(0.35, headPitch), new MotionKey(0.65, headPitch), new MotionKey(1.0, 0f))));
        }

        public static string NormalizeAmplitude(string type, string amplitude)
        {
            if (type == "blink") return "full";
            return amplitude == "small" ? "small" : "normal";
        }

        public static string BuildPlanJson(string decision, IReadOnlyList<ActionStepSpec> steps)
        {
            var sb = new StringBuilder(256);
            sb.Append("{\"version\":\"").Append(PlanVersion).Append("\",\"decision\":\"")
              .Append(EscapeJson(decision ?? "none")).Append("\",\"steps\":[");

            if (decision == "execute" && steps != null)
            {
                for (int s = 0; s < steps.Count; s++)
                {
                    if (s > 0) sb.Append(',');
                    sb.Append("{\"actions\":[");
                    var actions = steps[s]?.actions;
                    if (actions != null)
                    {
                        for (int a = 0; a < actions.Count; a++)
                        {
                            if (a > 0) sb.Append(',');
                            var item = actions[a];
                            string amp = NormalizeAmplitude(item.type, item.amplitude);
                            string spd = string.IsNullOrEmpty(item.speed) ? "normal" : item.speed;
                            int cnt = Math.Max(1, Math.Min(3, item.count));
                            sb.Append("{\"type\":\"").Append(EscapeJson(item.type)).Append('"')
                              .Append(",\"count\":").Append(cnt.ToString(CultureInfo.InvariantCulture))
                              .Append(",\"amplitude\":\"").Append(EscapeJson(amp)).Append('"')
                              .Append(",\"speed\":\"").Append(EscapeJson(spd)).Append("\"}");
                        }
                    }
                    sb.Append("]}");
                }
            }

            sb.Append("]}");
            return sb.ToString();
        }

        private static int ScalePeriod(int baseMs, float scale) => Math.Max(240, (int)Math.Round(baseMs * scale));
        private static float Clamp(float v, float min, float max) => v < min ? min : (v > max ? max : v);

        private static string EscapeJson(string s)
        {
            if (string.IsNullOrEmpty(s)) return string.Empty;
            return s.Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\n", "\\n").Replace("\r", "\\r");
        }
    }
}
