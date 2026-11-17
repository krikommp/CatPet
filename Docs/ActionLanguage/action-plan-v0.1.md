# 模型输出动作计划 v0.1（设计稿）

> **2026-11-17 迁移提示：本文保留为旧档位动作计划的历史规范。** 当前工程已有 v0.1 试验动作头及 Yukikaze 评审代码，不再是“尚未训练”的状态；代码已扩充的动作范围仍需与标签配置统一。用户的新目标是由模型预测逐次动作参数，后续采用独立的 [action-config.v0.2 草案](D:/UnityProjects/Pet/PetLive2d/Docs/ActionLanguage/action-config-v0.2.md)，不暗改本协议字段。当前实施入口见 [接入计划](D:/UnityProjects/Pet/PetLive2d/Docs/ActionLanguage/Yukikaze_ActionModel_Integration_Plan.md) 和 [训练方案](D:/UnityProjects/Pet/PetLive2d/Docs/ActionEncoderTraining.md)。

设计日期：2026-11-16。以下描述最初方案及当时证据：已实现严格解析、编译器和播放器接收组件，并验证 Natori 眨眼数值原型；示例不是已验收训练样本。当时的验证记录见 [ActionPlanIntegration.md](D:/UnityProjects/Pet/PetLive2d/Docs/ActionLanguage/ActionPlanIntegration.md)，不能代表后续全部代码的当前状态。

## 位置与格式

自然语言片段 → MiniRBT 与动作预测头 → 本文的动作计划 → 本地生成器 → 原生参数动作包 v0.1 → 现有 ActionContract / ActionPlayer / Live2DActionAdapter。

JSON 是模型预测字段的序列化格式，无需把 MiniRBT 改为逐字生成 JSON 的模型。区别于原生参数动作包的 `version: "0.1"`，本格式使用 `version: "action-plan.v0.1"`。

```json
{
  "version": "action-plan.v0.1",
  "decision": "execute",
  "steps": [
    {
      "actions": [
        { "type": "nod", "count": 2, "amplitude": "small", "speed": "normal" }
      ]
    },
    {
      "actions": [
        { "type": "blink", "count": 1, "amplitude": "full", "speed": "normal" }
      ]
    }
  ]
}
```

## 必须固定的语义

1. `steps` 按数组顺序执行。同一步中的 `actions` 同时开始，没有隐含的动作先后。
2. 下一步等待本步所有动作的全部循环结束。较短动作在本步剩余时间保持其模板定义的回收姿态。
3. `count` 表示完整动作周期的次数；周期包含运动与回收。同一 action 连续重复，无额外的隐式间隔。若需要停顿，应在后续协议显式扩展，不能猜测。
4. `speed` 是 `slow` / `normal` / `fast` 三档，具体周期由本地标定配置提供，不让模型猜毫秒。
5. 指令明确给出每次时长时，使用 `period_ms` 代替 `speed`，单位为毫秒，二者严格二选一。`period_ms` 是一个完整周期，不是整条 action 的时长；`count × period_ms` 是该条目的总周期时长。首版允许 240～3000ms 的整数，但仍须满足该动作模板的更严格时序约束。
6. 并行动作在同一步同时起始，各自按其周期运行；不强制同频率或同时结束，也不表达“每点一次头便眨一次眼”这种逐周期联动。
7. 本版每包总共最多 4 条 action，每步至少 1 条，总步数最多 4。`count: 3` 仍占一个 action 条目。JSON 保存嵌套列表；模型实现可用最多四个槽位与阶段索引预测，由代码组织成 steps；槽位数仍需实验验证。
8. 每条 action 的 `count` 为 1～5。编译后的整个动作控制阶段不得超过既有协议的 10000ms / 32个关键时刻 / 同参数间隔至少80ms等限制。因此不是所有字段各自合法的组合都能执行。
9. 每步本身不附加200ms释放。模板中的回正/睁眼属于动作周期；既有播放器只在整个最终动作包结束后执行一次200ms释放，交回实时基线。
10. 参考姿态、回收姿态和起姿容差由版本化标定模板明确给出。宿主提供实际初始合成姿态；首版在将控制的通道起姿不兼容时拒绝，并在提交阶段复核，不暗中插入准备动作或改成模型默认值。跨步骤模板的回收与下一步起姿也必须兼容。

## 字段与动作字典

| 字段 | 定义 |
| --- | --- |
| `version` | 固定 `action-plan.v0.1` |
| `decision` | `execute` / `none` / `unsupported` / `ambiguous` |
| `steps` | 有序步骤；非 execute 时必须为空 |
| `actions` | 当前步骤中同时开始的动作 |
| `type` | 本版候选语义类别：`nod` / `shake_head` / `blink` |
| `count` | 完整周期数，整数1～5 |
| `amplitude` | 头部动作：`small` / `normal` / `large`；眨眼：仅 `full` |
| `speed` | 三档周期预设，和 `period_ms` 二选一 |
| `period_ms` | 明确指定的周期时长，和 `speed` 二选一 |

候选类别的周期定义：

- `nod`：参考头部姿态 → 一次向下点头 → 回到参考姿态。
- `shake_head`：参考姿态 → 一侧 → 另一侧 → 回到参考姿态。完整左右往返算一次；起始侧由版本化模板固定，方向要求不在本版内。
- `blink`：睁眼 → 双眼完全闭合 → 睁眼。单眼眨眼、持续闭眼、半闭眼不是本版的 blink。

这些是待标定的语义定义，不能根据原生参数名称猜正负方向。`amplitude` 不是统一的0～1比例，必须由每个动作、每个角色的已验证映射决定。只有完成标定并在宿主能力表开放的类别、幅度和周期才可执行。

## 省略信息与标注一致性

输入未给出的信息由版本化标注/生成策略补齐，输出 JSON 仍必须显式填全必需字段：

- 普通单次动词未写次数：默认 `count: 1`。
- “连续/反复”但没有次数：本次有限动作默认 `count: 3`；“一直/永远/直到我说停”要求开放式持续控制，返回 unsupported。
- 未写速度：`speed: "normal"`。
- 头部动作未写幅度：`amplitude: "normal"`；双眼眨眼固定 `full`。
- “轻轻/小幅度”优先标为 small；“快速/慢慢”标为 fast/slow。“疯狂”等同时涉及风格、频率和次数的词，先固定经过人工校准的标注策略，再批量扩展训练语料，不临时猜测具体数值。

默认策略属于宿主绑定的 `label_policy_version`，不由模型生成版本号。该策略发生语义变化时必须升级版本，并记录训练数据版本。

## 非执行结果

```json
{"version":"action-plan.v0.1","decision":"unsupported","steps":[]}
```

- `none`：没有需要执行的动作，例如“不要点头”。
- `unsupported`：语义清楚，但超出当前角色能力或本版表达范围，例如未标定的“抖耳”、精确延迟起始、开放式无限循环。
- `ambiguous`：无法确定所指动作或关系，例如无上下文的“像刚才那样动一下”。

只要整句有必须执行但不受支持的子动作，首版整包返回 unsupported；不能把“点头，同时抖耳”静默降级为只点头。否定片段本身不使整包失败：“不要点头，眨一下眼”应只保留 blink。

无自由文本 reason 字段，界面可按 decision 显示说明。抽取无法执行的原文片段可在后续扩展，当前不假定模型已具备定位能力。

## 宿主绑定与编译门槛

模型输入在首版固定角色能力范围下训练；推理宿主绑定 capability profile、语义动作映射版本和默认策略版本。JSON 不含模型猜测的磁盘路径、原生参数ID、profile版本或运行权限。训练/回收记录单独保存 `capability_profile`、`motion_map_version`、`label_policy_version`、模型文件哈希及原始语句，以便复现。

`decision: execute` 只是待编译的候选，不等于通过执行授权。进入播放器前必须整包验证：

1. 严格JSON解析，拒绝重复键、未知字段、NaN/Infinity及尾随文本。
2. 验证本文Schema、总action数、枚举和整数范围。
3. 检查类别、幅度、周期在绑定角色上已标定并开放。当前 `natori-demo.v1` 是原生参数能力表，不能据此宣称已有完整语义动作映射。
4. 本步任何两条动作若写入相同原生参数，拒绝，不按数组顺序覆盖或静默混合。
5. 模板按周期和次数展开，逐步拼接、合并同时刻不同通道，转换成原生参数v0.1动作包。必须为尚未开始的通道显式生成等待保持点，为较短并行动作生成结束保持段；原生DSL会跨关键点插值，仅把后续步骤的目标时间后移会造成提前运动。补保持点后仍须满足80ms下限，不能静默修改时序来凑合法关键点。
6. 原样经过现有 ActionContract 的整包验证和宿主会话/角色绑定检查；超长、关键点过密或冲突都拒绝，不偷偷裁剪次数、时长或参数。

第一版支持完整循环、顺序和同时起始。任意重叠偏移、单独等待、保持姿态、渐强/渐弱、实时取消控制、逐周期联动留待后续协议，不通过附加任意字符串绕过结构约束。

机器可读结构见 `action-plan-v0.1.schema.json`。Schema无法表达的跨步骤总action数、通道冲突与编译后原生约束必须由本地编译器检查。`plan-examples/` 中的例子只是结构设计示例。

## 示例输入对应表

| 原始动作描述 | 示例文件 |
| --- | --- |
| 轻轻点两下头。 | `plan-examples/01-gentle-nod-twice.json` |
| 轻轻点两下头，然后眨一下眼。 | `plan-examples/02-nod-then-blink.json` |
| 快速、小幅度地点两下头，同时眨一下眼。 | `plan-examples/03-nod-and-blink.json` |
| 完整地眨两次眼，每次用0.6秒。 | `plan-examples/04-blink-exact-period.json` |
| 点头，同时抖耳。（当前耳朵未标定） | `plan-examples/05-unsupported-ears.json` |
| 不要点头。 | `plan-examples/06-no-action.json` |
