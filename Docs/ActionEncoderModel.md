# 本地 MiniRBT 模型来源与边界

本项目使用 `hfl/minirbt-h256` 作为本地中文文本编码器。它把文本转换成 token 隐藏状态以及池化向量；当前权重没有经过本项目的动作分类、次数识别或动作参数回归训练，不能把编码成功表述为已经学会生成动作。

## 固定来源

| 项目 | 值 |
| --- | --- |
| 官方模型 | [hfl/minirbt-h256](https://huggingface.co/hfl/minirbt-h256) |
| 固定 revision | `446e1b4012b10946f479563005700c54c9db3f7c` |
| 原项目 | [iflytek/MiniRBT](https://github.com/iflytek/MiniRBT) |
| 许可证 | Apache-2.0，来自固定 revision 的官方模型卡 front matter |
| 原始权重 | `pytorch_model.bin`，41,514,155 字节 |
| 原始权重 SHA-256 | `6728ca573fd5197f28198eb7e6119a76e4d5dc626f953fca8c0dc5ba2798f9fc` |
| 结构 | BERT，6 层，隐藏维度 256，8 个注意力头，FFN 1024，词表 21,128 |
| 上限 | 原模型 512 个位置；服务可设更短输入上限 |

下载文件固定为 `config.json`、`vocab.txt`、`README.md` 与原始权重；不执行仓库代码。配置、词表、模型卡按固定 Git blob hash 校验；权重 SHA-256 已对照[官方权重页面](https://huggingface.co/hfl/minirbt-h256/blob/446e1b4012b10946f479563005700c54c9db3f7c/pytorch_model.bin)。官方说明要求使用 `BertTokenizer` / `BertModel`，不是 `RobertaTokenizer` / `RobertaModel`。

2026-11-16 接入时，本机连接 `huggingface.co` 超时，下载使用 `https://hf-mirror.com` 镜像，仍固定相同 revision 并执行上述 hash 校验。镜像是传输来源，模型来源仍是 HFL 官方仓库。每个实际下载 URL 与官方 URL 都记录在本地 manifest。

## 目录与复现

运行目录为项目根目录 `D:\UnityProjects\Pet\PetLive2d`。

```powershell
# 下载固定版本，自动执行受限权重转换；环境由 bootstrap.ps1 安装。
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/download_model.py --endpoint https://hf-mirror.com

# 网络可直连官方仓库时，省略 --endpoint 即可。
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/download_model.py

# 已下载原始文件后，完全离线重新转换。
.\.venv-action-encoder\Scripts\python.exe Tools/ActionEncoder/download_model.py --convert-only
```

模型保存在 `.cache/action-encoder/model/`：

- `config.json`、`vocab.txt`、`README.md`：官方固定版本原文件。
- `source/pytorch_model.bin`：保留官方原始权重，便于校验和复现。
- `source-manifest.json`：来源、版本、许可证、下载 URL 与原文件 hash。
- `model.safetensors`：本机转换后的纯编码器权重。
- `manifest.json`：可加载文件的 SHA-256、大小，以及转换方式和 Torch 版本。

官方下载只有 PyTorch `.bin`，没有 safetensors。本地转换使用已修补的 PyTorch（项目固定版本为 `2.9.1+cpu`）和显式 `torch.load(..., map_location="cpu", weights_only=True)`；不允许 `weights_only=False` 或额外 pickle globals。转换保留原始 `bert.*` 编码器参数并去掉 `bert.` 前缀，省去预训练 MLM 词表预测头和 pooler，不创建新任务头。旧权重中的确定性 `position_ids` 缓冲区先核对等于 `0..511`，再省去，由当前 Transformers 按相同规则生成。后续加载只读取 `model.safetensors`，使用 `local_files_only=True`。

## 本次验证范围与后续边界

本轮按用户最终要求只安装环境：检查依赖可导入、下载文件 hash、受限权重转换和 `BertModel` 权重完整加载。暂不运行文本前向推理、性能测试、HTTP 服务或 Unity 联调。成功加载的实际结果应以本轮交付记录为准。

预训练文本向量不保证动作相似度可直接使用，均值池化也不是已训练的句向量检索模型。若要得到可靠的动作槽位、类别、阶段、次数和连续参数，需要合格样本、训练及独立评测；本次没有启动训练。

文本推理服务、视频评审、修改建议、动作候选搜索与训练样本回收已按用户本轮要求暂缓。环境安装不代表动作生成或视频评审闭环已经完成。
