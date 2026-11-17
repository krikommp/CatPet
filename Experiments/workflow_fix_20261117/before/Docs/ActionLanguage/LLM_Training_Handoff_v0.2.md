# 交给另一个 AI 的接手说明

更新：2026-11-17。先读 [接入主线](D:/UnityProjects/Pet/PetLive2d/Docs/ActionLanguage/Yukikaze_ActionModel_Integration_Plan.md) 和 [训练与验收](D:/UnityProjects/Pet/PetLive2d/Docs/ActionEncoderTraining.md)。本文不维护第二套流程。

可直接复制：

> 用户已确定以大模型主导、蒸馏合成数据为主，目前没有人工数据。教师直接生成动作描述与候选配置，规则检查后，在独立评审上下文中对照原句观看 Yukikaze 的完整视频，评价并修正配置，把实际审核通过的样本交给本地 MiniRBT 训练。冷启动不依赖学生先生成正确配置，不依赖人工标注或 keep。运行时上游 AI 给描述，本地模型预测动作参数并播放。
>
> 现有 v0.2 参数头、/configure、ActionConfigCompiler、PreviewSession、ReviewStore 和用户验收已经存在。不要重写或退回旧 /plan。模型测试统一使用 Tools/ActionEncoder/model_test.py；Unity 保留用户验收和编译检查入口，不恢复旧 Natori 演示及临时训练式冒烟测试。
>
> 下一步接 TeacherClient 与 TrainingRoundRunner，同时处理审查发现的冲突替换动作、同文泄漏和编译参数与标签不一致。教师服务配置可用后接文本与配置生成、独立视频评审和修正；保留生成／评审模型与提示版本、审核状态、配置／视频关联和资源／编译器绑定。完整录制结束后送评，修正配置重播再评价。AI 审核导出拟为 teacher_reviewed_action_config.jsonl，当前尚未实现；不得复用人工 keep 作为准入条件。用户验收用于可选抽查，不阻塞实验训练。
>
> 先按语义族固定切分，再扩写；同文、改写、参数变体和源候选派生不能跨切分，固定验收集不得回流训练。现有离线教师语料可在严格校验、去泄漏后作为单独标记的冷启动合成池，不补造视频审核证据。新执行样本回放通过后进入 AI 视觉审核池；非执行样本依据语义及资源能力审核。训练保存明确来源的数据快照和独立实验目录，不直接覆盖当前权重，不用验证损失代替实际预测结构、误执行和视觉评测。学生后续参与难例挖掘，教师仍负责修正并重播审核。
>
> 使用现有资源目录与 action-config.v0.2，无需第一版就引入强化学习、奖励模型或重建数据平台。完成后提供真实教师调用、完整回放评分修正记录、入库与模型测试结果，区分已完成和待完成。

关键文件：[输出协议](D:/UnityProjects/Pet/PetLive2d/Docs/ActionLanguage/action-config-v0.2.md)、[资源目录](D:/UnityProjects/Pet/PetLive2d/Docs/ActionLanguage/profiles/yukikaze-resources.v0.2.json)、[训练脚本](D:/UnityProjects/Pet/PetLive2d/Tools/ActionEncoder/train_action_config.py)、[推理](D:/UnityProjects/Pet/PetLive2d/Tools/ActionEncoder/encoder.py)、[录制播放](D:/UnityProjects/Pet/PetLive2d/Assets/Scripts/ActionLanguage/Editor/PreviewSession.cs)、[数据保存](D:/UnityProjects/Pet/PetLive2d/Assets/Scripts/ActionLanguage/ReviewStore.cs)。

当前教师视频 API、AI 审核导出与自动训练轮次尚未接通。本次修改确定数据主线，没有实现或运行这些模块。离线合成训练可以作为明确标记的冷启动实验，但只生成语料、直接覆盖 v02_latest，不算完成教师审核闭环。
