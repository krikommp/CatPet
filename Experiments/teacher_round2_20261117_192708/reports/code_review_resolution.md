# Resolution of independent code findings before training

The original independent `code_review.md` remains unchanged as failure evidence.

P1 exact-duration admission: the binder now requires a positive full-clause grammar plus an uninterrupted positive action anchor. It no longer promotes a broad numeric guard match by merely excluding a blacklist. All seven independent-review reproductions reject through the shared prediction helper; regression cases also cover unseen qualifiers and unrelated contexts. Rejection retains raw predicted structure and values.

P2 raw false execution: raw records now store finite status per head. A valid execute decision survives a nonfinite PAD stage tensor and counts as a raw false execution, while overall invalidity still prevents valid nonexecution credit. A regression test reproduces the original NaN case.

The final binding suite has29 tests and integration suite16 tests. Existing training workflow23 passed; evidence35 passed including2 actual ffmpeg integration tests. The feasible-head11 tests passed separately. These fixtures never enter training datasets.

Known deliberate grammar limit, discovered by read-only TRAIN gold-config auditing, without test-model predictions: current36 authored train rows have16 duration-bearing instructions, of which9 fit the narrow positive grammar and7 reject (01-r1,02-r1,05-r1,08-r1,10-r1,15-r1,16-r2); prior27 train rows have9 such instructions,5 fit and4 reject (03,05,06,08). Contextual prefixes such as “跟着节拍”, longer aliases such as “左右张望”, and instructional scene-setting are not stripped to invent a binding. Texts/labels remain unchanged and these failures will remain visible in per-epoch train diagnostics. No grammar expansion followed this audit. This policy improves exact supported forms; it is not a complete Chinese instruction parser.

Native visual bug: concurrent PreviewSession clones shared x=1000 and unrestricted camera visibility. Each session now owns `EditorSceneManager.NewPreviewScene()` and assigns `Camera.scene`; disposal closes that scene. Unity2022.3 compiled successfully. `preview_isolation_check.json` is a real renderer check with two overlapping previews and a moved second clone; first-camera pixels were identical and preview-scene counts returned to the starting value. Independent old-video reviewers and root fullframe inspections preserved actual ghost-image evidence; replacement pilot fullframes are clean.

Unity API references used for the rendering fix: [NewPreviewScene](https://docs.unity3d.com/2022.3/Documentation/ScriptReference/SceneManagement.EditorSceneManager.NewPreviewScene.html), [Camera.scene](https://docs.unity3d.com/2022.3/Documentation/ScriptReference/Camera-scene.html). Actual compilation and pixel checks, rather than documentation alone, establish the local behavior.
