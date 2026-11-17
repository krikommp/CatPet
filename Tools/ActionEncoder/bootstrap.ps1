[CmdletBinding()]
param(
    [string]$Python = 'python',
    [string]$ModelEndpoint = 'https://huggingface.co',
    [switch]$SkipModelDownload
)

$ErrorActionPreference = 'Stop'
$projectRoot = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
$venvRoot = Join-Path $projectRoot '.venv-action-encoder'
$venvPython = Join-Path $venvRoot 'Scripts/python.exe'
$cacheRoot = Join-Path $projectRoot '.cache/action-encoder'
$pipCache = Join-Path $cacheRoot 'pip'
$env:HF_HOME = Join-Path $cacheRoot 'huggingface'
$env:HF_HUB_DISABLE_TELEMETRY = '1'
$env:HF_HUB_DISABLE_IMPLICIT_TOKEN = '1'

function Assert-LastExitCode([string]$Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed with exit code $LASTEXITCODE." }
}

New-Item -ItemType Directory -Path $cacheRoot -Force | Out-Null
if (-not (Test-Path -LiteralPath $venvPython)) {
    & $Python -c 'import sys; assert sys.version_info[:2] == (3,11), "Use Python 3.11 for this pinned environment."'
    Assert-LastExitCode 'Python version check'
    & $Python -m venv $venvRoot
    Assert-LastExitCode 'Virtual environment creation'
}
& $venvPython -c 'import sys; assert sys.version_info[:2] == (3,11), "Existing environment must use Python 3.11."'
Assert-LastExitCode 'Virtual environment version check'

# Skip the remote Torch index entirely when the pinned wheel is already installed.
$installedTorch = & $venvPython -c 'import importlib.metadata as m; print(next((d.version for d in m.distributions() if d.metadata["Name"].lower() == "torch"), "missing"))'
Assert-LastExitCode 'Installed Torch version check'
if ($installedTorch -ne '2.9.1+cpu') {
    if (Get-Command uv -ErrorAction SilentlyContinue) {
        & uv pip install --python $venvPython --cache-dir (Join-Path $cacheRoot 'uv') --no-deps 'torch==2.9.1+cpu' --index-url 'https://download.pytorch.org/whl/cpu'
    } else {
        & $venvPython -m pip install --disable-pip-version-check --cache-dir $pipCache --timeout 60 --retries 3 --no-deps 'torch==2.9.1+cpu' --index-url 'https://download.pytorch.org/whl/cpu'
    }
    Assert-LastExitCode 'PyTorch CPU installation'
}
# Pinned official PyPI JSON metadata + SHA256 checked wheels avoid slow Simple index requests.
& $venvPython (Join-Path $PSScriptRoot 'install_dependencies.py')
Assert-LastExitCode 'Encoder dependency installation'
& $venvPython -m pip check
Assert-LastExitCode 'Dependency consistency check'
& $venvPython -c 'import json,torch,transformers; from transformers import BertModel,BertTokenizer; print(json.dumps({"torch":torch.__version__,"transformers":transformers.__version__,"cuda_available":torch.cuda.is_available(),"default_device":"cpu"}))'
Assert-LastExitCode 'Encoder dependency import check'

if (-not $SkipModelDownload) {
    & $venvPython (Join-Path $PSScriptRoot 'download_model.py') --endpoint $ModelEndpoint
    Assert-LastExitCode 'Pinned model download and verification'
}
Write-Output "Ready: $venvPython"
