# 第一轮真实教师采数与蒸馏训练结果

2026-11-17，PetLive2d。本轮已完成真实生成、Unity录制、独立AI审核、冻结、20 epoch训练及固定测试。新checkpoint为 **17ab06dfb9a0**，保持experimental。固定测试表现未改善，不能上线。

## 实际数据与审核

教师为当前OpenAI / Codex desktop根会话，没有调用Gemini。具体底层模型标识不可见，生成与审核记录均如实注明。审核由fork_turns=none的四个独立上下文完成：一个语义评审、三个视觉评审。提示、rubric、用户约束补充、原始反馈及实际上下文均已保存。

生成前固定54个语义场景族及split：目标train/val/test=36/9/9，执行24/6/6、非执行12/3/3。原句和配置由教师逐条撰写，脚本仅序列化；全部为instruction。没有混入旧语料或测试夹具。

| 环节 | 实际数量 |
| --- | ---: |
| 初始候选 | 54（执行36、非执行18） |
| 修正 | 1，新增tr1-val-05-r1，保留父候选、语义族及val归属 |
| 总生成ID | 55 |
| 录制前技术拒绝 | 1，原val-05幅度句式超出数字守卫语法，未录空视频 |
| 真实录制 | 36/36完成，0录制失败 |
| 全帧观察 | 2301帧、82页时间戳帧组、全部实际轨迹及额外原尺寸帧 |
| 独立审核 | 54：42接受、7拒绝、5不确定 |
| 冻结准入 | 42：24条ai_video_reviewed、18条ai_semantic_reviewed |

裁切、拒绝及不确定候选均无自然度分数。失败及反馈全部保留，没有改写标签迁就视觉失败。视觉失败需要动作标定/取景修正，本轮未更改绑定资源或人设来凑数。总录制36段，低于72段上限；单候选最多修正1次。

| split | execute | none | unsupported | ambiguous | 合计 |
| --- | ---: | ---: | ---: | ---: | ---: |
| train | 15 | 4 | 4 | 4 | 27 |
| val | 5 | 1 | 1 | 1 | 8 |
| test | 4 | 1 | 1 | 1 | 7 |

剔除由训练前的视觉/语义审核决定；测试在训练前冻结，没有按模型表现筛选。原计划测试9条中2条因视觉问题未准入。

## 视觉发现与覆盖

初始录制覆盖12资源，准入池覆盖10资源，训练集覆盖9资源（blink、nod、shake_head、tilt_head、look_around、smile、angry、shy、surprise）。

- cheer：高幅度水平伸臂，多条录像手指触及/越出画面，欢呼身份也不够明确；无准入样本。
- bow：实际偏浅低头，不能充分建立鞠躬身份；无准入样本。
- wave：A/B对问候语境的直臂侧抬保留不确定；C认为val-05-r1的逐次更大手臂挥动和test-01的眨眼/挥手信号可读，保留具体理由及补查帧。两条仅在heldout，训练集没有wave。判断差异是局限，不是正式标定通过。
- 顺序、并行、次数、逐次时长/幅度、否定及能力边界有覆盖。明确数值及递进关系的heldout样本位于验证集，最终7条测试没有明确数字递进请求，不能声称精确数值泛化通过。
- 没有dialogue数据。除blink外，资源继续保持Candidate。

## 冻结与训练

快照：frozen_snapshot/manifest.json，SHA256 **76ecaf278d5f7f64077e5995d37078509aebe1da7e2493d7a20fe3bda9feb3f2**。prepare、冻结包validate、训练器--validate-only均成功。快照绑定原句/配置、人设、编译器、资源、native profile、完整视频/轨迹及实际审核证据；训练前后再次核验。

沿用已验证的固定hfl/minirbt-h256底座及原有配置头架构，新初始化动作头、解冻末2层，seed=1337；PyTorch2.9.1+cpu，batch=32，threads=2。实际命令：

```text
retrain_and_eval.py train --snapshot-manifest Experiments/teacher_round_20261117_184246/frozen_snapshot/manifest.json --out-dir Experiments/teacher_round_20261117_184246/checkpoint_epoch20 --epochs 20 --batch-size 32 --threads 2
```

训练于北京时间19:00:46启动，19:01:09退出，exit=0。完整20个epoch及20份验证预测已保存并逐项核对哈希。既定predicted-resource验证指标选中epoch6，checkpoint ID **17ab06dfb9a0**。训练loss由6.7502降至3.1037，但选中轮次验证执行结构0/5、非执行误执行3/3、技术错误3/8；loss下降不是质量提升证据。

权重位于checkpoint_epoch20/。training_claim.json及reports/completion_summary.json记录完成状态。训练器原始training_request.json保留启动时request状态，最终完成由20轮记录、退出码及manifest证明。

## 同一固定测试的离线评估

两份报告位于checkpoint之外，对相同7条带role输入评估。旧模型使用冻结第9轮副本838f2c1ac110，遵循自身legacy输入策略；新模型使用action-input-role.v1。

| 指标 | 新17ab06dfb9a0 | 第9轮838f2c1ac110诊断 |
| --- | ---: | ---: |
| 决策正确 | 4/7 | 5/7 |
| 全结构正确（含非执行） | 0/7 | 3/7 |
| 执行动作结构正确 | 0/4 | 1/4 |
| 非执行误执行 | 3/3 | 1/3 |
| 技术错误 | 0/7 | 1/7 |

新模型7条输入全部预测单次blink，时长614–618ms，出现明显输出退化。它把“不要眨眼，也不要鞠躬”预测为眨眼；4条执行请求的资源/组合也全部错误。技术错误为0仅表示结构可解码，当前守卫对这些语义问题没有有效检查，不能解释为安全或准确。

第9轮仍有一条并行动作冲突技术错误、一条能力边界误执行，也不满足上线要求。旧训练数据与本轮场景的语义独立性未证明，因此只是同题诊断，不能作统计性的优劣结论。

完整预测与失败保留于reports/new_checkpoint_fixed_test.json、reports/round9_same_fixed_test_diagnostic.json、reports/fixed_test_failures.jsonl，以及checkpoint_epoch20/epoch_*_validation_predictions.jsonl。

## 完成边界

仅27条训练、7条测试，数据及资源覆盖不足。评估未将模型预测再次录制，不能声称新模型视觉表现通过。固定语义族切分避免同文/派生跨分区，共享动作原语不等于统计独立。

第9轮原权重、manifest、旧test_split和旧llm_v02_corpus共5项哈希保持不变，第9轮冻结副本也未改变。未覆盖latest/v02_latest、未启动或切换8765服务、未晋级ready。唯一新增共享C#文件ActionTrainingBatchEntry.cs只代理既有RunBatch，编译完成后才录制；录制中绑定源码及人设未修改。

机器可读结果及保护哈希见reports/completion_summary.json，准入明细见reports/admission_accepted_records.json。后续重点是校准被拒资源、明确挥手语义，并扩充独立审核数据后重新检验误执行与结构泛化。
