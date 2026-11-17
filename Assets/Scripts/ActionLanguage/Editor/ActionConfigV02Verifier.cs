using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEditor;
using UnityEngine;

namespace PetLive2d.ActionLanguage.Editor
{
    public static class ActionConfigV02Verifier
    {
        [MenuItem("Tools/PetLive2d/动作模型/模型测试（编译检查）")]
        public static void RunVerification()
        {
            var profile = YukikazeActionCatalog.CreateProfile();
            var catalog = ActionResourceCatalog.CreateYukikazeV02();
            var pose = BuildDefaultPose(profile);

            int passed = 0;

            // Current look_around catalog lacks a hold endpoint. Its nonzero default
            // must be rejected honestly until a versioned resource repair is replayed.
            foreach (var res in catalog.Resources)
            {
                string ampStr = res.DefaultAmplitudeScale.ToString("0.##", CultureInfo.InvariantCulture);
                string holdStr = res.DefaultHoldRatio.ToString("0.##", CultureInfo.InvariantCulture);
                string ctrls = res.SupportsAmplitudeScale
                    ? $"{{\"amplitude_scale\":{ampStr},\"hold_ratio\":{holdStr}}}"
                    : $"{{\"hold_ratio\":{holdStr}}}";
                string cfg = $"{{\"version\":\"action-config.v0.2\",\"decision\":\"execute\",\"steps\":[{{\"actions\":[{{\"resource_id\":\"{res.ResourceId}\",\"cycles\":[{{\"duration_ms\":{res.DefaultDurationMs},\"controls\":{ctrls}}}]}}]}}]}}";
                if (res.ResourceId == "look_around.basic")
                {
                    if (ActionConfigCompiler.TryCompile(cfg, profile, catalog, pose, HostExecutionMode.PreviewCandidate, out _, out var holdError) || holdError?.Code != "missing_hold_phase")
                        throw new InvalidOperationException("look_around positive hold must report missing_hold_phase.");
                    passed++;
                    continue;
                }
                if (!ActionConfigCompiler.TryCompile(cfg, profile, catalog, pose, HostExecutionMode.PreviewCandidate, out var comp, out var err))
                {
                    Debug.LogError($"[ActionConfig v0.2 Verify] Resource '{res.ResourceId}' failed: {err?.Code} - {err?.Message} | cfg={cfg}");
                    return;
                }
                passed++;
            }

            // 2. Per-cycle difference preserved ("点头两次，第二次更慢")
            string twoCycleCfg = "{\"version\":\"action-config.v0.2\",\"decision\":\"execute\",\"steps\":[{\"actions\":[{\"resource_id\":\"nod.basic\",\"cycles\":[{\"duration_ms\":700,\"controls\":{\"amplitude_scale\":0.55,\"hold_ratio\":0.15}},{\"duration_ms\":1200,\"controls\":{\"amplitude_scale\":0.55,\"hold_ratio\":0.15}}]}]}]}";
            if (!ActionConfigCompiler.TryCompile(twoCycleCfg, profile, catalog, pose, HostExecutionMode.PreviewCandidate, out var twoComp, out var twoErr) ||
                twoComp.Packet.DurationMs != 1900)
            {
                Debug.LogError($"[ActionConfig v0.2 Verify] Two-cycle duration mismatch: {twoErr?.Code} {twoErr?.Message}, dur={twoComp?.Packet?.DurationMs}");
                return;
            }
            passed++;

            // 3. Parallel channel conflict must be rejected (nod.basic + bow.basic both write ParamAngleY & ParamBodyAngleY)
            string conflictCfg = "{\"version\":\"action-config.v0.2\",\"decision\":\"execute\",\"steps\":[{\"actions\":[{\"resource_id\":\"nod.basic\",\"cycles\":[{\"duration_ms\":760,\"controls\":{\"amplitude_scale\":1.0,\"hold_ratio\":0.2}}]},{\"resource_id\":\"bow.basic\",\"cycles\":[{\"duration_ms\":1200,\"controls\":{\"amplitude_scale\":1.0,\"hold_ratio\":0.3}}]}]}]}";
            if (ActionConfigCompiler.TryCompile(conflictCfg, profile, catalog, pose, HostExecutionMode.PreviewCandidate, out _, out var confErr) ||
                confErr?.Code != "parallel_channel_conflict")
            {
                Debug.LogError($"[ActionConfig v0.2 Verify] Expected parallel_channel_conflict, got {confErr?.Code}");
                return;
            }
            passed++;

            // 4. FormalExecute mode rejects Candidate resources
            string candidateCfg = "{\"version\":\"action-config.v0.2\",\"decision\":\"execute\",\"steps\":[{\"actions\":[{\"resource_id\":\"nod.basic\",\"cycles\":[{\"duration_ms\":760,\"controls\":{\"amplitude_scale\":1.0,\"hold_ratio\":0.2}}]}]}]}";
            if (ActionConfigCompiler.TryCompile(candidateCfg, profile, catalog, pose, HostExecutionMode.FormalExecute, out _, out var formalErr) ||
                formalErr?.Code != "resource_not_calibrated")
            {
                Debug.LogError($"[ActionConfig v0.2 Verify] Expected resource_not_calibrated, got {formalErr?.Code}");
                return;
            }
            passed++;

            // 5. blink.full rejects amplitude_scale
            string blinkAmpCfg = "{\"version\":\"action-config.v0.2\",\"decision\":\"execute\",\"steps\":[{\"actions\":[{\"resource_id\":\"blink.full\",\"cycles\":[{\"duration_ms\":600,\"controls\":{\"amplitude_scale\":0.8,\"hold_ratio\":0.2}}]}]}]}";
            if (ActionConfigCompiler.TryCompile(blinkAmpCfg, profile, catalog, pose, HostExecutionMode.FormalExecute, out _, out var blinkErr) ||
                blinkErr?.Code != "unsupported_control")
            {
                Debug.LogError($"[ActionConfig v0.2 Verify] Expected unsupported_control for blink.full, got {blinkErr?.Code}");
                return;
            }
            passed++;

            Debug.Log($"[ActionConfig v0.2 Verify] ALL {passed} checks PASSED (11 defaults + unsupported hold mapping rejection + per-cycle duration + parallel conflict + formal gate + blink amplitude guard).");
        }

        private static Dictionary<string, float> BuildDefaultPose(CapabilityProfile profile)
        {
            var pose = new Dictionary<string, float>(StringComparer.Ordinal);
            foreach (var p in profile.Parameters) pose[p.Id] = p.DefaultValue;
            return pose;
        }
    }
}
