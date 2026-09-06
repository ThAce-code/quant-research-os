param([string]$Factor)
$ErrorActionPreference = 'Stop'
$quantPython = Join-Path $env:USERPROFILE 'miniconda3\envs\quant\python.exe'
if (-not (Test-Path -LiteralPath $quantPython)) { throw 'The quant Python environment is required.' }
$factorArgs = @('-u', (Join-Path $PSScriptRoot 'scripts\run_factors.py'))
if ($Factor) { $factorArgs += @('--factor', $Factor) }
& $quantPython @factorArgs
if ($LASTEXITCODE -ne 0) { throw "Factor engine failed (exit $LASTEXITCODE). Inspect the printed run directory." }
