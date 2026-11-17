# 冻结实验使用的 FFmpeg

`ffmpeg-win-x86_64-v7.1.exe` 是原电脑 `imageio-ffmpeg 0.6.0` 安装目录中的精确副本，用于恢复旧实验的视频证据校验。

- 文件大小：87,638,016 字节。
- SHA-256：`2ce797a0f88d7f067180338fb227f7b1928ea727bd9a4d7a1d022f7c52af71a3`。
- 原路径及哈希记录在 `Experiments/teacher_round_20261117_184246/frozen_snapshot/manifest.json`。
- 随附 `LICENSE-imageio-ffmpeg.txt` 为原 Python 包的许可说明；FFmpeg 二进制自身的编译与许可信息可用 `-version` 和 `-L` 查看。

当前校验器严格读取冻结清单中的 FFmpeg 绝对路径。换机后，从项目根目录运行以下 PowerShell 命令，将已核验的副本恢复到该路径（需要对目标目录有写入权限）。已有不同内容的文件不会被覆盖。

```powershell
$snapshot = Get-Content 'Experiments/teacher_round_20261117_184246/frozen_snapshot/manifest.json' -Raw | ConvertFrom-Json
$bundled = Join-Path (Get-Location) 'Tools/Video/ffmpeg-win-x86_64-v7.1.exe'
if ((Get-FileHash -LiteralPath $bundled -Algorithm SHA256).Hash -ne $snapshot.ffmpeg_sha256) {
    throw '仓库中的 FFmpeg 哈希不匹配。'
}
if (Test-Path -LiteralPath $snapshot.ffmpeg_path) {
    if ((Get-FileHash -LiteralPath $snapshot.ffmpeg_path -Algorithm SHA256).Hash -ne $snapshot.ffmpeg_sha256) {
        throw '目标路径已有不同的 FFmpeg；未覆盖，请检查。'
    }
} else {
    New-Item -ItemType Directory -Path (Split-Path -Parent $snapshot.ffmpeg_path) -Force -ErrorAction Stop | Out-Null
    Copy-Item -LiteralPath $bundled -Destination $snapshot.ffmpeg_path -ErrorAction Stop
}
```

恢复后可运行 `retrain_and_eval.py validate --snapshot-manifest Experiments/teacher_round_20261117_184246/frozen_snapshot/manifest.json` 重新校验。使用项目 `.venv-action-encoder/Scripts/python.exe` 启动该 Python 脚本。

新实验的 `retrain_and_eval.py prepare` 支持显式传入 `--ffmpeg Tools/Video/ffmpeg-win-x86_64-v7.1.exe`。现有冻结清单继续保持原样；如需跨平台或任意用户路径迁移，应另行实现保持哈希约束的重定位支持。
