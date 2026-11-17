# Independent visual review B: final isolated captures

Reviewer context: codex-desktop:/root/round2_visual_b:teacher_round2_20261117_192708
Provider: OpenAI / Codex desktop. Exact backend model identifier is not exposed.
The judgments below follow actual inspection of every manifest contact-sheet page, every trajectory_focus row, and the listed full-resolution frames. The previous contaminated captures were not used as visual evidence for these replacement judgments.
Semantic scores are binary under the admission rubric. Rejected or uncertain clips receive no naturalness score. Parameter labels alone do not establish visual gesture semantics.

## tr2-train-13-r2

Raw instruction: 摇头两次，第一次600毫秒，第二次1100毫秒，逐次变慢。
Input role: instruction; parent: tr2-train-13-r1
Result: accepted; semantic=1; naturalness=0.82
Observed: 2 complete contact-sheet pages, all 59 focus rows, full frames 4, 9, 26, 35.
Two coherent left-right head shakes are visible, first over 0–600 ms and second over 600–1700 ms. Full-resolution extrema at frames 4/9 and 26/35 resolve the two opposite head orientations. The second cycle visibly develops and returns more slowly; trajectory confirms equal amplitude (~15.3) with 600/1100 ms durations and neutral returns at 600/1700 ms. Available character and both hands remain uncropped. Smooth easing and stable head geometry support naturalness 0.82; the return phase is somewhat deliberate but readable.
Review UTC: 2026-11-17T12:03:18.260040+00:00

## tr2-train-14-r1

Raw instruction: 歪头两次，每次900毫秒，幅度越来越大。
Input role: instruction; parent: tr2-train-14
Result: accepted; semantic=1; naturalness=0.87
Observed: 2 complete contact-sheet pages, all 62 focus rows, full frames 13, 40.
Two same-side head tilts and returns are clearly visible, each lasting 900 ms. The second tilt is substantially larger in the full-resolution peak frames 13 and 40, matching head peaks ~10.956 and ~20.916 with body roll following proportionally. Each cycle returns to neutral at 900 and 1800 ms; no alternating-side claim is made. All visible character parts remain inside frame. Smooth coherent head/body movement and distinct repeated cycles support naturalness 0.87.
Review UTC: 2026-11-17T12:03:18.279042+00:00

## tr2-train-15-r1

Raw instruction: 左右张望两次，第一次1000毫秒，第二次1600毫秒。
Input role: instruction; parent: tr2-train-15
Result: accepted; semantic=1; naturalness=0.84
Observed: 3 complete contact-sheet pages, all 86 focus rows, full frames 7, 15, 42, 54.
Two clear left-right head-and-eye scans are visible. Full frames 7/15 and 42/54 resolve the gaze directions and repeated order. The first spans 0–1000 ms and the longer second spans 1000–2600 ms, returning head and gaze to center after each. The complete trajectory matches both timing and coordinated head/eye movement. Character and hands stay in frame. Smooth readable scans with a relatively slow final recentering support naturalness 0.84.
Review UTC: 2026-11-17T12:03:18.299412+00:00

## tr2-train-16-r2

Raw instruction: 示范侧抬右臂并张开手掌：挥手一次，持续900毫秒，随后放回。
Input role: instruction; parent: tr2-train-16-r1
Result: rejected; semantic=0; no naturalness score
Observed: 1 complete contact-sheet pages, all 35 focus rows, full frames 0, 13, 27.
One coherent broad arm lift with an open palm is visible, peaking around 433–467 ms and returning by 900 ms; all fingers remain in frame. However, full frame 13 shows the arm on image-right, which is the frontal character’s anatomical left side. The literal raw instruction requests the right arm. No established mirrored/viewer-side convention was supplied, and the RT parameter name alone cannot resolve this visible side mismatch. Count, duration and return match, but complete literal gesture semantics are uncertain.
Review UTC: 2026-11-17T12:03:18.314411+00:00

## tr2-train-17-r1

Raw instruction: 收到好消息先点头两次，再露出微笑。
Input role: instruction; parent: tr2-train-17
Result: accepted; semantic=1; naturalness=0.83
Observed: 3 complete contact-sheet pages, all 79 focus rows, full frames 0, 9, 18, 27, 54.
Two coherent downward nod-and-return movements occur first, with visible peaks at full frames 9 and 27 and an intervening neutral pose at 18. They occupy 0–600 and 600–1200 ms. A clear crescent-eye smile then appears, holds about 1567–2033 ms and returns to neutral at 2400 ms. The full trajectory confirms separated nod and smile stages without premature overlap. Full-resolution inspection resolves the modest nod amplitude. The available body and hands remain uncropped. Smooth modest nods and a clear friendly expression support naturalness 0.83.
Review UTC: 2026-11-17T12:03:18.329410+00:00

## tr2-train-18-r1

Raw instruction: 感谢鼓励，先微笑，再点头两次。
Input role: instruction; parent: tr2-train-18
Result: accepted; semantic=1; naturalness=0.83
Observed: 3 complete contact-sheet pages, all 79 focus rows, full frames 18, 45, 54, 63.
The character first gives a distinct crescent-eye smile, held approximately 367–833 ms and fully released by 1200 ms. Two visible downward nods then follow over 1200–1800 and 1800–2400 ms; full peak frames 45/63 and neutral frame 54 resolve their count and modest amplitude. No premature nod occurs during the smile. The complete trajectory corroborates the requested order and neutral returns. Whole available character and hands remain in frame. Smooth transitions and readable facial expression support naturalness 0.83.
Review UTC: 2026-11-17T12:03:18.348411+00:00

## tr2-train-19-r1

Raw instruction: 醒来突然听见警报：先眨眼两次，再露出惊讶表情。
Input role: instruction; parent: tr2-train-19
Result: accepted; semantic=1; naturalness=0.85
Observed: 2 complete contact-sheet pages, all 67 focus rows, full frames 7, 13, 20, 40.
Two distinct eyelid closures occur first, visible at full frames 7 and 20 with reopened eyes at frame 13 and again by 900 ms. A clear surprised expression follows, with pale wide eyes and an open square mouth, held approximately 1167–1600 ms and released by 2000 ms. All focus rows and both contact sheets show the requested order without extra gestures, followed by neutral completion at 2200 ms. The available character and hands remain in frame. Smooth blinks and the readable stylized surprise support naturalness 0.85.
Review UTC: 2026-11-17T12:03:18.363411+00:00

## tr2-train-20-r1

Raw instruction: 从震惊中缓过来，先惊讶，再眨眼两次。
Input role: instruction; parent: tr2-train-20
Result: accepted; semantic=1; naturalness=0.85
Observed: 2 complete contact-sheet pages, all 67 focus rows, full frames 13, 40, 47, 53.
The surprised expression occurs first over 0–1100 ms, visibly displaying pale wide eyes and an open square mouth. Two subsequent eyelid closures are separately resolved in full frames 40 and 53, with the intervening reopened eyes in frame 47. Both contact sheets and all focus rows confirm surprise release before the two 450 ms blinks, neutral return at 2000 ms and completion at 2200 ms. No character part is clipped by the frame. Smooth facial transitions and two distinct relaxed blinks support naturalness 0.85.
Review UTC: 2026-11-17T12:03:18.377580+00:00

## tr2-train-21-r1

Raw instruction: 先摇头否认，再歪头思考。
Input role: instruction; parent: tr2-train-21
Result: accepted; semantic=1; naturalness=0.82
Observed: 2 complete contact-sheet pages, all 66 focus rows, full frames 6, 13, 42.
A left-right head shake appears first, with the opposite head orientations resolved in full frames 6 and 13. It returns to center around 850 ms before a clear same-side head-and-body tilt begins. The tilt visibly holds at approximately 1267–1533 ms and returns by the end of the 1950 ms action, completing at 2167 ms. Every trajectory row corroborates this order and the absence of shake/tilt overlap. Full frame 42 confirms the tilted ear remains inside the image despite the small top margin, and both hands and the available body stay visible. Smooth readable motion with a relatively deliberate return supports naturalness 0.82.
Review UTC: 2026-11-17T12:03:18.395141+00:00

## tr2-train-22-r1

Raw instruction: 先歪头思考，再摇头给出否定答案。
Input role: instruction; parent: tr2-train-22
Result: accepted; semantic=1; naturalness=0.82
Observed: 2 complete contact-sheet pages, all 66 focus rows, full frames 16, 39, 46.
A clear head-and-body tilt occurs first, with its held pose resolved in full frame 16 and visible hold approximately 400–700 ms. It releases to center by 1100 ms. One left-right head shake follows over 1100–1950 ms, with its opposing orientations resolved at full frames 39 and 46, before neutral completion at 2167 ms. All contact-sheet frames and focus rows confirm the requested order without overlap. The tilted ear tip stays just inside the upper edge, and the available body and both hands remain fully inside the image. Smooth coherent motion with deliberate recentering supports naturalness 0.82.
Review UTC: 2026-11-17T12:03:18.413214+00:00

## tr2-train-23-r1

Raw instruction: 先露出生气表情，再左右张望寻找捣乱的人。
Input role: instruction; parent: tr2-train-23
Result: accepted; semantic=1; naturalness=0.8
Observed: 3 complete contact-sheet pages, all 85 focus rows, full frames 0, 18, 49, 59.
A visibly annoyed/angry expression appears first: full frame 18 resolves lowered inward brows, a tense narrowed eye shape and a small clenched mouth compared with neutral frame 0. It holds approximately 400–900 ms, then releases by 1300 ms. The character next scans left and right using coordinated head and gaze movement; full frames 49 and 59 resolve the opposite directions. All 85 focus rows and all three sheets confirm the sequential stages and return to center at 2600 ms, completing at 2800 ms. The available character and both hands remain in frame. The restrained but readable anger and smooth scan support naturalness 0.80.
Review UTC: 2026-11-17T12:03:18.430268+00:00

## tr2-train-24-r1

Raw instruction: 先左右张望检查周围，再露出生气表情。
Input role: instruction; parent: tr2-train-24
Result: accepted; semantic=1; naturalness=0.8
Observed: 3 complete contact-sheet pages, all 85 focus rows, full frames 10, 20, 57.
The character first scans left and right with coordinated head and eye movement; full frames 10 and 20 resolve the opposing directions. It recenters by 1300 ms before developing a visibly angry/annoyed expression. Full frame 57 resolves the lowered inward brows, tense eye shape and clenched mouth. The expression holds approximately 1700–2200 ms and releases to neutral at 2600 ms, completing at 2800 ms. All three contact sheets and all 85 focus rows show the requested sequential order without overlap. The available character and both hands stay inside the frame. Smooth scanning and a restrained but readable angry expression support naturalness 0.80.
Review UTC: 2026-11-17T12:03:18.448774+00:00
