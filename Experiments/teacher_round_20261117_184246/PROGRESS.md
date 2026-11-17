# First real teacher round — completed

2026-11-17 Asia/Shanghai. Completed: genuine teacher generation, Unity capture, independent review, frozen dataset, one complete training run and fixed-test evaluation.

- Experiment: teacher_round_20261117_184246. Real teacher: root Codex context; exact backend identifier unavailable. No Gemini invocation.
- Initial plan54 candidates, fixed train/val/test36/9/9. One pre-recording wording correction preserved parent/family/val split; total55 generated IDs.
- Recording36/36 complete, no recording failures. All2301 frames represented in82 pages. Independent reviewers inspected every page and all actual focus trajectories. Same assembly/persona during recording.
- Reviews:42 accepted (24 execute +18 nonexecute),7 rejected,5 uncertain. No naturalness scores for rejected/uncertain/clipped candidates. Original technical reject retained separately.
- Frozen splits27/8/7; each has none/unsupported/ambiguous. Snapshot SHA25676ecaf278d5f7f64077e5995d37078509aebe1da7e2493d7a20fe3bda9feb3f2. prepare/validate/validate-only succeeded. No old corpus or fixtures admitted.
- Training one launch,20/20 epochs,batch32,2 CPU threads,exit0. Started19:00:46,finished19:01:09. Selected epoch6; new checkpoint17ab06dfb9a0 in checkpoint_epoch20/. All20 validation prediction files verified.
- Fixed-test:new structure0/7,false execution3/3. All7 predictions collapsed to single blink. Round9 same-input diagnostic structure3/7,false execution1/3,technical error1/7. This does not demonstrate model-quality improvement.
- Coverage:accepted10 resources,train9. No admitted bow/cheer;wave only in val/test with reviewer-specific rationale. All instruction role. Numeric progression tested in validation, not final test.
- Protected checkpoint/corpus/test inputs and frozen round9 copy unchanged. No promotion, overwrite or service switch.

Final report:ROUND_REPORT.md. Machine-readable completion:reports/completion_summary.json. All feedback, failures, videos, trajectories and epoch predictions retained. No required work remains for this bounded first round.
