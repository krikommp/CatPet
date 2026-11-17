using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;

namespace PetLive2d.ActionLanguage
{
    public enum ParameterOwner
    {
        Foreground,
        Local
    }

    public sealed class ParameterDefinition
    {
        public string Id { get; }
        public int SlotIndex { get; }
        public float Min { get; }
        public float Max { get; }
        public float DefaultValue { get; }
        public ParameterOwner Owner { get; }
        public string Label { get; }
        public string SemanticStatus { get; }

        public ParameterDefinition(
            string id,
            int slotIndex,
            float min,
            float max,
            float defaultValue,
            ParameterOwner owner,
            string label = "",
            string semanticStatus = "")
        {
            Id = id ?? throw new ArgumentNullException(nameof(id));
            SlotIndex = slotIndex;
            Min = min;
            Max = max;
            DefaultValue = defaultValue;
            Owner = owner;
            Label = label ?? string.Empty;
            SemanticStatus = semanticStatus ?? string.Empty;
        }
    }

    public sealed class CapabilityProfile
    {
        public const string SupportedProtocolVersion = "0.1";
        public const int MaxJsonBytes = 32 * 1024;

        public string ProfileId { get; }
        public string ModelName { get; }
        public int MaxDurationMs { get; }
        public int MinDurationMs { get; }
        public int MaxFrames { get; }
        public int MaxDistinctParameters { get; }
        public int MinParameterSegmentMs { get; }
        public int ReleaseMs { get; }

        private readonly List<ParameterDefinition> _parameterList;
        private readonly Dictionary<string, ParameterDefinition> _parametersById;
        private readonly HashSet<string> _physicsOutputIds;

        public IReadOnlyList<ParameterDefinition> Parameters => _parameterList;
        public IReadOnlyCollection<string> PhysicsOutputIds => _physicsOutputIds;

        public CapabilityProfile(
            string profileId,
            string modelName,
            IEnumerable<ParameterDefinition> parameters,
            IEnumerable<string> physicsOutputIds = null,
            int minDurationMs = 80,
            int maxDurationMs = 10000,
            int maxFrames = 32,
            int maxDistinctParameters = 16,
            int minParameterSegmentMs = 80,
            int releaseMs = 200)
        {
            if (string.IsNullOrWhiteSpace(profileId))
            {
                throw new ArgumentException("ProfileId cannot be empty.", nameof(profileId));
            }

            ProfileId = profileId;
            ModelName = modelName ?? string.Empty;
            MinDurationMs = minDurationMs;
            MaxDurationMs = maxDurationMs;
            MaxFrames = maxFrames;
            MaxDistinctParameters = maxDistinctParameters;
            MinParameterSegmentMs = minParameterSegmentMs;
            ReleaseMs = releaseMs;

            _parameterList = new List<ParameterDefinition>();
            _parametersById = new Dictionary<string, ParameterDefinition>(StringComparer.Ordinal);
            if (parameters != null)
            {
                foreach (var param in parameters)
                {
                    if (param == null) continue;
                    var indexed = new ParameterDefinition(
                        param.Id,
                        _parameterList.Count,
                        param.Min,
                        param.Max,
                        param.DefaultValue,
                        param.Owner,
                        param.Label,
                        param.SemanticStatus);
                    _parameterList.Add(indexed);
                    _parametersById[indexed.Id] = indexed;
                }
            }

            _physicsOutputIds = physicsOutputIds != null
                ? new HashSet<string>(physicsOutputIds, StringComparer.Ordinal)
                : new HashSet<string>(StringComparer.Ordinal);
        }

        public bool TryGetParameter(string id, out ParameterDefinition definition)
        {
            return _parametersById.TryGetValue(id, out definition);
        }

        public bool IsPhysicsOutput(string id)
        {
            return _physicsOutputIds.Contains(id);
        }

        public static bool TryParseProfileJson(string json, out CapabilityProfile profile, out ActionValidationError error)
        {
            profile = null;
            if (!StrictJsonParser.TryParseRootObject(json, MaxJsonBytes * 4, out var root, out error))
            {
                return false;
            }

            if (!root.TryGetString("profile", "$.profile", out var profileId, out error) || string.IsNullOrEmpty(profileId))
            {
                error = error ?? new ActionValidationError("invalid_profile", "$.profile", "Profile ID is required.");
                return false;
            }

            string modelName = string.Empty;
            if (root.ContainsKey("model"))
            {
                if (!root.TryGetString("model", "$.model", out modelName, out error))
                {
                    return false;
                }
            }

            int maxDurationMs = 10000;
            int maxFrames = 32;
            int maxDistinctParameters = 16;
            int minSegmentMs = 80;
            int releaseMs = 200;

            if (root.TryGetObject("proposed_policy", "$.proposed_policy", out var policyObj, out error))
            {
                if (policyObj.ContainsKey("max_duration_ms") &&
                    !policyObj.TryGetInt("max_duration_ms", "$.proposed_policy.max_duration_ms", out maxDurationMs, out error))
                    return false;
                if (policyObj.ContainsKey("max_frames") &&
                    !policyObj.TryGetInt("max_frames", "$.proposed_policy.max_frames", out maxFrames, out error))
                    return false;
                if (policyObj.ContainsKey("max_distinct_parameters") &&
                    !policyObj.TryGetInt("max_distinct_parameters", "$.proposed_policy.max_distinct_parameters", out maxDistinctParameters, out error))
                    return false;
                if (policyObj.ContainsKey("min_parameter_segment_ms") &&
                    !policyObj.TryGetInt("min_parameter_segment_ms", "$.proposed_policy.min_parameter_segment_ms", out minSegmentMs, out error))
                    return false;
                if (policyObj.ContainsKey("release_ms") &&
                    !policyObj.TryGetInt("release_ms", "$.proposed_policy.release_ms", out releaseMs, out error))
                    return false;
            }
            else if (error != null)
            {
                return false;
            }

            if (!root.TryGetObject("parameters", "$.parameters", out var paramsObj, out error) || paramsObj == null)
            {
                error = error ?? new ActionValidationError("missing_parameters", "$.parameters", "Profile must define parameters.");
                return false;
            }

            var paramDefs = new List<ParameterDefinition>(paramsObj.Properties.Count);
            int slotIndex = 0;
            foreach (var kv in paramsObj.Properties)
            {
                string paramId = kv.Key;
                string paramPath = "$.parameters." + paramId;
                if (kv.Value.Kind != StrictJsonValueKind.Object)
                {
                    error = new ActionValidationError("invalid_parameter_def", paramPath, "Parameter entry must be an object.");
                    return false;
                }

                var pObj = kv.Value.ObjectValue;
                if (!pObj.TryGetFloat("min", paramPath + ".min", out float minVal, out error) ||
                    !pObj.TryGetFloat("max", paramPath + ".max", out float maxVal, out error) ||
                    !pObj.TryGetFloat("default", paramPath + ".default", out float defaultVal, out error) ||
                    !pObj.TryGetString("owner", paramPath + ".owner", out string ownerStr, out error))
                {
                    return false;
                }

                if (minVal > maxVal || defaultVal < minVal || defaultVal > maxVal)
                {
                    error = new ActionValidationError("invalid_parameter_range", paramPath, "Parameter min/max/default range is inconsistent.");
                    return false;
                }

                ParameterOwner owner;
                if (string.Equals(ownerStr, "foreground", StringComparison.Ordinal))
                {
                    owner = ParameterOwner.Foreground;
                }
                else if (string.Equals(ownerStr, "local", StringComparison.Ordinal))
                {
                    owner = ParameterOwner.Local;
                }
                else
                {
                    error = new ActionValidationError("invalid_parameter_owner", paramPath + ".owner", $"Unsupported parameter owner '{ownerStr}'.");
                    return false;
                }

                string label = string.Empty;
                if (pObj.ContainsKey("label") && !pObj.TryGetString("label", paramPath + ".label", out label, out error))
                    return false;

                string semanticStatus = string.Empty;
                if (pObj.ContainsKey("semantic_status") && !pObj.TryGetString("semantic_status", paramPath + ".semantic_status", out semanticStatus, out error))
                    return false;

                paramDefs.Add(new ParameterDefinition(paramId, slotIndex++, minVal, maxVal, defaultVal, owner, label, semanticStatus));
            }

            var physicsIds = new List<string>();
            if (root.ContainsKey("physics_output_ids"))
            {
                if (!root.TryGetArray("physics_output_ids", "$.physics_output_ids", out var physArr, out error))
                    return false;
                for (int i = 0; i < physArr.Count; i++)
                {
                    if (physArr[i].Kind != StrictJsonValueKind.String)
                    {
                        error = new ActionValidationError("invalid_physics_id", $"$.physics_output_ids[{i}]", "Physics output ID must be a string.");
                        return false;
                    }
                    physicsIds.Add(physArr[i].StringValue);
                }
            }

            profile = new CapabilityProfile(
                profileId,
                modelName,
                paramDefs,
                physicsIds,
                80,
                maxDurationMs,
                maxFrames,
                maxDistinctParameters,
                minSegmentMs,
                releaseMs);
            error = null;
            return true;
        }
    }

    public readonly struct ActionRequestContext
    {
        public string RequestId { get; }
        public string SessionId { get; }
        public string CharacterInstanceId { get; }
        public int Generation { get; }
        public double? ExpiresAtMs { get; }

        public ActionRequestContext(
            string requestId,
            string sessionId,
            string characterInstanceId,
            int generation,
            double? expiresAtMs = null)
        {
            RequestId = requestId ?? string.Empty;
            SessionId = sessionId ?? string.Empty;
            CharacterInstanceId = characterInstanceId ?? string.Empty;
            Generation = generation;
            ExpiresAtMs = expiresAtMs;
        }
    }

    public sealed class HostSessionState
    {
        public string SessionId { get; private set; }
        public string CharacterInstanceId { get; private set; }
        public string ActiveProfileId { get; private set; }
        public int Generation { get; private set; }

        private readonly HashSet<string> _committedRequestIds = new HashSet<string>(StringComparer.Ordinal);

        public HostSessionState(string sessionId, string characterInstanceId, string activeProfileId, int initialGeneration = 1)
        {
            SessionId = sessionId ?? string.Empty;
            CharacterInstanceId = characterInstanceId ?? string.Empty;
            ActiveProfileId = activeProfileId ?? string.Empty;
            Generation = initialGeneration;
        }

        public void AdvanceGeneration()
        {
            Generation++;
        }

        public void RebindCharacter(string characterInstanceId, string activeProfileId)
        {
            CharacterInstanceId = characterInstanceId ?? string.Empty;
            ActiveProfileId = activeProfileId ?? string.Empty;
            Generation++;
            _committedRequestIds.Clear();
        }

        public bool IsRequestCommitted(string requestId)
        {
            return !string.IsNullOrEmpty(requestId) && _committedRequestIds.Contains(requestId);
        }

        public void MarkRequestCommitted(string requestId)
        {
            if (!string.IsNullOrEmpty(requestId))
            {
                _committedRequestIds.Add(requestId);
            }
        }

        public ActionRequestContext CreateRequestContext(string requestId, double? expiresAtMs = null)
        {
            return new ActionRequestContext(requestId, SessionId, CharacterInstanceId, Generation, expiresAtMs);
        }
    }

    public sealed class ActionValidationError
    {
        public string Code { get; }
        public string FieldPath { get; }
        public string Message { get; }

        public ActionValidationError(string code, string fieldPath, string message)
        {
            Code = code ?? "validation_error";
            FieldPath = fieldPath ?? "$";
            Message = message ?? "Validation failed.";
        }

        public override string ToString()
        {
            return $"[{Code}] {FieldPath}: {Message}";
        }
    }

    public readonly struct CompiledKeyframe
    {
        public int AtMs { get; }
        public float TargetValue { get; }

        public CompiledKeyframe(int atMs, float targetValue)
        {
            AtMs = atMs;
            TargetValue = targetValue;
        }
    }

    public sealed class CompiledParameterCurve
    {
        public string ParameterId { get; }
        public int ProfileSlotIndex { get; }
        public float MinValue { get; }
        public float MaxValue { get; }
        public CompiledKeyframe[] Keyframes { get; }

        public CompiledParameterCurve(
            string parameterId,
            int profileSlotIndex,
            float minValue,
            float maxValue,
            CompiledKeyframe[] keyframes)
        {
            ParameterId = parameterId;
            ProfileSlotIndex = profileSlotIndex;
            MinValue = minValue;
            MaxValue = maxValue;
            Keyframes = keyframes;
        }
    }

    public sealed class CompiledActionPacket
    {
        public string Version { get; }
        public string ProfileId { get; }
        public int DurationMs { get; }
        public string Subtitle { get; }
        public CompiledParameterCurve[] Curves { get; }

        public CompiledActionPacket(
            string version,
            string profileId,
            int durationMs,
            string subtitle,
            CompiledParameterCurve[] curves)
        {
            Version = version;
            ProfileId = profileId;
            DurationMs = durationMs;
            Subtitle = subtitle;
            Curves = curves ?? Array.Empty<CompiledParameterCurve>();
        }
    }

    public static class ActionContract
    {
        public static bool ValidateRequestContext(
            in ActionRequestContext context,
            HostSessionState hostState,
            double nowMs,
            out ActionValidationError error)
        {
            if (hostState == null)
            {
                error = new ActionValidationError("host_not_ready", "$", "Host session state is null.");
                return false;
            }

            if (string.IsNullOrEmpty(context.RequestId))
            {
                error = new ActionValidationError("missing_request_id", "$.request.id", "Host request ID is required.");
                return false;
            }

            if (hostState.IsRequestCommitted(context.RequestId))
            {
                error = new ActionValidationError("duplicate_request", "$.request.id", $"Request '{context.RequestId}' has already been committed.");
                return false;
            }

            if (!string.Equals(context.SessionId, hostState.SessionId, StringComparison.Ordinal))
            {
                error = new ActionValidationError("session_mismatch", "$.request.session_id", "Request belongs to a different session.");
                return false;
            }

            if (!string.Equals(context.CharacterInstanceId, hostState.CharacterInstanceId, StringComparison.Ordinal))
            {
                error = new ActionValidationError("character_mismatch", "$.request.character_id", "Request belongs to a different character instance.");
                return false;
            }

            if (context.Generation != hostState.Generation)
            {
                error = new ActionValidationError("stale_generation", "$.request.generation", $"Request generation {context.Generation} does not match current host generation {hostState.Generation}.");
                return false;
            }

            if (context.ExpiresAtMs.HasValue && nowMs > context.ExpiresAtMs.Value)
            {
                error = new ActionValidationError("request_expired", "$.request.expires_at_ms", "Request expired before submission/commit.");
                return false;
            }

            error = null;
            return true;
        }

        public static bool TryValidateAndCompile(
            string json,
            CapabilityProfile profile,
            in ActionRequestContext requestContext,
            HostSessionState hostState,
            double nowMs,
            out CompiledActionPacket compiledPacket,
            out ActionValidationError error)
        {
            compiledPacket = null;

            if (profile == null)
            {
                error = new ActionValidationError("missing_profile", "$", "Active capability profile is null.");
                return false;
            }

            if (!ValidateRequestContext(in requestContext, hostState, nowMs, out error))
            {
                return false;
            }

            if (!string.Equals(profile.ProfileId, hostState.ActiveProfileId, StringComparison.Ordinal))
            {
                error = new ActionValidationError("host_profile_mismatch", "$.profile", "Host active profile does not match bound CapabilityProfile.");
                return false;
            }

            if (!TryValidateAndCompilePacketOnly(json, profile, out compiledPacket, out error))
            {
                return false;
            }

            return true;
        }

        public static bool TryValidateAndCompilePacketOnly(
            string json,
            CapabilityProfile profile,
            out CompiledActionPacket compiledPacket,
            out ActionValidationError error)
        {
            compiledPacket = null;

            if (profile == null)
            {
                error = new ActionValidationError("missing_profile", "$", "Active capability profile is null.");
                return false;
            }

            if (!StrictJsonParser.TryParseRootObject(json, CapabilityProfile.MaxJsonBytes, out var root, out error))
            {
                return false;
            }

            // 1. Check unknown root fields
            foreach (var key in root.Properties.Keys)
            {
                if (key != "version" && key != "profile" && key != "duration_ms" && key != "subtitle" && key != "frames")
                {
                    error = new ActionValidationError("unknown_field", "$." + key, $"Unknown field '{key}' at root object.");
                    return false;
                }
            }

            // 2. version == "0.1"
            if (!root.TryGetString("version", "$.version", out string version, out error))
            {
                return false;
            }
            if (!string.Equals(version, CapabilityProfile.SupportedProtocolVersion, StringComparison.Ordinal))
            {
                error = new ActionValidationError("unsupported_version", "$.version", $"Unsupported protocol version '{version}'. Expected '0.1'.");
                return false;
            }

            // 3. profile matches active profile
            if (!root.TryGetString("profile", "$.profile", out string packetProfile, out error))
            {
                return false;
            }
            if (packetProfile.Length < 1 || packetProfile.Length > 96)
            {
                error = new ActionValidationError("invalid_profile_length", "$.profile", "Profile identifier length must be between 1 and 96.");
                return false;
            }
            if (!string.Equals(packetProfile, profile.ProfileId, StringComparison.Ordinal))
            {
                error = new ActionValidationError("wrong_profile", "$.profile", $"Packet profile '{packetProfile}' does not match active profile '{profile.ProfileId}'.");
                return false;
            }

            // 4. duration_ms integer in 80..10000
            if (!root.TryGetInt("duration_ms", "$.duration_ms", out int durationMs, out error))
            {
                return false;
            }
            if (durationMs < profile.MinDurationMs || durationMs > profile.MaxDurationMs)
            {
                error = new ActionValidationError(
                    "invalid_duration",
                    "$.duration_ms",
                    $"duration_ms ({durationMs}) must be between {profile.MinDurationMs} and {profile.MaxDurationMs}.");
                return false;
            }

            // 5. optional subtitle (1..300 Unicode code points)
            string subtitle = null;
            if (root.ContainsKey("subtitle"))
            {
                if (!root.TryGetString("subtitle", "$.subtitle", out subtitle, out error))
                {
                    return false;
                }
                int codePoints = CountUnicodeCodePoints(subtitle);
                if (codePoints < 1 || codePoints > 300)
                {
                    error = new ActionValidationError(
                        "invalid_subtitle_length",
                        "$.subtitle",
                        $"subtitle length ({codePoints} code points) must be between 1 and 300.");
                    return false;
                }
            }

            // 6. frames (1..32 items)
            if (!root.TryGetArray("frames", "$.frames", out var framesArray, out error))
            {
                return false;
            }
            if (framesArray.Count < 1 || framesArray.Count > profile.MaxFrames)
            {
                error = new ActionValidationError(
                    "invalid_frames_count",
                    "$.frames",
                    $"frames count ({framesArray.Count}) must be between 1 and {profile.MaxFrames}.");
                return false;
            }

            var curvesBuilder = new Dictionary<string, List<CompiledKeyframe>>(StringComparer.Ordinal);
            var curveDefinitions = new Dictionary<string, ParameterDefinition>(StringComparer.Ordinal);
            var orderedParameterIds = new List<string>();

            int previousFrameAtMs = 0;

            for (int i = 0; i < framesArray.Count; i++)
            {
                string framePath = $"$.frames[{i}]";
                var frameVal = framesArray[i];
                if (frameVal.Kind != StrictJsonValueKind.Object)
                {
                    error = new ActionValidationError("invalid_frame", framePath, "Each frame must be a JSON object.");
                    return false;
                }

                var frameObj = frameVal.ObjectValue;
                foreach (var key in frameObj.Properties.Keys)
                {
                    if (key != "at_ms" && key != "values")
                    {
                        error = new ActionValidationError("unknown_field", $"{framePath}.{key}", $"Unknown field '{key}' in frame object.");
                        return false;
                    }
                }

                if (!frameObj.TryGetInt("at_ms", framePath + ".at_ms", out int atMs, out error))
                {
                    return false;
                }

                if (atMs <= 0)
                {
                    error = new ActionValidationError("explicit_zero", framePath + ".at_ms", "at_ms must be >= 80; explicit at_ms <= 0 is forbidden.");
                    return false;
                }

                if (atMs < profile.MinParameterSegmentMs)
                {
                    error = new ActionValidationError(
                        "short_parameter_segment",
                        framePath + ".at_ms",
                        $"at_ms ({atMs}) must be at least {profile.MinParameterSegmentMs}ms from implicit t=0.");
                    return false;
                }

                if (i > 0)
                {
                    if (atMs == previousFrameAtMs)
                    {
                        error = new ActionValidationError("duplicate_time", framePath + ".at_ms", $"Duplicate frame time at_ms={atMs}.");
                        return false;
                    }
                    if (atMs < previousFrameAtMs)
                    {
                        error = new ActionValidationError("non_increasing_time", framePath + ".at_ms", $"Frame at_ms ({atMs}) must be strictly greater than previous frame ({previousFrameAtMs}).");
                        return false;
                    }
                }

                if (atMs > durationMs)
                {
                    error = new ActionValidationError("frame_after_end", framePath + ".at_ms", $"Frame at_ms ({atMs}) exceeds duration_ms ({durationMs}).");
                    return false;
                }

                previousFrameAtMs = atMs;

                if (!frameObj.TryGetObject("values", framePath + ".values", out var valuesObj, out error))
                {
                    return false;
                }

                if (valuesObj.Properties.Count < 1 || valuesObj.Properties.Count > profile.MaxDistinctParameters)
                {
                    error = new ActionValidationError(
                        "invalid_values_count",
                        framePath + ".values",
                        $"Frame values must contain between 1 and {profile.MaxDistinctParameters} parameters.");
                    return false;
                }

                foreach (var kv in valuesObj.Properties)
                {
                    string paramId = kv.Key;
                    string valuePath = $"{framePath}.values.{paramId}";

                    if (string.IsNullOrEmpty(paramId) || paramId.Length > 128)
                    {
                        error = new ActionValidationError("invalid_parameter_id", valuePath, "Parameter ID must be 1..128 characters.");
                        return false;
                    }

                    if (profile.IsPhysicsOutput(paramId))
                    {
                        error = new ActionValidationError("physics_parameter_forbidden", valuePath, $"Parameter '{paramId}' is a physics output and cannot be controlled by foreground.");
                        return false;
                    }

                    if (!profile.TryGetParameter(paramId, out var paramDef))
                    {
                        error = new ActionValidationError("invented_parameter", valuePath, $"Parameter '{paramId}' is not listed in profile '{profile.ProfileId}'.");
                        return false;
                    }

                    if (paramDef.Owner != ParameterOwner.Foreground)
                    {
                        error = new ActionValidationError("reserved_local_parameter", valuePath, $"Parameter '{paramId}' is owned by local controller and cannot be controlled by foreground.");
                        return false;
                    }

                    if (!valuesObj.TryGetFloat(paramId, valuePath, out float targetValue, out error))
                    {
                        return false;
                    }

                    if (targetValue < paramDef.Min || targetValue > paramDef.Max)
                    {
                        error = new ActionValidationError(
                            "model_range_exceeded",
                            valuePath,
                            $"Value {targetValue} for '{paramId}' is outside allowed range [{paramDef.Min}, {paramDef.Max}].");
                        return false;
                    }

                    if (!curvesBuilder.TryGetValue(paramId, out var keyframeList))
                    {
                        if (curvesBuilder.Count >= profile.MaxDistinctParameters)
                        {
                            error = new ActionValidationError(
                                "too_many_distinct_parameters",
                                valuePath,
                                $"Packet exceeds maximum of {profile.MaxDistinctParameters} distinct parameters.");
                            return false;
                        }

                        keyframeList = new List<CompiledKeyframe>();
                        curvesBuilder[paramId] = keyframeList;
                        curveDefinitions[paramId] = paramDef;
                        orderedParameterIds.Add(paramId);
                    }
                    else
                    {
                        var prevKeyframe = keyframeList[keyframeList.Count - 1];
                        if (atMs - prevKeyframe.AtMs < profile.MinParameterSegmentMs)
                        {
                            error = new ActionValidationError(
                                "short_parameter_segment",
                                valuePath,
                                $"Parameter '{paramId}' segment interval ({atMs - prevKeyframe.AtMs}ms) is shorter than {profile.MinParameterSegmentMs}ms.");
                            return false;
                        }
                    }

                    keyframeList.Add(new CompiledKeyframe(atMs, targetValue));
                }
            }

            var compiledCurves = new CompiledParameterCurve[orderedParameterIds.Count];
            for (int i = 0; i < orderedParameterIds.Count; i++)
            {
                string paramId = orderedParameterIds[i];
                var def = curveDefinitions[paramId];
                var kfList = curvesBuilder[paramId];
                compiledCurves[i] = new CompiledParameterCurve(
                    paramId,
                    def.SlotIndex,
                    def.Min,
                    def.Max,
                    kfList.ToArray());
            }

            compiledPacket = new CompiledActionPacket(
                version,
                packetProfile,
                durationMs,
                subtitle,
                compiledCurves);
            error = null;
            return true;
        }

        public static int CountUnicodeCodePoints(string text)
        {
            if (text == null) return 0;
            int count = 0;
            for (int i = 0; i < text.Length; i++)
            {
                if (char.IsHighSurrogate(text[i]))
                {
                    if (i + 1 < text.Length && char.IsLowSurrogate(text[i + 1]))
                    {
                        i++;
                    }
                }
                count++;
            }
            return count;
        }
    }

    internal enum StrictJsonValueKind
    {
        Object,
        Array,
        String,
        Number,
        Boolean,
        Null
    }

    internal readonly struct StrictJsonValue
    {
        public StrictJsonValueKind Kind { get; }
        public StrictJsonObject ObjectValue { get; }
        public List<StrictJsonValue> ArrayValue { get; }
        public string StringValue { get; }
        public double NumberValue { get; }
        public bool IsIntegerToken { get; }
        public bool BoolValue { get; }

        public StrictJsonValue(StrictJsonObject obj)
        {
            Kind = StrictJsonValueKind.Object;
            ObjectValue = obj;
            ArrayValue = null;
            StringValue = null;
            NumberValue = 0;
            IsIntegerToken = false;
            BoolValue = false;
        }

        public StrictJsonValue(List<StrictJsonValue> arr)
        {
            Kind = StrictJsonValueKind.Array;
            ObjectValue = null;
            ArrayValue = arr;
            StringValue = null;
            NumberValue = 0;
            IsIntegerToken = false;
            BoolValue = false;
        }

        public StrictJsonValue(string str)
        {
            Kind = StrictJsonValueKind.String;
            ObjectValue = null;
            ArrayValue = null;
            StringValue = str;
            NumberValue = 0;
            IsIntegerToken = false;
            BoolValue = false;
        }

        public StrictJsonValue(double num, bool isIntegerToken)
        {
            Kind = StrictJsonValueKind.Number;
            ObjectValue = null;
            ArrayValue = null;
            StringValue = null;
            NumberValue = num;
            IsIntegerToken = isIntegerToken;
            BoolValue = false;
        }

        public StrictJsonValue(bool b)
        {
            Kind = StrictJsonValueKind.Boolean;
            ObjectValue = null;
            ArrayValue = null;
            StringValue = null;
            NumberValue = 0;
            IsIntegerToken = false;
            BoolValue = b;
        }

        public static StrictJsonValue CreateNull()
        {
            return new StrictJsonValue(StrictJsonValueKind.Null);
        }

        private StrictJsonValue(StrictJsonValueKind kind)
        {
            Kind = kind;
            ObjectValue = null;
            ArrayValue = null;
            StringValue = null;
            NumberValue = 0;
            IsIntegerToken = false;
            BoolValue = false;
        }
    }

    internal sealed class StrictJsonObject
    {
        public Dictionary<string, StrictJsonValue> Properties { get; } =
            new Dictionary<string, StrictJsonValue>(StringComparer.Ordinal);

        public bool ContainsKey(string key) => Properties.ContainsKey(key);

        public bool TryGetString(string key, string path, out string value, out ActionValidationError error)
        {
            value = null;
            if (!Properties.TryGetValue(key, out var jsonVal))
            {
                error = new ActionValidationError("missing_field", path, $"Required field '{key}' is missing.");
                return false;
            }
            if (jsonVal.Kind != StrictJsonValueKind.String)
            {
                error = new ActionValidationError("invalid_type", path, $"Field '{key}' must be a string.");
                return false;
            }
            value = jsonVal.StringValue;
            error = null;
            return true;
        }

        public bool TryGetInt(string key, string path, out int value, out ActionValidationError error)
        {
            value = 0;
            if (!Properties.TryGetValue(key, out var jsonVal))
            {
                error = new ActionValidationError("missing_field", path, $"Required field '{key}' is missing.");
                return false;
            }
            if (jsonVal.Kind != StrictJsonValueKind.Number || !jsonVal.IsIntegerToken)
            {
                error = new ActionValidationError("invalid_type", path, $"Field '{key}' must be an integer.");
                return false;
            }
            if (jsonVal.NumberValue < int.MinValue || jsonVal.NumberValue > int.MaxValue)
            {
                error = new ActionValidationError("number_out_of_range", path, $"Integer '{key}' is out of 32-bit range.");
                return false;
            }
            value = (int)jsonVal.NumberValue;
            error = null;
            return true;
        }

        public bool TryGetFloat(string key, string path, out float value, out ActionValidationError error)
        {
            value = 0f;
            if (!Properties.TryGetValue(key, out var jsonVal))
            {
                error = new ActionValidationError("missing_field", path, $"Required field '{key}' is missing.");
                return false;
            }
            if (jsonVal.Kind != StrictJsonValueKind.Number)
            {
                error = new ActionValidationError("invalid_type", path, $"Field '{key}' must be a finite number.");
                return false;
            }
            double d = jsonVal.NumberValue;
            if (double.IsNaN(d) || double.IsInfinity(d) || d < -1000000.0 || d > 1000000.0)
            {
                error = new ActionValidationError("non_finite_or_out_of_bounds", path, $"Field '{key}' must be a finite number within [-1000000, 1000000].");
                return false;
            }
            float f = (float)d;
            if (float.IsNaN(f) || float.IsInfinity(f))
            {
                error = new ActionValidationError("non_finite_number", path, $"Field '{key}' is not a finite float.");
                return false;
            }
            value = f;
            error = null;
            return true;
        }

        public bool TryGetObject(string key, string path, out StrictJsonObject value, out ActionValidationError error)
        {
            value = null;
            if (!Properties.TryGetValue(key, out var jsonVal))
            {
                error = new ActionValidationError("missing_field", path, $"Required field '{key}' is missing.");
                return false;
            }
            if (jsonVal.Kind != StrictJsonValueKind.Object)
            {
                error = new ActionValidationError("invalid_type", path, $"Field '{key}' must be an object.");
                return false;
            }
            value = jsonVal.ObjectValue;
            error = null;
            return true;
        }

        public bool TryGetArray(string key, string path, out List<StrictJsonValue> value, out ActionValidationError error)
        {
            value = null;
            if (!Properties.TryGetValue(key, out var jsonVal))
            {
                error = new ActionValidationError("missing_field", path, $"Required field '{key}' is missing.");
                return false;
            }
            if (jsonVal.Kind != StrictJsonValueKind.Array)
            {
                error = new ActionValidationError("invalid_type", path, $"Field '{key}' must be an array.");
                return false;
            }
            value = jsonVal.ArrayValue;
            error = null;
            return true;
        }
    }

    internal static class StrictJsonParser
    {
        public static bool TryParseRootObject(
            string json,
            int maxUtf8Bytes,
            out StrictJsonObject rootObject,
            out ActionValidationError error)
        {
            rootObject = null;
            if (string.IsNullOrEmpty(json))
            {
                error = new ActionValidationError("empty_json", "$", "JSON input cannot be null or empty.");
                return false;
            }

            int byteCount = Encoding.UTF8.GetByteCount(json);
            if (byteCount > maxUtf8Bytes)
            {
                error = new ActionValidationError("payload_too_large", "$", $"JSON payload size ({byteCount} bytes) exceeds {maxUtf8Bytes} bytes limit.");
                return false;
            }

            var state = new ParserState(json);
            if (!state.SkipWhitespace(out error))
            {
                return false;
            }

            if (state.IsAtEnd)
            {
                error = new ActionValidationError("empty_json", "$", "JSON input contains only whitespace.");
                return false;
            }

            if (state.Peek() != '{')
            {
                error = new ActionValidationError("invalid_json_root", "$", "Root JSON value must be an object starting with '{'. Code fences or non-object roots are forbidden.");
                return false;
            }

            if (!state.TryParseObject("$", out rootObject, out error))
            {
                return false;
            }

            if (!state.SkipWhitespace(out error))
            {
                return false;
            }

            if (!state.IsAtEnd)
            {
                error = new ActionValidationError("trailing_text", "$", "Trailing text after root JSON object is forbidden.");
                return false;
            }

            error = null;
            return true;
        }

        private ref struct ParserState
        {
            private readonly string _src;
            private int _pos;

            public ParserState(string src)
            {
                _src = src;
                _pos = 0;
            }

            public bool IsAtEnd => _pos >= _src.Length;
            public char Peek() => _src[_pos];
            public char Read() => _src[_pos++];

            public bool SkipWhitespace(out ActionValidationError error)
            {
                while (_pos < _src.Length)
                {
                    char c = _src[_pos];
                    if (c == ' ' || c == '\t' || c == '\r' || c == '\n')
                    {
                        _pos++;
                    }
                    else if (c == '/')
                    {
                        error = new ActionValidationError("comments_forbidden", "$", "JSON comments are forbidden.");
                        return false;
                    }
                    else if (c == '`')
                    {
                        error = new ActionValidationError("code_fence_forbidden", "$", "Markdown code fences are forbidden.");
                        return false;
                    }
                    else
                    {
                        break;
                    }
                }
                error = null;
                return true;
            }

            public bool TryParseValue(string path, out StrictJsonValue value, out ActionValidationError error)
            {
                value = default;
                if (!SkipWhitespace(out error)) return false;
                if (IsAtEnd)
                {
                    error = new ActionValidationError("unexpected_eof", path, "Unexpected end of JSON input.");
                    return false;
                }

                char c = Peek();
                switch (c)
                {
                    case '{':
                        if (!TryParseObject(path, out var obj, out error)) return false;
                        value = new StrictJsonValue(obj);
                        return true;
                    case '[':
                        if (!TryParseArray(path, out var arr, out error)) return false;
                        value = new StrictJsonValue(arr);
                        return true;
                    case '"':
                        if (!TryParseString(path, out var str, out error)) return false;
                        value = new StrictJsonValue(str);
                        return true;
                    case 't':
                        if (MatchLiteral("true"))
                        {
                            value = new StrictJsonValue(true);
                            return true;
                        }
                        error = new ActionValidationError("invalid_literal", path, "Invalid token starting with 't'.");
                        return false;
                    case 'f':
                        if (MatchLiteral("false"))
                        {
                            value = new StrictJsonValue(false);
                            return true;
                        }
                        error = new ActionValidationError("invalid_literal", path, "Invalid token starting with 'f'.");
                        return false;
                    case 'n':
                        if (MatchLiteral("null"))
                        {
                            value = StrictJsonValue.CreateNull();
                            return true;
                        }
                        error = new ActionValidationError("invalid_literal", path, "Invalid token starting with 'n'.");
                        return false;
                    default:
                        if (c == '-' || (c >= '0' && c <= '9'))
                        {
                            return TryParseNumber(path, out value, out error);
                        }
                        error = new ActionValidationError("invalid_token", path, $"Unexpected character '{c}' at position {_pos}.");
                        return false;
                }
            }

            public bool TryParseObject(string path, out StrictJsonObject obj, out ActionValidationError error)
            {
                obj = new StrictJsonObject();
                Read(); // consume '{'
                if (!SkipWhitespace(out error)) return false;
                if (IsAtEnd)
                {
                    error = new ActionValidationError("unexpected_eof", path, "Unterminated JSON object.");
                    return false;
                }

                if (Peek() == '}')
                {
                    Read();
                    return true;
                }

                while (true)
                {
                    if (!SkipWhitespace(out error)) return false;
                    if (IsAtEnd || Peek() != '"')
                    {
                        error = new ActionValidationError("expected_property_name", path, "Expected double-quoted property name in JSON object.");
                        return false;
                    }

                    if (!TryParseString(path, out string key, out error))
                    {
                        return false;
                    }

                    string propPath = path + "." + key;
                    if (obj.Properties.ContainsKey(key))
                    {
                        error = new ActionValidationError("duplicate_key", propPath, $"Duplicate object key '{key}' is forbidden.");
                        return false;
                    }

                    if (!SkipWhitespace(out error)) return false;
                    if (IsAtEnd || Read() != ':')
                    {
                        error = new ActionValidationError("expected_colon", propPath, $"Expected ':' after property '{key}'.");
                        return false;
                    }

                    if (!TryParseValue(propPath, out var propVal, out error))
                    {
                        return false;
                    }

                    obj.Properties.Add(key, propVal);

                    if (!SkipWhitespace(out error)) return false;
                    if (IsAtEnd)
                    {
                        error = new ActionValidationError("unexpected_eof", path, "Unterminated JSON object.");
                        return false;
                    }

                    char sep = Read();
                    if (sep == '}')
                    {
                        return true;
                    }
                    if (sep != ',')
                    {
                        error = new ActionValidationError("expected_comma_or_close", path, $"Expected ',' or '}}' in object at '{path}'.");
                        return false;
                    }
                }
            }

            private bool TryParseArray(string path, out List<StrictJsonValue> arr, out ActionValidationError error)
            {
                arr = new List<StrictJsonValue>();
                Read(); // consume '['
                if (!SkipWhitespace(out error)) return false;
                if (IsAtEnd)
                {
                    error = new ActionValidationError("unexpected_eof", path, "Unterminated JSON array.");
                    return false;
                }

                if (Peek() == ']')
                {
                    Read();
                    return true;
                }

                int index = 0;
                while (true)
                {
                    string itemPath = $"{path}[{index}]";
                    if (!TryParseValue(itemPath, out var itemVal, out error))
                    {
                        return false;
                    }
                    arr.Add(itemVal);
                    index++;

                    if (!SkipWhitespace(out error)) return false;
                    if (IsAtEnd)
                    {
                        error = new ActionValidationError("unexpected_eof", path, "Unterminated JSON array.");
                        return false;
                    }

                    char sep = Read();
                    if (sep == ']')
                    {
                        return true;
                    }
                    if (sep != ',')
                    {
                        error = new ActionValidationError("expected_comma_or_close", path, $"Expected ',' or ']' in array at '{path}'.");
                        return false;
                    }
                }
            }

            private bool TryParseString(string path, out string result, out ActionValidationError error)
            {
                result = null;
                Read(); // consume opening '"'
                var sb = new StringBuilder();
                while (!IsAtEnd)
                {
                    char c = Read();
                    if (c == '"')
                    {
                        result = sb.ToString();
                        error = null;
                        return true;
                    }
                    if (c < 0x20)
                    {
                        error = new ActionValidationError("unescaped_control_char", path, "Unescaped control character in JSON string.");
                        return false;
                    }
                    if (c == '\\')
                    {
                        if (IsAtEnd)
                        {
                            error = new ActionValidationError("unexpected_eof", path, "Unterminated escape sequence in string.");
                            return false;
                        }
                        char esc = Read();
                        switch (esc)
                        {
                            case '"': sb.Append('"'); break;
                            case '\\': sb.Append('\\'); break;
                            case '/': sb.Append('/'); break;
                            case 'b': sb.Append('\b'); break;
                            case 'f': sb.Append('\f'); break;
                            case 'n': sb.Append('\n'); break;
                            case 'r': sb.Append('\r'); break;
                            case 't': sb.Append('\t'); break;
                            case 'u':
                                if (_pos + 4 > _src.Length ||
                                    ! ushort.TryParse(_src.Substring(_pos, 4), NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture, out ushort codeUnit))
                                {
                                    error = new ActionValidationError("invalid_unicode_escape", path, "Invalid \\uXXXX escape sequence.");
                                    return false;
                                }
                                _pos += 4;
                                sb.Append((char)codeUnit);
                                break;
                            default:
                                error = new ActionValidationError("invalid_escape", path, $"Invalid escape sequence '\\{esc}'.");
                                return false;
                        }
                    }
                    else
                    {
                        sb.Append(c);
                    }
                }

                error = new ActionValidationError("unterminated_string", path, "Unterminated JSON string.");
                return false;
            }

            private bool TryParseNumber(string path, out StrictJsonValue value, out ActionValidationError error)
            {
                value = default;
                int start = _pos;
                bool isFractionOrExp = false;

                if (Peek() == '-')
                {
                    Read();
                    if (IsAtEnd || Peek() < '0' || Peek() > '9')
                    {
                        error = new ActionValidationError("invalid_number", path, "Invalid negative number token.");
                        return false;
                    }
                }

                if (Peek() == '0')
                {
                    Read();
                    if (!IsAtEnd && Peek() >= '0' && Peek() <= '9')
                    {
                        error = new ActionValidationError("leading_zero", path, "Leading zeros are forbidden in JSON numbers.");
                        return false;
                    }
                }
                else
                {
                    while (!IsAtEnd && Peek() >= '0' && Peek() <= '9')
                    {
                        Read();
                    }
                }

                if (!IsAtEnd && Peek() == '.')
                {
                    isFractionOrExp = true;
                    Read();
                    if (IsAtEnd || Peek() < '0' || Peek() > '9')
                    {
                        error = new ActionValidationError("invalid_number_fraction", path, "Decimal point must be followed by digits.");
                        return false;
                    }
                    while (!IsAtEnd && Peek() >= '0' && Peek() <= '9')
                    {
                        Read();
                    }
                }

                if (!IsAtEnd && (Peek() == 'e' || Peek() == 'E'))
                {
                    isFractionOrExp = true;
                    Read();
                    if (!IsAtEnd && (Peek() == '+' || Peek() == '-'))
                    {
                        Read();
                    }
                    if (IsAtEnd || Peek() < '0' || Peek() > '9')
                    {
                        error = new ActionValidationError("invalid_number_exponent", path, "Exponent must contain digits.");
                        return false;
                    }
                    while (!IsAtEnd && Peek() >= '0' && Peek() <= '9')
                    {
                        Read();
                    }
                }

                string token = _src.Substring(start, _pos - start);
                if (!double.TryParse(token, NumberStyles.Float, CultureInfo.InvariantCulture, out double num) ||
                    double.IsNaN(num) || double.IsInfinity(num))
                {
                    error = new ActionValidationError("invalid_number", path, $"Number '{token}' is not a valid finite double.");
                    return false;
                }

                value = new StrictJsonValue(num, !isFractionOrExp);
                error = null;
                return true;
            }

            private bool MatchLiteral(string literal)
            {
                if (_pos + literal.Length > _src.Length) return false;
                for (int i = 0; i < literal.Length; i++)
                {
                    if (_src[_pos + i] != literal[i]) return false;
                }
                _pos += literal.Length;
                return true;
            }
        }
    }
}
