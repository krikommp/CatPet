# Independent follow-up: original three Python findings

Reviewed 2026-11-17. Scope is limited to the three findings in `code_review.md`; no broader review or model-quality conclusion is implied. The original review remains unchanged. Read the proposed resolution and current binder/metric code, then reran the exact seven original text reproductions and the original NaN reproduction using synthetic fixture logits. No model checkpoints, held-out predictions, training, or Unity execution were accessed.

**Result: all three original findings are resolved in the revisions below. No blocker remains from these three findings.** This is clearance of the identified Python defects, not release approval.

## Findings 1 and 2: resolved

The binder now requires full-clause positive exact-duration syntax and uninterrupted positive action scope. It also explicitly rejects the two original non-required action forms. Every original reproduction rejects with `ModelOutputError` before creating any binding. The exception retains the original execute/nod/one-cycle structure and original 961 ms duration; it does not repair decision, resource, stage, count, or values.

| Original synthetic input | Observed result | Rejection |
| --- | --- | --- |
| 不需要点头一次，每次1秒 | rejected; zero bindings; raw config preserved | `explicitly_negated_predicted_action` |
| 无需点头一次，每次1秒 | rejected; zero bindings; raw config preserved | `explicitly_negated_predicted_action` |
| 点头一次，每次不满1秒 | rejected; zero bindings; raw config preserved | `unsupported_literal_context` |
| 点头一次，每次不超1秒 | rejected; zero bindings; raw config preserved | `unsupported_literal_context` |
| 点头一次，每次1秒也不用 | rejected; zero bindings; raw config preserved | `unsupported_literal_context` |
| 点头一次，每次不一定是1秒 | rejected; zero bindings; raw config preserved | `unsupported_literal_context` |
| 点头一次，背景音乐1秒 | rejected; zero bindings; raw config preserved | `unsupported_literal_context` |

## Finding 3: resolved

The original finite execute decision plus `stage[0, 1, 2] = NaN` now retains `decision="execute"`, reports `finite=false`, and records per-head validity (`decision=true`, `stage=false`). Against gold `none`, `false_execution=1`, `nonexecute_prediction=0`, and `nonexecute_specificity=0`. Thus structural invalidity no longer erases the raw false execution or earns nonexecution credit.

```json
{
  "raw_prediction": {
    "finite": false,
    "head_finite": {
      "decision": true,
      "resource_id": true,
      "stage": false,
      "cycle_count": true
    },
    "decision": "execute",
    "resource_ids": [
      "nod.basic",
      "PAD"
    ],
    "stages": [
      0,
      2
    ],
    "cycle_counts": [
      1,
      0
    ]
  },
  "metric_subset": {
    "false_execution": 1,
    "nonexecute_prediction": 0,
    "nonexecute_specificity": 0.0
  }
}
```

## Current revision hashes

SHA-256 hashes were captured before the reproductions and verified unchanged afterward.

| File | SHA-256 |
| --- | --- |
| `Tools\ActionEncoder\encoder.py` | `f14c7059f70fa52cf7cb34d3e07ebab100cd5a67683eccc5fba189b83c80a2b0` |
| `Tools\ActionEncoder\train_action_config.py` | `55d6c424d3286c50b6ae783a5cba491e91b42adc92cdd36d76fcdcf0dbe39bf4` |
| `Tools\ActionEncoder\retrain_and_eval.py` | `8aadcf5e2b6ae637df728f5c8a54fba9d4c201856be65c1bf60859991054ba06` |
| `Tools\ActionEncoder\config_prediction.py` | `9f5c3de6e0d2af8e0721059ec9e94f32277cfde2cdb7d0440eb02be645cca7fe` |
| `Tools\ActionEncoder\feasible_config.py` | `12bac82733f4c2d1efe906bbf18d7a3e921947295541372ee5419d68e1936637` |
| `Tools\ActionEncoder\literal_bindings.py` | `b20875d14122eb03e9a2c2e3ad9761566eeeef52438a0031fb601fcf79d6b844` |
| `tests\test_literal_bindings.py` | `1f1f111230c36d40b72c288a9db3aa880fcf038259cfd3dd325e725b3311dbd5` |
| `tests\test_feasible_integration.py` | `0bec4d77218f86c231ed6877da421bbfb0b7640a4409efd501ad355785e0d80a` |

Verification: seven rejected binding reproductions plus one corrected raw-metric reproduction; all explicit assertions passed. Existing broader regression-suite counts in `code_review_resolution.md` were not independently rerun in this intentionally narrow follow-up.
