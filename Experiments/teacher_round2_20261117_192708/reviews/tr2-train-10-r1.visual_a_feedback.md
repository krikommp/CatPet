# Independent visual review: tr2-train-10-r1

Raw instruction: 发出手臂信号：挥手三次，每次750毫秒，右臂侧抬并张开手掌，再放回。
Role: instruction; parent: tr2-train-10
Status: uncertain; semantic: 0; naturalness: not scored

All three contact sheets (75 frames), all focused trajectory rows and originals 0/11/34 were inspected. Three clean side lifts with an open palm and return are visible, peaking near 367/1133/1867 ms and returning at 750/1500/2250 ms. The full moving hand stays within frame and geometry is coherent. However the limb rises on screen right in a front-facing character. RT/Right Upper Arm metadata names do not establish whether this is anatomical right or screen right, and no mirroring convention was found. The explicit right-arm requirement is therefore not an unambiguous visual match. Withdraw the provisional naturalness assessment; no naturalness score or training acceptance is assigned.

Limitations: The visible moving limb is on screen right. The raw instruction explicitly specifies right arm, but no anatomical-versus-screen or mirroring convention is established by the observed image or binding sources. Exact side semantics remain unresolved.

Observed every one of 3 pages, 75 frames and 75 focused trajectory rows. Additional original-resolution frame indices: 0, 11, 34.
Observation uses timestamped frames and trajectory; no native-speed playback claim.
No formal resource calibration is asserted. Old capture evidence is not reused for acceptance.

Reviewed UTC: 2026-11-17T11:59:05.469824+00:00
Provider: OpenAI / Codex desktop; model: Codex (exact backend model identifier not exposed)
Context: codex-desktop:/root/round2_visual_a:teacher_round2_20261117_192708
Prompt: codex-review-round2.v1; rubric: codex-independent-video.v1

Canonical config SHA256: cd0069c37c7db365ecc96a664c293780172913d7af4727359c22b87b299e7191
Raw SHA256: 5997df9703a69d7ed4255ef4906d827513ac153bc66cafcddf829cb6f7a3f0aa
Evidence SHA256: 78080d16829bb49204ec00b6ae2c19e88595a9207bd9b07f6087b00a31feb1af
Video SHA256: 9e6828158dd0c93d6c057b8a13fa3239bcbb6b1194e5489c904685833219ad0d

Viewed observation artifacts:

- D:\UnityProjects\Pet\PetLive2d\Experiments\teacher_round2_20261117_192708\observations\tr2-train-10-r1\observation_manifest.json
- D:\UnityProjects\Pet\PetLive2d\Experiments\teacher_round2_20261117_192708\observations\tr2-train-10-r1\trajectory_focus.jsonl
- D:\UnityProjects\Pet\PetLive2d\Experiments\teacher_round2_20261117_192708\snapshots_fixpilot\tr2-train-10-r1\trajectory.jsonl
- D:\UnityProjects\Pet\PetLive2d\Experiments\teacher_round2_20261117_192708\observations\tr2-train-10-r1\contact_sheets\page_001.png
- D:\UnityProjects\Pet\PetLive2d\Experiments\teacher_round2_20261117_192708\observations\tr2-train-10-r1\contact_sheets\page_002.png
- D:\UnityProjects\Pet\PetLive2d\Experiments\teacher_round2_20261117_192708\observations\tr2-train-10-r1\contact_sheets\page_003.png
- D:\UnityProjects\Pet\PetLive2d\Experiments\teacher_round2_20261117_192708\observations\tr2-train-10-r1\frames\frame_000000.png
- D:\UnityProjects\Pet\PetLive2d\Experiments\teacher_round2_20261117_192708\observations\tr2-train-10-r1\frames\frame_000011.png
- D:\UnityProjects\Pet\PetLive2d\Experiments\teacher_round2_20261117_192708\observations\tr2-train-10-r1\frames\frame_000034.png
