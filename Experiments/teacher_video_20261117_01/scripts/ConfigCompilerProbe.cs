using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using PetLive2d.ActionLanguage;

// Executes the project's actual parser, resource catalog and native validator.
// No Unity process, scene or asset state is touched.
public static class ConfigCompilerProbe
{
    static CapabilityProfile Profile = YukikazeActionCatalog.CreateProfile();
    static ActionResourceCatalog Catalog = ActionResourceCatalog.CreateYukikazeV02();
    static Dictionary<string, float> Pose = new Dictionary<string, float>();
    static string Q(string s) => "\"" + (s ?? "").Replace("\\", "\\\\").Replace("\"", "\\\"").Replace("\r", "\\r").Replace("\n", "\\n") + "\"";
    static string Cycle(int ms, double hold, double? amp = null) =>
        "{\"duration_ms\":" + ms + ",\"controls\":{\"hold_ratio\":" + hold.ToString("R", CultureInfo.InvariantCulture) +
        (amp.HasValue ? ",\"amplitude_scale\":" + amp.Value.ToString("R", CultureInfo.InvariantCulture) : "") + "}}";
    static string Act(string rid, params string[] cycles) => "{\"resource_id\":" + Q(rid) + ",\"cycles\":[" + string.Join(",", cycles) + "]}";
    static string Step(params string[] acts) => "{\"actions\":[" + string.Join(",", acts) + "]}";
    static string Cfg(params string[] steps) => "{\"version\":\"action-config.v0.2\",\"decision\":\"execute\",\"steps\":[" + string.Join(",", steps) + "]}";
    static bool Compile(string cfg, out ActionPlanCompilation c, out ActionValidationError e, HostExecutionMode mode = HostExecutionMode.PreviewCandidate) =>
        ActionConfigCompiler.TryCompile(cfg, Profile, Catalog, Pose, mode, out c, out e);

    static int failed, passed;
    static void Check(string name, bool expected, string cfg, string expectedError = null, Func<ActionPlanCompilation, bool> inspect = null, HostExecutionMode mode = HostExecutionMode.PreviewCandidate)
    {
        bool ok = Compile(cfg, out var comp, out var error, mode);
        bool pass = ok == expected && (expectedError == null || error?.Code == expectedError) && (!ok || inspect == null || inspect(comp));
        if (pass) passed++; else failed++;
        Console.WriteLine("{\"test\":" + Q(name) + ",\"passed\":" + pass.ToString().ToLowerInvariant() + ",\"compile_ok\":" + ok.ToString().ToLowerInvariant() +
            ",\"error\":" + Q(error?.Code) + ",\"native\":" + (comp?.NativeJson ?? "null") + "}");
    }

    public static int Main(string[] args)
    {
        foreach (var p in Profile.Parameters) Pose[p.Id] = p.DefaultValue;
        if (args.Length > 0 && args[0] == "--catalog")
        {
            foreach (var resource in Catalog.Resources)
            {
                double maxAmp = resource.MaxAmplitudeScale;
                foreach (var channel in resource.Channels)
                {
                    Profile.TryGetParameter(channel.ParameterId, out var definition);
                    if (!channel.Scalable) continue;
                    foreach (var point in channel.Points)
                    {
                        double delta = point.BaseValue - channel.ReferenceValue;
                        if (delta > 0) maxAmp = Math.Min(maxAmp, (definition.Max - channel.ReferenceValue) / delta);
                        if (delta < 0) maxAmp = Math.Min(maxAmp, (definition.Min - channel.ReferenceValue) / delta);
                    }
                }
                Console.WriteLine("{\"resource_id\":" + Q(resource.ResourceId) + ",\"core_max_amplitude\":" + maxAmp.ToString("R",CultureInfo.InvariantCulture) +
                    ",\"status\":" + Q(resource.Status.ToString()) + ",\"enter_return_alpha\":" + resource.EnterReturnAlpha.ToString("R",CultureInfo.InvariantCulture) + "}");
            }
            return 0;
        }
        if (args.Length > 0)
        {
            int row = 0;
            foreach (var cfg in File.ReadLines(args[0]))
            {
                bool ok = Compile(cfg, out var comp, out var error);
                Console.WriteLine("{\"row\":" + (++row) + ",\"compile_ok\":" + ok.ToString().ToLowerInvariant() + ",\"error\":" + Q(error?.Code) +
                    ",\"field\":" + Q(error?.FieldPath) + ",\"native\":" + (comp?.NativeJson ?? "null") + "}");
            }
            return 0;
        }

        foreach (var r in Catalog.Resources)
        {
            bool mappedHold = r.ResourceId != "look_around.basic";
            Check("default_" + r.ResourceId, mappedHold,
                Cfg(Step(Act(r.ResourceId, Cycle(r.DefaultDurationMs, r.DefaultHoldRatio, r.SupportsAmplitudeScale ? (double?)r.DefaultAmplitudeScale : null)))),
                mappedHold ? null : "missing_hold_phase");
        }
        Check("hold_30ms_rejected", false, Cfg(Step(Act("blink.full", Cycle(600, .05)))), "unrepresentable_hold");
        Check("hold_submillisecond_rejected", false, Cfg(Step(Act("blink.full", Cycle(600, .0001)))), "unrepresentable_hold");
        Check("hold_79ms_rejected", false, Cfg(Step(Act("blink.full", Cycle(1000, .079)))), "unrepresentable_hold");
        Check("zero_hold_valid", true, Cfg(Step(Act("blink.full", Cycle(600, 0)))), null,
            c => c.Packet.Curves[0].Keyframes.Length == 2 && c.Packet.Curves[0].Keyframes[0].AtMs == 300 && c.Packet.Curves[0].Keyframes[1].AtMs == 600);
        Check("hold_80ms_preserved", true, Cfg(Step(Act("blink.full", Cycle(1000, .08)))), null,
            c => c.Packet.Curves[0].Keyframes[1].AtMs - c.Packet.Curves[0].Keyframes[0].AtMs == 80);
        Check("hold_120ms_preserved", true, Cfg(Step(Act("blink.full", Cycle(600, .2)))), null,
            c => c.Packet.Curves[0].Keyframes[0].AtMs == 240 && c.Packet.Curves[0].Keyframes[1].AtMs == 360 && c.Packet.DurationMs == 600);
        Check("move_segment_not_clamped", false, Cfg(Step(Act("blink.full", Cycle(300, .5)))), "short_parameter_segment");
        Check("lookaround_zero_hold", true, Cfg(Step(Act("look_around.basic", Cycle(1100, 0, 1)))));
        Check("cycle_order_numeric_values", true, Cfg(Step(Act("nod.basic", Cycle(700, .2, 1), Cycle(1200, .2, .5)))), null,
            c => {
                foreach (var curve in c.Packet.Curves)
                    if (curve.ParameterId == "ParamAngleY")
                        return c.Packet.DurationMs == 1900 && curve.Keyframes[2].AtMs == 700 && curve.Keyframes[5].AtMs == 1900
                            && curve.Keyframes[0].TargetValue == -18f && curve.Keyframes[1].TargetValue == -18f
                            && curve.Keyframes[3].TargetValue == -9f && curve.Keyframes[4].TargetValue == -9f
                            && curve.Keyframes[2].TargetValue == 0f && curve.Keyframes[5].TargetValue == 0f;
                return false;
            });
        Check("three_blinks_preserved", true, Cfg(Step(Act("blink.full", Cycle(600, .2), Cycle(600, .2), Cycle(600, .2)))), null,
            c => c.Packet.DurationMs == 1800 && c.Packet.Curves[0].Keyframes.Length == 9);
        Check("four_cycles_rejected", false, Cfg(Step(Act("blink.full", Cycle(600,.2), Cycle(600,.2), Cycle(600,.2), Cycle(600,.2)))), "invalid_cycle_count");
        Check("parallel_conflict_rejected", false, Cfg(Step(Act("nod.basic", Cycle(760,.2,1)), Act("bow.basic", Cycle(1200,.3,1)))), "parallel_channel_conflict");
        Check("parallel_independent_valid", true, Cfg(Step(Act("blink.full", Cycle(600,.2)), Act("nod.basic", Cycle(760,.2,1)))), null, c => c.Packet.DurationMs == 760);
        Check("sequence_anchor_preserved", true, Cfg(Step(Act("blink.full", Cycle(600,.2))), Step(Act("nod.basic", Cycle(1000,.2,1)))), null,
            c => { foreach(var curve in c.Packet.Curves) if(curve.ParameterId == "ParamAngleY") return curve.Keyframes[0].AtMs == 600 && curve.Keyframes[0].TargetValue == 0; return false; });
        Check("formal_candidate_rejected", false, Cfg(Step(Act("nod.basic", Cycle(760,.2,1)))), "resource_not_calibrated", null, HostExecutionMode.FormalExecute);
        Check("formal_blink_valid", true, Cfg(Step(Act("blink.full", Cycle(600,.2)))), null, null, HostExecutionMode.FormalExecute);
        Check("fractional_duration_rejected", false, Cfg(Step(Act("blink.full", Cycle(600,.2)))).Replace("600", "600.5"));
        Check("non_execute_actions_rejected", false, Cfg(Step(Act("blink.full", Cycle(600,.2)))).Replace("execute", "none"), "non_execute_steps_forbidden");
        Console.WriteLine("{\"summary\":true,\"passed\":" + passed + ",\"failed\":" + failed + "}");
        return failed == 0 ? 0 : 1;
    }
}
