param([int]$Port = 8765, [switch]$Background)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$pythonExe = Join-Path $projectRoot '.venv-action-encoder/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonExe)) {
    throw 'Run Tools/ActionEncoder/bootstrap.ps1 first.'
}
$serverPath = Join-Path $PSScriptRoot 'server.py'
if ($Background) {
    $runDir = Join-Path $projectRoot '.action-encoder'
    New-Item -ItemType Directory -Path $runDir -Force | Out-Null
    $statePath = Join-Path $runDir 'server-process.json'
    if (Test-Path -LiteralPath $statePath) {
        $state = Get-Content -LiteralPath $statePath -Raw | ConvertFrom-Json
        $existing = Get-Process -Id $state.pid -ErrorAction SilentlyContinue
        if ($existing -and $existing.StartTime.ToUniversalTime().Ticks.ToString() -eq $state.start_ticks) {
            throw 'A background encoder already runs. Use stop.ps1 before starting another.'
        }
    }
    $process = Start-Process -FilePath $pythonExe -ArgumentList @('"' + $serverPath + '"', '--port', $Port) -WorkingDirectory $projectRoot -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runDir 'server.stdout.log') -RedirectStandardError (Join-Path $runDir 'server.stderr.log')
    @{pid=$process.Id; start_ticks=$process.StartTime.ToUniversalTime().Ticks.ToString(); port=$Port} | ConvertTo-Json | Set-Content -LiteralPath $statePath -Encoding UTF8
    Write-Output "Started background encoder PID $($process.Id). Health: http://127.0.0.1:$Port/health"
    Write-Output 'Logs: .action-encoder/server.*.log; stop with Tools/ActionEncoder/stop.ps1'
    return
}
& $pythonExe $serverPath --port $Port
if ($LASTEXITCODE -ne 0) { throw "Encoder exited with code $LASTEXITCODE" }
