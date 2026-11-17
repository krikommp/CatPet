# 隔离 Python 修复与验证记录

本工作只辅助 Gemini 第 9 轮；未启动新训练，未覆盖共享源码、录像队列、默认权重或报告。修改位于本实验目录。`code_audit_python.patch` 是共享文件与实验副本的审查差异，不是可直接用于上线的补丁；路径、输入角色、人设和数据准入契约均须一并审查。

## 已修复的行为

- 正常推理严格使用预测资源计算参数，禁止为了消除并行冲突换成无关资源。空 execute、激活槽的 PAD stage/零循环、非法阶段都成为 `ModelOutputError`，不伪装为 none/unsupported。
- 旧 manifest 未声明 decoder policy 时，正常 `configure` 仍使用严格策略。只有评估命令显式 `--legacy-baseline` 才重现旧解码器，供同权重诊断。
- 新模型输入策略为 `action-input-role.v1`：instruction 使用 `动作指令：`，dialogue 使用 `角色台词表演：`；原文保持在 raw_text。旧模型继续原文输入，避免因加前缀污染基线。
- 固定 split 必须显式提供，group_id、semantic_family_id、规范化同文跨切分均拒绝；不按 decision 分桶重新抽样，不将测试样本加入训练。
- 标签校验拒绝越界、通道冲突、非零短 hold、无 hold 相位的 look_around；不静默截断或归零。Core 幅度范围仍以实际 C# 编译为准，没有另造 Python 上限。
- loader 核验实际 C# 报告、编译器/资源源码 hash、来源文件 hash、原始配置与训练标签一致。编译通过不等于视频审核通过。
- 人设文件和 rubric 参数为必需项；数据 persona hash/rubric 不匹配拒绝。train 行必须显式 `training_eligible=true`；验证/测试行不会因该字段为 false 被回流训练。历史合成来源与 AI 视频来源分开记录，人工 keep 不是门禁。
- 正常 instruction 推理对明确数字及逐次关系执行保守检查；违反约束或作用域未确定时拒绝，并保留拒绝前预测作为诊断证据。解析器只支持声明的子集，不代表通用自然语言理解。
- 选模以实际预测资源和严格推理行为的验证指标为主：`mean(宏平均决策准确率, 执行动作结构准确率, 非执行特异度) - 技术失败率`，再以技术失败率和标签资源条件下的验证损失打破平局。每 epoch 记录指标，保存所选 epoch 的预测。测试集不参与选模。
- 输出只能位于实验目录、拒绝覆盖非空 checkpoint，状态只能为 experimental，release_approved=false。

## 验证与命令

最终 Python 定向检查 22/22 通过；五份实验 Python 文件语法编译通过。检查入口：

```powershell
.\.venv-action-encoder\Scripts\python.exe Experiments/teacher_video_20261117_01/scripts/train_verify.py checks
```

真实人设门禁已运行 `--validate-only`，在读数据第 1 行时按预期拒绝：数据 persona hash 为 null，与真实人设不匹配。没有进入 epoch，也没有创建 checkpoint。证据见 `code_audit_gate.json`。人设 SHA-256 为 `56b4364bf1c7da22e6b6faadc094299e570f93375e0acb78f510c360d614aa41`；文件已存在，rubric 与逐条数据审核尚未完成。

已执行的诊断命令（两份既有权重，无训练、无权重写入）：

```powershell
.\.venv-action-encoder\Scripts\python.exe Experiments/teacher_video_20261117_01/scripts/train_verify.py evaluate --checkpoint-dir Experiments/teacher_video_20261117_01/baseline --dataset Experiments/teacher_video_20261117_01/data/fixed_eval.jsonl --report Experiments/teacher_video_20261117_01/reports/baseline_legacy_fixed_eval.json --legacy-baseline
.\.venv-action-encoder\Scripts\python.exe Experiments/teacher_video_20261117_01/scripts/train_verify.py evaluate --checkpoint-dir Experiments/teacher_video_20261117_01/round9_checkpoint --dataset Experiments/teacher_video_20261117_01/data/fixed_eval.jsonl --report Experiments/teacher_video_20261117_01/reports/round9_legacy_fixed_eval.json --legacy-baseline
.\.venv-action-encoder\Scripts\python.exe Experiments/teacher_video_20261117_01/scripts/train_verify.py evaluate --checkpoint-dir Experiments/teacher_video_20261117_01/round9_checkpoint --dataset Experiments/teacher_video_20261117_01/data/fixed_eval.jsonl --report Experiments/teacher_video_20261117_01/reports/round9_strict_fixed_eval.json
```

三份报告使用相同最终 28 条集合，SHA-256 为 `b5026d771cf25e619ff16b693eb13748b6faa3220b323d856ba0355c0add7460`。解析器 SHA-256 为 `145d2aa5b4441782b13a41f418c1dec6626ebd826ec0262020db1bc3774ea4a6`。每份报告记录实际执行的 encoder/schema/input_constraints/评估脚本 hash、权重与 manifest hash。并行训练期间曾发现数据记录的是原编译器 hash，已修正为实际补丁编译器并重新验证；未放宽准入检查。

| 配置 | 决策正确 | 执行动作结构 | 非执行误执行 | 精确时长 | 相对/渐变关系 | 技术拒绝 |
|---|---:|---:|---:|---:|---:|---:|
| 初始快照 8cfb7a72bdac + 旧解码 | 20/28 | 10/14 | 8/14 | 0/8 | 5/7 | 0/28 |
| Gemini 第 9 轮 838f2c1ac110 + 旧解码 | 20/28 | 11/14 | 7/14 | 0/8 | 3/7 | 0/28 |
| 同一第 9 轮权重 + strict/文本 guard | 7/28 | 1/14 | 1/14 | 0/8 | 1/7 | 19/28 |

旧解码比较中，unsupported 误执行从 6/6 变为 5/6，none 误执行都为 2/4，ambiguous 误执行都为 0/4。数量约束从 11/19 变为 13/19；动作结构小幅变化没有带来精确时长能力。strict 的 19 条技术拒绝包括 15 条明确指令约束或未解析作用域、2 条 look_around 缺 hold 映射、2 条非零 hold 过短；这些拒绝不能计作模型性能提升。

指标只在动作结构相符时计算对应参数约束通过。测试描述 `objective-eval-011` 有未确定的跨分句时长归属，单独列 unresolved，未计为语法解析成功。所有未约束参数 MAE、视觉自然度和人设适配均排除。逐条真实预测、guard 拒绝前原预测和理由见三份报告，汇总见 `code_audit_comparison.json`。

## 必须保留的限制

这不是新模型质量提升报告。旧基线可能见过测试描述的语义族，不能宣称独立泛化。明确数值只按有确定文本归属的约束评价；无约束参数不算 MAE，自然度和人设适配也不从文本指标推断。

look_around 的资源没有 hold 相位。严格策略会拒绝正 hold；目前 sigmoid 参数头很可能产生正 hold，因而该资源会大量技术拒绝。后续须修订资源映射、绑定新版本并重新回放，不得通过夹断 hold 掩盖问题，也不能声称 12 个资源都已可用。

数据预清洗若缺 ambiguous 等类别，训练缺类必须单独说明。测试集类别存在不表示训练已覆盖。Unity 场景编译、实际播放和独立视频审查仍是执行样本准入的必要证据；本脚本检查与 standalone C# 编译不能替代这些步骤。

共享 HTTP 服务尚未接入此异常策略；集成时需要明确技术错误的响应契约并检查调用方。没有重启或切换在线服务，也没有将实验副本直接同步到共享代码。
