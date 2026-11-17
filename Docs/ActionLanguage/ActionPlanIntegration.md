# 旧 action-plan 接入说明

2026-11-16 的 Natori / action-plan.v0.1 原型入口已由 [Yukikaze 接入主线](D:/UnityProjects/Pet/PetLive2d/Docs/ActionLanguage/Yukikaze_ActionModel_Integration_Plan.md) 替代。

2026-11-17 整理后，旧 Natori 演示、播放探针及旧测试菜单移除；日常使用用户验收和模型测试，见 [训练与验收](D:/UnityProjects/Pet/PetLive2d/Docs/ActionEncoderTraining.md)。

ActionPlanCompiler / ActionPlanReceiver 和 /plan 保留兼容历史调用，不作为新训练入口。原生 v0.1 关键帧协议与 ActionContract / ActionPlayer / Live2DActionAdapter 仍是 v0.2 的执行基础。