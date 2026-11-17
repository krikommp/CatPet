using System;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Globalization;
using System.Text;

namespace PetLive2d.ActionLanguage
{
    public readonly struct MotionKey
    {
        public double Fraction { get; }
        public float Value { get; }
        public MotionKey(double fraction, float value) { Fraction = fraction; Value = value; }
    }

    public sealed class MotionChannel
    {
        public string ParameterId { get; }
        public float ReferenceValue { get; }
        public float StartTolerance { get; }
        public IReadOnlyList<MotionKey> Keys { get; }
        public MotionChannel(string parameterId, float referenceValue, float startTolerance, params MotionKey[] keys)
        {
            ParameterId = parameterId;
            ReferenceValue = referenceValue;
            StartTolerance = startTolerance;
            Keys = Array.AsReadOnly((MotionKey[])(keys ?? Array.Empty<MotionKey>()).Clone());
        }
    }

    /// <summary>Trusted host data. A complete cycle ends at each channel's reference value.</summary>
    public sealed class ActionMotionTemplate
    {
        public string Type { get; }
        public string Amplitude { get; }
        public IReadOnlyList<MotionChannel> Channels { get; }
        public int SlowPeriodMs { get; }
        public int NormalPeriodMs { get; }
        public int FastPeriodMs { get; }
        public ActionMotionTemplate(string type, string amplitude, int slowPeriodMs, int normalPeriodMs,
            int fastPeriodMs, params MotionChannel[] channels)
        {
            Type = type; Amplitude = amplitude;
            SlowPeriodMs = slowPeriodMs; NormalPeriodMs = normalPeriodMs; FastPeriodMs = fastPeriodMs;
            Channels = Array.AsReadOnly((MotionChannel[])(channels ?? Array.Empty<MotionChannel>()).Clone());
        }
        internal int Period(string speed) => speed == "slow" ? SlowPeriodMs : speed == "fast" ? FastPeriodMs : NormalPeriodMs;
    }

    public sealed class ActionMotionMap
    {
        public string Version { get; }
        public string ProfileId { get; }
        private readonly Dictionary<string, ActionMotionTemplate> _templates = new Dictionary<string, ActionMotionTemplate>(StringComparer.Ordinal);
        public ActionMotionMap(string version, string profileId, params ActionMotionTemplate[] templates)
        {
            if (string.IsNullOrWhiteSpace(version) || string.IsNullOrWhiteSpace(profileId))
                throw new ArgumentException("Motion map version and profile are required.");
            Version = version; ProfileId = profileId;
            foreach (var template in templates ?? Array.Empty<ActionMotionTemplate>())
            {
                if (template == null) throw new ArgumentException("Null template.");
                _templates.Add(template.Type + "/" + template.Amplitude, template);
            }
        }
        internal bool TryGet(string type, string amplitude, out ActionMotionTemplate template) =>
            _templates.TryGetValue(type + "/" + amplitude, out template);

        /// <summary>
        /// Explicit numerical prototype using the verified Natori eye IDs/ranges. This is not
        /// evidence of visual quality or a trained natural-language mapping. No head/ear mapping.
        /// </summary>
        public static ActionMotionMap CreateNatoriBlinkPrototype()
        {
            var keys = new[] { new MotionKey(1.0 / 3, 0), new MotionKey(2.0 / 3, 0), new MotionKey(1, 1) };
            return new ActionMotionMap("natori-blink-prototype.v0.1", "natori-demo.v1",
                new ActionMotionTemplate("blink", "full", 900, 600, 300,
                    new MotionChannel("ParamEyeLOpen", 1, 0.02f, keys),
                    new MotionChannel("ParamEyeROpen", 1, 0.02f, keys)));
        }
    }

    public sealed class ActionPlanCompilation
    {
        public string Decision { get; }
        public string NativeJson { get; }
        public CompiledActionPacket Packet { get; }
        public string MotionMapVersion { get; }
        private readonly IReadOnlyDictionary<string, float> _initialPose;
        private readonly IReadOnlyDictionary<string, float> _tolerances;
        private readonly IReadOnlyDictionary<string, float> _references;
        private readonly CapabilityProfile _profile;
        internal ActionPlanCompilation(string decision, string nativeJson, CompiledActionPacket packet,
            string mapVersion, Dictionary<string, float> initialPose, Dictionary<string, float> tolerances,
            Dictionary<string, float> references, CapabilityProfile profile)
        {
            Decision = decision; NativeJson = nativeJson; Packet = packet; MotionMapVersion = mapVersion;
            _initialPose = new ReadOnlyDictionary<string, float>(initialPose);
            _tolerances = new ReadOnlyDictionary<string, float>(tolerances);
            _references = new ReadOnlyDictionary<string, float>(references);
            _profile = profile;
        }

        /// <summary>Call again at the actual commit boundary, before submitting the native packet.</summary>
        public bool ValidateStartPose(IReadOnlyDictionary<string, float> currentPose, out ActionValidationError error)
        {
            foreach (var pair in _initialPose)
            {
                if (currentPose == null || !currentPose.TryGetValue(pair.Key, out var value) ||
                    !ActionPlanCompiler.IsFinite(value) || Math.Abs(value - pair.Value) > _tolerances[pair.Key] ||
                    Math.Abs(value - _references[pair.Key]) > _tolerances[pair.Key] ||
                    _profile == null || !_profile.TryGetParameter(pair.Key, out var definition) || value < definition.Min || value > definition.Max)
                    return ActionPlanCompiler.Fail("start_pose_changed", "$.pose." + pair.Key,
                        "The compiled initial pose changed; recompile or wait for a compatible pose.", out error);
            }
            error = null;
            return true;
        }
    }

    public static class ActionPlanCompiler
    {
        private sealed class Item { public string Type, Amplitude, Speed, Path; public int Count, PeriodMs; }
        internal static bool IsFinite(float value) => !float.IsNaN(value) && !float.IsInfinity(value);
        internal static bool Fail(string code, string path, string message, out ActionValidationError error)
        { error = new ActionValidationError(code, path, message); return false; }

        public static bool TryCompile(string planJson, CapabilityProfile profile, ActionMotionMap motionMap,
            IReadOnlyDictionary<string, float> currentPose, out ActionPlanCompilation result, out ActionValidationError error)
        {
            result = null;
            if (!TryParse(planJson, out var decision, out var steps, out error)) return false;
            var snapshot = new Dictionary<string, float>(StringComparer.Ordinal);
            var tolerances = new Dictionary<string, float>(StringComparer.Ordinal);
            if (decision != "execute")
            {
                result = new ActionPlanCompilation(decision, null, null, motionMap?.Version, snapshot, tolerances,
                    new Dictionary<string, float>(), profile);
                return true;
            }
            if (profile == null || motionMap == null || profile.ProfileId != motionMap.ProfileId)
                return Fail("motion_map_profile_mismatch", "$", "Bind a motion map to the active capability profile.", out error);

            var curves = new SortedDictionary<string, SortedDictionary<int, float>>(StringComparer.Ordinal);
            var references = new Dictionary<string, float>(StringComparer.Ordinal);
            int startMs = 0;
            foreach (var step in steps)
            {
                var occupied = new HashSet<string>(StringComparer.Ordinal);
                var resolved = new List<(Item item, ActionMotionTemplate template, int period)>();
                int stepDuration = 0;
                foreach (var item in step)
                {
                    if (!motionMap.TryGet(item.Type, item.Amplitude, out var template))
                        return Fail("unsupported_motion", item.Path, "No host-authorized motion template for this type/amplitude.", out error);
                    int period = item.PeriodMs != 0 ? item.PeriodMs : template.Period(item.Speed);
                    if (period < 240 || period > 3000)
                        return Fail("invalid_template_period", item.Path, "Resolved cycle must be 240..3000 ms.", out error);
                    if (template.Channels.Count == 0)
                        return Fail("invalid_motion_template", item.Path, "Template must write at least one channel.", out error);
                    foreach (var channel in template.Channels)
                    {
                        if (!ValidateChannel(channel, profile, item.Path, out error)) return false;
                        string id = channel.ParameterId;
                        if (!occupied.Add(id))
                            return Fail("parallel_channel_conflict", item.Path, "Parallel actions may not share native channels: " + id, out error);
                        if (references.TryGetValue(id, out var existingReference) && existingReference != channel.ReferenceValue)
                            return Fail("incompatible_reference_pose", item.Path, "Sequential templates disagree about their reference pose.", out error);
                        references[id] = channel.ReferenceValue;
                        if (!snapshot.ContainsKey(id))
                        {
                            profile.TryGetParameter(id, out var parameter);
                            if (currentPose == null || !currentPose.TryGetValue(id, out var initial) || !IsFinite(initial) ||
                                initial < parameter.Min || initial > parameter.Max || Math.Abs(initial - channel.ReferenceValue) > channel.StartTolerance)
                                return Fail("start_pose_mismatch", "$.pose." + id, "Actual pose is incompatible with the template reference.", out error);
                            snapshot.Add(id, initial);
                            tolerances.Add(id, channel.StartTolerance);
                            curves.Add(id, new SortedDictionary<int, float>());
                        }
                        else tolerances[id] = Math.Min(tolerances[id], channel.StartTolerance);
                    }
                    stepDuration = Math.Max(stepDuration, item.Count * period);
                    resolved.Add((item, template, period));
                }
                if (startMs + stepDuration > profile.MaxDurationMs)
                    return Fail("plan_duration_exceeded", "$.steps", "Compiled plan exceeds the native duration limit.", out error);
                foreach (var entry in resolved)
                {
                    foreach (var channel in entry.template.Channels)
                    {
                        var curve = curves[channel.ParameterId];
                        // A delayed first target alone would interpolate before this stage starts.
                        float startValue = curve.Count == 0 ? snapshot[channel.ParameterId] : channel.ReferenceValue;
                        if (!AddPoint(curve, startMs, startValue, out error)) return false;
                        for (int cycle = 0; cycle < entry.item.Count; cycle++)
                            foreach (var key in channel.Keys)
                            {
                                int offset = (int)Math.Round(key.Fraction * entry.period, MidpointRounding.AwayFromZero);
                                if (offset <= 0) return Fail("short_parameter_segment", entry.item.Path, "Template target rounds to the cycle start.", out error);
                                int time = startMs + cycle * entry.period + offset;
                                if (!AddPoint(curve, time, key.Value, out error)) return false;
                            }
                        if (!AddPoint(curve, startMs + stepDuration, channel.ReferenceValue, out error)) return false;
                    }
                }
                startMs += stepDuration;
            }
            // Only remove mathematically redundant constant-interval keys; never move a timestamp.
            var frames = new SortedDictionary<int, SortedDictionary<string, float>>();
            foreach (var pair in curves)
            {
                var keys = new List<KeyValuePair<int, float>>(pair.Value);
                for (int i = keys.Count - 2; i > 0; i--)
                    if (keys[i - 1].Value == keys[i].Value && keys[i].Value == keys[i + 1].Value) keys.RemoveAt(i);
                while (keys.Count > 1 && keys[keys.Count - 1].Value == keys[keys.Count - 2].Value) keys.RemoveAt(keys.Count - 1);
                foreach (var key in keys)
                {
                    if (!frames.TryGetValue(key.Key, out var values)) frames.Add(key.Key, values = new SortedDictionary<string, float>(StringComparer.Ordinal));
                    values.Add(pair.Key, key.Value);
                }
            }
            string nativeJson = Serialize(profile.ProfileId, startMs, frames);
            if (!ActionContract.TryValidateAndCompilePacketOnly(nativeJson, profile, out var packet, out error)) return false;
            var compilation = new ActionPlanCompilation(decision, nativeJson, packet, motionMap.Version, snapshot, tolerances, references, profile);
            if (!compilation.ValidateStartPose(currentPose, out error)) return false;
            result = compilation;
            return true;
        }

        private static bool ValidateChannel(MotionChannel channel, CapabilityProfile profile, string path, out ActionValidationError error)
        {
            if (channel == null || string.IsNullOrEmpty(channel.ParameterId) ||
                !profile.TryGetParameter(channel.ParameterId, out var parameter) || parameter.Owner != ParameterOwner.Foreground ||
                profile.IsPhysicsOutput(channel.ParameterId))
                return Fail("invalid_motion_channel", path, "Template channel is not a foreground capability.", out error);
            if (!IsFinite(channel.ReferenceValue) || channel.ReferenceValue < parameter.Min || channel.ReferenceValue > parameter.Max ||
                !IsFinite(channel.StartTolerance) || channel.StartTolerance < 0 || channel.Keys.Count == 0)
                return Fail("invalid_motion_template", path, "Invalid reference, tolerance or empty curve.", out error);
            double last = 0;
            foreach (var key in channel.Keys)
            {
                if (double.IsNaN(key.Fraction) || double.IsInfinity(key.Fraction) || key.Fraction <= last || key.Fraction > 1 ||
                    !IsFinite(key.Value) || key.Value < parameter.Min || key.Value > parameter.Max)
                    return Fail("invalid_motion_template", path, "Template keys must be ordered, finite and within capability bounds.", out error);
                last = key.Fraction;
            }
            if (last != 1 || channel.Keys[channel.Keys.Count - 1].Value != channel.ReferenceValue)
                return Fail("invalid_motion_template", path, "A full cycle must end at fraction 1 and return to the reference pose.", out error);
            error = null; return true;
        }

        private static bool AddPoint(SortedDictionary<int, float> curve, int time, float value, out ActionValidationError error)
        {
            error = null;
            if (time == 0) return true; // Native DSL supplies the actual implicit t=0 pose.
            if (curve.TryGetValue(time, out var existing) && existing != value)
                return Fail("keyframe_collision", "$.steps", "Template targets collide at a rounded timestamp.", out error);
            curve[time] = value;
            return true;
        }

        private static bool TryParse(string json, out string decision, out List<List<Item>> steps, out ActionValidationError error)
        {
            decision = null; steps = new List<List<Item>>();
            if (!StrictJsonParser.TryParseRootObject(json, CapabilityProfile.MaxJsonBytes, out var root, out error) ||
                !Only(root, "$", out error, "version", "decision", "steps") ||
                !root.TryGetString("version", "$.version", out var version, out error) ||
                !root.TryGetString("decision", "$.decision", out decision, out error) ||
                !root.TryGetArray("steps", "$.steps", out var rawSteps, out error)) return false;
            if (version != "action-plan.v0.1") return Fail("unsupported_plan_version", "$.version", "Expected action-plan.v0.1.", out error);
            if (decision != "execute" && decision != "none" && decision != "unsupported" && decision != "ambiguous")
                return Fail("invalid_decision", "$.decision", "Unknown decision.", out error);
            if (decision != "execute")
                return rawSteps.Count == 0 || Fail("nonexecute_has_steps", "$.steps", "Non-execute decisions require empty steps.", out error);
            if (rawSteps.Count < 1 || rawSteps.Count > 4) return Fail("invalid_steps", "$.steps", "Expected 1..4 steps.", out error);
            int total = 0;
            for (int i = 0; i < rawSteps.Count; i++)
            {
                string path = "$.steps[" + i + "]";
                if (rawSteps[i].Kind != StrictJsonValueKind.Object) return Fail("invalid_type", path, "Step must be an object.", out error);
                var step = rawSteps[i].ObjectValue;
                if (!Only(step, path, out error, "actions") || !step.TryGetArray("actions", path + ".actions", out var rawActions, out error)) return false;
                if (rawActions.Count < 1 || (total += rawActions.Count) > 4)
                    return Fail("action_count_limit", path + ".actions", "At least one action per step; at most four in the whole plan.", out error);
                var items = new List<Item>();
                for (int j = 0; j < rawActions.Count; j++)
                {
                    string ap = path + ".actions[" + j + "]";
                    if (rawActions[j].Kind != StrictJsonValueKind.Object) return Fail("invalid_type", ap, "Action must be an object.", out error);
                    var obj = rawActions[j].ObjectValue;
                    var item = new Item { Path = ap };
                    if (!Only(obj, ap, out error, "type", "count", "amplitude", "speed", "period_ms") ||
                        !obj.TryGetString("type", ap + ".type", out item.Type, out error) ||
                        !obj.TryGetInt("count", ap + ".count", out item.Count, out error) ||
                        !obj.TryGetString("amplitude", ap + ".amplitude", out item.Amplitude, out error)) return false;
                    if (!IsSupportedSemanticAction(item.Type))
                        return Fail("unknown_action_type", ap + ".type", "Unknown semantic action.", out error);
                    if (item.Count < 1 || item.Count > 5) return Fail("invalid_count", ap + ".count", "Count must be 1..5.", out error);
                    if (item.Type == "blink" ? item.Amplitude != "full" :
                        item.Amplitude != "small" && item.Amplitude != "normal" && item.Amplitude != "large")
                        return Fail("invalid_amplitude", ap + ".amplitude", "Amplitude is invalid for this action type.", out error);
                    if (obj.ContainsKey("speed") == obj.ContainsKey("period_ms"))
                        return Fail("ambiguous_timing", ap, "Provide exactly one of speed and period_ms.", out error);
                    if (obj.ContainsKey("speed"))
                    {
                        if (!obj.TryGetString("speed", ap + ".speed", out item.Speed, out error)) return false;
                        if (item.Speed != "slow" && item.Speed != "normal" && item.Speed != "fast")
                            return Fail("invalid_speed", ap + ".speed", "Speed must be slow, normal or fast.", out error);
                    }
                    else
                    {
                        if (!obj.TryGetInt("period_ms", ap + ".period_ms", out item.PeriodMs, out error)) return false;
                        if (item.PeriodMs < 240 || item.PeriodMs > 3000)
                            return Fail("invalid_period", ap + ".period_ms", "Period must be 240..3000 ms.", out error);
                    }
                    items.Add(item);
                }
                steps.Add(items);
            }
            error = null; return true;
        }

        private static bool Only(StrictJsonObject obj, string path, out ActionValidationError error, params string[] allowed)
        {
            foreach (string key in obj.Properties.Keys)
                if (Array.IndexOf(allowed, key) < 0) return Fail("unknown_field", path + "." + key, "Unknown field.", out error);
            error = null; return true;
        }

        private static string Quote(string value)
        {
            var text = new StringBuilder("\"");
            foreach (char c in value)
                if (c == '\\' || c == '"') text.Append('\\').Append(c);
                else if (c < 32) text.Append("\\u").Append(((int)c).ToString("x4", CultureInfo.InvariantCulture));
                else text.Append(c);
            return text.Append('"').ToString();
        }

        private static string Serialize(string profile, int duration, SortedDictionary<int, SortedDictionary<string, float>> frames)
        {
            var json = new StringBuilder("{\"version\":\"0.1\",\"profile\":").Append(Quote(profile))
                .Append(",\"duration_ms\":").Append(duration).Append(",\"frames\":[");
            bool firstFrame = true;
            foreach (var frame in frames)
            {
                if (!firstFrame) json.Append(','); firstFrame = false;
                json.Append("{\"at_ms\":").Append(frame.Key).Append(",\"values\":{");
                bool firstValue = true;
                foreach (var pair in frame.Value)
                {
                    if (!firstValue) json.Append(','); firstValue = false;
                    json.Append(Quote(pair.Key)).Append(':').Append(pair.Value.ToString("R", CultureInfo.InvariantCulture));
                }
                json.Append("}}");
            }
            return json.Append("]}").ToString();
        }

        private static bool IsSupportedSemanticAction(string type)
        {
            switch (type)
            {
                case "blink":
                case "nod":
                case "shake_head":
                case "tilt_head":
                case "look_around":
                case "smile":
                case "angry":
                case "shy":
                case "surprise":
                case "wave":
                case "cheer":
                case "bow":
                    return true;
                default:
                    return false;
            }
        }
    }
}
