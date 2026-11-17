# v0.2 数据、训练与评估入口

`retrain_and_eval.py` 现在有四个明确阶段：prepare → validate → train → evaluate。prepare、validate、evaluate 都不会自动启动训练；训练不会覆盖 latest/v02_latest、自动标记 ready 或切换在线服务。

当前历史 3232 条快照以及共享 `llm_v02_corpus.jsonl` **没有因为本次修复就成为有效冻结训练包**。历史无视频数据只能作为单独标识的 `historical_synthetic`，不能补写“视频审核通过”。本次没有运行新训练。

数据入口要求真实记录：

- 每行明确 raw_text、input_role（instruction/dialogue）、config、candidate/parent、group_id、semantic_family_id、split。
- 教师生成与 AI 审核使用独立 context；审核绑定原句、配置、人设、rubric、编译器和资源 hash。AI 通过足够，不需要人工 keep。
- 执行类 AI 样本需要完整回放及真实视频/帧序列观察证据；非执行类使用语义审核，不需要空视频。
- 历史冷启动数据绑定原始文件及行、实际标签政策审核；执行标签绑定成功的编译记录。不会冒充 AI 视频数据。
- 语义族和原始验证/测试归属在导出前固定，测试来源不能回流训练。数据/证据内容变更会使冻结校验失败。

记录格式与来源规则见同目录 `review_evidence.py` 的模块说明和 `--help`。下面是路径占位的命令模板，只有提供真实证据后才能执行成功。

```powershell
# 冻结已完成审核的记录，不训练。
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/retrain_and_eval.py prepare --records <records.jsonl> --out-dir <new-snapshot-dir> --persona-file Docs/ActionLanguage/personas/gemini-cyber-cat.md --review-rubric-version <actual-rubric-version>

# 复核完整冻结包，以及模型的标签/长度兼容性；不训练。
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/retrain_and_eval.py validate --snapshot-manifest <snapshot-dir/manifest.json>
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/train_action_config.py --snapshot-manifest <snapshot-dir/manifest.json> --validate-only

# 后续明确开始训练时使用不存在的新目录。
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/retrain_and_eval.py train --snapshot-manifest <snapshot-dir/manifest.json> --out-dir <new-checkpoint-dir> --epochs 20 --batch-size 32 --threads 2

# 在相同固定测试切分上评估，报告必须是新文件且位于checkpoint之外。
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/retrain_and_eval.py evaluate --checkpoint-dir <checkpoint-dir> --snapshot-manifest <snapshot-dir/manifest.json> --split test --report <new-report.json>
```

`evaluate --dataset <jsonl>` 仅用于单独诊断，不能赋予训练准入。行带 split 时按 `--split val|test` 过滤；部分行缺 split 会被拒绝。全部不带 split 时报告明确标为 unspecified_diagnostic_input，不能称为独立测试集。

新模型 manifest 记录 `input_policy=action-input-role.v1`。instruction 编码为 `动作指令：<原文>`，dialogue 为 `角色台词表演：<原文>`；旧模型继续使用其原始输入策略。训练损失仍是 MiniRBT 监督学习；选模评估实际预测资源和真实 guard 结果，测试集不参与选模。缺类、技术失败和误执行会保留，不能以格式通过或 loss 下降宣称视觉表现改善。

回归命令：

```powershell
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/test_training_workflow.py
```

测试夹具不是真实审核数据，标记 test_fixture 的包只能验证，不能启动训练。旧 v0.1 权重仍在原处；旧训练脚本不属于此 v0.2 工作流，不要用旧模型评测或 ready 门槛代替本流程。
