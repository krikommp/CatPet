using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using PetLive2d.ActionEncoder;
using UnityEngine;

namespace PetLive2d.ActionLanguage
{
    public sealed class CandidateRequest
    {
        public string RawText;
        public string InputRole = "instruction";
        public string Decision = "execute";
        public List<ActionStepSpec> SeedSteps = new List<ActionStepSpec>();
        public string ParentCandidateId;
        public YukikazeMotionTuning Tuning = new YukikazeMotionTuning();
        public bool ReviseStyleOnly;
        public int VariantCursor;
    }

    public sealed class CandidateResult
    {
        public string InputRole;
        public string ProviderKind;
        public string ProviderVersion;
        public string ModelVersion;
        public string PlanJson;
        public YukikazeMotionTuning Tuning;
        public string Note;
    }

    public interface ICandidateProvider
    {
        string Kind { get; }
        string Version { get; }
        bool SupportsFreeTextUnderstanding { get; }
        Task<CandidateResult> GenerateAsync(CandidateRequest request, CancellationToken cancellationToken);
    }

    /// <summary>
    /// Manual seed + template variant provider. Does not claim free-text NLU capability.
    /// </summary>
    public sealed class SeedCandidateProvider : ICandidateProvider
    {
        public string Kind => "manual_seed_template";
        public string Version => "seed-v1";
        public bool SupportsFreeTextUnderstanding => false;

        private static readonly YukikazeMotionTuning[] StylePresets =
        {
            new YukikazeMotionTuning { variantId = "default", periodScale = 1.0f, amplitudeScale = 1.0f, blinkHoldFraction = 1f / 3f },
            new YukikazeMotionTuning { variantId = "crisp_fast", periodScale = 0.80f, amplitudeScale = 1.05f, blinkHoldFraction = 0.22f },
            new YukikazeMotionTuning { variantId = "gentle_soft", periodScale = 1.25f, amplitudeScale = 0.80f, blinkHoldFraction = 0.38f },
            new YukikazeMotionTuning { variantId = "expressive_wide", periodScale = 1.10f, amplitudeScale = 1.20f, blinkHoldFraction = 0.30f }
        };

        public Task<CandidateResult> GenerateAsync(CandidateRequest request, CancellationToken cancellationToken)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var tuning = request.Tuning ?? new YukikazeMotionTuning();
            if (request.ReviseStyleOnly)
            {
                int idx = Math.Abs(request.VariantCursor) % StylePresets.Length;
                var preset = StylePresets[idx];
                tuning = new YukikazeMotionTuning
                {
                    variantId = preset.variantId,
                    periodScale = preset.periodScale,
                    amplitudeScale = preset.amplitudeScale,
                    blinkHoldFraction = preset.blinkHoldFraction
                };
            }

            string planJson = YukikazeActionCatalog.BuildPlanJson(request.Decision, request.SeedSteps);
            return Task.FromResult(new CandidateResult
            {
                ProviderKind = Kind,
                ProviderVersion = Version,
                ModelVersion = "none",
                PlanJson = planJson,
                Tuning = tuning,
                Note = request.ReviseStyleOnly ? $"style_variant:{tuning.variantId}" : "manual_seed"
            });
        }
    }

    /// <summary>
    /// Calls the local MiniRBT /plan HTTP service.
    /// </summary>
    public sealed class LocalModelCandidateProvider : ICandidateProvider
    {
        private readonly LocalActionEncoderClient _client;
        public string Kind => "local_minirbt";
        public string Version => "local-plan-v1";
        public bool SupportsFreeTextUnderstanding => true;

        public LocalModelCandidateProvider(string baseUrl = LocalActionEncoderClient.DefaultBaseUrl)
        {
            _client = new LocalActionEncoderClient(baseUrl);
        }

        public async Task<CandidateResult> GenerateAsync(CandidateRequest request, CancellationToken cancellationToken)
        {
            if (string.IsNullOrWhiteSpace(request.RawText))
                throw new ArgumentException("RawText cannot be empty for local model inference.");

            var req = new ActionPlanServiceRequest
            {
                request_id = Guid.NewGuid().ToString("N"),
                text = request.RawText.Trim(),
                capability_profile = YukikazeActionCatalog.ProfileId,
                motion_map_version = YukikazeActionCatalog.MotionMapVersion,
                label_policy_version = YukikazeActionCatalog.LabelPolicyVersion
            };

            var resp = await _client.PlanAsync(req, 10, cancellationToken);
            var tuning = request.Tuning ?? new YukikazeMotionTuning();
            return new CandidateResult
            {
                ProviderKind = resp.source ?? Kind,
                ProviderVersion = Version,
                ModelVersion = resp.model_version ?? "unknown",
                PlanJson = resp.plan_json,
                Tuning = tuning,
                Note = "local_minirbt_plan"
            };
        }
    }

    /// <summary>
    /// Calls the local MiniRBT v0.2 /configure HTTP service for per-cycle continuous parameters.
    /// </summary>
    public sealed class LocalConfigV02CandidateProvider : ICandidateProvider
    {
        private readonly LocalActionEncoderClient _client;
        public string Kind => "local_minirbt_v02";
        public string Version => "local-configure-v0.2";
        public bool SupportsFreeTextUnderstanding => true;

        public LocalConfigV02CandidateProvider(string baseUrl = LocalActionEncoderClient.DefaultBaseUrl)
        {
            _client = new LocalActionEncoderClient(baseUrl);
        }

        public async Task<CandidateResult> GenerateAsync(CandidateRequest request, CancellationToken cancellationToken)
        {
            if (string.IsNullOrWhiteSpace(request.RawText))
                throw new ArgumentException("RawText cannot be empty for local v0.2 inference.");

            var req = new ActionConfigServiceRequest
            {
                input_role = request.InputRole,
                request_id = Guid.NewGuid().ToString("N"),
                text = request.RawText.Trim(),
                capability_profile = YukikazeActionCatalog.ProfileId,
                resource_catalog_version = ActionResourceCatalog.DefaultCatalogVersion,
                parameter_schema_version = ActionConfigCompiler.SupportedVersion,
                label_policy_version = "action-config-labels.v0.2"
            };

            var resp = await _client.ConfigureAsync(req, 10, cancellationToken);
            return new CandidateResult
            {
                ProviderKind = resp.source ?? Kind,
                ProviderVersion = Version,
                ModelVersion = resp.model_version ?? "unknown",
                InputRole = resp.input_role,
                PlanJson = resp.config_json,
                Tuning = new YukikazeMotionTuning(),
                Note = "local_minirbt_v02_configure"
            };
        }
    }
}
