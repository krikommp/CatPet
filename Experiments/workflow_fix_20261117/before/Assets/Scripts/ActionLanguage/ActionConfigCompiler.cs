using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace PetLive2d.ActionLanguage
{
    public enum HostExecutionMode
    {
        PreviewCandidate,
        FormalExecute
    }

    /// <summary>
    /// Strict parser and deterministic expander for action-config.v0.2 -> native v0.1 packet.
    /// Preserves continuous per-cycle duration_ms, amplitude_scale, and hold_ratio without quantizing to enums.
    /// </summary>
    public static class ActionConfigCompiler
    {
        public const string SupportedVersion = "action-config.v0.2";
        public const int MaxJsonBytes = 32 * 1024;

        private sealed class CycleSpec
        {
            public int DurationMs;
            public float AmplitudeScale;
            public float HoldRatio;
        }

        private sealed class ActionSpec
        {
            public ActionResourceDefinition Resource;
            public readonly List<CycleSpec> Cycles = new List<CycleSpec>();
            public string Path;
        }

        public static bool TryCompile(
            string json,
            CapabilityProfile profile,
            ActionResourceCatalog catalog,
            IReadOnlyDictionary<string, float> currentPose,
            HostExecutionMode mode,
            out ActionPlanCompilation compilation,
            out ActionValidationError error)
        {
            compilation = null;
            if (profile == null) return Fail("missing_profile", "$", "CapabilityProfile cannot be null.", out error);
            if (catalog == null) return Fail("missing_catalog", "$", "ActionResourceCatalog cannot be null.", out error);
            if (!string.Equals(catalog.ProfileId, profile.ProfileId, StringComparison.Ordinal))
                return Fail("catalog_profile_mismatch", "$", "Resource catalog profile does not match host profile.", out error);

            if (string.IsNullOrWhiteSpace(json)) return Fail("empty_json", "$", "Config JSON cannot be empty.", out error);
            if (json.Contains("```")) return Fail("code_fence_forbidden", "$", "Markdown code fences are forbidden.", out error);
            if (Encoding.UTF8.GetByteCount(json) > MaxJsonBytes) return Fail("json_too_large", "$", "Config JSON exceeds 32 KiB.", out error);

            if (!StrictJsonParser.TryParseRootObject(json, MaxJsonBytes, out var root, out error)) return false;
            if (!Only(root, "$", out error, "version", "decision", "steps") ||
                !root.TryGetString("version", "$.version", out var version, out error) ||
                !root.TryGetString("decision", "$.decision", out var decision, out error) ||
                !root.TryGetArray("steps", "$.steps", out var rawSteps, out error))
                return false;

            if (version != SupportedVersion)
                return Fail("unsupported_config_version", "$.version", $"Expected '{SupportedVersion}'.", out error);

            if (decision != "execute" && decision != "none" && decision != "unsupported" && decision != "ambiguous")
                return Fail("invalid_decision", "$.decision", "Decision must be execute, none, unsupported or ambiguous.", out error);

            if (decision != "execute")
            {
                if (rawSteps.Count != 0)
                    return Fail("non_execute_steps_forbidden", "$.steps", "steps must be empty unless decision is execute.", out error);
                compilation = new ActionPlanCompilation(
                    decision, null, null, catalog.Version,
                    new Dictionary<string, float>(), new Dictionary<string, float>(), new Dictionary<string, float>(), profile);
                return true;
            }

            if (rawSteps.Count < 1 || rawSteps.Count > 2)
                return Fail("invalid_step_count", "$.steps", "execute requires 1 to 2 steps in v0.2.", out error);

            var parsedSteps = new List<List<ActionSpec>>();
            int totalActions = 0;

            for (int s = 0; s < rawSteps.Count; s++)
            {
                string stepPath = $"$.steps[{s}]";
                if (rawSteps[s].Kind != StrictJsonValueKind.Object)
                    return Fail("invalid_type", stepPath, "Step must be an object.", out error);
                var stepObj = rawSteps[s].ObjectValue;
                if (!Only(stepObj, stepPath, out error, "actions") ||
                    !stepObj.TryGetArray("actions", stepPath + ".actions", out var rawActions, out error))
                    return false;
                if (rawActions.Count < 1)
                    return Fail("empty_step_actions", stepPath + ".actions", "Each step must contain at least 1 action.", out error);

                var stepActions = new List<ActionSpec>();
                for (int a = 0; a < rawActions.Count; a++)
                {
                    totalActions++;
                    if (totalActions > 2)
                        return Fail("too_many_actions", stepPath + $".actions[{a}]", "v0.2 supports at most 2 actions in total.", out error);

                    string ap = stepPath + $".actions[{a}]";
                    if (!ParseActionSpec(rawActions[a], ap, catalog, mode, out var actionSpec, out error))
                        return false;
                    stepActions.Add(actionSpec);
                }
                parsedSteps.Add(stepActions);
            }

            // Expand steps and cycles into native frames
            var frames = new SortedDictionary<int, SortedDictionary<string, float>>();
            var initialPose = new Dictionary<string, float>(StringComparer.Ordinal);
            var tolerances = new Dictionary<string, float>(StringComparer.Ordinal);
            var references = new Dictionary<string, float>(StringComparer.Ordinal);
            var activeInEarlierStep = new HashSet<string>(StringComparer.Ordinal);
            int stepStartMs = 0;

            for (int s = 0; s < parsedSteps.Count; s++)
            {
                var stepActions = parsedSteps[s];
                var stepChannels = new HashSet<string>(StringComparer.Ordinal);
                var stepEndByParam = new Dictionary<string, (int EndMs, float RefValue)>(StringComparer.Ordinal);
                int stepEndMs = stepStartMs;

                foreach (var act in stepActions)
                {
                    foreach (var ch in act.Resource.Channels)
                    {
                        if (!stepChannels.Add(ch.ParameterId))
                            return Fail("parallel_channel_conflict", act.Path, $"Parallel actions conflict on parameter '{ch.ParameterId}'.", out error);

                        if (!profile.TryGetParameter(ch.ParameterId, out var def))
                            return Fail("unknown_parameter", act.Path, $"Parameter '{ch.ParameterId}' is missing from profile.", out error);

                        if (!initialPose.ContainsKey(ch.ParameterId))
                        {
                            if (currentPose == null || !currentPose.TryGetValue(ch.ParameterId, out float curVal) || !ActionPlanCompiler.IsFinite(curVal))
                                return Fail("missing_pose_value", "$.pose." + ch.ParameterId, "Missing current pose value.", out error);
                            if (curVal < def.Min || curVal > def.Max || Math.Abs(curVal - ch.ReferenceValue) > ch.StartTolerance)
                                return Fail("incompatible_start_pose", "$.pose." + ch.ParameterId, $"Parameter '{ch.ParameterId}' is outside start pose tolerance.", out error);

                            initialPose[ch.ParameterId] = curVal;
                            tolerances[ch.ParameterId] = ch.StartTolerance;
                            references[ch.ParameterId] = ch.ReferenceValue;
                        }

                        // Anchor before first step if needed so later steps don't interpolate early.
                        if (stepStartMs > 0 && !activeInEarlierStep.Contains(ch.ParameterId))
                        {
                            SetFrameValue(frames, stepStartMs, ch.ParameterId, ch.ReferenceValue);
                        }
                    }

                    int cycleStartMs = stepStartMs;
                    for (int c = 0; c < act.Cycles.Count; c++)
                    {
                        var cyc = act.Cycles[c];
                        ExpandCycle(act.Resource, cyc, cycleStartMs, profile.MinParameterSegmentMs, frames);
                        cycleStartMs += cyc.DurationMs;
                    }

                    foreach (var ch in act.Resource.Channels)
                    {
                        stepEndByParam[ch.ParameterId] = (cycleStartMs, ch.ReferenceValue);
                        activeInEarlierStep.Add(ch.ParameterId);
                    }
                    if (cycleStartMs > stepEndMs) stepEndMs = cycleStartMs;
                }

                // Hold shorter parallel actions at reference until the longest action in this step finishes.
                if (s + 1 < parsedSteps.Count)
                {
                    foreach (var pair in stepEndByParam)
                    {
                        if (pair.Value.EndMs < stepEndMs)
                        {
                            SetFrameValue(frames, stepEndMs, pair.Key, pair.Value.RefValue);
                        }
                    }
                }
                stepStartMs = stepEndMs;
            }

            if (stepStartMs > profile.MaxDurationMs)
                return Fail("duration_exceeded", "$.steps", $"Total duration {stepStartMs}ms exceeds max {profile.MaxDurationMs}ms.", out error);

            string nativeJson = SerializeNative(profile.ProfileId, stepStartMs, frames);
            if (!ActionContract.TryValidateAndCompilePacketOnly(nativeJson, profile, out var packet, out error))
                return false;

            compilation = new ActionPlanCompilation(
                "execute", nativeJson, packet, catalog.Version, initialPose, tolerances, references, profile);
            return true;
        }

        private static bool ParseActionSpec(
            StrictJsonValue val,
            string ap,
            ActionResourceCatalog catalog,
            HostExecutionMode mode,
            out ActionSpec spec,
            out ActionValidationError error)
        {
            spec = null;
            if (val.Kind != StrictJsonValueKind.Object)
                return Fail("invalid_type", ap, "Action must be an object.", out error);
            var obj = val.ObjectValue;
            if (!Only(obj, ap, out error, "resource_id", "cycles") ||
                !obj.TryGetString("resource_id", ap + ".resource_id", out var resourceId, out error) ||
                !obj.TryGetArray("cycles", ap + ".cycles", out var rawCycles, out error))
                return false;

            if (!catalog.TryGetResource(resourceId, out var resDef))
                return Fail("unknown_resource_id", ap + ".resource_id", $"Unknown resource '{resourceId}'.", out error);

            if (mode == HostExecutionMode.FormalExecute && resDef.Status != ResourceCalibrationStatus.Calibrated)
                return Fail("resource_not_calibrated", ap + ".resource_id", $"Resource '{resourceId}' is not calibrated for formal execution.", out error);

            if (rawCycles.Count < 1 || rawCycles.Count > 3)
                return Fail("invalid_cycle_count", ap + ".cycles", "cycles length must be 1 to 3.", out error);

            spec = new ActionSpec { Resource = resDef, Path = ap };
            for (int c = 0; c < rawCycles.Count; c++)
            {
                string cp = ap + $".cycles[{c}]";
                if (rawCycles[c].Kind != StrictJsonValueKind.Object)
                    return Fail("invalid_type", cp, "Cycle must be an object.", out error);
                var cObj = rawCycles[c].ObjectValue;
                if (!Only(cObj, cp, out error, "duration_ms", "controls") ||
                    !cObj.TryGetInt("duration_ms", cp + ".duration_ms", out int durMs, out error) ||
                    !cObj.TryGetObject("controls", cp + ".controls", out var ctrlObj, out error))
                    return false;

                if (durMs < 240 || durMs > 3000 || durMs < resDef.MinDurationMs || durMs > resDef.MaxDurationMs)
                    return Fail("invalid_duration_ms", cp + ".duration_ms", $"duration_ms {durMs} is outside resource bounds [{resDef.MinDurationMs}, {resDef.MaxDurationMs}].", out error);

                float ampScale = resDef.DefaultAmplitudeScale;
                float holdRatio = resDef.DefaultHoldRatio;

                foreach (var kv in ctrlObj.Properties)
                {
                    if (kv.Key == "amplitude_scale")
                    {
                        if (!resDef.SupportsAmplitudeScale)
                            return Fail("unsupported_control", cp + ".controls.amplitude_scale", $"Resource '{resourceId}' does not allow amplitude_scale.", out error);
                        if (!TryGetFiniteFloat(kv.Value, cp + ".controls.amplitude_scale", out ampScale, out error))
                            return false;
                        if (ampScale < resDef.MinAmplitudeScale || ampScale > resDef.MaxAmplitudeScale)
                            return Fail("control_out_of_range", cp + ".controls.amplitude_scale", $"amplitude_scale {ampScale} outside [{resDef.MinAmplitudeScale}, {resDef.MaxAmplitudeScale}].", out error);
                    }
                    else if (kv.Key == "hold_ratio")
                    {
                        if (!resDef.SupportsHoldRatio)
                            return Fail("unsupported_control", cp + ".controls.hold_ratio", $"Resource '{resourceId}' does not allow hold_ratio.", out error);
                        if (!TryGetFiniteFloat(kv.Value, cp + ".controls.hold_ratio", out holdRatio, out error))
                            return false;
                        if (holdRatio < resDef.MinHoldRatio || holdRatio > resDef.MaxHoldRatio)
                            return Fail("control_out_of_range", cp + ".controls.hold_ratio", $"hold_ratio {holdRatio} outside [{resDef.MinHoldRatio}, {resDef.MaxHoldRatio}].", out error);
                    }
                    else
                    {
                        return Fail("unknown_control", cp + ".controls." + kv.Key, $"Unknown control '{kv.Key}'.", out error);
                    }
                }

                if (resDef.SupportsAmplitudeScale && !ctrlObj.ContainsKey("amplitude_scale"))
                    return Fail("missing_control", cp + ".controls.amplitude_scale", "amplitude_scale is required for this resource.", out error);
                if (resDef.SupportsHoldRatio && !ctrlObj.ContainsKey("hold_ratio"))
                    return Fail("missing_control", cp + ".controls.hold_ratio", "hold_ratio is required for this resource.", out error);

                spec.Cycles.Add(new CycleSpec { DurationMs = durMs, AmplitudeScale = ampScale, HoldRatio = holdRatio });
            }

            error = null;
            return true;
        }

        private static void ExpandCycle(
            ActionResourceDefinition res,
            CycleSpec cyc,
            int startMs,
            int minSegmentMs,
            SortedDictionary<int, SortedDictionary<string, float>> frames)
        {
            double holdMs = cyc.DurationMs * cyc.HoldRatio;
            double moveMs = cyc.DurationMs - holdMs;
            // ActionContract rejects any parameter segment shorter than MinParameterSegmentMs (80ms).
            if (holdMs < minSegmentMs || moveMs < 2.0 * minSegmentMs)
            {
                holdMs = 0.0;
                moveMs = cyc.DurationMs;
            }
            double enterMs = Math.Max(minSegmentMs, Math.Min(moveMs - minSegmentMs, moveMs * res.EnterReturnAlpha));
            double returnMs = moveMs - enterMs;

            foreach (var ch in res.Channels)
            {
                foreach (var pt in ch.Points)
                {
                    double offsetMs;
                    if (pt.Phase == "enter")
                    {
                        offsetMs = enterMs * pt.LocalFraction;
                    }
                    else if (pt.Phase == "hold")
                    {
                        if (holdMs < 1.0) continue; // skip zero-hold duplicate
                        offsetMs = enterMs + holdMs * pt.LocalFraction;
                    }
                    else
                    {
                        offsetMs = enterMs + holdMs + returnMs * pt.LocalFraction;
                    }

                    int atMs = startMs + (int)Math.Round(offsetMs, MidpointRounding.AwayFromZero);
                    if (atMs <= startMs) atMs = startMs + 1;

                    float targetVal = ch.Scalable
                        ? ch.ReferenceValue + cyc.AmplitudeScale * (pt.BaseValue - ch.ReferenceValue)
                        : pt.BaseValue;
                    SetFrameValue(frames, atMs, ch.ParameterId, targetVal);
                }
            }
        }

        private static void SetFrameValue(SortedDictionary<int, SortedDictionary<string, float>> frames, int atMs, string paramId, float value)
        {
            if (!frames.TryGetValue(atMs, out var dict))
            {
                dict = new SortedDictionary<string, float>(StringComparer.Ordinal);
                frames.Add(atMs, dict);
            }
            dict[paramId] = value;
        }

        private static bool TryGetFiniteFloat(StrictJsonValue val, string path, out float result, out ActionValidationError error)
        {
            result = 0f;
            if (val.Kind != StrictJsonValueKind.Number)
                return Fail("invalid_type", path, "Expected finite number.", out error);
            double d = val.NumberValue;
            if (double.IsNaN(d) || double.IsInfinity(d))
                return Fail("non_finite_number", path, "Non-finite number is forbidden.", out error);
            result = (float)d;
            error = null;
            return true;
        }

        private static bool Only(StrictJsonObject obj, string path, out ActionValidationError error, params string[] allowed)
        {
            var set = new HashSet<string>(allowed, StringComparer.Ordinal);
            foreach (var kv in obj.Properties)
            {
                if (!set.Contains(kv.Key))
                    return Fail("unknown_field", path + "." + kv.Key, $"Unknown field '{kv.Key}'.", out error);
            }
            error = null;
            return true;
        }

        private static string SerializeNative(string profile, int duration, SortedDictionary<int, SortedDictionary<string, float>> frames)
        {
            var sb = new StringBuilder("{\"version\":\"0.1\",\"profile\":").Append('"').Append(profile).Append('"')
                .Append(",\"duration_ms\":").Append(duration).Append(",\"frames\":[");
            bool firstF = true;
            foreach (var f in frames)
            {
                if (!firstF) sb.Append(',');
                firstF = false;
                sb.Append("{\"at_ms\":").Append(f.Key).Append(",\"values\":{");
                bool firstV = true;
                foreach (var kv in f.Value)
                {
                    if (!firstV) sb.Append(',');
                    firstV = false;
                    sb.Append('"').Append(kv.Key).Append("\":").Append(kv.Value.ToString("R", CultureInfo.InvariantCulture));
                }
                sb.Append("}}");
            }
            return sb.Append("]}").ToString();
        }

        private static bool Fail(string code, string path, string msg, out ActionValidationError error)
        {
            error = new ActionValidationError(code, path, msg);
            return false;
        }
    }
}
