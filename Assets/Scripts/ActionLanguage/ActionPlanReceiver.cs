using System;
using System.Collections.Generic;
using Live2D.Cubism.Framework;
using UnityEngine;

namespace PetLive2d.ActionLanguage
{
    /// <summary>Queues a semantic plan and rechecks its pose/binding immediately before synthesis.</summary>
    [DisallowMultipleComponent]
    [RequireComponent(typeof(Live2DActionAdapter))]
    public sealed class ActionPlanReceiver : MonoBehaviour, ICubismUpdatable
    {
        public int ExecutionOrder => Live2DActionAdapter.AdapterExecutionOrder - 1;
        public bool NeedsUpdateOnEditing => false;
        public bool HasUpdateController { get; set; }
        public bool HasPendingPlan => _pending != null;
        public string LastStatus { get; private set; } = "not_configured";
        public ActionValidationError LastError { get; private set; }

        private Live2DActionAdapter _adapter;
        private ActionMotionMap _map;
        private ActionResourceCatalog _catalog;
        private ActionPlanCompilation _pending;
        private ActionPlayer _pendingPlayer;
        private ActionRequestContext _context;
        private int _requestSequence;

        public void Configure(ActionMotionMap motionMap)
        {
            _adapter = GetComponent<Live2DActionAdapter>();
            _map = motionMap ?? throw new ArgumentNullException(nameof(motionMap));
            _pending = null;
            _pendingPlayer = null;
            LastError = null;
            LastStatus = "ready";
            GetComponent<CubismUpdateController>()?.Refresh();
        }

        public void ConfigureCatalog(ActionResourceCatalog catalog)
        {
            _adapter = GetComponent<Live2DActionAdapter>();
            _catalog = catalog ?? throw new ArgumentNullException(nameof(catalog));
            _pending = null;
            _pendingPlayer = null;
            LastError = null;
            LastStatus = "ready";
            GetComponent<CubismUpdateController>()?.Refresh();
        }

        public bool TryQueueConfigJson(
            string json,
            HostExecutionMode mode,
            out ActionPlanCompilation compilation,
            out ActionValidationError error)
        {
            compilation = null;
            error = null;
            if (_adapter == null || !_adapter.IsBound || _catalog == null)
                return Fail("config_receiver_not_ready", "Bind the adapter and configure a resource catalog first.", out error);
            if (_pending != null)
                return Fail("plan_pending", "A plan is already waiting for the next synthesis phase.", out error);
            if (!ActionConfigCompiler.TryCompile(json, _adapter.Profile, _catalog, ReadPose(), mode, out compilation, out error))
            {
                LastError = error;
                LastStatus = "rejected";
                return false;
            }
            if (compilation.Decision != "execute")
            {
                LastError = null;
                LastStatus = compilation.Decision;
                return true;
            }
            if (!CheckIdle(out error)) return false;
            _pending = compilation;
            _pendingPlayer = _adapter.Player;
            _context = _adapter.HostState.CreateRequestContext("cfg-" + GetInstanceID() + "-" + ++_requestSequence,
                _adapter.GetCurrentTimeMs() + 2000);
            LastError = null;
            LastStatus = "queued";
            return true;
        }

        /// <summary>Cancels any queued plan that has not yet been committed to the adapter.</summary>
        public bool CancelPending()
        {
            bool hadPending = _pending != null;
            _pending = null;
            _pendingPlayer = null;
            _requestSequence++;
            LastError = null;
            if (hadPending)
            {
                LastStatus = "cancelled_pending";
            }
            return hadPending;
        }

        /// <summary>Cancels pending plans and resets status for a new preview/review session.</summary>
        public void ResetSession()
        {
            CancelPending();
            if (_adapter != null && _adapter.IsBound && _map != null)
            {
                LastStatus = "ready";
            }
        }

        public bool TryQueuePlanJson(string json, out ActionPlanCompilation compilation, out ActionValidationError error)
        {
            compilation = null;
            error = null;
            if (_adapter == null || !_adapter.IsBound || _map == null)
                return Fail("plan_receiver_not_ready", "Bind the adapter and configure a motion map first.", out error);
            if (_pending != null)
                return Fail("plan_pending", "A plan is already waiting for the next synthesis phase.", out error);
            if (!ActionPlanCompiler.TryCompile(json, _adapter.Profile, _map, ReadPose(), out compilation, out error))
            {
                LastError = error;
                LastStatus = "rejected";
                return false;
            }
            if (compilation.Decision != "execute")
            {
                LastError = null;
                LastStatus = compilation.Decision;
                return true;
            }
            if (!CheckIdle(out error)) return false;
            _pending = compilation;
            _pendingPlayer = _adapter.Player;
            _context = _adapter.HostState.CreateRequestContext("plan-" + GetInstanceID() + "-" + ++_requestSequence,
                _adapter.GetCurrentTimeMs() + 2000);
            LastError = null;
            LastStatus = "queued";
            return true;
        }

        // Also usable by deterministic editor probes before calling StepSynthesis at the same clock.
        public bool TryCommitPending(out ActionValidationError error)
        {
            error = null;
            if (_pending == null) return true;
            ActionPlanCompilation pending = _pending;
            _pending = null;
            if (_adapter == null || !_adapter.IsBound || _adapter.Player != _pendingPlayer)
                return Fail("plan_binding_changed", "The adapter binding changed before plan commit.", out error);
            if (!CheckIdle(out error)) return false;
            if (!pending.ValidateStartPose(ReadPose(), out error) ||
                !_adapter.SubmitActionJsonWithContext(pending.NativeJson, in _context, out error))
            {
                LastError = error;
                LastStatus = "rejected";
                return false;
            }
            LastError = null;
            LastStatus = "submitted";
            return true;
        }

        public void OnLateUpdate()
        {
            if (isActiveAndEnabled && _pending != null) TryCommitPending(out _);
        }

        private Dictionary<string, float> ReadPose()
        {
            var pose = new Dictionary<string, float>(StringComparer.Ordinal);
            foreach (var parameter in _adapter.Profile.Parameters)
                pose.Add(parameter.Id, _adapter.ReadCurrentParameterValue(parameter.Id));
            return pose;
        }

        private bool CheckIdle(out ActionValidationError error)
        {
            var player = _adapter.Player;
            if (player.IsPaused || player.HasPendingSubmission || player.HasActiveForeground)
                return Fail("plan_player_busy", "The prototype accepts plans only when the action track is idle and unpaused.", out error);
            for (int i = 0; i < _adapter.Profile.Parameters.Count; i++)
                if (player.IsChannelReleasing(i))
                    return Fail("plan_player_busy", "Wait for the current release to finish.", out error);
            error = null;
            return true;
        }

        private bool Fail(string code, string message, out ActionValidationError error)
        {
            error = new ActionValidationError(code, "$", message);
            LastError = error;
            LastStatus = "rejected";
            return false;
        }

        private void OnDisable()
        {
            _pending = null;
        }
    }
}
