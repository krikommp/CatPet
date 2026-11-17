# PetLive2d

Unity Live2D 宠物与本地动作模型项目。此仓库保存 Unity 资源、源码、数据集、训练权重，以及实验录制和审核记录。

## 换电脑继续

1. 克隆仓库：

   ```powershell
   git clone https://github.com/krikommp/CatPet.git
   cd CatPet
   ```

2. 在 Unity Hub 中添加克隆后的目录，使用 **Unity 2022.3.53f1c1** 打开。首次打开会重新导入资源并恢复 Package Manager 依赖。
3. 安装 **Python 3.11**，在项目根目录运行：

   ```powershell
   .\Tools\ActionEncoder\bootstrap.ps1
   # 如无法连接 Hugging Face，可指定镜像下载固定版本：
   # .\Tools\ActionEncoder\bootstrap.ps1 -ModelEndpoint https://hf-mirror.com
   .\Tools\ActionEncoder\start.ps1
   ```

   服务地址为 `http://127.0.0.1:8765`。Python 环境和官方 MiniRBT 基座通过安装脚本重建；项目训练权重已保存在仓库中。
4. Unity 菜单 `Tools > PetLive2d > 动作模型 > 用户验收` 是日常验收入口。

## 当前进度（2026-11-17）

- 环境与操作：[安装和启动](Docs/ActionEncoderSetup.md)、[训练和验收](Docs/ActionEncoderTraining.md)。
- 主线：[Yukikaze 动作模型接入计划](Docs/ActionLanguage/Yukikaze_ActionModel_Integration_Plan.md)。
- 最近完成的一轮：[真实教师采数与训练报告](Experiments/teacher_round_20261117_184246/ROUND_REPORT.md)。新 checkpoint `17ab06dfb9a0` 保持 experimental，固定测试未改善，未替换当前模型。
- 最新排查：[单次眨眼退化诊断](Experiments/teacher_round_20261117_184246/diagnosis_20261117_191221/DIAGNOSIS.md)，包含有效更新次数、参数表示及后续修复依据。
- 当前模型版本保存在 `Tools/ActionEncoder/checkpoints/`；各次实验的独立权重、冻结数据、评审及录制证据保存在 `Experiments/`。

仓库不包含 Unity Library、临时文件、Python 虚拟环境、下载缓存和本机服务状态。首次克隆数据量较大，因为保留了完整实验图像证据。

冻结训练清单会核对文件 SHA-256；`.gitattributes` 保留文件原始字节及换行，不自动转换。历史报告中可能含原电脑绝对路径；新电脑执行命令时以当前克隆目录为准。

**继续校验或训练旧冻结快照前**，还需要恢复清单绑定的 FFmpeg 绝对路径。对应的精确工具副本已保存，按 [FFmpeg 恢复说明](Tools/Video/README.md) 操作；不要修改原冻结清单或哈希。普通模型服务启动和 Unity 录制不需要这一步。
