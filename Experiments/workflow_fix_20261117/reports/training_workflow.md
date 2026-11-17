# 共享 v0.2 训练流程修复

修改前已逐文件对照 `before_manifest.json`，train_action_config.py 与 retrain_and_eval.py 均一致。当前实际修改共享代码，不再只有实验补丁。没有启动新的训练、重启服务或修改现有权重。

## 改动

- `training_data.py` 复用 `review_evidence.validate_frozen_snapshot` 核验实际数据、审核证据、视频/编译配置、资源、人设及 rubric 的绑定；AI 认可即可准入，不需要 human keep。历史合成、AI 视频、AI 非执行语义来源分别统计。
- 所有切分必须在冻结数据时明确指定。group_id、semantic_family_id、规范化同文全局一致，不再按 decision 分桶抽组。保留测试集，禁止 held-out 来源回流 train。训练行须显式 training_eligible=true；测试行 false 合法。
- 指令与台词分别采用 `动作指令：` / `角色台词表演：` 前缀，manifest 记录 action-input-role.v1。训练和推理共同使用 input_constraints，普通“一边/轻轻/打个招呼”等措辞不被泛化数字扫描误拒；明确次数不符仍拒绝。
- MiniRBT 监督学习方式不变。训练损失仍使用标签资源，选模使用真实预测资源下的配置/技术失败/误执行指标，测试集不参与选模。每 epoch 和所选验证预测均持久化，缺类明确记录。
- 新权重必须写显式、尚不存在的目录。拒绝 latest/v02_latest、已有空目录及已有报告覆盖；模型永远 experimental，release_approved=false。旧一键 v0.1 合并、3 倍人工样本、覆盖 latest、自动晋级 ready 及破坏式 rollback 路径已从该入口移除；旧模型文件未变。
- 冻结快照在开始和结束时复核；训练源码改变或数据/证据哈希变化时不保存最终权重。测试夹具只能 validate-only，不能启动真实训练。
- `retrain_and_eval.py` 现在明确分为 prepare、validate、train、evaluate；准备、验证和评估不会自动调用训练。

## 使用方式

先按 `review_evidence.py` 的记录契约提供真实 AI 审核或历史清洗证据，显式预分配 split。下列路径仅是命令参数示例，不表示已经生成或审核通过该数据。

```powershell
# 冻结真实审核记录；无人工 keep 前置要求，不自动训练。
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/retrain_and_eval.py prepare --records <审核记录.jsonl> --out-dir <新的数据快照目录> --persona-file Docs/ActionLanguage/personas/gemini-cyber-cat.md --review-rubric-version <实际rubric版本>

# 核查冻结证据；不启动训练。
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/retrain_and_eval.py validate --snapshot-manifest <数据快照目录/manifest.json>
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/train_action_config.py --snapshot-manifest <数据快照目录/manifest.json> --validate-only

# 后续明确启动训练时使用新目录；本轮没有执行此命令。
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/retrain_and_eval.py train --snapshot-manifest <数据快照目录/manifest.json> --out-dir <新的checkpoint目录> --epochs 20 --batch-size 32 --threads 2

# 固定测试切分单独评估，报告不写入checkpoint、不自动ready。
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/retrain_and_eval.py evaluate --checkpoint-dir <checkpoint目录> --snapshot-manifest <数据快照目录/manifest.json> --split test --report <新的诊断报告.json>
```

`evaluate --dataset` 也可读取显式带 input_role 的诊断数据，但会标为 diagnostic_only_not_training_admission，不把诊断数据变成训练准入或独立泛化证据。

## 验证

运行 `python Tools/ActionEncoder/test_training_workflow.py`：23/23 通过，见 `training_checks.json`。覆盖真实导出后篡改 dataset/persona/manifest 必须失败、语义族与同文泄漏、测试回流、不可覆盖权重/报告、缺少训练准入、角色前缀、惯用语与明确次数、预测参数条件资源、validate-only 不初始化模型训练、测试夹具不能训练。测试 AI 记录明确标记 TEST_FIXTURE_NOT_REAL_REVIEW，仅在自动清理的临时目录存在，没有计入真实采样池。

已用新 evaluate 入口实际加载冻结的 Gemini 第 9 轮 838f2c1ac110，对既有 28 条诊断数据完成一次真实预测，生成 `training_entrypoint_model_diagnostic.json`；无训练和权重写入。该次结果含 19 条技术拒绝，目的在验证入口与错误记录，不表示模型已合格。推理代理仍在修订边界时运行的诊断不能代替最终版本模型评价。

四份分配范围内 Python 文件语法检查通过。人工偏好未被证明，实际 Unity 回放与独立视觉评价仍是执行类 AI 数据准入的必要环节；训练器不会从 loss 下降或 JSON 通过推断视觉质量。

最终入口复核补充：raw evaluate 数据若含 split，严格筛选所选 val/test；部分缺失拒绝；完全无 split 明确标为非独立诊断输入。新回归已覆盖三种情况。命令简表另见 Tools/ActionEncoder/training_workflow.md。

最后补项：每个 epoch 保存 epoch_<n>_validation_predictions.jsonl，epoch_metrics.jsonl 绑定其文件名和 SHA-256；成功及技术失败预测均保留 input_role。对应回读及不可覆盖测试已通过，没有执行训练。推理代理独立只读复核三份训练入口及冻结验证链，未发现额外可执行绕过问题。
