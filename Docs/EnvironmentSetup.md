# PetLive2d 环境安装记录

安装与验证日期：2026-11-16。

## 当前组合

| 组件 | 已安装版本 / 状态 |
| --- | --- |
| Unity Editor | 2022.3.53f1c1 |
| Universal Render Pipeline | 14.0.11，继续使用 URP-HighFidelity |
| Unity Skills | 3.0.0，当前项目实例 PetLive2d_CF8A3BFA |
| Live2D Cubism SDK for Unity | Cubism 5 R4_1，官方完整发行包 |
| Cubism Core | 包内原生库已安装，Windows x86_64 编辑器运行验证通过 |
| 官方示例模型 | Clipping、Koharu、Mao、Natori、Rice |

选择 R4_1 是因为其官方 README 明确列出 Unity 2022.3 开发环境；这不是当前最新 SDK。当前 Unity 2022.3.53f1c1 与 URP 14.0.11 的组合已在本机完成下述验证，未升级 Unity 或切换渲染管线。本次没有编写 AI 动作引擎或接入模型服务。

## 安装来源与文件

- [官方完整 unitypackage](https://cubism.live2d.com/sdk-unity/bin/CubismSdkForUnity-5-r.4.1.unitypackage)
- [R4_1 官方源码说明](https://github.com/Live2D/CubismUnityComponents/tree/5-r.4.1)
- SDK 根目录：`Assets/Live2D/Cubism/`。
- 安装包同时提供 `Assets/csc.rsp`、`Assets/mcs.rsp`，内容为 `-unsafe`；SDK 自身程序集也启用了 unsafe。
- 下载缓存：`.setup/downloads/CubismSdkForUnity-5-r.4.1.unitypackage`。
- 下载文件 SHA-256：`2777b69d4cd02fecd48dc0fe9871700c95943f6d141c18758027bd9aa2ed1de6`。
- 安装文件清单与原始哈希：`.setup/live2d-r4_1/install-manifest.json`。
- 安装前的项目设置与包配置备份：`.setup/live2d-r4_1/before-install/`。
- 许可文件保留在 SDK 自带的 `LICENSE.md` 与插件目录中。

安装时按 unitypackage 的 pathname 与 asset.meta 还原文件，保留官方 GUID，再通过 Unity Skills 的 AssetDatabase 刷新完成导入。

## 已完成的验证

1. Unity 编译完成，新脚本域加载成功，编译错误数为 0。
2. 官方 `Samples/Masking/Masking.unity` 运行观察 8 秒，运行错误数为 0。截图确认组合 Logo 正常显示、GPU 遮罩纹理生成。单张截图不覆盖所有遮罩边界情况。
3. 官方 `Samples/OriginalWorkflow/Demo/Demo.unity` 运行观察 10 秒，运行错误数为 0，Natori 角色显示正常。
4. 通过已加载的 `CubismParameter` 读取了真实参数信息。例如 Natori 的 `ParamAngleX` 范围为 -30～30、默认值为 0；`ParamBreath` 范围为 0～1、默认值为 0。
5. 对 Demo 显式推进 30 个播放帧，`ParamBreath.Value` 从 0 变为 0.1612674，确认动画正在驱动参数。记录位于 `.setup/live2d-r4_1/animation-step-check.json`。普通后台等待期间编辑器可能不持续推进播放帧，因此此项采用显式帧推进验证。

截图：

- `Assets/Screenshots/live2d-urp-mask-check.png`
- `Assets/Screenshots/live2d-demo-ready.png`

上述检查覆盖 Windows 编辑器内导入、编译、基础渲染、遮罩纹理生成和动画参数更新；尚未验证独立构建、桌面透明窗口、其他平台或任意外部模型。

## 已知编译警告

SDK 原始文件产生两条不阻断编译的警告，未修改第三方源码：

- `CubismMotion3Json.cs:439`：CS0162，不可达代码。
- 旧编译器响应文件 `mcs.rsp` 已过时，Unity 提示使用 `csc.rsp`；官方包同时包含后者。

## 继续使用

当前编辑器停留在官方 Demo 场景，已退出播放模式。点击 Play 可运行 Natori 示例。

也可打开：

- `Assets/Live2D/Cubism/Samples/Animation/Animation.unity`：Mecanim 示例。
- `Assets/Live2D/Cubism/Samples/OriginalWorkflow/Motion/Motion.unity`：动作播放示例。
- `Assets/Live2D/Cubism/Samples/Models/`：五个模型及其导入资源。

后续 AI 动作协议应从所选模型读取实际参数 ID、范围与默认值；此处的示例参数不能假定适用于所有模型。
