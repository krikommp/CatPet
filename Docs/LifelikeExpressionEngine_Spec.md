# PetLive2d · 生命感表达引擎精简架构规范

> **状态：早期架构草案。** SDK 与示例模型的实际安装状态见 [环境安装记录](EnvironmentSetup.md)。动作协议已另行整理为 [Action Language v0.1 设计草案](ActionLanguage/v0.1.md)，新增动作包以该文档为准。本文的 Canvas 参数示例、性能目标和后续模块不表示已经实现。
>
> **当前方向：** 优先验证大模型直接生成结构化动作参数，由 Unity + Live2D 执行。动作质量、时序与模型适配仍需实测；本地即时反馈和按需云端调用作为后续架构方向。

---

## 1. 端云双层架构（解决高成本与实时反馈矛盾）

```text
[本地脊髓反射层 · Unity C# / Win32 · 0 Token · <16ms]
  ├── 系统感知：键鼠空闲时长(GetLastInputInfo)、前台窗口(GetForegroundWindow)、音频频谱(WASAPI)
  ├── 告别死板 Idle：Perlin Noise 叠加微晃 + 随机微动作池(舔爪/抖耳/打哈欠) + 音乐踩点 + 离开3分钟打盹
  └── Live2D 原生自主层：CubismEyeBlink / CubismLook(鼠标追随) / CubismPhysics / CubismMouth

[本地状态聚合器 · State Aggregator]
  └── 将过去一段时间的本地感知压缩为 ~30 字摘要，平时不发云端；
      仅在“用户主动对话”或“强事件阈值(如久坐/深夜/连续报错)”时夹带唤醒大模型。

[云端大脑 · LLM] ──(输出台词 + 动作语言)──▶ [Unity 执行引擎] ──▶ [Live2D + UGUI气泡 + 道具/粒子]
```

---

## 2. 动作语言（Action DSL）协议设计

本节保留旧 Canvas 原型的格式，供背景参考。它在 `t` 时刻修改弹簧目标，不能视为已确定的 Live2D 参数或“在该时刻到达姿态”的协议。最新字段、真实参数能力表、稀疏插值和中断语义见 [v0.1 草案](ActionLanguage/v0.1.md)。

采用 **“稀疏关键帧 + 局部增量（Delta）”**，大模型只需在关键节点输出变化字段，中间过渡由本地二阶弹簧物理补齐（后续可升级为台词内联锚点去掉手动 `t` 估算）：

```json
{
  "subtitle": "*(舞台动作旁白)*",
  "steps": [
    {
      "t": 0,
      "ear_l": 1.0, "ear_r": 1.0,
      "head_tilt": 12,
      "squash": 0.88,
      "lean_scale": 1.18,
      "eye_style": "star",
      "arms_mode": "hold_prop", "prop": "☕",
      "vfx": "sparkle",
      "tail_speed": 6.5,
      "say": "主人今天有出去晒太阳吗？"
    },
    { "t": 220, "jump_y": 32, "squash": 1.08 },
    { "t": 450, "jump_y": 0, "squash": 1.0 }
  ]
}
```

---

## 3. Unity + Live2D 执行引擎核心映射

| 逻辑通道 | Unity / Live2D 对应实现 | 说明 |
| :--- | :--- | :--- |
| **头部/五官/耳尾** | `CubismParameter.Value`（`ParamAngleX/Y/Z`, `ParamCheek`, 自定义耳/尾参数） | **必须在 `LateUpdate()` 写入**，且执行顺序排在 `Animator` 之后、`CubismPhysicsController` 之前 |
| **2D 夸张形变** | 模型根节点 `transform.localScale`（体积守恒压扁/拉伸）+ `localPosition.y`（跳跃） | 叠加二阶弹簧阻尼公式，产生 Q 弹回弹感 |
| **头顶气泡 & 口型** | UGUI / TextMeshPro 打字机流式显示 + `CubismMouthController`（音频或吐字驱动） | `say` 吐字期间同步驱动嘴巴开合 |
| **动态道具槽** | 挂载在手部骨骼定位点下的 `SpriteRenderer` / 图标容器 | 支持通用捧物姿势 + 动态切换图标（`🐟` `📄` `☕` `💻`），避免为每种道具重做动画 |
| **漫画特效粒子** | Unity `ParticleSystem` / 预设 Sprite（`✨` `❓` `💧` `💖` `💢`） | 弥补 2D 非现实夸张表现力 |
| **桌面透明置顶** | Camera SolidColor `(0,0,0,0)` + Win32 `DwmExtendFrameIntoClientArea` / `WS_EX_TRANSPARENT` | 透明区域鼠标穿透，待机时动态降帧（如 30 FPS）省电 |

---

## 4. 建议落地里程碑

1. **M1 躯壳就位**：确认 Live2D 测试模型导入 + Windows 透明置顶与像素级鼠标穿透窗口跑通。
2. **M2 执行引擎**：编写 `ActionTimelineRunner` 与二阶弹簧参数控制器，用本地 JSON 剧本验证打字机气泡 + 动作同步。
3. **M3 本地生命感（0 Token）**：接入 Perlin Noise 微动态、键鼠空闲睡觉/惊醒、音频频谱踩点，彻底替换死板循环 Idle。
4. **M4 大脑接入**：接入流式 LLM 接口 + 本地 30 字状态摘要注入 + 按需截图（VLM 视觉问答）。
