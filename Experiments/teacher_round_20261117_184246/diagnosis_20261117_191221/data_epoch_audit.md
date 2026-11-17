# Data and epoch audit for checkpoint 17ab06dfb9a0

The persisted model is epoch 6, with only **6 optimizer updates** from a fresh action head. The full run contains 20 updates, because 27 training rows fit in the configured batch of 32. This is a sparse-data, limited-training result; the logs do not establish that merely increasing epochs would fix it.

## Integrity and coverage

- 42 accepted rows equal the 42 frozen rows on text, input role, config, split and semantic family. All saved split rows exactly equal their frozen subset.
- 42 distinct (role, text) inputs; no cross-split semantic-family IDs. All six current training-source hashes match the recorded run.
- All 42 rows use `instruction`; dialogue coverage is zero.
- Train: 27 rows / 27 families, comprising execute 15 and none/unsupported/ambiguous 4 each. Every family has only one accepted example. Val: 8 rows, execute 5 and each negative class 1. Test: 7 rows, execute 4 and each negative class 1.
- The initial numeric audit covers 41 accepted rows and reports zero violations/unresolved fields; revised val05-r1 is outside that initial audit. This is partial constraint evidence, not proof of all semantics.

## Actual supervised labels

Counts below include only the 15 execute rows, consistent with the loss mask. Parallel actions are sorted by `RESOURCE_IDS` before slot assignment.

| Label | Slot 1 | Slot 2 |
|---|---:|---:|
| PAD | 0 | 9 |
| blink.full | 2 | 1 |
| nod.basic | 2 | 1 |
| shake_head.basic | 2 | 1 |
| tilt_head.basic | 2 | 0 |
| look_around.basic | 1 | 0 |
| smile.basic | 1 | 1 |
| angry.basic | 2 | 1 |
| shy.basic | 1 | 1 |
| surprise.basic | 2 | 0 |
| wave.basic | 0 | 0 |
| cheer.basic | 0 | 0 |
| bow.basic | 0 | 0 |

- Topology: single action 9, sequential two actions 4, parallel two actions 2.
- Stage: slot 1 has stage 0 fifteen times; active slot 2 has stage 1 four times and stage 0 twice. Nine PAD slot-2 values are masked out of stage/cycle losses.
- Cycle count: slot 1 has one cycle 12 times and two cycles 3 times; active slot 2 has one cycle 6 times. No train action has three cycles.
- There are 21 active action instances / 24 cycles; hold ratio is exactly zero in 13 cycles, 0.35 in 2, 0.4 in 4, and 0.45 in 5.
- Wave, cheer and bow have no train labels. Validation contains a wave and three 3-cycle cases; test contains a wave and four two-action cases. Slot-2 look_around, surprise, tilt and wave have zero train positives.
- Execute (15/27), slot-2 PAD (9/15) and one active cycle (18/21) are dominant priors. **Blink is not a unique majority label**: blink/nod/shake/angry each occur 3 times overall, and six resources tie at 2 occurrences in slot 1.

## Validation evolution

| Epoch | Train loss | Conditional val loss | Technical errors / 8 | Correct structures | Selection score |
|---|---:|---:|---:|---:|---:|
| 1 | 6.750181 | 6.476397 | 3 | 0 | -0.341667 |
| 2 | 6.356987 | 6.172255 | 8 | 0 | -0.666667 |
| 3 | 5.930193 | 5.853094 | 8 | 0 | -0.666667 |
| 4 | 5.514457 | 5.547507 | 8 | 0 | -0.666667 |
| 5 | 5.028537 | 5.347601 | 8 | 0 | -0.666667 |
| 6 | 4.615986 | 5.373582 | 3 | 0 | -0.341667 |
| 7 | 4.320644 | 5.599566 | 3 | 0 | -0.341667 |
| 8 | 4.068721 | 5.885306 | 3 | 0 | -0.341667 |
| 9 | 3.873299 | 6.158144 | 3 | 0 | -0.341667 |
| 10 | 3.711173 | 6.408611 | 3 | 0 | -0.341667 |
| 11 | 3.682430 | 6.647935 | 3 | 0 | -0.341667 |
| 12 | 3.633486 | 6.816763 | 5 | 0 | -0.369444 |
| 13 | 3.581160 | 6.928370 | 4 | 0 | -0.355556 |
| 14 | 3.502696 | 7.020051 | 6 | 0 | -0.383333 |
| 15 | 3.521818 | 7.132382 | 7 | 0 | -0.525000 |
| 16 | 3.447983 | 7.272541 | 7 | 0 | -0.525000 |
| 17 | 3.398340 | 7.358647 | 6 | 0 | -0.383333 |
| 18 | 3.460926 | 7.318344 | 6 | 0 | -0.383333 |
| 19 | 3.292292 | 7.204417 | 5 | 0 | -0.369444 |
| 20 | 3.103706 | 7.110812 | 6 | 0 | -0.383333 |

- Epoch 1 has mostly two-action predictions; none match the gold structures.
- Epochs 2-5: all 8 rows fail `invalid_hold_mapping`; predicted look_around has positive hold although its native topology requires hold exactly zero.
- Epochs 6-7: all 8 known raw predictions are execute + one blink + one cycle. At epoch 6, durations are 615-620 ms and hold ratios 0.132-0.133, giving native rounded hold spans **81-83 ms**, only 1-3 ms above the 80 ms limit.
- Epochs 8-9: all 8 raw predictions are one surprise action; the collapse changes resource instead of learning the requested structures.
- Epoch 10 onward introduces `hold_segment_too_short` failures. At epoch 20, 6/8 fail this native 80 ms hold constraint; the other two return single angry and single surprise.
- Epoch 6 numeric guards block the three repeat cases: nod requires 3 cycles at 1200/900/600 ms; wave requires 3 cycles at 900 ms with increasing amplitude; tilt requires 3 cycles at 700/1000/1400 ms. Predicting blink leaves action/count/duration scopes unresolved.
- Decoder failures do not include raw predictions in these logs. Exact epoch-20 duration/ratio values cannot be recovered from the per-epoch files alone.

## Why epoch 6 was saved

The trainer maximizes `(selection_score, -technical_error_rate, -conditional_val_loss)` at `Tools/ActionEncoder/train_action_config.py:240`. Epochs 1 and 6-11 tie on primary score -0.3416666667 and error rate 3/8. Epoch 6 has the lowest conditional val loss among those ties (5.3735818863). Epoch 5 has slightly lower conditional val loss (5.3476009369), but all 8 predictions fail and its score is -0.6666666667. Epoch 20 scores -0.3833333333 with 6 errors, so its lower training loss does not make it the selected checkpoint.

Epoch 6 has macro decision accuracy 0.1, execute structure accuracy 0, non-execution specificity 0 and error rate 0.375; `(0.1+0+0)/3-0.375 = -0.3416666667`. Epoch 20 has macro 0.1, structure 0, specificity 1 (all three negatives error instead of returning execute), error rate 0.75; `(0.1+0+1)/3-0.75 = -0.3833333333`. Specificity here must not be read as correctly classified negatives. Every epoch has zero correct structures.

## Bounded conclusion

The admitted train data is small and fragmented across multiple independent heads, with strong one-action/one-cycle priors, missing role/resource/repetition coverage, and only six updates in the selected checkpoint. Validation selection rewards the least technically invalid configuration among uniformly wrong structures. The observed hold errors expose a disconnected legal parameter space (zero hold or a native span of at least 80 ms), so shrinking continuous error toward a zero-hold target can still produce an invalid small positive hold. This mechanism is consistent with the logged failures; exact gradients and failing parameters were not recorded.

No mutation of frozen label fields was found. This audit alone cannot exclude every semantic review issue, nor identify a unique cause for blink winning among tied resource frequencies. No old corpus was read; no source, labels, snapshots, checkpoints or service were modified. No training or model execution was performed by this sub-audit.

See `data_epoch_audit.json` for exact source hashes, full histograms, metrics, selection keys and per-epoch error-message counts.
