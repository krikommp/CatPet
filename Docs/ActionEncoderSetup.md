# 本地动作模型：安装与启动

更新：2026-11-17。已有 MiniRBT v0.2 参数头及试验权重，主接口 POST /configure。完整流程见 [接入主线](D:/UnityProjects/Pet/PetLive2d/Docs/ActionLanguage/Yukikaze_ActionModel_Integration_Plan.md)。

## 环境与服务

项目已配置 Python 3.11、PyTorch CPU、Transformers 和固定 hfl/minirbt-h256。来源与哈希见 [模型记录](D:/UnityProjects/Pet/PetLive2d/Docs/ActionEncoderModel.md)。

在项目根目录 PowerShell 执行：

```powershell
# 首次安装，已有环境不用重复。
.\Tools\ActionEncoder\bootstrap.ps1

# 前台运行，Ctrl+C 停止。
.\Tools\ActionEncoder\start.ps1

# 或后台启动，通过 stop.ps1 停止对应进程。
.\Tools\ActionEncoder\start.ps1 -Background
.\Tools\ActionEncoder\stop.ps1
```

服务仅监听 http://127.0.0.1:8765，使用本地权重，不需要 API Key。大模型教师是另一个待接入服务。

## 日常入口

- 用户验收：Unity 的 Tools > PetLive2d > 动作模型 > 用户验收。
- 模型测试：`.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/model_test.py`。
- 编译检查：Unity 同组的“模型测试（编译检查）”。
- 数据、训练、报告及启用版本见 [训练与验收](D:/UnityProjects/Pet/PetLive2d/Docs/ActionEncoderTraining.md)。

旧编码探针与零散冒烟测试已合并／移除。/encode、/plan 保留兼容，新训练及验收使用 /configure。

## 目录

| 目录 | 用途 |
| --- | --- |
| Tools/ActionEncoder/ | 安装、推理、训练、数据校验、模型测试 |
| .venv-action-encoder/ | Python 环境 |
| .cache/action-encoder/model/ | 基础模型 |
| Tools/ActionEncoder/checkpoints/ | 模型版本，实验不覆盖当前版本 |
| .action-encoder/ | 服务日志、模型测试报告 |
| Dataset/ActionCards/ | 候选、评价、合格语料、视频 |
| Assets/Scripts/ActionLanguage/ | 编译、播放、验收及记录 |