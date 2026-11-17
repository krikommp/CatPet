using System;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using UnityEngine;
using UnityEngine.Networking;

namespace PetLive2d.ActionEncoder
{
    [Serializable]
    public sealed class EncoderActionHead
    {
        public string status;
        public bool can_generate_actions;
        public string model_version;
        public string checkpoint_id;
        public string capability_profile;
        public string motion_map_version;
        public string label_policy_version;
        public int max_length;
        public string[] supported_actions;
    }

    [Serializable]
    public sealed class ActionPlanServiceRequest
    {
        public string request_id;
        public string text;
        public string capability_profile;
        public string motion_map_version;
        public string label_policy_version;
    }

    [Serializable]
    public sealed class ActionPlanServiceErrorPayload
    {
        public string code;
        public string message;
    }

    [Serializable]
    public sealed class ActionPlanServiceErrorEnvelope
    {
        public ActionPlanServiceErrorPayload error;
    }

    [Serializable]
    public sealed class ActionPlanServiceResponse
    {
        public string request_id;
        public string source;
        public string model_version;
        public string capability_profile;
        public string motion_map_version;
        public string label_policy_version;
        public string plan_json;
    }

    [Serializable]
    public sealed class ActionConfigServiceRequest
    {
        public string request_id;
        public string text;
        public string input_role = "instruction";
        public string capability_profile;
        public string resource_catalog_version;
        public string parameter_schema_version;
        public string label_policy_version;
    }

    [Serializable]
    public sealed class ActionConfigServiceResponse
    {
        public string request_id;
        public string input_role;
        public string input_policy;
        public string decoder_policy;
        public string source;
        public string model_version;
        public string capability_profile;
        public string resource_catalog_version;
        public string parameter_schema_version;
        public string label_policy_version;
        public string config_json;
    }

    public sealed class ActionPlanServiceException : Exception
    {
        public long HttpStatus { get; }
        public string ErrorCode { get; }
        public ActionPlanServiceException(long httpStatus, string errorCode, string message) : base(message)
        {
            HttpStatus = httpStatus;
            ErrorCode = errorCode ?? "service_error";
        }
    }

    [Serializable]
    public sealed class EncoderHealth
    {
        public string status;
        public string model_id;
        public string model_revision;
        public int hidden_size;
        public EncoderActionHead action_head;
    }

    [Serializable]
    public sealed class EncoderRequest
    {
        public string[] texts;
        public int max_length = 128;
    }

    // JsonUtility does not support jagged arrays: every embedding has a values field.
    [Serializable]
    public sealed class EncoderEmbedding
    {
        public float[] values;
    }

    [Serializable]
    public sealed class EncoderResponse
    {
        public string model_id;
        public string model_revision;
        public int hidden_size;
        public string embedding_kind;
        public EncoderEmbedding[] embeddings;
        public int[] token_counts;
        public bool[] truncated;
        public EncoderActionHead action_head;
    }

    /// <summary>
    /// Calls the local feature encoder. It does not produce or submit Action DSL packets.
    /// Invoke from Unity's main thread so UnityWebRequest and its continuation stay there.
    /// </summary>
    public sealed class LocalActionEncoderClient
    {
        public const string DefaultBaseUrl = "http://127.0.0.1:8765";
        public const string ExpectedModelId = "hfl/minirbt-h256";
        public const string ExpectedEmbeddingKind = "attention_masked_mean_last_hidden_state";
        private readonly string _baseUrl;

        public LocalActionEncoderClient(string baseUrl = DefaultBaseUrl)
        {
            if (!Uri.TryCreate(baseUrl, UriKind.Absolute, out var uri) ||
                uri.Scheme != Uri.UriSchemeHttp || !uri.IsLoopback ||
                !string.IsNullOrEmpty(uri.UserInfo) || !string.IsNullOrEmpty(uri.Query) ||
                !string.IsNullOrEmpty(uri.Fragment) || uri.AbsolutePath != "/")
            {
                throw new ArgumentException("Encoder base URL must be an HTTP loopback origin without credentials or a path.", nameof(baseUrl));
            }
            _baseUrl = uri.GetLeftPart(UriPartial.Authority);
        }

        /// <summary>Reads /health without requiring the action head to be untrained.</summary>
        public async Task<EncoderHealth> GetHealthSnapshotAsync(CancellationToken cancellationToken = default)
        {
            string json = await SendAsync("GET", "/health", null, cancellationToken);
            var health = JsonUtility.FromJson<EncoderHealth>(json);
            if (health == null || health.status != "ok" || health.model_id != ExpectedModelId ||
                health.hidden_size != 256 || string.IsNullOrEmpty(health.model_revision))
            {
                throw new InvalidOperationException("Local encoder health response does not describe a ready MiniRBT h256 model.");
            }
            return health;
        }

        public async Task<ActionPlanServiceResponse> PlanAsync(
            ActionPlanServiceRequest request,
            int timeoutSeconds = 10,
            CancellationToken cancellationToken = default)
        {
            if (request == null || string.IsNullOrWhiteSpace(request.text))
                throw new ArgumentException("Plan request text cannot be empty.", nameof(request));
            if (string.IsNullOrWhiteSpace(request.request_id))
                request.request_id = Guid.NewGuid().ToString("N");

            string json = await SendAsync("POST", "/plan", JsonUtility.ToJson(request), cancellationToken, timeoutSeconds);
            var response = JsonUtility.FromJson<ActionPlanServiceResponse>(json);
            if (response == null || string.IsNullOrEmpty(response.source))
                throw new InvalidOperationException("Invalid /plan response payload.");
            if (response.request_id != request.request_id)
                throw new InvalidOperationException("Mismatched request_id in /plan response.");
            if (!string.IsNullOrEmpty(request.capability_profile) && response.capability_profile != request.capability_profile)
                throw new InvalidOperationException("Capability profile mismatch in /plan response.");
            if (!string.IsNullOrEmpty(request.label_policy_version) && response.label_policy_version != request.label_policy_version)
                throw new InvalidOperationException("Label policy version mismatch in /plan response.");

            response.plan_json = ExtractJsonObjectField(json, "plan");
            if (string.IsNullOrEmpty(response.plan_json))
                throw new InvalidOperationException("Missing plan object in /plan response.");
            return response;
        }

        public async Task<ActionConfigServiceResponse> ConfigureAsync(
            ActionConfigServiceRequest request,
            int timeoutSeconds = 10,
            CancellationToken cancellationToken = default)
        {
            if (request == null || string.IsNullOrWhiteSpace(request.text))
                throw new ArgumentException("Configure request text cannot be empty.", nameof(request));
            if (request.input_role != "instruction" && request.input_role != "dialogue")
                throw new ArgumentException("Configure input_role must be instruction or dialogue.", nameof(request));
            if (string.IsNullOrWhiteSpace(request.request_id))
                request.request_id = Guid.NewGuid().ToString("N");

            string json = await SendAsync("POST", "/configure", JsonUtility.ToJson(request), cancellationToken, timeoutSeconds);
            var response = JsonUtility.FromJson<ActionConfigServiceResponse>(json);
            if (response == null || string.IsNullOrEmpty(response.source))
                throw new InvalidOperationException("Invalid /configure response payload.");
            if (response.request_id != request.request_id)
                throw new InvalidOperationException("Mismatched request_id in /configure response.");
            if (response.input_role != request.input_role)
                throw new InvalidOperationException("Missing or mismatched input_role in /configure response; the service must use the current role-aware code.");
            if (!string.IsNullOrEmpty(request.resource_catalog_version) && response.resource_catalog_version != request.resource_catalog_version)
                throw new InvalidOperationException("Resource catalog version mismatch in /configure response.");
            if (!string.IsNullOrEmpty(request.label_policy_version) && response.label_policy_version != request.label_policy_version)
                throw new InvalidOperationException("Label policy version mismatch in /configure response.");
            if (!string.IsNullOrEmpty(request.capability_profile) && response.capability_profile != request.capability_profile)
                throw new InvalidOperationException("Capability profile mismatch in /configure response.");
            if (!string.IsNullOrEmpty(request.parameter_schema_version) && response.parameter_schema_version != request.parameter_schema_version)
                throw new InvalidOperationException("Parameter schema version mismatch in /configure response.");

            response.config_json = ExtractJsonObjectField(json, "config");
            if (string.IsNullOrEmpty(response.config_json))
                throw new InvalidOperationException("Missing config object in /configure response.");
            return response;
        }

        private static string ExtractJsonObjectField(string json, string fieldName)
        {
            if (string.IsNullOrEmpty(json)) return null;
            string token = "\"" + fieldName + "\"";
            int keyIdx = json.IndexOf(token, StringComparison.Ordinal);
            if (keyIdx < 0) return null;
            int colonIdx = json.IndexOf(':', keyIdx + token.Length);
            if (colonIdx < 0) return null;
            int start = colonIdx + 1;
            while (start < json.Length && char.IsWhiteSpace(json[start])) start++;
            if (start >= json.Length || json[start] != '{') return null;

            int depth = 0;
            bool inString = false;
            bool escaped = false;
            for (int i = start; i < json.Length; i++)
            {
                char c = json[i];
                if (inString)
                {
                    if (escaped) { escaped = false; continue; }
                    if (c == '\\') { escaped = true; continue; }
                    if (c == '"') { inString = false; }
                    continue;
                }
                if (c == '"') { inString = true; continue; }
                if (c == '{') depth++;
                else if (c == '}')
                {
                    depth--;
                    if (depth == 0)
                        return json.Substring(start, i - start + 1);
                }
            }
            return null;
        }

        public async Task<EncoderHealth> GetHealthAsync(CancellationToken cancellationToken = default)
        {
            string json = await SendAsync("GET", "/health", null, cancellationToken);
            var health = JsonUtility.FromJson<EncoderHealth>(json);
            if (health == null || health.status != "ok" || health.model_id != ExpectedModelId ||
                health.hidden_size != 256 || string.IsNullOrEmpty(health.model_revision))
            {
                throw new InvalidOperationException("Local encoder health response does not describe a ready MiniRBT h256 model.");
            }
            RequireUntrainedHead(health.action_head);
            return health;
        }

        public async Task<EncoderResponse> EncodeAsync(EncoderRequest request, CancellationToken cancellationToken = default)
        {
            if (request == null || request.texts == null || request.texts.Length < 1 || request.texts.Length > 8)
                throw new ArgumentException("A batch must contain 1 to 8 texts.", nameof(request));
            if (request.max_length < 8 || request.max_length > 512)
                throw new ArgumentOutOfRangeException(nameof(request), "max_length must be between 8 and 512.");
            foreach (string value in request.texts)
            {
                if (string.IsNullOrWhiteSpace(value) || CountCodePoints(value) > 2048)
                    throw new ArgumentException("Texts must be nonempty strings of at most 2048 Unicode code points.", nameof(request));
            }

            string json = await SendAsync("POST", "/encode", JsonUtility.ToJson(request), cancellationToken);
            var response = JsonUtility.FromJson<EncoderResponse>(json);
            ValidateResponse(response, request.texts.Length, request.max_length);
            return response;
        }

        public static void ValidateResponse(EncoderResponse response, int expectedCount, int maxLength)
        {
            if (response == null || response.model_id != ExpectedModelId || response.hidden_size != 256 ||
                string.IsNullOrEmpty(response.model_revision) || response.embedding_kind != ExpectedEmbeddingKind)
                throw new InvalidOperationException("Unexpected encoder model, revision, dimensions or embedding representation.");
            if (response.embeddings == null || response.embeddings.Length != expectedCount ||
                response.token_counts == null || response.token_counts.Length != expectedCount ||
                response.truncated == null || response.truncated.Length != expectedCount)
                throw new InvalidOperationException("Encoder output count or token metadata does not match the input batch.");

            RequireUntrainedHead(response.action_head);
            for (int row = 0; row < expectedCount; row++)
            {
                float[] values = response.embeddings[row]?.values;
                if (values == null || values.Length != response.hidden_size)
                    throw new InvalidOperationException($"Embedding {row} has the wrong dimension.");
                if (response.token_counts[row] < 2 || response.token_counts[row] > maxLength)
                    throw new InvalidOperationException($"Embedding {row} has an invalid token count.");
                double squaredNorm = 0;
                foreach (float value in values)
                {
                    if (float.IsNaN(value) || float.IsInfinity(value))
                        throw new InvalidOperationException($"Embedding {row} contains a non-finite value.");
                    squaredNorm += (double)value * value;
                }
                if (squaredNorm <= 0)
                    throw new InvalidOperationException($"Embedding {row} is the zero vector.");
            }
        }

        private static void RequireUntrainedHead(EncoderActionHead actionHead)
        {
            if (actionHead == null || actionHead.status != "not_trained" || actionHead.can_generate_actions)
                throw new InvalidOperationException("This client expects the untrained action head to be explicitly unavailable.");
        }

        private static int CountCodePoints(string value)
        {
            int count = 0;
            for (int i = 0; i < value.Length; i++, count++)
            {
                if (char.IsHighSurrogate(value[i]) && i + 1 < value.Length && char.IsLowSurrogate(value[i + 1]))
                    i++;
            }
            return count;
        }

        private async Task<string> SendAsync(string method, string path, string body, CancellationToken cancellationToken, int timeoutSeconds = 120)
        {
            cancellationToken.ThrowIfCancellationRequested();
            using (var request = new UnityWebRequest(_baseUrl + path, method))
            {
                request.downloadHandler = new DownloadHandlerBuffer();
                request.timeout = Math.Max(1, timeoutSeconds);
                request.redirectLimit = 0;
                request.SetRequestHeader("Accept", "application/json");
                if (body != null)
                {
                    request.uploadHandler = new UploadHandlerRaw(Encoding.UTF8.GetBytes(body));
                    request.SetRequestHeader("Content-Type", "application/json; charset=utf-8");
                }
                var operation = request.SendWebRequest();
                while (!operation.isDone)
                {
                    if (cancellationToken.IsCancellationRequested)
                    {
                        request.Abort();
                        cancellationToken.ThrowIfCancellationRequested();
                    }
                    await Task.Yield();
                }
                cancellationToken.ThrowIfCancellationRequested();
                if (request.result != UnityWebRequest.Result.Success)
                {
                    string detail = request.downloadHandler.text;
                    string parsedCode = null;
                    string parsedMessage = null;
                    if (!string.IsNullOrEmpty(detail))
                    {
                        try
                        {
                            var errEnv = JsonUtility.FromJson<ActionPlanServiceErrorEnvelope>(detail);
                            if (errEnv?.error != null)
                            {
                                parsedCode = errEnv.error.code;
                                parsedMessage = errEnv.error.message;
                            }
                        }
                        catch { }
                    }
                    if (!string.IsNullOrEmpty(parsedCode))
                    {
                        throw new ActionPlanServiceException(request.responseCode, parsedCode, parsedMessage ?? detail);
                    }
                    if (!string.IsNullOrEmpty(detail) && detail.Length > 512) detail = detail.Substring(0, 512);
                    throw new InvalidOperationException($"Local encoder {path} failed (HTTP {request.responseCode}): {request.error}. {detail}");
                }
                return request.downloadHandler.text;
            }
        }
    }
}
