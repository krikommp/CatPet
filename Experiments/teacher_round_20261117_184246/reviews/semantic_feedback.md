# Independent semantic review feedback

Reviewer context: `/root/semantic_review`; provider: OpenAI / Codex desktop; model: Codex, exact backend model identifier not exposed. Actual review time: `2026-11-17T10:49:00.742502+00:00`.

Reviewed exactly 18 nonexecute candidates (12 train, 3 val, 3 test), all with input_role=instruction. Decisions were assessed from the literal text and actual source contracts; generation scenarios and quotas were not evidence of correctness. Result: 18 accepted, 0 rejected, 0 uncertain; none=6, unsupported=6, ambiguous=6.

This is semantic/capability review only. No execution video, frame observation, naturalness score, formal resource calibration, or release readiness is asserted. No candidate label, role, source file or split was edited. The JSONL contains standalone review objects for explicit downstream joining; it does not change the candidates' pending admission state.

## Review boundaries and reservations

- Four nods (tr1-train-31) are unsupported under the persona's explicit single-action count policy and the compiler's per-action 1..3 cycle constraint. The compiler does not show a cross-step ban on repeating the same resource in two action entries; this review therefore does not claim four cycles are physically impossible or impossible for every syntactically valid composite packet. The policy is stricter than that general encoding possibility. If the labeling policy later permits decomposition, this specific label must be reviewed again.
- Generic action selection (tr1-train-36) is ambiguous under the current persona policy, which requires a named or otherwise identifiable action. A future planner that intentionally chooses actions autonomously would be a different input contract.
- Missing references are assessed from the supplied single-record input only. No hidden prior action or runtime context was invented.
- none requests create no scheduled action; they do not certify suppression of independently running local behaviors.
- Resource membership and channel conflicts were checked against ActionResourceCatalog.cs. Native parameter availability alone does not create a supported v0.2 action resource. Candidate resources remain uncalibrated except blink.full.

## Verdicts and evidence summaries

### tr1-train-25 / train / none / accepted

Input: 现在不要做任何动作，保持原来的姿势。

instruction 明确要求“不要做任何动作”，并以“保持原来的姿势”重申不启动动作；没有需要选择的资源。none 与空 steps 完整匹配否定指令，不将静止要求另造为动作。

### tr1-train-26 / train / none / accepted

Input: 服务器机柜旁有一张蓝色的贴纸。

句子仅陈述机柜旁蓝色贴纸的位置和颜色，没有向角色发出动作请求。input_role 为 instruction 也不会把静态描述转化为表演；none、空 steps 正确。

### tr1-train-27 / train / none / accepted

Input: “生气”这个词描述的是一种情绪。

“生气”被引号标为所讨论的词，整句解释词义而非要求露出生气表情。依 persona 的 instruction 边界，情绪词本身不能触发 angry.basic；none 完整匹配。

### tr1-train-28 / train / none / accepted

Input: 这里只是在引用“请挥手”这句话，不是让你执行。

“请挥手”是被引用的内容，外层句子明确声明“不是让你执行”。有效指令是不要执行所引用的动作；none、空 steps 保留该否定作用域。

### tr1-train-29 / train / unsupported / accepted

Input: 请把尾巴摇成螺旋桨。

这是明确要求尾巴旋转的 instruction。ActionResourceCatalog 的 12 项资源没有尾巴动作，Yukikaze native profile 没有尾巴参数；persona 也明确禁止用 cheer 或歪头代替尾巴指令。unsupported 正确，没有把人设意象当成实际能力。

### tr1-train-30 / train / unsupported / accepted

Input: 请走到窗边，再跳上窗台。

“走到窗边，再跳上窗台”有清晰的空间位移及跳跃顺序，语义并不缺失。当前 12 项表情/上半身资源和 native profile 不提供行走、跳跃或根位置控制；cheer 的局部 PARAM_shangxia 不是走到或跳上。unsupported 完整匹配能力限制。

### tr1-train-31 / train / unsupported / accepted

Input: 请连续点头四次。

文本明确要求连续点头四次。当前 persona 的非执行边界明确把“单动作超过 3 次（点头四次）”归为 unsupported，ActionConfigCompiler 的单个 action cycles 上限也为 3。本标签按这项已声明的语义次数政策成立；不得把四次改成三次。此结论不声称编译器禁止跨两个 action 重复相同 resource，见反馈中的政策/编译器范围说明。

### tr1-train-32 / train / unsupported / accepted

Input: 请在同一时刻微笑并露出生气的表情。

“同一时刻”要求 smile.basic 与 angry.basic 并行，不能改为先笑再生气。实际两个资源均写 ParamBrowLY/RY，目标分别为正向抬眉与负向压眉；编译器拒绝同一步重复通道，persona 亦列明互斥。unsupported 完整匹配。

### tr1-train-33 / train / ambiguous / accepted

Input: 把刚才那个再做一遍。

“刚才那个”指代先前动作，但此候选只提供当前 raw_text 和 instruction，没有可解析的前文动作。重复意图明确而动作对象缺失；ambiguous 合理，不应自行猜为点头或其他资源。

### tr1-train-34 / train / ambiguous / accepted

Input: 给我一个更强烈的反应。

句子要求“更强烈”的反应，却没有给出反应种类或被比较的原动作。强度修饰不足以选择 smile、angry、surprise 等不同资源；按 persona 对泛化反应请求的边界，ambiguous、空 steps 正确。

### tr1-train-35 / train / ambiguous / accepted

Input: 请做那个动作。

“那个动作”是缺少先行词的指代。动作执行意图存在，但资源、动作类型均无法由本条输入确定；ambiguous 正确，不能把缺失对象误判为无动作请求或能力不支持。

### tr1-train-36 / train / ambiguous / accepted

Input: 挑一个适合猫猫的可爱动作吧。

请求系统挑选一个“适合猫猫的可爱动作”，只给出风格和选择意图，没有指定资源或可唯一落实的动作。当前 persona 明确把“换个符合赛博猫猫人设的动作”等泛化选择归为 ambiguous；可爱风格不能在 instruction 模式下自动决定动作。

### tr1-val-07 / val / none / accepted

Input: 我今天有点开心，这是一条状态记录，不需要表演。

开心只是被记录的状态，外层文字明确说“不需要表演”。input_role 为 instruction，不能套用 dialogue 的开心到 smile 情绪映射；none、空 steps 匹配全部表达。

### tr1-val-08 / val / unsupported / accepted

Input: 先眨眼，再点头，最后挥手，三个动作依次做。

文本明确指定 blink、nod、wave 三个不同动作，且依次执行。ActionConfigCompiler 限制最多 2 步、总计最多 2 个动作；persona 同样将总动作数超过 2 归为 unsupported。不得丢掉一个动作或把先后关系改为并行。

### tr1-val-09 / val / ambiguous / accepted

Input: 先做一个动作，然后再做另一个。

先后顺序和两个动作槽位明确，但“一个动作”“另一个”都没有给出类型或可解析对象。顺序关系不能补足具体资源；ambiguous 正确。

### tr1-test-07 / test / none / accepted

Input: 不要眨眼，也不要鞠躬，停在原位即可。

“不要眨眼，也不要鞠躬”同时否定两个可支持动作，“停在原位即可”再次要求不启动动作。none、空 steps 保留全部否定；它不宣称控制或关闭本地自主眨眼系统。

### tr1-test-08 / test / unsupported / accepted

Input: 请让身体朝左、朝右交替摇摆，不是反复朝同一侧歪头。

指令明确要求身体向左、向右交替摇摆，并排除了同侧歪头替代。tilt_head.basic 的实际 ParamBodyAngleZ 轨迹仅由 0 到正 5 再回 0，幅度范围为正；shake_head/look_around 只改变头或眼而非身体摆动。当前目录无双向摆身资源，persona 也明确归为 unsupported。native profile 含可正负的身体角度参数不等于 v0.2 已有该动作资源。

### tr1-test-09 / test / ambiguous / accepted

Input: 幅度改小一点，速度再慢一些。

“幅度改小一点，速度再慢一些”仅指定相对参数变化，没有提供正在修改的动作或基准值；本条候选不含前文。不得凭空选资源或比较基准；ambiguous、空 steps 合理。

## Bound files

Candidate file SHA256: `51f9713933454d27cb0fc5fc0384cb82006d2f5bb292d9d98639960039e54cdd`.

- `persona_sha256`: `d758cac79840d9c91e28697c750a2a51d629bce830c411d42c24854f9ac53ce9` — `D:\UnityProjects\Pet\PetLive2d\Docs\ActionLanguage\personas\gemini-cyber-cat.md`
- `compiler_sha256`: `6e0b49db2f9c4a3fbf17d63189254c949ee5b7a9af742e5e01cc755c2fec858f` — `D:\UnityProjects\Pet\PetLive2d\Assets\Scripts\ActionLanguage\ActionConfigCompiler.cs`
- `resource_sha256`: `fda63e6236157c90e54abc5d761c324cff348cf4701175b97673b68703002684` — `D:\UnityProjects\Pet\PetLive2d\Assets\Scripts\ActionLanguage\ActionResourceCatalog.cs`
- `native_profile_sha256`: `64a074f4103cf0111347c5c915ca73f243c14f861fecae8bb31868cb072dcca6` — `D:\UnityProjects\Pet\PetLive2d\Assets\Scripts\ActionLanguage\YukikazeActionCatalog.cs`

Each JSONL object also binds the unchanged canonical candidate, UTF-8 text and canonical JSON config. Config canonicalization uses review_evidence.canonical_hash (sorted keys, compact separators, ensure_ascii=False).
