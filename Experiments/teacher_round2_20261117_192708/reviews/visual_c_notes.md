# Independent visual review C — round 2

Reviewer: OpenAI / Codex desktop; exact backend model identifier not exposed. Independent context: `codex-desktop:/root/round2_visual_c:teacher_round2_20261117_192708`. Prompt: `codex-review-round2.v1`; unchanged rubric: `codex-independent-video.v1`. Reviewed at 2026-11-17T12:02:02Z.

Reviewed only final replacements 25–36: 29/30 are `r2`; all others `r1`. No unsuffixed or quarantined capture was admitted. Read the actual bound persona `Docs/ActionLanguage/personas/gemini-cyber-cat.md` (SHA256 d758cac79840d9c91e28697c750a2a51d629bce830c411d42c24854f9ac53ce9), compiler, catalog, native profile and `review_evidence.py` contract. An older persona copy was read initially but was not used as the bound source; the current actual persona was read before final decisions.

All 26 full contact-sheet pages were individually displayed with `tools.view_image`; all 626 timestamped video frames therefore appeared without skipping. All 626 focus trajectory rows were read in frame order, and full trajectory parameters were cross-checked programmatically against the focus rows. An additional 30 original-resolution frames were displayed for faces, blink counts, hands and movement details. Every observation artifact path in the JSONL refers to an artifact actually inspected. The character asset's available thigh-ended drawing is surrounded by background within the source frame; none of these final clips showed viewport cropping of the available character or hands.

Re-ran `validate_capture_only` for every final video with the manifest-bound ffmpeg executable, obtaining `valid=true` and `full_decode=true` for all 12. Verified current SHA256 of every manifest-listed evidence, video, metadata, done report, queue, focus/full trajectory, page and original-resolution frame. Verified current source bindings, actual config/raw/parent identity, complete done/ok and frame counts. The first recheck attempt failed only because ffmpeg was not on the environment search path; rerunning with the existing manifest-bound executable succeeded without installation or source changes.

Outcome: 6 accepted, 5 uncertain (literal arm laterality), 1 rejected (closed eyes obscure looking/searching). Only accepted reviews contain naturalness scores. No quota was applied; no source, candidate, Unity or code files were edited.

The parent supplied a factual reminder to check actual arm laterality and reported no explicit screen/anatomical/mirror convention in the metadata. This reviewer independently saw screen-right arm movement in every assigned wave clip and did not rely on another reviewer's judgments. The normal front-facing anatomical interpretation makes this the character's left arm; the explicit raw right-arm request cannot be unambiguously validated by the RT parameter name alone.

## tr2-train-25-r1

Raw: 先表演害羞，再眨眼两次调整心情。

Status: **accepted**. Scores: {"semantic":1,"naturalness":0.84}.

完整观察73帧：0–1300ms先出现向一侧歪头、侧下方视线和嘟嘴的害羞姿态，约400–900ms停留后回正；随后在约1533ms和1967ms出现两次完整闭眼，两次之间约1767ms明显睁开，2200ms恢复。原分辨率确认害羞嘴型、两次闭眼及其间睁眼。角色全部可用图形与双手保持在画框内，进入、保持和回位连续；害羞定格略显模板化但整体自然。符合instruction中的动作顺序及次数。

Feedback: 可保留本条顺序组合；害羞段有可辨识表情与停留，随后两次眨眼独立可数。

Coverage: 73 frames; 3 pages; original-resolution frames 0, 18, 46, 53, 59, 72. Native duration 2200 ms; final player time 2400.000 ms.

Evidence SHA256: `ae06ca942cfbe381abe93959a8e56cac02b8bdfecae4a27bba36193782a8ecae`. Video SHA256: `e8bcff60639a1d92df3f0060cb0b8fd99fd355d402d6bbd484727b200eb96d8b`.

## tr2-train-26-r1

Raw: 先眨眼两次，再切换成害羞的表情。

Status: **accepted**. Scores: {"semantic":1,"naturalness":0.84}.

完整观察73帧：先在约233ms和667ms闭眼，两次间约467ms充分睁开；900ms之后才进入害羞动作，约1300–1800ms维持歪头、侧下方视线及嘟嘴，2200ms回正。原分辨率确认两次眨眼和后续害羞嘴型。所有可用角色图形及双手始终在框内，节奏与衔接平顺，满足先两次眨眼再害羞的明确指令。

Feedback: 可保留本条反向顺序；与25相比，害羞参数和可见表演均推迟到两次眨眼完成后。

Coverage: 73 frames; 3 pages; original-resolution frames 7, 14, 20, 45. Native duration 2200 ms; final player time 2400.000 ms.

Evidence SHA256: `1e4c84965b4e47580d2dcc86c9b729dd11719220d13f61cc876a9465eb4b614d`. Video SHA256: `c200dc2214cdfaaaf83e49aa8f6045cbdb6634c9991953ba1bbb4661b2a73a78`.

## tr2-train-27-r1

Raw: 先挥手，右臂侧抬、张开手掌再放回，随后点头确认。

Status: **uncertain**. Scores: {"semantic":0.5}.

完整观察58帧与原分辨率13/39帧。0–900ms清楚出现画面右侧手臂侧抬、手掌展开和放回，900–1700ms随后点头并回位，顺序可确认且未裁切。但正面角色抬起的是screen-right手臂，通常对应角色自身左臂；raw明确要求右臂，而现有绑定资料没有明确屏幕侧别或镜像约定。PARAM_Arm_RT_Angle命名不能消除这项视觉语义不确定，因此不能给semantic=1或naturalness。

Feedback: 保留当前样本为不确定。未来需明确并视觉核验角色自身左右与屏幕左右的约定，再生成对应新样本；不可把现有raw的右臂默认为画面右侧。

Coverage: 58 frames; 2 pages; original-resolution frames 13, 39. Native duration 1700 ms; final player time 1900.000 ms.

Evidence SHA256: `dd623442169ca2d6e598385d30e8e3ab04a5a8f3a88d6b68e255b8ff1fc6b512`. Video SHA256: `223f3e4e5dba914c1e968e386a98ff7c417ae4b119582212469bbf560a328df2`.

## tr2-train-28-r1

Raw: 先点头确认，再挥手，右臂侧抬、张开手掌后放回。

Status: **uncertain**. Scores: {"semantic":0.5}.

完整观察58帧与原分辨率12/37帧。先在0–800ms低头点头并回正，之后800–1700ms画面右侧手臂侧抬、张掌再放回，动作顺序与画面完整性确认。但raw要求角色右臂，正面画面的screen-right手臂通常为角色左臂，资料没有足够的屏幕/自身左右或镜像定义；仅凭资源参数名不能接受该侧别。无naturalness评分。

Feedback: 顺序实现正确，侧别仍需独立定义和视觉标定后新建样本，当前保持不确定。

Coverage: 58 frames; 2 pages; original-resolution frames 12, 37. Native duration 1700 ms; final player time 1900.000 ms.

Evidence SHA256: `e921403e2d83abaa4b748731ae5685686671fef8e90d66143d8a77d6d41a75a5`. Video SHA256: `c14c06ffe22040e63f189e4cad29933ef9ffada2c1afac903fcde23876f56b86`.

## tr2-train-29-r2

Raw: 做个俏皮练习：眨眼一次和歪头一次同时开始。

Status: **accepted**. Scores: {"semantic":1,"naturalness":0.86}.

完整观察37帧及原分辨率15帧：双眼闭合和头身侧倾同时从起始中性姿态发展，约367–633ms保持完整闭眼及清楚的同侧歪头，随后同时回到睁眼与正中，1000ms完成，两者均只有一次。全可用角色图形、耳尖与双手在框内；没有多余动作或突跳。符合俏皮练习中一次眨眼和一次歪头同时开始，保持稍长但仍自然。

Feedback: 可保留；单次并行闭眼与歪头在视觉和逐帧轨迹中一致，完成后回位明确。

Coverage: 37 frames; 2 pages; original-resolution frames 15. Native duration 1000 ms; final player time 1200.000 ms.

Evidence SHA256: `16a40d93ceee49098375d5b413583f8285870c516aead6fbf7a97f0b07f30b0d`. Video SHA256: `9c40f46514a58953cfbf28b67c64c8921ed780d369ab0f0c6bc3d3e46812eaf4`.

## tr2-train-30-r2

Raw: 做眼睛与头部的配合练习，眨眼两次和摇头两次同时开始。

Status: **accepted**. Scores: {"semantic":1,"naturalness":0.8}.

完整观察46帧并补看5/10/20/24/29原分辨率帧：0–650ms与650–1300ms各有一组左右转头并回中，两个周期分别伴随约333ms和967ms完整闭眼，约667ms双眼重新睁开。首个运动间隔已同时出现眼睑收合与头部转向，符合同时开始。画面清晰未裁切，所有可用角色图形及双手保持在框内；转头往返较快、机械感略强，但连续无跳变且次数清楚。

Feedback: 可保留这一配合练习；两个摇头周期与两个眨眼周期都可独立计数，建议后续采样补充更舒缓速度以扩展节奏。

Coverage: 46 frames; 2 pages; original-resolution frames 5, 10, 20, 24, 29. Native duration 1300 ms; final player time 1500.000 ms.

Evidence SHA256: `64c91e58491f542edbc7550d6f445723740c23167409f55067e3c89492f8491d`. Video SHA256: `5d44f949a8cd31ce9afc4b287deaa7890bd5b25f18f9cc449e6dc6c4555592e2`.

## tr2-train-31-r1

Raw: 开心地赞同，点头和微笑同时开始。

Status: **accepted**. Scores: {"semantic":1,"naturalness":0.86}.

完整观察46帧及原分辨率15帧：微笑的月牙眼与上扬表情和点头同时进入；500ms附近清楚下点，随后回正，微笑在点头过程中保持并延续至约900ms后渐退，1300ms恢复。可用角色图形和双手全程在框内；姿态与表情衔接自然，视觉上呈现开心赞同，满足raw并行开始的要求。

Feedback: 可保留；微笑保持覆盖点头主体，点头回位后微笑自然结束。

Coverage: 46 frames; 2 pages; original-resolution frames 15. Native duration 1300 ms; final player time 1500.000 ms.

Evidence SHA256: `26bff1bf4bc705c02806983d5a51b0170e0a386a23695a1cee9ab1bceb968d73`. Video SHA256: `2633b8f05ae99f7bc4ac716b4ed1ab14c69792bed38db65dbd508a003c173e77`.

## tr2-train-32-r1

Raw: 带着笑意寻找朋友，左右张望和微笑同时开始。

Status: **rejected**. Scores: {"semantic":0.6}.

完整观察50帧及6/10/21/34原分辨率帧。微笑和左右头部转动确实同时起始，1400ms回位，未裁切。但主要左右扫视期间双眼变成完全闭合的月牙眼：约433–967ms眼睑值为0，700ms头部转向另一侧峰值时原分辨率画面也完全闭眼。画面主要表现笑着转头，缺少能看清的双向视线寻找；无法无歧义履行raw的左右张望寻找朋友，参数存在眼球运动不足以替代可见语义。故拒绝且不评分naturalness。

Feedback: 后续需采用视觉上能保持睁眼的微笑资源或另行设计有可见双向观察的样本；不能仅以look_around资源名和眼球轨迹认定当前闭眼表演已完成寻找。

Coverage: 50 frames; 2 pages; original-resolution frames 6, 10, 21, 34. Native duration 1400 ms; final player time 1633.333 ms.

Evidence SHA256: `70f269e5be9707a008530536f8f4a28714847cb914b81c8c077645229e91121f`. Video SHA256: `30e1eac18e0af7fb5984174e9e00fb061315158128f1eacd49b5dbfabb4ae978`.

## tr2-train-33-r1

Raw: 惊讶地琢磨这个问题，歪头和惊讶表情同时开始。

Status: **accepted**. Scores: {"semantic":1,"naturalness":0.83}.

完整观察47帧及原分辨率18帧：歪头与惊讶表情同时展开，约433–767ms头身侧倾配合明显的震惊眼、抬眉及张大的替换嘴，之后逐渐恢复，1300ms回中。整个可用角色图形、耳尖和双手未出框；这是清楚的惊讶思考式歪头，虽为夸张动画表情，进出平顺并符合角色表现，满足raw同时开始。

Feedback: 可保留；惊讶表情在原分辨率下清晰，歪头和表情保持阶段重叠，无裁切或可见通道冲突。

Coverage: 47 frames; 2 pages; original-resolution frames 18. Native duration 1300 ms; final player time 1533.333 ms.

Evidence SHA256: `e7ca1f151b85f2edfedeb888d036d55dbea0375d3b5b2f47ad4f1873baeb65bd`. Video SHA256: `aedd6e9e2f52b94edacd7185bf0c421249d9ba5a80edebd25579054cf1a2615f`.

## tr2-train-34-r1

Raw: 带着害羞表情示范挥手，两者同时开始，右臂侧抬、张开手掌再放回。

Status: **uncertain**. Scores: {"semantic":0.5}.

完整观察50帧及原分辨率15帧。害羞的歪头、回避视线和嘟嘴与侧抬张掌同时进入；手臂1000ms放回，害羞1400ms结束。可用角色图形和活动手指均未裁切。但活动手臂在画面右侧，正面角色通常对应自身左臂，而raw明确说右臂；未有明确镜像/屏幕侧别约定可支持这一差异。尽管其余并行结构可见，侧别语义仍不确定，不能接受或给naturalness。

Feedback: 害羞与张掌并行结构可见；当前右臂表述需先解决角色左右和屏幕左右约定，保留不确定记录。

Coverage: 50 frames; 2 pages; original-resolution frames 15. Native duration 1400 ms; final player time 1633.333 ms.

Evidence SHA256: `de548fd50287cb16d3598fea8017f448600c75e74c7ef2adf18c16641130ca8b`. Video SHA256: `3105d54101f44d3a1c8639e94a74931a7c2b2b631015bb8205307d5404252408`.

## tr2-train-35-r1

Raw: 用动作表示拒绝：摇头和挥手同时开始，挥手时右臂侧抬、张开手掌再放回。

Status: **uncertain**. Scores: {"semantic":0.5}.

完整观察38帧及原分辨率7/15帧。头部先朝一侧、再朝另一侧并回中，侧抬张掌同起，1000ms共同回位；画面完整，活动手指没有出框。摇头支持拒绝的动作语境，但抬起的是screen-right手臂，正面角色通常为自身左臂；raw明确要求右臂，现有资料不能证实镜像或屏幕左右解释。因此全句语义不确定，无naturalness评分。

Feedback: 摇头与侧抬张掌的并发关系已观察到；侧别未证实之前不应将本条作为明确右臂训练正例。

Coverage: 38 frames; 2 pages; original-resolution frames 7, 15. Native duration 1000 ms; final player time 1233.333 ms.

Evidence SHA256: `f6cfb075736d8a11e065229326bc409ca72963bfb2ac2d04fc93996ca8fc9685`. Video SHA256: `30565d6c21340b61a2d80c987c9acf9ad2765006762ae3043fa0ba862fa0f655`.

## tr2-train-36-r1

Raw: 微笑着示范挥手，两者同时开始，右臂侧抬、张开手掌再放回。

Status: **uncertain**. Scores: {"semantic":0.5}.

完整观察50帧及原分辨率15帧。笑眼与侧抬张掌从开头同时进入，500ms附近手臂抬至最大、手掌展开，1000ms手臂放回，1400ms笑容退去，画面完整。可见表演符合微笑加侧抬张掌，但手臂是画面右侧，正面角色通常对应自身左臂，raw所述右臂没有明确镜像/屏幕约定支撑。故不确定且不提供naturalness。

Feedback: 微笑与手臂的时间关系可确认，但必须先解决raw右臂的坐标含义再制作新的可接受正例。

Coverage: 50 frames; 2 pages; original-resolution frames 15. Native duration 1400 ms; final player time 1633.333 ms.

Evidence SHA256: `0fd5dcfb0df57b91e7dc6073fc855ad2dae808dd7b7d1bb91b1113e4b9bb10c3`. Video SHA256: `0b6d350783940f20d15dbfa6c328733269c6235e6651bb7adf9500ca4b7757a6`.

