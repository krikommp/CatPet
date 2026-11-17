# 动作模型：数据冻结、训练、评估与回放

更新：2026-11-17。主线仍是教师生成描述和配置 → Unity 回放 → 独立教师审核 → 冻结样本 → MiniRBT 监督训练。AI 审核不依赖人工 keep；用户验收是可选抽查。教师 API 和自动轮次调度尚未实现，以下确定性入口已接入共享代码。

## 本次修复后的边界

- 每条新样本明确 `input_role=instruction|dialogue`。动作指令检查明确次数、时长和相对关系；角色台词按人设表现。旧 API 省略角色兼容为 instruction，但新数据不得缺角色。新权重使用 `action-input-role.v1` 前缀，旧权重仍使用原始文本。
- 预测冲突、无效执行结构和数值约束失败报告技术错误；HTTP `/configure` 返回 422 `model_output_invalid`，非法请求返回 400。解码器不再换成无关资源或把空执行改成 none。
- 编译器不再吞掉过短的正 hold。hold 段不足 80ms 或资源缺 hold 端点直接拒绝；`look_around.basic` 当前只支持 `hold_ratio=0`。
- EditMode 录制采用 30fps 固定播放器步长和 720×840 完整角色取景，覆盖动作、释放回位和最终完成帧；取消、替换或播放故障不会记为自然完成。`evidence.json` 绑定配置、native、源码、程序集、角色资产、人设及视频哈希；`trajectory.jsonl` 记录每帧播放器时间及实际 Cubism 参数。仅有 MP4 文件不代表成功。
- 历史回放产生新候选并保留 `parent_candidate_id`。批量录制输出新的 run 目录，禁止覆盖旧视频。现有旧视频不能补写成当时已具备这些证据。

## 数据来源与冻结

`Tools/ActionEncoder/review_evidence.py` 是证据验证与快照导出入口，其文件头定义输入契约。数据来源分为：

| source_type | 必需证据 |
| --- | --- |
| historical_synthetic | 原始文件/行号/哈希、人设标签规则核对；execute 还需当前配置的真实编译证据。不能宣称视频审核通过 |
| ai_video_reviewed | 独立生成/评审上下文与模型、提示/rubric 版本、accepted、语义及自然度评价、完整录像和轨迹、配置及所有版本绑定 |
| ai_semantic_reviewed | 非执行样本的独立语义/能力审核，不要求空视频 |

先分配 `group_id`、`semantic_family_id`、固定 `split`，再扩写。同文、同组、语义族和父候选派生不得跨切分；测试来源不得回流 train。训练行必须明确 `training_eligible=true`。导出会完整解码视频、复制证据到新快照并绑定哈希；训练前后重新核验。测试夹具禁止真实训练。

原有 `Dataset/ActionCards/llm_v02_corpus.jsonl` 保留为历史待审语料。本次没有将其自动清洗后批准，也没有生成真实 AI accepted 数据。需要实际补齐规则核对/编译证据或重播独立审核，然后才能冻结为新训练输入。

## 分阶段命令

在项目根目录 PowerShell 执行。尖括号是待提供的实际路径/版本，不代表文件已存在。各阶段不会自动衔接下一阶段。

```powershell
# 校验真实记录并冻结；无人工 keep 前置要求。
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/retrain_and_eval.py prepare --records <审核记录.jsonl> --out-dir <新的数据快照目录> --persona-file Docs/ActionLanguage/personas/gemini-cyber-cat.md --review-rubric-version <实际rubric版本>

# 只验证，不加载模型训练。
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/retrain_and_eval.py validate --snapshot-manifest <数据快照目录/manifest.json>
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/train_action_config.py --snapshot-manifest <数据快照目录/manifest.json> --validate-only

# 明确启动训练；输出必须是尚不存在的新目录。
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/retrain_and_eval.py train --snapshot-manifest <数据快照目录/manifest.json> --out-dir <新的checkpoint目录> --epochs 20 --batch-size 32 --threads 2

# 独立评估，报告不会把版本晋级 ready。
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/retrain_and_eval.py evaluate --checkpoint-dir <checkpoint目录> --snapshot-manifest <数据快照目录/manifest.json> --split test --report <新的报告.json>
```

训练器不再接受未冻结的 `--dataset`，也不再随机重新分组切分。MiniRBT 训练损失仍使用标签资源条件；选模根据真实预测资源下的配置、技术错误和误执行指标，保留每轮验证预测。测试集不参与选模。输出始终 experimental，禁止覆盖 latest/v02_latest 或已有目录，不自动上线。

`evaluate --dataset <JSONL>` 可用于带显式 input_role 的诊断，必须单独标记非训练准入；不能证明与旧权重独立。`model_test.py` 保留旧权重诊断兼容入口，旧 test_split 不视为已证明独立的验收集。数值守卫拒绝错误预测是执行安全性修复，不是模型准确率提升。

## Unity 回放与验收

1. 按原方式启动 `Tools/ActionEncoder/start.ps1`；共享 Python 修改在新启动的进程中生效。
2. 打开 Tools > PetLive2d > 动作模型 > 用户验收，选择“动作指令”或“角色台词表演”。
3. 用本地模型或手工 v0.2 配置生成候选，在 EditMode 完整播放录制。
4. 查看语义和视觉结果；人工通过/未通过/跳过作为可选补充。AI 审核另走上述证据导出入口。

窗口视频位于 `Dataset/ActionCards/snapshots/<新candidate_id>/`；批录位于 `Dataset/ActionCards/runs/<新run_id>/`。队列每行应有 candidate_id、raw_text、input_role、decision、plan_json，派生候选还应有 parent_candidate_id。完整录制失败不准进入视频审核通过池。

Unity 的“模型测试（编译检查）”验证编译规则；“验证训练回放流程”检查单动作/串行/并行真实录制、非执行、短 hold 拒绝和不可覆盖，输出独立实验目录。二者都不等于模型语义或视觉质量通过。

## 第 9 轮与后续启用

本次排查使用第 9 轮 checkpoint `838f2c1ac110` 的冻结副本。权重、原语料及原常驻服务均未替换；没有启动第 10 轮。28 条诊断的严格路径仍有大量技术拒绝，因此不能称第 9 轮已经可用。当前只有 blink 资源正式标定，其他资源仍是候选，编译通过不等于自然度审核通过。

新模型必须用冻结测试集比较误执行、结构、精确数字、逐次关系及独立视频表现，再明确选择启用。教师 API 和自动生成→审核→有限修正的轮次调度是剩余接入工作；现有修复提供可核验的录制、准入、训练及评估接口，不会伪造教师调用或审核结果。
