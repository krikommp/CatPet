# Gemini 第 9 轮辅助审计与隔离修复

本目录是辅助工作区。用户最新指令为“Gemini 在训练第 9 轮，你辅助”。本会话没有训练新权重，没有改共享源码、共享语料、录像队列、在线服务或 `v02_latest`。这里的修复已在实验副本执行验证，尚未合入 Gemini 正在使用的入口。

## 已固定的输入与并发边界

- 初始一致性基线：checkpoint `8cfb7a72bdac`，2591/321/320；权重、代码、3232 条语料及资源源码均保存 hash。见 `snapshot_manifest.json`、`baseline/`、`input/original_python/`。
- 17:47 观察到 Gemini 训练进程启动，命令使用共享语料与 `v02_latest`。17:53 保存的独立语料观测快照有 3290 条，比初始快照新增或变动 58 条。运行进程已加载哪一版本的语料不能由后续磁盘文件证明。
- `input/round9_observed/` 仅用于指出第 9 轮的潜在问题；不替换运行任务的数据。
- 18:02 训练进程不再存在，磁盘产生 checkpoint `838f2c1ac110`，2649/315/326，已一致性复制到 `round9_checkpoint/`。这是 Gemini 的产物，本会话只读评估；不据此推断 Gemini 整个工作已结束。见 `reports/round9_checkpoint_snapshot.json`。
- 人设已阅读并复制：`Docs/ActionLanguage/personas/gemini-cyber-cat.md`，SHA256 `56b4364bf1c7da22e6b6faadc094299e570f93375e0acb78f510c360d614aa41`。文件已到位，评分规范尚未冻结；没有据此追认旧标签或自然度分数。

## 可审查的修复

1. `source/action_config_schema.py`、`source/encoder.py`：并行资源冲突、空 execute、非法活动槽和次数明确作为技术错误。取消换成无关动作及把空 execute 当 none；参数头根据最终预测资源计算。旧解码行为仅用于显式基线诊断。角色前缀由新模型 manifest 绑定，旧权重仍使用原文。
2. `source/train_action_config.py`：固定外部 split，全局组/规范同文防交叉；区分 instruction/dialogue；人设 hash、来源、审核状态、真实编译报告与标签关联门禁；输出限定本实验且不覆盖非空 checkpoint。选模记录实际预测资源下的结构、各类误执行与技术拒绝，监督训练本体仍是 MiniRBT。没有启动 epoch。
3. `source/csharp/ActionConfigCompiler.cs`：过短正数 hold 明确拒绝，不归零；不夹断进入/返回时间来改写比例；正数 hold 缺少资源保持端点时拒绝。保留真实原生校验器最终检查。没有改变共享资源映射或正式标定状态。
4. `scripts/dataset_*` 与 `data/`：分离自由台词与准确动作指令，隔离不支持动作近似、连续参数矛盾、数字/逐次关系不满足和真实编译失败；同文、参数变体、源组及保守语义族并集合并，固定新切分。历史记录始终是无视频审核的冷启动来源。

这些实验文件不是可以直接覆盖整个在线服务的部署包。尤其是新 `input_role` 协议、数据来源门禁和固定切分需要调用方同时适配；当前正式客户端没有被本会话改动。

## 真实验证与证据

- Python推理/训练门禁 22/22，数字/数据隔离 57/57，C#编译定向 30/30；合计109项针对性检查通过。人设已到位但预审数据仍被训练门禁拒绝，未创建新checkpoint。
- 最终冷启动待审池1336条，预定893/68/375；隔离1896条包含语法覆盖不足、待裁决及已确认错误，不能把全部隔离项称为错标。训练缺ambiguous类，全部 `training_eligible=false`，不具备直接训练条件。
- 同一28条诊断中，Gemini第9轮执行结构11/14，冻结基线10/14；两版精确时长均0/8，逐次/渐变关系5/7降至3/7。第9轮仍有7/14非执行题误执行。严格版本19/28技术拒绝，只代表拦截行为，不代表更准。详见 `reports/round9_comparison.md`。
- C# 定向检查：原实现 25/30，修复后 30/30。检查包括 0/30/79/80/120ms hold、逐次时长和峰值幅度、顺序锚点、次数、并行冲突、候选资源正式门禁。执行环境是 Mono C#，编译并运行项目真实 parser/catalog/native validator 源码；这不是 Unity 画面验证。
- 3232 条历史语料经原 C# 编译器有 45 条 Core 范围失败；严格修复后 2441 条通过，549 条短 hold、200 条缺保持相位、42 条 Core 越界被拒绝（按首个错误统计）。不能用原编译成功掩盖标签被改写。
- 3290 条第 9 轮观测语料按旧划分函数重算，有 train/val 同文16个、train/test20个、val/test7个。原编译器有54条 Core 越界；见 `reports/round9_observation.json`。这是磁盘快照审计，不宣称当前进程使用了这些字节。
- 视频盘点：90目录、90 meta、88 MP4全部可解码。独立视觉子代理实际查看24段全部626帧，确认7条硬错误，10条部分视觉确认，7条无法确认。训练准入0，风格/自然度评分0。见 `reports/video_objective_audit.md` 与 `reviews/video_objective_audit.jsonl`。
- 视频中缺资源内容hash、完整播放/编码器关闭的可靠绑定及实测参数时间轨迹；`native_json`是目标轨迹。24条都保留待新candidate_id重播，不能补造历史证据。

## 人设需要对齐的客观边界

- `cheer` 幅度1.20使8.5的原生峰值达到10.2，超过Core上限10；应选择合法候选并明确记录，不能静默夹断。
- `blink`资源最高1800ms；“bow+blink 1700–1950ms”不能把1950直接给眨眼。
- 当前 `tilt` 每次均为同方向侧倾再回正，重复两次不等于左右交替摇摆。
- 明确“摇尾巴”的动作指令不能用smile+cheer冒充。自由台词的情绪表演可另定策略，但必须有显式角色和可审查的标签规则。
- 当前只有blink正式标定。其他资源的实验预览、语料存在和编译通过都不构成正式标定。

## 复现入口（从项目根目录执行）

```powershell
& Experiments/teacher_video_20261117_01/scripts/verify_compiler.ps1
.\.venv-action-encoder\Scripts\python.exe Experiments/teacher_video_20261117_01/scripts/round9_observation.py
.\.venv-action-encoder\Scripts\python.exe Experiments/teacher_video_20261117_01/scripts/train_verify.py checks
```

第一条重新编译并执行真实C#检查与3232条编译审计；第二条只审计冻结的3290条观测快照；第三条只运行Python修复验证。均不训练模型。详细数据清洗、数字检查及只读模型预测命令见 `reports/dataset_handoff.md`、`reports/code_audit.md`（以实际文件为准）。

## 后续条件

先由 Gemini 审查本目录补丁与失败清单，在其第9轮工作结束后按适用部分合入。冻结人设评价规范并补足独立语义族，完成真实版本绑定的回放/参数测量与独立评价，再制作训练快照。未准入视频不得混入 AI 通过池，固定测试族不得回流训练。本会话没有自行训练新模型，只审计 Gemini 权重与冻结基线，没有启用变更。
