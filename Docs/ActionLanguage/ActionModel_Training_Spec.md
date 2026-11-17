# 动作模型训练规范入口

旧的情绪分类、人工逐条抽卡训练草案已合并到当前方案，避免多个文档给出不同的实施要求。

- [接入主线](D:/UnityProjects/Pet/PetLive2d/Docs/ActionLanguage/Yukikaze_ActionModel_Integration_Plan.md)：大模型生成描述、看视频评分与修正，本地模型学习并执行。
- [训练与验收](D:/UnityProjects/Pet/PetLive2d/Docs/ActionEncoderTraining.md)：数据、训练命令、模型测试及用户验收。
- [输出协议](D:/UnityProjects/Pet/PetLive2d/Docs/ActionLanguage/action-config-v0.2.md)：资源选择、动作编排、逐 cycle 参数。
- [AI 接手说明](D:/UnityProjects/Pet/PetLive2d/Docs/ActionLanguage/LLM_Training_Handoff_v0.2.md)：下一步只补教师接口和训练调度。

更新：2026-11-17。已有 v0.2 模型和视频录制；自动教师视频评价尚未接通。