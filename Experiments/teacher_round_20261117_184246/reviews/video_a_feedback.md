# Independent visual review A

Reviewer context: /root/visual_review_a. Provider: OpenAI / Codex desktop. Model: Codex (exact backend unavailable). Rubric: codex-independent-video.v1.

Reviewed all 23 contact-sheet pages covering all 568 recorded frames for train01–12, read every focus-trajectory frame, and inspected 13 full-size extracted frames for detailed checks. All review artifacts are bound in the JSONL. No rejected, uncertain, or clipped candidate receives a naturalness score. Integrity reports were checked only as capture prerequisites, never as semantic approval.

Result: 9 accepted, 2 rejected, 1 uncertain. The doubtful wave and failed cheer/bow remain excluded.
## tr1-train-01 — accepted

Viewed both contact sheets, every frame 0–36 (0–1200 ms), and full-resolution frame 7. The two eyes close and reopen together twice, with visible closure around 233–267 and 733–767 ms; the measured minima are 0.012741 at the samples surrounding the unsampled exact 250/750 ms peaks. Both eyes are fully open at 500 and 1000 ms, and remain open through Completed at 1200 ms. This matches two 500 ms blink cycles with zero hold. The face stays coherent, the available character artwork stays inside the frame, and the gradual closure/reopening has no visible snap or distortion. No corrective change required.

Semantic: 1. Naturalness: 0.92.

## tr1-train-02 — accepted

Viewed both contact sheets, every frame 0–50 (0–1666.7 ms), and full-resolution neutral frame 0 and first nod peak frame 11. Two modest but recognizable downward head motions return toward upright between cycles and at the end. Actual head/body pitch reaches about −19.7799/−4.9450 degrees at 366.7 ms and −19.7205/−4.9301 at 1066.7 ms; at 700/733.3 ms the head is within 0.18 degrees of neutral, consistent with the 720 ms cycle boundary. At 1433.3 ms it is −0.0201 degrees and the final residual is below 0.00006 degrees. There is no plateau, matching zero hold and two 720 ms cycles. The motion is smooth and readable, although the rig renders pitch less strongly than its numeric angle; no clipping or persistent deformation is visible. No corrective change required.

Semantic: 1. Naturalness: 0.8.

## tr1-train-03 — accepted

Viewed the single contact sheet containing every frame 0–33, through Completed at 1100 ms, and read all actual focus rows. One clear side-to-side head shake is visible: head yaw moves negative to −17.8555 degrees at 233.3 ms, crosses the center, reaches +17.9278 at 466.7 ms, then returns to zero at 900 ms. It stays neutral through release. This matches one 900 ms refusal shake with amplitude 1.0 and zero hold. The reversal is brisk but continuously eased; the character remains coherent and within the frame. No corrective change required.

Semantic: 1. Naturalness: 0.82.

## tr1-train-04 — accepted

Viewed both sheets, all frames 0–42 through 1400 ms, and every actual focus row. The head and upper body tilt together toward one side, hold visibly, and return once. Head/body roll reaches 22/5.5 degrees at 400 ms and remains there through 800 ms; the plateau samples agree with the configured 390–810 ms hold (0.35 of 1200 ms). Both channels return to zero by 1200 ms and remain there through Completed. The curious tilted pose is readable, smooth and unclipped, matching one 1200 ms tilt with a short middle pause. No corrective change required.

Semantic: 1. Naturalness: 0.88.

## tr1-train-05 — accepted

Viewed both sheets, every frame 0–45 through 1500 ms, plus full-resolution frames 10 and 20 to verify the gaze, and read all focus rows. The head and gaze search one side, cross to the other, then recenter in one continuous cycle. At 333.3 ms head yaw/eyeball X is −13.9457/−0.7969; at 666.7 ms it is +13.9729/+0.7984. Full-size frames show the associated left/right facial orientation and eye direction rather than a tilt. There is no held plateau, correctly using hold_ratio=0. Both channels return to zero at 1300 ms and stay neutral through Completed. Motion is modest but coherent and readable, with no clipping. No corrective change required.

Semantic: 1. Naturalness: 0.83.

## tr1-train-06 — accepted

Viewed both sheets, all frames 0–49 through 1633.3 ms, and full-size frame 18, and read all focus rows. One unmistakable crescent-eye smile forms, is held, then returns to open-eyed neutral. The smile-eye channel is 1 and both eyelids 0 from the 400 to 1000 ms samples; mouth-form/open channels are 0.931/0.49 and brows 0.588, agreeing with amplitude 0.98 and the 630 ms hold within the 1400 ms cycle. The visible mouth remains small, but the raised crescent eyes make the requested obvious smile clear; I do not claim a visibly large open-mouth smile. All targeted channels are neutral by 1400 ms and remain neutral through Completed. Smooth, symmetric, unclipped expression without persistent distortion. No corrective change required.

Semantic: 1. Naturalness: 0.88.

## tr1-train-07 — accepted

Viewed both sheets, every frame 0–52 through 1733.3 ms, full-size frames 20 and 6, and all focus rows. The face transitions from neutral to a clearly annoyed, toothed/wavy protesting mouth with tense brows, holds it, and releases. Full-size frame 20 resolves the angry mouth and brow shape; frame 6 verifies the transition is a blended onset rather than a missing mouth. Angry-eye/FXmouth1 reach 1 and normal mouth reaches 0 from 433.3 to 1066.7 ms; brows are −0.588 X/−0.882 Y, agreeing with amplitude 0.98 and the configured 675 ms hold. All return to baseline by 1500 ms and stay there. The one 1500 ms angry performance is readable, with smooth transition and no visible clipping or deformation. No corrective change required.

Semantic: 1. Naturalness: 0.83.

## tr1-train-08 — accepted

Viewed both sheets, every frame 0–54 through 1800 ms, full-size frame 20 and every focus row. A single sideways head lean with a small pout and averted gaze is visible, held long enough to read as bashful embarrassment, then restored. The affect is restrained, but distinguishable from the neutral start. From 466.7 to 1133.3 ms the head roll is −19.8 degrees, gaze X/Y is 0.88/−0.495, brows −0.44, FXmouth2 1 and normal mouth 0; this agrees with amplitude 1.1 and the 720 ms hold in the 1600 ms cycle. All return to neutral at 1600 ms and remain there through completion. Hair and face follow the tilt continuously; no clipping or persistent distortion is visible. No corrective change required.

Semantic: 1. Naturalness: 0.78.

## tr1-train-09 — accepted

Viewed both sheets, every frame 0–42 through 1400 ms, full-size frame 15, and every focus row. The eye effect changes to the startled pale wide-eye look while the mouth opens into the large surprise shape, producing one clear shocked reaction; it is held then fades back to neutral. FXeye/FXmouth3 are 1, normal mouth 0 and brows 0.88 from the 300 through 766.7 ms samples, matching amplitude 1.1 and the 480 ms hold of this 1200 ms surprise. All targeted channels reach baseline at 1200 ms and stay there to Completed. The comic surprise matches the persona and is not treated as accidental distortion. No visible clipping or unexplained jump; no corrective change required.

Semantic: 1. Naturalness: 0.87.

## tr1-train-10 — uncertain

Viewed both sheets, every frame 0–54 through 1800 ms, full-size frame 12 and every focus row. Timing and count are correct: the screen-right arm and hand channels rise to 8/0.9 at 400 and 1200 ms, return to 0 at 800 and 1600 ms, and remain neutral through Completed. The hand is inside the frame, though close to the right edge. Visually this is two broad straight-arm outward lifts with an opening palm, rather than a clearly recognizable greeting wave. The supplied raw text specifically asks to wave hello to a friend; I cannot establish exact semantic match merely from wave.basic or the correct cycle count. Do not admit this ambiguous performance. No naturalness score is assigned. Correction advice: calibrate a visibly communicative hand/forearm waving gesture, or obtain a revised rendering with a clearly readable greeting action; changing duration alone does not settle the semantic ambiguity.

Semantic: 0.75. Naturalness: not assigned.

## tr1-train-11 — rejected

Viewed both sheets, every frame 0–48 through 1600 ms, full-size frame 20 and every focus row. The numerical execution is one 1400 ms cycle: both upper-arm channels plateau at 8.925 and vertical-bounce at 0.8925 from 466.7 to 933.3 ms, consistent with hold_ratio 0.35, then return to 0 at 1400 ms. However the actual peak image is a horizontal, outstretched T-like pose with a neutral face rather than a clearly raised-hands celebratory gesture. At peak the outer fingers meet/cross both source-frame edges, so it fails the uncropped-character requirement even though the contact-sheet builder did not crop its input. Reject; no naturalness score is assigned because the hands are clipped. Correction advice: widen recording framing and calibrate the arm pose to read as celebration, then re-record and review the complete gesture. Correct timings and resource name do not cure the visible failure.

Semantic: 0.55. Naturalness: not assigned.

## tr1-train-12 — rejected

Viewed both sheets, every frame 0–51 through 1700 ms, full-size frame 20 and every focus row. The actual head/body channels reach −22/−9.35 degrees from 466.7 through 1033.3 ms, agreeing with amplitude 1.1 and the 570 ms hold in a 1500 ms cycle; both return to zero at 1500 ms and stay there. The rendering, however, shows only a shallow held head dip with the torso still almost upright and gaze forward, much like an extended nod. It does not clearly communicate the requested solemn bow to a senior. Reject on visual semantic mismatch despite correct trajectory and smooth return. No naturalness score is assigned to this rejected candidate. Correction advice: calibrate the body/head mapping so a forward bow is visibly distinct from nodding before re-recording; do not relabel this same held nod as a solemn bow to satisfy the quota.

Semantic: 0.6. Naturalness: not assigned.
