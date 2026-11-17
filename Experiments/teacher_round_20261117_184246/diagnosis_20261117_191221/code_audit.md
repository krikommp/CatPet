# 首轮 teacher 检查点代码审计

审计对象：`checkpoint_epoch20`，checkpoint ID `17ab06dfb9a0`。仅诊断，未修改训练、推理、标签、固定评测或检查点。项目根目录为 `D:/UnityProjects/Pet/PetLive2d/`；下文省略路径的 Python 源码文件均位于 `Tools/ActionEncoder/`，`checkpoint_epoch20/` 位于 `Experiments/teacher_round_20261117_184246/`，其余诊断 JSON 文件位于本报告同目录。行号均为一基行号。

结论：保存的是仅更新 6 次、已经在训练集上退化为常量输出的检查点；这不是单纯的陌生测试样本泛化失败。后续内存对照表明同一架构能学会训练集的离散标签，但连续参数的训练域与解码合法域不一致，导致离散预测正确后仍大量解码失败。数据覆盖和验证指标又限制了泛化判断。不能据此宣称增加轮数即可解决实际执行效果。

## 1. 已确认的初始化、优化和选模事实

- `Tools/ActionEncoder/train_action_config.py:185` 从基础 MiniRBT 加载 backbone，`:193` 随机新建任务头；没有从旧任务检查点继续训练的路径。
- `checkpoint_epoch20/manifest.json:36` 记录 27 条训练样本；`checkpoint_epoch20/training_request.json:1376` 记录 batch size 32。训练循环 `train_action_config.py:220`、`:229` 因而每轮只有一次优化更新。
- `checkpoint_epoch20/manifest.json:39` 明确记录 `best_epoch=6`。20 轮是运行长度，保存的是第 6 次更新后的最佳权重，见 `train_action_config.py:240`、`:248`、`:258`。
- 原始 20 轮的执行结构准确率全部为 0/5。第 1、6–11 轮 selection score 同为 -0.3416667，按 validation loss 打破平局后选中第 6 轮。后期训练 loss 下降而 validation loss 上升，不能据训练 loss 推断泛化改善。
- `checkpoint_probe_summary.json` 确认 train+val 共 35 条原始输出全部为 `execute / blink.full / PAD`，训练集最终结构正确数为 0/27。
- `controlled_fit_summary.json` 的 original recipe 对照在第 6 次更新时与保存权重完全一致：head 和 backbone 的最大绝对差均为 0.0。这排除了“检查点加载成另一个模型”作为本次现象的解释。
- 相同配方延长到 50 和 100 次更新后，训练集原始 decision 为 27/27，15 条执行样本的 resource slots 和 active cycle counts 均为 15/15。说明原架构和梯度路径能够拟合这些离散训练标签；该证据支持早期优化不足，而非离散头完全无法学习。它不证明对未见语义族泛化良好。

## 2. 确认的连续参数可行域缺口

- `action_config_schema.py:38` 允许 `look_around.basic` 的 hold 在 0–0.30 回归，但 `:271`–`:272` 要求 hold 精确为零。参数头经 sigmoid（`:212`）和线性映射（`:323`），零目标在训练中容易产生仍非零的小正数，直到舍入阈值以下才合法。
- 原始第 2–5 轮验证预测，每轮 8/8 均报 `invalid_hold_mapping`，详见对应 `checkpoint_epoch20/epoch_*_validation_predictions.jsonl`。
- 合法非零 hold 必须产生至少 80ms 停留段（`action_config_schema.py:274`–`:277`），但训练分别回归 duration、hold，损失不表达这个联合合法域（`train_action_config.py:128`–`:130`）。hold 的合法集合包含零与足够长的非零停留，中间小正数区间会被拒绝。
- 内存对照在第 50、100 次更新已经学对离散训练标签，仍有 9 条 decoder errors：8 条 `hold_segment_too_short`，1 条 `invalid_hold_mapping`。这直接佐证参数化缺口会独立于资源分类错误持续存在。
- 限定的修复方向是使资源参数化表达真实合法域，例如固定零 hold 的资源采用固定范围，零/非零 hold 及非零最短时长采用显式合法域表达。此处没有实施修复，也不建议关闭 guard、替换动作或静默修正输出。

## 3. 指标与结构监督的解释边界

- `train_action_config.py:49`–`:63` 在 decode 和输入约束检查成功后才累计 decision/structure；`:66` 将失败计入 technical errors。因此当前 decision accuracy 混合了语义判断与执行合法性，不能直接定位分类头是否学会。
- `train_action_config.py:75` 的 specificity 只扣除成功解码后的 false execution，所以第 2–5 轮全技术失败仍显示 specificity=1.0。这可表示最终没有执行，但不能解释为模型正确识别了非执行意图。宜分开记录原始决策混淆矩阵、离散结构、decoder failure 和 guard rejection。
- `train_action_config.py:77` 的评分结合语义和技术错误，所有执行结构均错误时仍会选出“相对最好”的模型。它解释了第 6 轮被保存，但没有证据表明原 20 轮内存在被错误丢弃的优秀模型。
- `action_config_schema.py:175`–`:177` 的资源、阶段、次数是共享 trunk 上的独立分类头；stage/cycle 只在 gold active slots 上监督（`train_action_config.py:118`–`:121`）。其 PAD 类没有正例，联合结构没有被显式约束。这是设计限制，现有证据不足以认定它导致本次常量输出。
- 参数训练用 gold resource（`train_action_config.py:123`–`:124`），推理用 predicted resource（`encoder.py:246`–`:247`）。这是明确的训练/推理条件差异，但不是标签索引错误，也不能据此单独归因。

## 4. 数据先验与覆盖限制

- train 的 execute 占 15/27；执行样本第二槽 PAD 为 9/15；第一槽单次为 12/15；第二槽活动动作全部单次。这与早期“execute、单动作、单次”的常量输出方向一致。
- blink 不是独占多数：第一槽有六类资源各 2 条，另外三类各 1 条。不能把眨眼 collapse 解释为眨眼标签远多于其他动作。
- train 没有 cycle_count=3 正例，而 val 五条执行样本中三条要求三次；wave 没有训练正例却出现在 val/test。全部训练行属于 instruction。这些限制独立存在，但不能解释已经在训练集出现的 collapse。
- 保持固定评测不变；如后续补数据，应增加独立训练语义族，不应把 held-out 行搬回训练。

## 5. 已排除或未发现的问题

- 六个训练来源文件的当前 SHA256 全部与 manifest 一致。
- 角色前缀一致：`training_data.py:83` 与 `encoder.py:231`；attention-masked mean pooling 一致：`train_action_config.py:138`–`:141` 与 `encoder.py:242`–`:244`。
- 运行时加载对应 head/backbone 并设为 eval：`encoder.py:159`–`:170`。未发现 exec、active slot、cycle、amplitude mask 与 canonical targets 错位。
- 训练使用默认 SDPA，运行时使用 eager，但同权重 pooled 最大绝对差仅 3.33786e-6；单条与批量 pooled 最大差 1.66893e-6，decision logits 最大差 1.78814e-7。结合上述精确第 6 步重现，该差异不是本次 collapse 的原因。

证据文件：同目录的 `checkpoint_probe_summary.json`、`checkpoint_probe_rows.jsonl`、`controlled_fit_plan.json`、`controlled_fit_summary.json`、`controlled_fit_metrics.jsonl`、`fit_original_recipe_200_updates_*_train.jsonl`，以及 `../checkpoint_epoch20/epoch_metrics.jsonl` 和逐轮验证预测。内存对照没有写入模型检查点，没有访问固定 test；正式修复与重新评估尚未开展。
