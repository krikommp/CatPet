# Independent Python code review

Reviewed 2026-11-17. This is a read-only code audit plus synthetic fixtures; no training, model test-set inference, model test-result access, or Unity execution was performed. The report describes the file revisions listed below. Subsequent fixes require a separate re-review.

**Release assessment: blocked on findings 1 and 2; finding 3 should also be fixed before relying on raw false-execution counts.** All 26 feasible/integration fixtures and 24 literal-binding fixtures passed, but the additional adversarial examples below exposed gaps.

## Findings

### 1. [P1] A negated action can acquire an exact-duration binding and pass the final guard

Location: `Tools/ActionEncoder/literal_bindings.py:24`, `:158`.

The scoped prohibition check recognizes `不要|不许|不能|不得|禁止|别`, but not `不需要` or `无需`. With a fixed predicted `nod.basic`, stage 0, one cycle, `predict_config(..., architecture=FEASIBLE_MODEL_ARCHITECTURE)` accepts both:

- `不需要点头一次，每次1秒`
- `无需点头一次，每次1秒`

Both return `decision=execute`, overwrite the raw predicted duration from 961 ms to 1000 ms, report one accepted binding, and set the final instruction guard's `passed_checked_constraints` to true. The prohibition is in the earlier clause; the duration clause has no negation, so the literal-context blacklist also misses it. This does not alter the model's discrete structure, but it converts a rejected duration mismatch into an executable output for explicitly non-required action text. The legacy path would reject this fixture's original 961 ms duration mismatch.

Reject this scope as unresolved/prohibited without changing the decision. Add regression fixtures covering scoped `不需要`/`无需` and separated duration clauses. The binding policy should not rely exclusively on a short prohibition blacklist to establish positive action scope.

### 2. [P1] Nonexact or unrelated durations can be promoted to exact cycle durations

Location: `Tools/ActionEncoder/literal_bindings.py:25-33`, `:51`, `:166-199`.

The binder trusts the shared guard's `exact_duration_ms` checks after rejecting only a blacklist of contexts. The shared guard's grammar is broader than an exact binding grammar. Using the same one-cycle fixture, each input below is accepted, changes 961 ms to 1000 ms, and passes the final guard:

- `点头一次，每次不满1秒` — a strict upper bound, violated by binding to exactly 1000 ms.
- `点头一次，每次不超1秒` — an upper bound incorrectly treated as equality.
- `点头一次，每次1秒也不用` — a less-than expression incorrectly treated as equality.
- `点头一次，每次不一定是1秒` — expressly does not require equality.
- `点头一次，背景音乐1秒` — an unrelated object's duration is assigned to the action using preceding-action scope.

The final guard cannot catch these cases because it uses the same overly broad exact check. Prefer accepting a deliberately small, positive exact-duration syntax with explicit action/cycle scope; reject other numeric syntax as unresolved. At minimum add these fixtures and do not fix them by changing resource, count, stage, or decision.

### 3. [P2] An unrelated nonfinite structural head erases a valid raw execute decision

Location: `Tools/ActionEncoder/config_prediction.py:64-71`, `:133`.

`raw_prediction_record` calculates one `finite` flag over all discrete heads and sets `decision=None` whenever any resource/stage/count value is nonfinite. Consequently an otherwise finite execute decision is absent from `RawPredictionMetrics.false_execution` if a separate head is invalid. A synthetic reproduction with the ordinary finite execute/nod logits and only `stage[0,1,2] = NaN` produced:

```json
{"finite": false, "decision": null, "resource_ids": ["nod.basic", "PAD"], "stages": [0, 2], "cycle_counts": [1, 0]}
```

Adding this record against gold `none` produced `false_execution=0`. The raw decision logits still unambiguously select execute. This undermines the intended separation of raw false executions from decoder/technical failures. Keep per-head validity, preserve a finite decision head's argmax independently, and count its raw false execution even if structural output is rejected. Keep overall invalidity for technical error reporting; it must not grant valid nonexecution credit.

## Reproduction

Run from the repository root using `.venv-action-encoder/Scripts/python.exe`; all imported fixtures are synthetic and read no checkpoint or dataset:

```python
import sys
sys.path[:0] = ["Tools/ActionEncoder", "tests"]
from test_feasible_integration import logits, parameters
from config_prediction import (
    FEASIBLE_MODEL_ARCHITECTURE, predict_config,
    raw_prediction_record, RawPredictionMetrics,
)
from action_config_schema import CONFIG_VERSION

for text in (
    "不需要点头一次，每次1秒", "无需点头一次，每次1秒",
    "点头一次，每次不满1秒", "点头一次，每次不超1秒",
    "点头一次，每次1秒也不用", "点头一次，每次不一定是1秒",
    "点头一次，背景音乐1秒",
):
    config, audit = predict_config(
        logits(("nod.basic", 0, 1)), parameters(), text,
        "instruction", FEASIBLE_MODEL_ARCHITECTURE,
    )
    print(text, config, audit["constraint_audit"]["passed_checked_constraints"])

disc = logits(("nod.basic", 0, 1))
disc["stage"][0, 1, 2] = float("nan")
raw = raw_prediction_record(disc)
metrics = RawPredictionMetrics()
metrics.add(raw, {"version": CONFIG_VERSION, "decision": "none", "steps": []})
print(raw, metrics.summary())
```

## Checks without additional findings

- Missing architecture dispatches to the original `ActionConfigV02Model`; feasible architecture requires matching parameterization, binding and decoder policy versions. Strict state loading prevents cross-architecture weights from silently loading. Synthetic legacy configure output matches the original decoder and performs no literal binding.
- The changed training loop uses train rows for optimizer updates, train diagnostics only for reporting, and validation metrics/loss for checkpoint selection. No new per-epoch test evaluation exists. Serialization of the frozen test split is pre-existing behavior and is not model evaluation.
- Raw discrete structure is not modified by feasible decoding/binding. Invalid stage/count/conflicts reject. Canonical action ordering is consistent across decoder, binder and target encoding. The duration binding policy is architecture/version controlled.
- Guarded technical errors no longer count as valid nonexecution. Finite raw execute predictions rejected by binding/guard are counted separately as raw false executions; finding 3 covers the remaining nonfinite-head gap.
- Source/checkpoint/dataset hash checks improve evaluation provenance. No existing default checkpoint, service, or release status was changed during this review.

## Reviewed revisions (SHA-256)

| File | SHA-256 |
| --- | --- |
| `encoder.py` | `F14C7059F70FA52CF7CB34D3E07EBAB100CD5A67683ECCC5FBA189B83C80A2B0` |
| `train_action_config.py` | `55D6C424D3286C50B6AE783A5CBA491E91B42ADC92CDD36D76FCDCF0DBE39BF4` |
| `retrain_and_eval.py` | `8AADCF5E2B6AE637DF728F5C8A54FBA9D4C201856BE65C1BF60859991054BA06` |
| `config_prediction.py` | `C550FC67B515A7485489E52C50E309031B4246F7789A90EEC6CB87F55126B845` |
| `feasible_config.py` | `12BAC82733F4C2D1EFE906BBF18D7A3E921947295541372EE5419D68E1936637` |
| `literal_bindings.py` | `E06E5970CD18970BBB25EB21B4C1D3DD7953A2BD4BD1412892174BE656F5859C` |

The review did not establish historical checkpoint coverage beyond the synthetic legacy fixtures, native Unity playback validity, or model quality on held-out data.
