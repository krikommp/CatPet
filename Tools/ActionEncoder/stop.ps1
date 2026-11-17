$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$statePath = Join-Path $projectRoot '.action-encoder/server-process.json'
if (-not (Test-Path -LiteralPath $statePath)) { Write-Output 'No managed background encoder.'; return }
$state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
$process = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
if ($process) {
    $expectedExe = (Join-Path $projectRoot '.venv-action-encoder/Scripts/python.exe').Replace('/', '\')
    if ($process.StartTime.ToUniversalTime().Ticks.ToString() -ne $state.start_ticks -or $process.Path -ne $expectedExe) {
        throw 'Process identity differs from the launched encoder; no process was stopped.'
    }
    Stop-Process -Id $process.Id
    Write-Output "Stopped encoder PID $($process.Id)."
}
Remove-Item -LiteralPath $statePath
