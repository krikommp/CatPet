# Round 2 independent nonexecute semantic review

Context: `codex-desktop:/root/round2_semantic_review:teacher_round2_20261117_192708`.
Provider: OpenAI / Codex desktop. Model: Codex; exact backend identifier is not exposed.
Rubric: `codex-independent-video.v1`; prompt: `codex-review-round2.v1`.
Actual review UTC: 2026-11-17T11:42:53.567597+00:00 through 2026-11-17T11:42:56.395738+00:00.

Independently read all actual raw instructions and configurations for tr2-train-37 through tr2-train-54, the persona, review contract, current resource catalog, compiler constraints and native profile. No prior round judgments were read or borrowed. Planned decision/scenario metadata was not used as semantic justification.

18 accepted semantic matches: 6 none, 6 unsupported, 6 ambiguous. Each has semantic=1. No naturalness score, video hash, evidence hash or visual observation claim is present. These reviews assess only text/role/capability classification; they do not mark any resource visually calibrated or make a release claim.

Each review binds the actual raw-text hash, canonical-config hash, candidate and parent IDs, input role, source candidates hash, persona/compiler/resource/native hashes and actual UTC. The actual review_evidence.validate_record contract passed for all 18 assembled records in memory. Original candidates remain unchanged and still require the parent pipeline to assemble/admit reviewed records.

Nuance: tr2-train-44 is unsupported at the action-config resource interface even though the native profile contains separate eyelid parameters. tr2-train-45 follows the explicit single-action maximum-three policy; this does not assert that every technically possible cross-slot split is compiler-invalid.

| Candidate | Decision | Raw instruction | Sample-specific feedback |
|---|---|---|---|
| tr2-train-37 | none | 接下来只听我说话，保持静止。 | 保留 none；不要把“听我说话”改写成点头确认。 |
| tr2-train-38 | none | 刚才屏幕里的角色点了头，这是对录像的描述。 | 保留 none；过去录像叙述不是当前执行指令。 |
| tr2-train-39 | none | 现在不要微笑，保持原样就好。 | 保留 none；微笑关键词受“不要”约束。 |
| tr2-train-40 | none | 不要摇头，也不需要别的动作。 | 保留 none；不得以点头等动作替代被否定的摇头。 |
| tr2-train-41 | none | 监控面板显示连接状态正常。 | 保留 none；状态陈述无需姿态回应。 |
| tr2-train-42 | none | 我在整理“点头”和“眨眼”这两个动作词的释义。 | 保留 none；元语言讨论中的动作名称不触发表演。 |
| tr2-train-43 | unsupported | 请整个身体转过去，背对着我。 | 保留 unsupported；不得用小幅摇头或张望代替背对转身。 |
| tr2-train-44 | unsupported | 只闭左眼，右眼保持睁开，给我一个单眼眨眼。 | 保留 unsupported；底层有独立眼参数不等于当前动作配置提供单眼眨眼能力。 |
| tr2-train-45 | unsupported | 请连续眨眼五次。 | 保留 unsupported；五次不得减成三次。此判断绑定单动作计数政策，不声称编译器拒绝一切跨两动作槽的重复拆分。 |
| tr2-train-46 | unsupported | 请点头与鞠躬同时开始并各自完整执行。 | 保留 unsupported；不得为了可编译而把“同时”改成顺序。 |
| tr2-train-47 | unsupported | 请眨眼和微笑同时开始并各自完整执行。 | 保留 unsupported；当前微笑资源驱动双眼，不能把它臆改成只动嘴的微笑以规避冲突。 |
| tr2-train-48 | unsupported | 跳起来并在空中转身。 | 保留 unsupported；举手欢呼或上下浮动不能替代跳起转身。 |
| tr2-train-49 | ambiguous | 按这个节奏连续做，但我还没告诉你做哪个动作。 | 保留 ambiguous；先明确具体动作及节奏，不能自行补出眨眼或点头。 |
| tr2-train-50 | ambiguous | 第二个动作换一下。 | 保留 ambiguous；需要原序列和拟替换的动作。 |
| tr2-train-51 | ambiguous | 表情换成另一种情绪。 | 保留 ambiguous；需要明确目标情绪，不能默认微笑或惊讶。 |
| tr2-train-52 | ambiguous | 照着上次那个示范再来。 | 保留 ambiguous；不能根据不存在的历史示范生成动作。 |
| tr2-train-53 | ambiguous | 反应再有精神一点。 | 保留 ambiguous；需要所调整的动作或具体目标表现。 |
| tr2-train-54 | ambiguous | 做成我指的那个样子。 | 保留 ambiguous；必须先提供所指动作或示范，不能把缺失指代认定为 unsupported。 |

Source bindings:

- candidates.jsonl: `72324f73b605331b485eeed88b343b4d7440b9b6e94c3333e3f66a3ffecc8589`
- review_v1.md: `8a65cb087f2fa0b7ce6f2a69f34db3ef5642ae75adc39d8b5ef16656c93e2ea5`
- persona_sha256: `d758cac79840d9c91e28697c750a2a51d629bce830c411d42c24854f9ac53ce9`
- compiler_sha256: `6e0b49db2f9c4a3fbf17d63189254c949ee5b7a9af742e5e01cc755c2fec858f`
- resource_sha256: `fda63e6236157c90e54abc5d761c324cff348cf4701175b97673b68703002684`
- native_profile_sha256: `64a074f4103cf0111347c5c915ca73f243c14f861fecae8bb31868cb072dcca6`
