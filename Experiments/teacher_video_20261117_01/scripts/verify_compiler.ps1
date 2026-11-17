$ErrorActionPreference = 'Stop'
$runRoot = Split-Path -Parent $PSScriptRoot
$projectRoot = Split-Path -Parent (Split-Path -Parent $runRoot)
$compiler = 'C:\Program Files\Mono\bin\csc.bat'
$names = @('ActionConfigCompiler.cs','ActionResourceCatalog.cs','ActionContract.cs','ActionPlanCompiler.cs','YukikazeActionCatalog.cs')
foreach ($version in @('baseline','patched')) {
    $sourceRoot = if ($version -eq 'baseline') { Join-Path $runRoot 'input/Assets/Scripts/ActionLanguage' } else { Join-Path $runRoot 'source/csharp' }
    $exePath = Join-Path $PSScriptRoot "compiler_$version.exe"
    $sourceFiles = $names | ForEach-Object { Join-Path $sourceRoot $_ }
    & $compiler /nologo /langversion:9 "/out:$exePath" (Join-Path $PSScriptRoot 'ConfigCompilerProbe.cs') @sourceFiles
    if ($LASTEXITCODE -ne 0) { throw "C# compilation failed: $version" }
    $lines = & $exePath
    $code = $LASTEXITCODE
    $lines | Set-Content -LiteralPath (Join-Path $runRoot "reports/compiler_${version}_checks.jsonl") -Encoding utf8
    $result = $lines[-1] | ConvertFrom-Json
    if ($version -eq 'patched' -and ($code -ne 0 -or $result.failed -ne 0)) { throw 'Patched compiler regression failed' }
    if ($version -eq 'baseline' -and $result.failed -ne 5) { throw 'Baseline no longer reproduces the five documented defects' }
    Write-Output "$version : passed=$($result.passed), failed=$($result.failed)"
}
& (Join-Path $projectRoot '.venv-action-encoder/Scripts/python.exe') (Join-Path $PSScriptRoot 'compiler_audit.py')
if ($LASTEXITCODE -ne 0) { throw 'Corpus compiler audit failed' }
