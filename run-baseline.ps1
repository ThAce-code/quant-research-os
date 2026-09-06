param([switch]$SkipDownload)
$ErrorActionPreference = 'Stop'
$quantPython = Join-Path $env:USERPROFILE 'miniconda3\envs\quant\python.exe'
if (-not (Test-Path -LiteralPath $quantPython)) { throw 'Activate the quant environment and run python scripts/run_baseline.py.' }
$runArgs = @('-u', (Join-Path $PSScriptRoot 'scripts\run_baseline.py'))
if ($SkipDownload) { $runArgs += '--skip-download' }
& $quantPython @runArgs
if ($LASTEXITCODE -ne 0) { throw "Baseline failed (exit $LASTEXITCODE). See experiments status.json/error.txt." }
