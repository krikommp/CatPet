# 数据辅助审查交付

本次仅处理冻结的 **3232 条**语料快照（SHA256 `aef5ce445eb8356857014f3ec35ddc57dea66ab0923a362ad65842f1d1654a10`），没有混入 Gemini 第 9 轮之后新增的共享语料、没有改共享文件、没有训练。

## 已完成

- `data/cold_start.jsonl`：1336 条待审冷启动样本，预定 train/val/test = 893/68/375。全部标 `historical_synthetic`、`cold_start_synthetic_unreviewed`、`training_eligible=false`，没有补造视频审核来源。
- `data/quarantined.jsonl`：1896 条排除记录，含原行号和全部原因。原因会重叠，不能相加成总数。保守数值语法门禁把未覆盖的表达也隔离，并非这 1896 条都已证实标错。
- `data/family_splits.json`：按资源及顺序/并行拓扑归族，忽略次数、时长和幅度变体；再与原始 source group、规范同文做全局连通合并。已冻结归属，测试优先于验证、训练；后续视频修正和新文本须沿用所属族。
- `data/fixed_eval.jsonl`：28 条新生成的客观挑战，包含四种 decision、否定、次数、顺序、并行、精确周期时长和逐次关系。它只用于 decision/动作结构/显式约束，禁止把参考配置中未被文本约束的参数拿来计算 MAE；没有视觉或人设通过声明。`objective-eval-011` 的跨分句数值归属仍明确标 unresolved，不能假装确定性解析已覆盖。
- `scripts/dataset_constraints.py`：保守规则检查器，不修改配置。明确次数、单位和第 X 次/每次的时长绑定、严格逐次/渐变关系均有检查；归属不能确定时返回 `unresolved`。它不是通用中文语义解析器，结果必须结合 `coverage_is_partial` 读取。
- `reports/dataset_verification.json`：57/57 检查通过，覆盖数值误归属、逐次颠倒、显式跨次参照、负数、非整数次数/序号、否定关系、短 hold、缺 hold 相位、跨切分泄漏与真实 C# 编译结果关联。

## 已确认的质量问题

原训练脚本的随机切分可复现为 2591/321/320，同文 train/test=11、train/val=15、val/test=4。129 组重复原句存在不同连续参数，结构冲突为 0；本轮将这些全部隔离待裁决，未把它们夸大为结构标签冲突。

清洗结合 `reports/compiler_patched_corpus.jsonl` 的实际 C# 编译结果，不仅检查 Python 参数范围：保留记录全部在隔离修复版 C# 下编译通过。该报告的模型范围、过短 hold、缺少 hold 相位失败全部参与排除。Python 同时列出多项客观失败，因此逐原因计数与 C# 首错计数不同。隔离编译通过不等于 Unity 完整回放通过。

最初逐条检查确认的 24 条语料不满足明确逐次幅度关系。例如“第二下轻一点”两次幅度完全相同，“幅度越来越大”出现相邻值相等。最终更保守规则共有 47 条约束违反标记，含窄语法下次数作用域冲突；不能把全部 47 条直接宣称为已经人工确认的标错。1188 行另有未覆盖/未消歧的数值表达（1622 个 unresolved 项），其中也含“一边”“一点”等可能被保守词法检查拦截的惯用语；需要扩展经验证的语法或教师裁决，不能放行后冒称精确数值已检查。

支持子集限于明确动作邻接整数次数、阿拉伯数字秒/毫秒、显式第 X 次/每次的周期时长、若干相对方向及“比第 X 次”参照。不支持的半秒、中文小数、秒钟、中文百位数、单位为空的幅度数值、半幅度及复杂否定关系返回 unresolved；负数数量、0/非整数序号也拒绝。它既不从预测动作数推断文本作用域，也不把“第二次不要更重”反转为更重。未来扩语法需保持这些反例测试。

已排除自由台词、RP 舞台表现及未区分输入角色的组，并记录“打哈欠 → bow+blink”的不支持动作近似。未来 `instruction` 必须严格执行明确动作及数字；`dialogue` 可按人设做表演，但需要显式输入角色，不能用台词近似政策覆盖准确指令。

## 尚未可训练的原因

语义族与源组的保守并集合并揭示旧 ambiguous 数据通过源组形成一个大连通族。此族冻结为 test 后，训练池暂缺 ambiguous 类。none 数据也存在跨语义源组形成的大族。为制造四类齐全而拆散已知来源关系会重新引入泄漏；需要新增独立的非执行语义族，或在公开标记为重设协议的下一轮重新定义并冻结划分。当前池不应直接开始训练。

实际 Gemini 人设已观察并保存为 `data/persona_observed.md`，SHA256 `56b4364bf1c7da22e6b6faadc094299e570f93375e0acb78f510c360d614aa41`。这仅证明读过哪个版本，尚未逐条复核旧标签，因此每条数据的 `persona_sha256` 和审核 rubric 仍为空，状态保留 pending。人设中的建议不能超越资源/编译硬约束：blink 的周期上限是 1800ms，不能直接采纳表中 1950ms；cheer 的 1.20 等建议仍须真实 Core 范围检查；“左右倾摆”等视觉描述必须由视频证据确认。

所有非 blink 资源仍是候选标定状态；本轮没有把它们宣布正式可用。固定挑战的新文本也不等于基线未见过其语义族；当前基线已使用旧语料训练，不能拿新划分的分数宣称公平独立泛化。

## 复现

在项目根目录依次运行：

```powershell
.\.venv-action-encoder\Scripts\python.exe Experiments/teacher_video_20261117_01/scripts/dataset_prepare.py
.\.venv-action-encoder\Scripts\python.exe Experiments/teacher_video_20261117_01/scripts/dataset_fixed_eval.py
.\.venv-action-encoder\Scripts\python.exe Experiments/teacher_video_20261117_01/scripts/dataset_verify.py
```

前置输入是本轮冻结 `input` 与 `reports/compiler_patched_corpus.jsonl`，后者逐行核对 raw_text、group_id。不得将另一个版本的编译报告或第 9 轮共享语料直接替换进来。
