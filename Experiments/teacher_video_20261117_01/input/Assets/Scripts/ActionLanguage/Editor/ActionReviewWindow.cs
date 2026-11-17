using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using System.Threading;
using Live2D.Cubism.Core;
using UnityEditor;
using UnityEngine;

namespace PetLive2d.ActionLanguage.Editor
{
    public sealed class ActionReviewWindow : EditorWindow
    {
        private sealed class V02CycleDraft
        {
            public int DurationMs = 760;
            public float AmplitudeScale = 1.0f;
            public float HoldRatio = 0.2f;
        }

        private PreviewSession _preview;
        private ReviewStore _store;
        private LocalConfigV02CandidateProvider _localV02Provider;
        private ActionResourceCatalog _v02Catalog;
        private string[] _v02ResourceIds;

        private CubismModel _selectedSourceModel;
        private string _sessionId;
        private string _rawText = "眨两次眼";
        private int _providerMode; // 0 = Local v0.2, 1 = Manual v0.2 configuration

        // Manual configuration controls
        private int _seedDecisionIdx;

        // v0.2 per-cycle seed controls
        private int _v02Res1Idx = 1; // nod.basic
        private int _v02Cycles1Count = 2;
        private readonly V02CycleDraft[] _v02Cycles1 =
        {
            new V02CycleDraft { DurationMs = 700, AmplitudeScale = 0.6f, HoldRatio = 0.15f },
            new V02CycleDraft { DurationMs = 1150, AmplitudeScale = 0.6f, HoldRatio = 0.15f },
            new V02CycleDraft { DurationMs = 900, AmplitudeScale = 0.6f, HoldRatio = 0.15f },
        };
        private bool _v02HasSecond;
        private bool _v02Parallel;
        private int _v02Res2Idx; // blink.full
        private int _v02Cycles2Count = 1;
        private readonly V02CycleDraft[] _v02Cycles2 =
        {
            new V02CycleDraft { DurationMs = 600, AmplitudeScale = 1.0f, HoldRatio = 0.25f },
            new V02CycleDraft { DurationMs = 600, AmplitudeScale = 1.0f, HoldRatio = 0.25f },
            new V02CycleDraft { DurationMs = 600, AmplitudeScale = 1.0f, HoldRatio = 0.25f },
        };

        // Active candidate & evaluation UI state
        private ActionCardCandidate _currentCandidate;
        private string _semanticMatch = "unconfirmed";
        private int _naturalnessScore;
        private string _reasonTags = string.Empty;
        private string _note = string.Empty;
        private bool _showDetails;

        private CancellationTokenSource _genCts;
        private string _uiStatus = "就绪";
        private Vector2 _historyScroll;

        [MenuItem("Tools/PetLive2d/动作模型/用户验收")]
        public static void ShowWindow()
        {
            var win = GetWindow<ActionReviewWindow>("Yukikaze 用户验收");
            win.minSize = new Vector2(860f, 560f);
        }

        private void OnEnable()
        {
            _providerMode = 0;
            _store = new ReviewStore();
            _localV02Provider = new LocalConfigV02CandidateProvider();
            _v02Catalog = ActionResourceCatalog.CreateYukikazeV02();
            var rList = new List<string>();
            foreach (var r in _v02Catalog.Resources) rList.Add(r.ResourceId);
            _v02ResourceIds = rList.ToArray();
            _preview = new PreviewSession();
            _sessionId = "sess-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss");

            TryAutoSelectYukikaze();
            EditorApplication.update += OnEditorUpdate;
        }

        private void OnDisable()
        {
            EditorApplication.update -= OnEditorUpdate;
            _genCts?.Cancel();
            _genCts?.Dispose();
            _genCts = null;
            _preview?.Dispose();
            _preview = null;
        }

        private void OnEditorUpdate()
        {
            if (_preview != null && _preview.IsReady)
            {
                _preview.Tick();
                Repaint();
            }
        }

        private void TryAutoSelectYukikaze()
        {
            if (_selectedSourceModel != null) return;
            var models = FindObjectsOfType<CubismModel>();
            foreach (var m in models)
            {
                if (m != null && !m.name.StartsWith("__Yukikaze", StringComparison.Ordinal))
                {
                    if (m.name.IndexOf("xuefeng", StringComparison.OrdinalIgnoreCase) >= 0 ||
                        m.name.IndexOf("yukikaze", StringComparison.OrdinalIgnoreCase) >= 0)
                    {
                        _selectedSourceModel = m;
                        break;
                    }
                }
            }
            if (_selectedSourceModel != null && _preview != null && !_preview.IsReady)
            {
                _preview.Initialize(_selectedSourceModel, OnCandidatePlaybackCompleted, OnCandidateCompileOutcome);
            }
        }

        private void OnCandidateCompileOutcome(ActionCardCandidate candidate, bool compileOk, bool isNonExecute)
        {
            _store?.RecordCompileOutcome(
                candidate.candidate_id,
                _sessionId,
                compileOk,
                candidate.native_json,
                candidate.compile_error_code,
                candidate.compile_error_message,
                isNonExecute);
        }

        private void OnCandidatePlaybackCompleted(ActionCardCandidate candidate)
        {
            _store?.MarkPlaybackCompleted(candidate.candidate_id, _sessionId);
            Repaint();
        }

        private void OnGUI()
        {
            DrawHeaderBar();
            EditorGUILayout.BeginHorizontal();
            DrawLeftPreviewColumn();
            DrawRightControlAndHistoryColumn();
            EditorGUILayout.EndHorizontal();
        }

        private void DrawHeaderBar()
        {
            EditorGUILayout.BeginHorizontal(EditorStyles.toolbar);
            GUILayout.Label("预览角色:", GUILayout.Width(68));
            var newModel = (CubismModel)EditorGUILayout.ObjectField(_selectedSourceModel, typeof(CubismModel), true, GUILayout.Width(200));
            if (newModel != _selectedSourceModel)
            {
                _selectedSourceModel = newModel;
                if (_selectedSourceModel != null)
                {
                    _preview.Initialize(_selectedSourceModel, OnCandidatePlaybackCompleted, OnCandidateCompileOutcome);
                }
            }

            if (GUILayout.Button("重新绑定", EditorStyles.toolbarButton, GUILayout.Width(75)))
            {
                if (_selectedSourceModel != null)
                    _preview.Initialize(_selectedSourceModel, OnCandidatePlaybackCompleted, OnCandidateCompileOutcome);
            }

            GUILayout.FlexibleSpace();
            GUILayout.Label($"已保存候选: {_store.Candidates.Count}", EditorStyles.miniLabel);
            if (GUILayout.Button("导出合格训练集", EditorStyles.toolbarButton, GUILayout.Width(115)))
            {
                int totalV02 = _store.ExportQualifiedV02Configs(out int skippedV02);
                _uiStatus = $"已导出 {totalV02} 条合格动作配置；跳过 {skippedV02} 条未达标保留项。";
            }
            EditorGUILayout.EndHorizontal();
        }

        private void DrawLeftPreviewColumn()
        {
            EditorGUILayout.BeginVertical(GUILayout.Width(380));
            GUILayout.Label("动作预览 · 自动录制 12fps 视频", EditorStyles.boldLabel);

            Rect previewRect = GUILayoutUtility.GetRect(360f, 420f, GUILayout.ExpandWidth(false), GUILayout.ExpandHeight(false));
            if (_preview != null && _preview.PreviewTexture != null)
            {
                EditorGUI.DrawPreviewTexture(previewRect, _preview.PreviewTexture, null, ScaleMode.ScaleToFit);
            }
            else
            {
                EditorGUI.DrawRect(previewRect, new Color(0.12f, 0.12f, 0.15f, 1f));
                GUI.Label(previewRect, "请在上方选择场景中的 Yukikaze (xuefeng)", EditorStyles.centeredGreyMiniLabel);
            }

            EditorGUILayout.HelpBox($"{_preview?.StatusDetail}\n{_uiStatus}", MessageType.Info);
            _showDetails = EditorGUILayout.Foldout(_showDetails, "技术详情", true);
            if (_showDetails && _preview != null && _preview.IsReady)
            {
                float eyeL = _preview.Adapter.ReadCurrentParameterValue("ParamEyeLOpen");
                float eyeR = _preview.Adapter.ReadCurrentParameterValue("ParamEyeROpen");
                float angY = _preview.Adapter.ReadCurrentParameterValue("ParamAngleY");
                float angX = _preview.Adapter.ReadCurrentParameterValue("ParamAngleX");
                EditorGUILayout.LabelField($"预览状态: {_preview.State}");
                EditorGUILayout.LabelField($"EyeL={eyeL:F2}, EyeR={eyeR:F2}, AngleY={angY:F1}, AngleX={angX:F1}");
            }
            EditorGUILayout.EndVertical();
        }

        private void DrawRightControlAndHistoryColumn()
        {
            EditorGUILayout.BeginVertical();

            // 1. Target description & provider
            GUILayout.Label("1. 输入动作描述", EditorStyles.boldLabel);
            EditorGUI.BeginChangeCheck();
            _rawText = EditorGUILayout.TextField("动作描述", _rawText);
            if (EditorGUI.EndChangeCheck())
            {
                StartNewSession("修改描述，已开启新会话并取消旧请求。");
            }

            int nextProviderMode = GUILayout.Toolbar(_providerMode, new[] { "本地模型", "手工配置" });
            if (nextProviderMode != _providerMode)
            {
                _providerMode = nextProviderMode;
                StartNewSession("已切换生成方式。");
            }
            if (_providerMode == 1)
            {
                DrawV02SeedControls();
            }

            EditorGUILayout.BeginHorizontal();
            if (GUILayout.Button("生成并播放", GUILayout.Height(28)))
            {
                _ = GenerateAndPlayAsync();
            }
            if (GUILayout.Button("重播", GUILayout.Height(28), GUILayout.Width(60)))
            {
                ReplayCurrent();
            }
            if (GUILayout.Button("停止", GUILayout.Height(28), GUILayout.Width(60)))
            {
                _genCts?.Cancel();
                _preview.NextGeneration();
                _preview.CancelCurrentAndReset("人工停止");
            }
            EditorGUILayout.EndHorizontal();

            EditorGUILayout.Space(6);

            // 2. Current card & evaluation
            DrawEvaluationPanel();

            EditorGUILayout.Space(6);

            // 3. History list for close-and-reopen replay
            GUILayout.Label("3. 验收记录", EditorStyles.boldLabel);
            _historyScroll = EditorGUILayout.BeginScrollView(_historyScroll, GUILayout.ExpandHeight(true));
            for (int i = _store.Candidates.Count - 1; i >= Math.Max(0, _store.Candidates.Count - 40); i--)
            {
                var c = _store.Candidates[i];
                var latest = _store.GetLatestDecisionEvent(c.candidate_id);
                string tag = latest != null && latest.is_kept ? "[已保留]" :
                    (latest?.event_type == "reject" ? "[未通过]" : (latest?.event_type == "skip" ? "[跳过]" : "[待验收]"));
                EditorGUILayout.BeginHorizontal(EditorStyles.helpBox);
                GUILayout.Label($"{tag} {c.raw_text}", GUILayout.ExpandWidth(true));
                if (GUILayout.Button("回放", GUILayout.Width(55)))
                {
                    LoadAndReplayHistoricalCandidate(c);
                }
                EditorGUILayout.EndHorizontal();
            }
            EditorGUILayout.EndScrollView();

            EditorGUILayout.EndVertical();
        }

        private void DrawV02SeedControls()
        {
            EditorGUILayout.BeginVertical(EditorStyles.helpBox);
            _seedDecisionIdx = EditorGUILayout.Popup("动作判定", _seedDecisionIdx, YukikazeActionCatalog.SupportedDecisions);
            if (_seedDecisionIdx == 0 && _v02ResourceIds != null && _v02ResourceIds.Length > 0)
            {
                DrawV02ActionBlock("动作 1", ref _v02Res1Idx, ref _v02Cycles1Count, _v02Cycles1);
                _v02HasSecond = EditorGUILayout.Toggle("启用动作 2", _v02HasSecond);
                if (_v02HasSecond)
                {
                    _v02Parallel = EditorGUILayout.Toggle("两个动作同时开始", _v02Parallel);
                    DrawV02ActionBlock("动作 2", ref _v02Res2Idx, ref _v02Cycles2Count, _v02Cycles2);
                }
            }
            EditorGUILayout.EndVertical();
        }

        private void DrawV02ActionBlock(string label, ref int resIdx, ref int cycleCount, V02CycleDraft[] drafts)
        {
            EditorGUILayout.BeginHorizontal();
            int nextRes = EditorGUILayout.Popup(label, resIdx, _v02ResourceIds);
            if (nextRes != resIdx)
            {
                resIdx = nextRes;
                if (_v02Catalog.TryGetResource(_v02ResourceIds[resIdx], out var newDef))
                {
                    for (int i = 0; i < drafts.Length; i++)
                    {
                        drafts[i].DurationMs = newDef.DefaultDurationMs;
                        drafts[i].AmplitudeScale = newDef.DefaultAmplitudeScale;
                        drafts[i].HoldRatio = newDef.DefaultHoldRatio;
                    }
                }
            }
            cycleCount = EditorGUILayout.IntSlider("次数", cycleCount, 1, 3);
            EditorGUILayout.EndHorizontal();

            if (_v02Catalog.TryGetResource(_v02ResourceIds[resIdx], out var def))
            {
                for (int c = 0; c < cycleCount; c++)
                {
                    var d = drafts[c];
                    EditorGUILayout.BeginHorizontal();
                    GUILayout.Label($"第 {c + 1} 次", GUILayout.Width(64));
                    d.DurationMs = EditorGUILayout.IntSlider("时长ms", d.DurationMs, def.MinDurationMs, def.MaxDurationMs);
                    if (def.SupportsAmplitudeScale)
                        d.AmplitudeScale = EditorGUILayout.Slider("幅度", d.AmplitudeScale, def.MinAmplitudeScale, def.MaxAmplitudeScale);
                    if (def.SupportsHoldRatio)
                        d.HoldRatio = EditorGUILayout.Slider("保持", d.HoldRatio, def.MinHoldRatio, def.MaxHoldRatio);
                    EditorGUILayout.EndHorizontal();
                }
            }
        }

        private void DrawEvaluationPanel()
        {
            GUILayout.Label("2. 用户验收", EditorStyles.boldLabel);
            EditorGUILayout.BeginVertical(EditorStyles.helpBox);
            if (_currentCandidate == null)
            {
                GUILayout.Label("请生成动作，播放完成后确认语义并评分。", EditorStyles.miniLabel);
            }
            else
            {
                GUILayout.Label($"当前描述: {_currentCandidate.raw_text}");
                GUILayout.Label($"动作判定: {_currentCandidate.decision}", EditorStyles.miniLabel);
                if (_showDetails)
                {
                    EditorGUILayout.SelectableLabel($"ID: {_currentCandidate.candidate_id}\n来源: {_currentCandidate.provider_kind} | 模型: {_currentCandidate.model_version}", GUILayout.Height(32));
                    EditorGUILayout.TextArea(_currentCandidate.plan_json, GUILayout.Height(70));
                }

                EditorGUILayout.BeginHorizontal();
                GUILayout.Label("语义确认:", GUILayout.Width(70));
                if (GUILayout.Toggle(_semanticMatch == "true", "符合语义", "Button")) _semanticMatch = "true";
                if (GUILayout.Toggle(_semanticMatch == "false", "不符合语义", "Button")) _semanticMatch = "false";
                if (GUILayout.Toggle(_semanticMatch == "unconfirmed", "未确认", "Button")) _semanticMatch = "unconfirmed";
                EditorGUILayout.EndHorizontal();

                EditorGUILayout.BeginHorizontal();
                GUILayout.Label("自然度分:", GUILayout.Width(70));
                for (int s = 1; s <= 5; s++)
                {
                    if (GUILayout.Toggle(_naturalnessScore == s, s.ToString(), "Button", GUILayout.Width(32)))
                        _naturalnessScore = s;
                }
                if (GUILayout.Button("清空评分", GUILayout.Width(70))) _naturalnessScore = 0;
                EditorGUILayout.EndHorizontal();

                if (_showDetails)
                    _reasonTags = EditorGUILayout.TextField("原因标签", _reasonTags);
                _note = EditorGUILayout.TextField("备注", _note);

                EditorGUILayout.BeginHorizontal();
                if (GUILayout.Button("通过并保留"))
                {
                    RecordEvaluation("keep", isKept: true);
                }
                if (GUILayout.Button("未通过"))
                {
                    RecordEvaluation("reject", isKept: false);
                    _uiStatus = "已记录未通过；可修改描述或手工配置后重新生成。";
                }
                if (GUILayout.Button("跳过"))
                {
                    RecordEvaluation("skip", isKept: false);
                }
                EditorGUILayout.EndHorizontal();
            }
            EditorGUILayout.EndVertical();
        }

        private void StartNewSession(string detail)
        {
            _sessionId = "sess-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss");
            _genCts?.Cancel();
            _preview?.NextGeneration();
            _preview?.CancelCurrentAndReset(detail);
            _currentCandidate = null;
            ResetEvaluationInputs();
            _uiStatus = detail;
        }

        private void ResetEvaluationInputs()
        {
            _semanticMatch = "unconfirmed";
            _naturalnessScore = 0;
            _reasonTags = string.Empty;
            _note = string.Empty;
        }

        private async System.Threading.Tasks.Task GenerateAndPlayAsync()
        {
            if (_preview == null || !_preview.IsReady)
            {
                _uiStatus = "请先绑定场景中的 Yukikaze 实例。";
                return;
            }

            _genCts?.Cancel();
            _genCts?.Dispose();
            _genCts = new CancellationTokenSource();
            var ct = _genCts.Token;
            int gen = _preview.NextGeneration();

            _preview.CancelCurrentAndReset("准备新候选...");

            try
            {
                _uiStatus = "正在生成候选...";
                CandidateResult result;
                if (_providerMode == 1)
                {
                    result = new CandidateResult
                    {
                        ProviderKind = "manual_seed_v02",
                        ProviderVersion = "seed-v0.2",
                        ModelVersion = "none",
                        PlanJson = BuildV02ConfigJson(),
                        Tuning = new YukikazeMotionTuning(),
                        Note = "manual_v02_per_cycle_seed"
                    };
                }
                else
                {
                    result = await _localV02Provider.GenerateAsync(new CandidateRequest { RawText = _rawText }, ct);
                }

                // Drop stale responses if user refreshed or changed text.
                if (ct.IsCancellationRequested || gen != _preview.RequestGeneration)
                    return;

                var candidate = new ActionCardCandidate
                {
                    session_id = _sessionId,
                    candidate_id = Guid.NewGuid().ToString("N"),
                    request_generation = gen,
                    timestamp_utc = DateTime.UtcNow.ToString("O"),
                    raw_text = _rawText?.Trim() ?? string.Empty,
                    group_id = ComputeStableGroupId(_rawText),
                    provider_kind = result.ProviderKind,
                    provider_version = result.ProviderVersion,
                    model_version = result.ModelVersion,
                    decision = ExtractDecision(result.PlanJson),
                    plan_json = result.PlanJson,
                    motion_tuning_json = JsonUtility.ToJson(result.Tuning ?? new YukikazeMotionTuning())
                };

                _currentCandidate = candidate;
                ResetEvaluationInputs();

                _store.AppendCandidate(candidate);
                bool ok = _preview.TryPlayCandidate(candidate, out string playErr);

                if (!ok)
                {
                    _store.AppendEvaluation(new ActionCardEvaluationEvent
                    {
                        session_id = _sessionId,
                        candidate_id = candidate.candidate_id,
                        event_type = "fail",
                        note = playErr,
                        is_kept = false
                    });
                    _uiStatus = "候选编译/播放失败: " + playErr;
                }
                else
                {
                    _uiStatus = "已生成候选，准备验收。";
                }
            }
            catch (OperationCanceledException)
            {
                _uiStatus = "生成请求已取消。";
            }
            catch (Exception ex)
            {
                _uiStatus = "生成失败: " + ex.Message;
            }
            Repaint();
        }

        private void ReplayCurrent()
        {
            if (_currentCandidate == null || _preview == null) return;
            _store.AppendEvaluation(new ActionCardEvaluationEvent
            {
                session_id = _sessionId,
                candidate_id = _currentCandidate.candidate_id,
                event_type = "replay",
                semantic_match = _semanticMatch,
                naturalness_score = _naturalnessScore,
                is_kept = false
            });
            _preview.TryPlayCandidate(_currentCandidate, out string err);
            _uiStatus = string.IsNullOrEmpty(err) ? "正在原样重播当前候选..." : "重播失败: " + err;
        }

        private void LoadAndReplayHistoricalCandidate(ActionCardCandidate c)
        {
            _genCts?.Cancel();
            _preview.NextGeneration();
            _currentCandidate = c;
            _rawText = c.raw_text;
            ResetEvaluationInputs();
            var latest = _store.GetLatestDecisionEvent(c.candidate_id);
            if (latest != null)
            {
                _semanticMatch = latest.semantic_match;
                _naturalnessScore = latest.naturalness_score;
                _reasonTags = latest.reason_tags;
                _note = latest.note;
            }
            _preview.TryPlayCandidate(c, out string err);
            _uiStatus = string.IsNullOrEmpty(err) ? $"已加载历史候选并原样回放 ({c.candidate_id.Substring(0, 8)})" : "回放失败: " + err;
        }

        private void RecordEvaluation(string eventType, bool isKept)
        {
            if (_currentCandidate == null) return;
            var ev = new ActionCardEvaluationEvent
            {
                session_id = _sessionId,
                candidate_id = _currentCandidate.candidate_id,
                event_type = eventType,
                semantic_match = _semanticMatch,
                naturalness_score = _naturalnessScore,
                reason_tags = _reasonTags,
                note = _note,
                is_kept = isKept
            };
            _store.AppendEvaluation(ev);
            if (isKept)
            {
                bool qualified = _store.IsCandidateQualifiedForExport(_currentCandidate, ev, out string reason);
                _uiStatus = qualified
                    ? "已通过并保留，点击“导出合格训练集”即可入库。"
                    : $"已保留（暂不导出为合格正例：{reason}）。";
            }
            else
            {
                _uiStatus = $"已记录评价事件 ({eventType})。";
            }
        }

        private string BuildV02ConfigJson()
        {
            string decision = YukikazeActionCatalog.SupportedDecisions[_seedDecisionIdx];
            if (decision != "execute")
            {
                return $"{{\"version\":\"action-config.v0.2\",\"decision\":\"{decision}\",\"steps\":[]}}";
            }

            var sb = new StringBuilder(512);
            sb.Append("{\"version\":\"action-config.v0.2\",\"decision\":\"execute\",\"steps\":[");
            sb.Append("{\"actions\":[");
            AppendV02ActionJson(sb, _v02ResourceIds[_v02Res1Idx], _v02Cycles1Count, _v02Cycles1);
            if (_v02HasSecond && _v02Parallel)
            {
                sb.Append(',');
                AppendV02ActionJson(sb, _v02ResourceIds[_v02Res2Idx], _v02Cycles2Count, _v02Cycles2);
            }
            sb.Append("]}");
            if (_v02HasSecond && !_v02Parallel)
            {
                sb.Append(",{\"actions\":[");
                AppendV02ActionJson(sb, _v02ResourceIds[_v02Res2Idx], _v02Cycles2Count, _v02Cycles2);
                sb.Append("]}");
            }
            sb.Append("]}");
            return sb.ToString();
        }

        private void AppendV02ActionJson(StringBuilder sb, string resourceId, int cycleCount, V02CycleDraft[] drafts)
        {
            _v02Catalog.TryGetResource(resourceId, out var def);
            sb.Append("{\"resource_id\":\"").Append(resourceId).Append("\",\"cycles\":[");
            for (int c = 0; c < cycleCount; c++)
            {
                if (c > 0) sb.Append(',');
                var d = drafts[c];
                sb.Append("{\"duration_ms\":").Append(d.DurationMs).Append(",\"controls\":{");
                bool needComma = false;
                if (def != null && def.SupportsAmplitudeScale)
                {
                    sb.Append("\"amplitude_scale\":").Append(d.AmplitudeScale.ToString("0.###", CultureInfo.InvariantCulture));
                    needComma = true;
                }
                if (def != null && def.SupportsHoldRatio)
                {
                    if (needComma) sb.Append(',');
                    sb.Append("\"hold_ratio\":").Append(d.HoldRatio.ToString("0.###", CultureInfo.InvariantCulture));
                }
                sb.Append("}}");
            }
            sb.Append("]}");
        }

        private static string ComputeStableGroupId(string rawText)
        {
            string normalized = (rawText ?? string.Empty).Trim();
            unchecked
            {
                ulong hash = 14695981039346656037UL;
                for (int i = 0; i < normalized.Length; i++)
                {
                    hash ^= normalized[i];
                    hash *= 1099511628211UL;
                }
                return "grp-" + hash.ToString("x16");
            }
        }

        private static string ExtractDecision(string planJson)
        {
            if (string.IsNullOrEmpty(planJson)) return "none";
            foreach (string d in YukikazeActionCatalog.SupportedDecisions)
            {
                if (planJson.Contains($"\"{d}\"")) return d;
            }
            return "unknown";
        }
    }
}
