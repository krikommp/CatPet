# Independent heldout video review C

Reviewer: OpenAI / Codex desktop; Codex (exact backend ID unavailable); context /root/visual_review_c. Actual review recorded at 2026-11-17T10:58:17.613270+00:00.

Reviewed the 12 requested execute candidates only, including val-05-r1 instead of its technically rejected unrecorded parent. All 32 timestamped contact-sheet pages, 970 actual focused per-frame trajectory rows, and 12 selected full-resolution frames were viewed/read in this context. Every focused value was additionally checked against the corresponding full trajectory; hashes and capture integrity reports were verified. No generator conversation was inherited.

Outcome: 9 accepted, 3 rejected. Naturalness was omitted for the two visually ambiguous bow candidates and the clipped/ambiguous cheer-then-bow candidate. Accepted entries require semantic score 1 and naturalness >= .70. These results are diagnostic experimental candidate reviews, not resource calibration, release approval, or training-set admission. All rows remain heldout.

Framing: contact sheets preserve the entire 720x840 recorded frame. The model artwork is an upper-body presentation ending above the bottom border; no full-body action capability is inferred. Action clipping is assessed at the actual frame boundaries. Test-04 loses left fingertips during the cheer plateau.

## tr1-val-01 — rejected

Instruction: 告别前辈时先鞠躬行礼，再挥手道别。 (input_role=instruction)

Observed all pages 1-3, frames 0-105 (0-3500 ms), plus full-resolution frames 0 and 24. The trace correctly holds head/body pitch at -22/-9.35 from sampled 500-1100 ms, returns both to zero at 1600 ms, then makes two right-arm excursions peaking near 2033 and 2867 ms and settles by 3300 ms. The two waves and sequence are visible, smooth and contained in the frame. However the first act reads as a shallow head dip: the torso remains almost upright, and the full-resolution 800 ms pose does not establish a clearly recognizable bow of greeting. Numerical bow channels alone cannot resolve that semantic uncertainty; reject instead of awarding semantic=1.

Scores: {"semantic": 0.7}

Correction/retention advice: No reliable config-only correction is established. Bow amplitude is already 1.10 with body pitch -9.35 near its -10 native limit; increasing hold or duration cannot demonstrate a missing torso bend. Retain this rejection until a separately recorded candidate visibly establishes the bow. Do not change the bound source or relabel the requested bow as a nod.

## tr1-val-02 — accepted

Instruction: 从局促变得放松：先表演害羞，再露出微笑。 (input_role=instruction)

Observed pages 1-3, every frame 0-95 (0-3166.7 ms), with full-resolution shy frame 24 and smile frame 64. A sideways head lean, averted gaze and small pout are visible first, followed by a distinct closed-eye smile. Actual shy peak is roll -19.8, gaze X .88/Y -.495, brow -.44 and FXmouth2=1 from sampled 466.7-1033.3 ms. All shy channels return to reference at 1500 ms before smile starts. Smile eye=1, eye openness=0, mouth form=.931/open=.49 and brow=.588 are held from sampled 1900-2533.3 ms, released by 2966.7 ms, and Completed at 3166.7 ms. The requested shy-to-relaxed transition is legible, with smooth entry/exit, no persistent conflict or clipping.

Scores: {"semantic": 1, "naturalness": 0.82}

Correction/retention advice: No correction requested for this experimental candidate.

## tr1-val-03 — accepted

Instruction: 先左右张望，随后因为发现异常而露出惊讶的表情。 (input_role=instruction)

Observed pages 1-3, every frame 0-86 (0-2866.7 ms), and full-resolution surprise frame 60. Visible gaze/head movement goes one way then the other, returns to center, and only then changes to conspicuously wide pale eyes and open shocked mouth. Actual look trace reaches yaw about -14.603 at 333.3 ms and +14.7 at 700 ms, with gaze -.834/+ .84, no hold, and zero yaw/gaze at 1400 ms. Surprise then enters: FXeye/FXmouth3 reach 1 and brow .88 by 1700 ms, remain through 2200 ms, and return to neutral by 2666.7 ms. The order and facial identity match the instruction; movement and expression transitions are coherent and unclipped.

Scores: {"semantic": 1, "naturalness": 0.82}

Correction/retention advice: No correction requested for this experimental candidate.

## tr1-val-04 — accepted

Instruction: 点头三次，第一次1200毫秒，第二次900毫秒，第三次600毫秒，越点越快。 (input_role=instruction)

Observed pages 1-3, every frame 0-87 (0-2900 ms), and every actual two-channel trajectory row. Three small but visible downward-and-up head gestures occur. Head/body pitch leave reference and return at 1200, 2100 and 2700 ms, establishing durations 1200, 900 and 600 ms. The sampled minima are -18/-4.5 at 600 ms, about -17.9278/-4.4819 at 1633.3 and 1666.7 ms (the 1650 ms peak lies between samples), and -18/-4.5 at 2400 ms. These are three comparable-amplitude nods with progressively shorter periods, not an amplitude ramp. Each returns to reference before the next; the last returns before the release tail and Completed at 2900 ms. No clipping or unexplained discontinuity was visible; the subtle head motion is sufficient to read as nodding.

Scores: {"semantic": 1, "naturalness": 0.77}

Correction/retention advice: No correction requested; preserve the three explicit cycle durations.

## tr1-val-05-r1 — accepted

Instruction: 挥手三次，每次900毫秒，幅度越来越大。 (input_role=instruction)

Observed pages 1-3, every frame 0-88 (0-2933.3 ms). Three distinct right-arm/hand lift-and-return waves are visible, each larger than the previous. Actual reference returns occur at 900, 1800 and 2700 ms, matching three 900 ms cycles. Sampled arm/hand maxima are 3.9839/.4482 around 433.3-466.7 ms, 6.3743/.7171 around 1333.3-1366.7 ms, and 8.7647/.986 around 2233.3-2266.7 ms, consistent with scales .50/.80/1.10 without inventing values at unsampled peaks. Motion remains smooth, distinct and within the captured frame even on the largest wave; final neutral and Completed are present. This review applies only to revision r1 and does not retroactively accept its unrecorded parent.

Scores: {"semantic": 1, "naturalness": 0.8}

Correction/retention advice: No correction requested; retain parent association and heldout val split.

## tr1-val-06 — accepted

Instruction: 朝同一侧歪头三次，每次都回正，第一次700毫秒，第二次1000毫秒，第三次1400毫秒，逐次变慢。 (input_role=instruction)

Observed pages 1-3, every frame 0-99 (0-3300 ms). Three clear tilts all go toward the same side and visibly straighten between them. Actual roll/body-roll are always nonnegative, with sampled first peak 19.8683/4.9671 at 333.3-366.7 ms, then 20/5 at 1200 and 2400 ms. Both channels return to zero at 700, 1700 and 3100 ms, giving exact 700, 1000 and 1400 ms cycles and the requested progressive slowing. No alternating-side movement is present. Return and release remain stable through Completed at 3300 ms; there is no clipping, jump or persistent deformation.

Scores: {"semantic": 1, "naturalness": 0.85}

Correction/retention advice: No correction requested; do not relabel these same-side cycles as left/right sway.

## tr1-test-01 — accepted

Instruction: 用眨眼和挥手一起发出招呼信号，两种动作同时开始。 (input_role=instruction)

Observed pages 1-2, every frame 0-42 (0-1400 ms). Two blinks are visibly synchronized with two right-hand waves. The very first playing sample at 33.3 ms already changes both arm (.2743) and eyelids (.9657), proving common onset within capture resolution; at 300 and 900 ms the arm reaches 8/.9 hand while both eyes reach complete closure 0. Both sets return to reference at 600 and 1200 ms. Count was unspecified in raw text, and the two matched cycles in config are permissible. End neutral, release and Completed are visible. The combination is legible, smoothly coordinated and unclipped.

Scores: {"semantic": 1, "naturalness": 0.83}

Correction/retention advice: No correction requested for this experimental candidate.

## tr1-test-02 — accepted

Instruction: 合影摆姿势时，歪头的同时微笑，保持片刻后回正。 (input_role=instruction)

Observed pages 1-2, every frame 0-51 (0-1700 ms). Head/body tilt and closed-eye smile visibly begin together, hold as a coherent photo pose, and return together. Actual roll/body peak 21/5.25, smile-eye 1, eyelids 0, mouth .931/.49 and brows .588 are reached by sampled 466.7 ms and remain through 1033.3 ms, consistent with the configured 600 ms hold bounded at 450/1050 ms. All channels reach reference at 1500 ms before Completed at 1700 ms. The pose clearly satisfies simultaneous tilt/smile plus brief hold/straightening, with no clipping or abrupt conflict.

Scores: {"semantic": 1, "naturalness": 0.88}

Correction/retention advice: No correction requested for this experimental candidate.

## tr1-test-03 — rejected

Instruction: 表演不情愿地赔礼：鞠躬时同时保持生气的表情。 (input_role=instruction)

Observed pages 1-2, every frame 0-54 (0-1800 ms), and full-resolution frame 24 at 800 ms. Angry eyes, tightened brow and jagged small mouth are visible while the head lowers. Actual angry-eye/FXmouth1 reach 1 with brows Y -.882/X -.588, while bow pitch reaches -20 head/-8.5 body from sampled 500-1100 ms; channels enter concurrently and return by 1600 ms, with Completed at 1800 ms. The concurrency and angry expression are supported. But the torso remains visually almost upright and the pose is a mild downward head movement, insufficiently clear as the requested bow/apology. Full-resolution viewing does not remove this identity ambiguity, so semantic=1 and naturalness are withheld.

Scores: {"semantic": 0.65}

Correction/retention advice: A separate preview could test bow scale 1.15 within native bounds, but only a small increase is available and no acceptance is predicted. Keep the current candidate rejected until a rerecord makes a bow unambiguous; do not modify bound resources or reinterpret the instruction.

## tr1-test-04 — rejected

Instruction: 谢幕先举手欢呼，接着鞠躬致谢。 (input_role=instruction)

Observed pages 1-3, every frame 0-99 (0-3300 ms), and full-resolution frames 20 and 68. Both arms visibly spread/raise first, return by 1500 ms, then the head/body pitch gesture begins. Actual cheer arm values plateau at 9.35/9.35 with vertical channel .935 from sampled 466.7-1033.3 ms; bow later holds -22/-9.35 from 2000-2600 ms and returns at 3100 ms. Sequence and numerical completion are correct. However the left fingertips run through x=0 in the 720x840 full-resolution cheer frame 20, also visible across the plateau contact-sheet tiles; therefore the required action is clipped. The bow at full-resolution frame 68 also reads as a shallow head dip with nearly upright torso. Reject; no naturalness score is issued for clipped/uncertain evidence.

Scores: {"semantic": 0.6}

Correction/retention advice: A separate config-only preview may reduce cheer amplitude from 1.10 to .95 to create a hand margin while retaining the two-arm rise, but it must be rerecorded and observed. That alone does not resolve bow identity. Keep this rejection and do not treat camera-cropped hand evidence as complete action visibility.

## tr1-test-05 — accepted

Instruction: 先露出微笑，接着收起笑容左右张望，像是要去找人。 (input_role=instruction)

Observed pages 1-3, every frame 0-88 (0-2933.3 ms). A clear closed-eye smile appears first, fully fades to the neutral open-eye face, then head and gaze scan both sides. Actual smile-eye is 1 and eyelids 0 from sampled 433.3-966.7 ms; all smile channels reach reference at 1400 ms. Only after that do yaw/gaze move, reaching about -13.946/-.797 at 1733.3 ms and +13.973/.798 at 2066.7 ms, while smile stays 0 throughout. The look-around has zero hold and returns to center at 2700 ms. This directly satisfies removing the smile before looking around; transitions, release and final Completed at 2933.3 ms are smooth and unclipped.

Scores: {"semantic": 1, "naturalness": 0.84}

Correction/retention advice: No correction requested; preserve zero hold on look_around.

## tr1-test-06 — accepted

Instruction: 表现改口：先点头，回正后再摇头。 (input_role=instruction)

Observed pages 1-2, every frame 0-64 (0-2133.3 ms). One visible nod occurs, the character straightens, then the head turns side-to-side as a shake. Actual head/body pitch reaches about -17.9278/-4.4819 at 433.3-466.7 ms and both reach zero at 900 ms while yaw is still zero. Yaw first departs reference at 933.3 ms, reaches about -18.6592 at 1133.3 ms then +18.9 at 1400 ms, and returns at 1900 ms; pitch remains zero throughout the shake. Thus the explicit return-before-shake ordering is fulfilled without concurrent residual nodding. Movement is modest but readable, with no clipping or persistent conflict through Completed at 2133.3 ms.

Scores: {"semantic": 1, "naturalness": 0.79}

Correction/retention advice: No correction requested for this experimental candidate.

## Wave identity addendum

After the initial review, the parent flagged a possible ambiguity between a greeting wave and a straight-arm side lift. I viewed val-05-r1 full-resolution frames 13/41/68 and test-01 frame 9. My judgement remains accepted for these two candidates: the complete clips show outward/upward open-hand sweeps and downward returns; val-05-r1 clearly increases the hand reach each time and test-01 pairs both sweeps with complete blinks. I read these as broad whole-arm waves. Neither raw instruction requires a bent elbow or wrist oscillation, and I do not claim those motions occur. This is a sample-specific visual judgement, not reliance on the resource name. Initial verdicts are preserved in video_c_reviews.initial.jsonl; final records bind the additional observed frames and updated actual UTC times.
