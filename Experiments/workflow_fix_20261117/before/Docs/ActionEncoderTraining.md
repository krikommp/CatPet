# 动作模型：训练、模型测试与用户验收

更新：2026-11-17。架构以 [接入主线](D:/UnityProjects/Pet/PetLive2d/Docs/ActionLanguage/Yukikaze_ActionModel_Integration_Plan.md) 为准：大模型直接生成描述与配置，独立评价 Yukikaze 回放，通过的实际配置用于蒸馏本地 MiniRBT。当前没有人工数据，人工标注和 keep 均不是采数、实验训练的前置条件。

## 当前状态与数据

已有 v0.2 参数头、/configure、编译播放器、12fps 视频和人工验收入口。2026-11-17 本次检查的试验权重为 a093379507f0，支持 12 个资源、最多 2 个动作、每动作 1～3 次循环；训练／验证／测试为 2552／320／315 条。自动教师评价、AI 审核导出和训练调度尚未接入。

每条数据至少包含 raw_text、group_id、config。参数定义与资源范围见 [输出协议](D:/UnityProjects/Pet/PetLive2d/Docs/ActionLanguage/action-config-v0.2.md) 和 [资源目录](D:/UnityProjects/Pet/PetLive2d/Docs/ActionLanguage/profiles/yukikaze-resources.v0.2.json)。

- AI 审核池标签必须是通过评价的实际配置；评分本身不能代替参数标签，教师修正必须重播再评价。无视频证据的合成数据可用于明确标记的冷启动实验，不冒称视频已审核。
- AI 来源、教师版本与配置／视频关联需要在接入时补齐，不能假冒人工评价。技术失败、跳过、未评价不进入 AI 审核通过池；冷启动合成数据使用独立来源状态。
- AI 审核导出拟为 Dataset/ActionCards/teacher_reviewed_action_config.jsonl，按规则、回放及教师评价准入，不依赖人工 keep；该导出尚未实现。现有人工导出 qualified_action_config.jsonl 保留为可选补充，文件缺失不阻止使用其他明确来源的数据进行实验。
- 同文、改写及参数变体必须在同一切分组；当前语料存在同文跨组和连续参数标签不一致，需先清洗并建立独立固定验收集。已核实训练／测试重叠原句 11 个、训练／验证 15 个、验证／测试 4 个；重复原句未发现动作结构冲突。
- 覆盖 execute、none、unsupported、ambiguous，以及顺序、并行、次数、逐次快慢／轻重关系。

现有离线 LLM 语料没有视频审核证据，可在严格校验和去泄漏后作为冷启动合成数据；应单独标记来源并记录每轮使用量，不能当作已验收金标准。训练器当前不会强制检查这些来源字段，后续教师调度必须根据实验类型筛选数据快照。不要把现有人工导出路径的“合格数为 0”解释为“没有人工数据就不能训练”。

## 训练

在项目根目录 PowerShell 执行。以下为 AI 审核导出接通后的操作示例，当前目标文件尚未生成，本次仅更新方案、没有运行训练。冷启动实验可将输入改为已清洗且来源明确的合成快照，并在实验记录中注明未完成视频审核；不直接沿用有泄漏的现有切分。

```powershell
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/validate_v02_corpus.py Dataset/ActionCards/teacher_reviewed_action_config.jsonl

# 每次使用独立的新目录，不直接覆盖 v02_latest。
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/train_action_config.py --dataset Dataset/ActionCards/teacher_reviewed_action_config.jsonl --out-dir Tools/ActionEncoder/checkpoints/teacher-round-001 --epochs 15 --batch-size 32 --unfreeze-layers 2
```

当前是 MiniRBT + 离散头 + 资源条件化的逐 cycle 参数头，使用分类交叉熵与参数 SmoothL1。每次从基础预训练模型开始，不是评分一次即时学习。验证损失使用真实资源条件；模型测试使用推理预测资源，二者不能混淆。

格式通过不等于编译及视觉通过。当前编译器可能合并过短的 hold 段，教师闭环还需核对实际展开效果与标签一致性。

## 模型测试：一个命令

```powershell
# 使用当前权重与其 test_split；不需要常驻服务，不重新训练。
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/model_test.py

# 测新训练版本；可用 --dataset 指向固定评估 JSONL。
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/model_test.py --checkpoint-dir Tools/ActionEncoder/checkpoints/teacher-round-001
```

报告写入 .action-encoder/model-test-report.json，包括接口边界、decision 分类分母、动作／顺序／次数结构、结构匹配后的参数 MAE、误执行、推理耗时和失败样例。不修改权重、manifest 或发布状态。

Unity 的 Tools > PetLive2d > 动作模型 > 模型测试（编译检查）保留 v0.2 编译规则验证。它不代表模型语义准确率或视觉质量。

缺类、数据不足和独立性未核实必须明确报告。当前模型留出集不是已证明独立的评估集；脚本完成或接口通过均不代表模型发布合格。

2026-11-17 本次检查的最新报告（权重 a093379507f0，315 条留出数据；读取已有报告，没有重跑训练）：

| 项目 | 结果 |
| --- | --- |
| 决策准确率 | 298/315，94.60% |
| 执行动作结构正确率 | 214/274，78.10% |
| 非执行被误执行 | none 3/13；unsupported 8/20；ambiguous 2/8，合计 13/41 |
| 匹配结构后的参数 MAE | 时长 347.45ms（411 项）；幅度 0.136737（388 项）；保持比例 0.064934（411 项） |
| 自动检查 | 报告标记通过，release_approved=false |
| 输出约束 | 报告无无效预测；解码器仍会为消除冲突替换资源，不能据此认定语义正确 |

这些数据来自现有留出集，不能证明独立泛化或人的审美偏好。此前精简阶段曾记录 Unity 编译和 16 项编译检查通过，本次文档更新未重新运行 Unity 检查，也没有训练、改权重或自动判定发布通过。后续应按实际预测资源评估结构、误执行、精确数字和逐次参数关系，再比较独立视频评价；不能只按教师条件下的验证损失选启用版本。

## 用户验收：一个窗口

1. 启动 Tools/ActionEncoder/start.ps1。
2. Unity 打开 Tools > PetLive2d > 动作模型 > 用户验收。
3. 输入描述，用默认“本地模型”生成并观察 Yukikaze；必要时使用“手工配置”检验 v0.2 配置。
4. 确认语义、评分，选择通过／未通过／跳过；可回放历史。
5. 导出 v0.2 合格数据。执行样本仍须编译成功、完整播放、语义正确、自然度达标并明确通过。

12fps 视频位于 Dataset/ActionCards/snapshots/<candidate_id>/preview.mp4。重复原句确定性推理不会自动改善；修改描述／配置或通过后续教师修正产生新候选。

用户验收是可选抽查与版本确认入口。AI 数据采集和实验训练不依赖此窗口、人工打分或人工合格导出。

## 启用版本

训练、模型测试、可选人工抽查分别执行。新版本经过固定评测与版本比较后再选择启用，保留上一版目录；当前没有自动上线流程。试用指定版本可显式启动：

```powershell
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/server.py --config-head-dir Tools/ActionEncoder/checkpoints/teacher-round-001 --port 8765
```

同端口已有服务时先按原启动方式停止。不能因为训练结束、测试命令退出成功或验证损失下降就标记 ready。
