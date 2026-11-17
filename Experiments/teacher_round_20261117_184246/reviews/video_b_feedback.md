# Independent visual reviewer B

Context: `/root/visual_review_b`; provider OpenAI / Codex desktop; exact backend model ID unavailable. Independently read the persona, raw instruction/input role/config, resource contract and review contract. Observed every listed contact-sheet page, read every actual focused trajectory entry, and opened the additional full-size frames recorded in each review. No teacher conversation, candidate/source edits or fixture tags were used.

Coverage: 12 complete recorded clips, 27 contact-sheet pages, 763 video/trajectory frames. Six accepted; train15/16/20/22 uncertain on literal wave/bow semantics; train19 and train24 rejected for visible image-left fingertip clipping. All uncertain/clipped clips have no naturalness score. Other resources remain candidates; this is sample review, not formal resource calibration.

Before serialization, a cross-review consistency question prompted a literal semantic recheck of the already observed wave/bow clips. Final judgments below are based on this reviewer's actual images: repetitive straight-arm raises indicate a greeting but do not unequivocally establish a wave, and head dips with nearly upright torso do not unequivocally establish a bow. No prior verdict JSONL had been written or overwritten.

## tr1-train-13 — accepted

刚睡醒确认消息：先眨眼一次，再点头一次。

眨眼与点头顺序清楚。全部50帧显示双眼逐渐闭合，frame9/300ms完全闭眼，600ms恢复睁眼；头和上身此前保持正位，随后下沉，在frame30/1000ms达到头俯仰-18、身体-4.5，再回正。两段分别600ms、800ms且无停留，1400ms回到参考值，释放后1633.3ms Completed。画面中的闭眼、随后轻点头和恢复均清楚，没有突跳、额外次数或裁切。

Scores: {"semantic": 1, "naturalness": 0.88}

## tr1-train-14 — accepted

表现和好的情绪转折：先露出生气的表情，再微笑。

92帧先出现压眉、锯齿露齿嘴的生气神态，后转为闭眼月牙笑；额外查看0、20、60帧原图确认细小面部变化。生气从0到1400ms，frame13..29/433.3..966.7ms保持PARAM_Angry_eye=1、FXmouth1=1、眉Y=-.882、眉X=-.588；1400ms恢复普通嘴后才开始笑。frame54..72/1800..2400ms笑眼=1、双眼开度=0、嘴形=.931、嘴开=.49，2800ms回正，3033.3ms完成。实际顺序、持续时间和两段hold与配置一致，情绪转折可辨，无冲突或残留。

Scores: {"semantic": 1, "naturalness": 0.86}

## tr1-train-15 — uncertain

先左右张望寻找朋友，找到后再挥手。

全部74帧和全轨迹已观察。头与眼先左右张望，333.3ms约-13.946/-.7969、666.7ms约13.973/.79845，1300ms回中且无hold；然后右臂1333.3ms起向侧面抬起，1733.3/1766.7ms达到采样峰8.3663、手形.94121，2200ms放下，2433.3ms完成。原图52确认手掌与指尖完整，但可见手臂基本伸直，是一次侧抬、再落下；没有明确的手掌或前臂来回挥动。张望与先后顺序匹配，然而本条明确要求找到朋友后挥手，现有画面也可被看作侧伸手示意，无法无歧义确认挥手语义，故uncertain，语义不计满分且不评分自然度。

Scores: {"semantic": 0.7}

Correction advice: Do not relabel a side arm raise or shallow head dip as a confirmed wave or bow merely because compilation succeeds. Preserve the literal instruction and verify that any valid resource adjustment makes that gesture visually clear; otherwise retain uncertainty/exclusion.

## tr1-train-16 — uncertain

道歉时先鞠躬，再露出害羞的神态。

全部98帧和全轨迹已观察。前半段500..1000ms头Y=-22、身体Y=-9.35并保持，1500ms回正；随后害羞侧倾，1966.7..2533.3ms头Z=-19.8、眼X=.88/Y=-.495、眉Y=-.44、FXmouth2=1，3000ms回位，3233.3ms完成。原图20的头确实低下，但躯干仍接近直立，缺少清楚的腰部前屈，视觉上更接近浅点头；原图65可确认后段侧倾嘟嘴神态。参数名bow及身体Y变化不能替代可见鞠躬证据，本条道歉时先鞠躬的字面要求不能确认已完整实现，故uncertain，语义不计满分且不评分自然度。

Scores: {"semantic": 0.65}

Correction advice: Do not relabel a side arm raise or shallow head dip as a confirmed wave or bow merely because compilation succeeds. Preserve the literal instruction and verify that any valid resource adjustment makes that gesture visually clear; otherwise retain uncertainty/exclusion.

## tr1-train-17 — accepted

先惊讶，随后摇头，表现难以置信。

71帧中先出现夸张瞪眼和张口惊讶，再单次左右摇头。原图15确认白色震惊眼效果和张开的替换嘴是清楚的惊讶表情。300..766.7ms FXeye/FXmouth3=1、眉Y=.88；1200ms普通嘴恢复，随后头X由负向峰约-17.856(1433.3ms)转为正峰约17.928(1666.7ms)，2100ms回中，2333.3ms完成。惊讶1200ms、摇头900ms，零摇头hold及先后顺序均匹配；表情转回后才摇头，无通道串扰。

Scores: {"semantic": 1, "naturalness": 0.86}

## tr1-train-18 — accepted

看不懂这张图：先歪头，再眨眼。

59帧清楚显示一次同侧歪头，回正以后才眨眼。400..800ms头Z=22、身体Z=5.5保持，1200ms两者回零；眼睛此前保持睁开，之后闭合，在1433.3/1466.7ms采样开度约.012741，图中眼睑已闭合，1700ms完全重开，1933.3ms完成。半周期峰值1450ms位于两采样帧之间，不虚称采样值为0。倾斜、保持、回正与眨眼时序完整，细节可辨，无跳变或裁切。

Scores: {"semantic": 1, "naturalness": 0.9}

## tr1-train-19 — rejected

获得奖励时，微笑和举手欢呼同时开始。

已逐页观察全部53帧并读全轨迹，确认微笑与双臂同时启动：33.3ms两者均离开参考值；433.3ms笑眼达到1、双眼闭合，466.7..1033.3ms双臂为9.35、竖向参数.935；1500ms恢复，1733.3ms完成。语义上的同时微笑与抬臂庆祝可辨，时间与hold匹配。但双臂展开时图像左侧手指被视频边缘截断，原图frame20/666.7ms明确可见手指延伸到x=0且尖端缺失；接触表plateau连续多帧重复此裁切。该缺陷不能由成功编译或正确参数覆盖。拒绝，按要求不给裁切片自然度分。

Scores: {"semantic": 1}

Correction advice: Re-record with wider framing or a verified smaller cheer amplitude within the existing valid resource range; preserve the simultaneous facial action and required celebration. A new clip must undergo independent complete observation again.

## tr1-train-20 — uncertain

迎接朋友时，一边微笑，一边挥手。

全部52帧和全轨迹已观察。微笑与手臂同时启动，笑眼433.3..1066.7ms保持1；右臂两次抬起又落下，366.7ms与1133.3ms采样峰均7.9883、手形.89869，约750ms回低位，1500ms整体回位，1700ms完成。原图11确认手掌完整；笑脸与重复抬臂使招呼意图比单次抬臂更容易读出，但画面仍主要是伸直的手臂侧抬和放下，缺少明确的手掌/前臂往复挥动，也可读作反复伸臂。并行与两周期配置正确，却不能仅据此保证原文挥手的完整视觉语义；保留uncertain，不给自然度分。

Scores: {"semantic": 0.8}

Correction advice: Do not relabel a side arm raise or shallow head dip as a confirmed wave or bow merely because compilation succeeds. Preserve the literal instruction and verify that any valid resource adjustment makes that gesture visually clear; otherwise retain uncertainty/exclusion.

## tr1-train-21 — accepted

嘴硬地否认：生气的表情和摇头同时做。

52帧显示生气嘴和压眉伴随两周期左右摇头。两组通道在33.3ms均开始变化；第一轮头X负峰约-19.332/200ms、正峰19.571/366.7ms；第二轮负峰-19.764/933.3ms、正峰19.771/1133.3ms。433.3..1066.7ms怒眼和锯齿嘴保持1、眉Y=-.882；原图25确认生气嘴、眉和偏头同框。1500ms回中与普通嘴，1700ms完成。双周期750ms、无摇头hold、表情1500ms均符合配置，没有扭曲或明显不自然跳跃。

Scores: {"semantic": 1, "naturalness": 0.83}

## tr1-train-22 — uncertain

表现困倦，缓慢鞠躬的同时闭眼再睁开。

全部58帧和全轨迹已观察。双眼与头部同时缓慢下沉，500..1200ms头Y=-20、身体Y=-8.5、双眼开度0，1700ms参考值恢复、1900ms完成。1700ms与.45hold、闭眼再睁开及同步关系均匹配；可见长时间闭眼和低头确实传达困倦。然而身躯在画面中仍大体直立，前俯主要可见于头部，不能明确辨为原文额外要求的鞠躬。情绪匹配不足以补足字面动作约束，故uncertain且不给自然度分。

Scores: {"semantic": 0.8}

Correction advice: Do not relabel a side arm raise or shallow head dip as a confirmed wave or bow merely because compilation succeeds. Preserve the literal instruction and verify that any valid resource adjustment makes that gesture visually clear; otherwise retain uncertainty/exclusion.

## tr1-train-23 — accepted

不好意思地答应，害羞的同时点头。

55帧中侧倾、嘟嘴和回避目光与轻点头同步形成。500ms头Y=-14.4、身体Y=-3.6，同时头Z=-18、眼X=.8/Y=-.45、FXmouth2=1；1000ms俯仰已回零而害羞侧倾继续保持至1100ms，1600ms表情和侧倾恢复，1800ms完成。原图15与30分别确认点头低位和点头回正但仍害羞的不同姿态。点头1000ms无hold、害羞1600ms/.4hold及较轻.8点头幅度均与配置一致，重叠明确，未见额外次数、裁切或通道冲突。

Scores: {"semantic": 1, "naturalness": 0.81}

## tr1-train-24 — rejected

看到惊喜礼物时，同时露出惊讶的表情并举手欢呼。

已逐页观察全部49帧和全轨迹。惊讶眼、张嘴与双臂抬起都从33.3ms运动帧开始；366.7ms惊讶FX=1，433.3..966.7ms双臂8.925、竖向.8925，惊讶在约896ms后先渐退而双臂保持到约980ms，两资源均1400ms回参考值、1600ms完成，符合各自phase比例。原图20/666.7ms清楚显示惊讶与展开双臂同框，同时图像左侧手指越过x=0边界、尖端被切掉；多帧保持段均有同样问题。动作语义与并行关系可辨，但裁切使这条录像不合格；拒绝且不给自然度分。

Scores: {"semantic": 1}

Correction advice: Re-record with wider framing or a verified smaller cheer amplitude within the existing valid resource range; preserve the simultaneous facial action and required celebration. A new clip must undergo independent complete observation again.

Mechanical validation: current source/persona hashes matched all 12 physical integrity reports; all manifest-bound artifacts still matched SHA256, candidate text/config matched the captures, focus parameters matched full trajectory values frame by frame, finished batch and completed playback/encoder were confirmed. These checks were used only for evidence integrity; visual verdicts above were made from the observed images and trajectories.
