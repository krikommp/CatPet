using System;

namespace PetLive2d.ActionLanguage
{
    public enum PreviewPlayState
    {
        Idle,
        Generating,
        Validating,
        Queued,
        Submitted,
        Playing,
        Releasing,
        Completed,
        NonExecuteReady,
        Failed,
        Cancelled
    }

    [Serializable]
    public sealed class ActionCardCandidate
    {
        public string session_id;
        public string candidate_id;
        public string parent_candidate_id;
        public int request_generation;
        public string timestamp_utc;

        public string raw_text;
        public string text_source = "manual_review_ui";
        public string group_id;

        public string provider_kind;
        public string provider_version;
        public string model_version;

        public string character_asset_id = "xuefeng.model3.json";
        public string capability_profile = YukikazeActionCatalog.ProfileId;
        public string motion_map_version = YukikazeActionCatalog.MotionMapVersion;
        public string label_policy_version = YukikazeActionCatalog.LabelPolicyVersion;
        public string preview_condition_version = "isolated_yukikaze_preview.v1";

        public string decision;
        public string plan_json;
        public string motion_tuning_json;
        public string native_json;

        public bool compile_ok;
        public string compile_error_code;
        public string compile_error_message;
        public string playback_status = "not_started";
        public bool playback_completed;
    }

    [Serializable]
    public sealed class ActionCardEvaluationEvent
    {
        public string event_id;
        public string session_id;
        public string candidate_id;
        public string timestamp_utc;
        public string event_type; // evaluate | keep | reject | skip | replay | fail | compile_succeeded | compile_failed | playback_completed | non_execute_ready
        public string semantic_match = "unconfirmed"; // unconfirmed | true | false
        public int naturalness_score; // 0 = unscored, 1..5
        public string reason_tags;
        public string note;
        public string native_json;
        public bool is_kept;
    }

    [Serializable]
    public sealed class QualifiedSemanticSample
    {
        public string sample_id;
        public string candidate_id;
        public string session_id;
        public string group_id;
        public string raw_text;
        public string decision;
        public string plan_json;
        public string motion_tuning_json;
        public string native_json;
        public string capability_profile;
        public string motion_map_version;
        public string label_policy_version;
        public string supervision_mode = "discrete_v0_1";
        public string semantic_match;
        public int naturalness_score;
        public string exported_utc;
    }
}
