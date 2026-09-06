$ErrorActionPreference = 'Stop'
$quantPython = Join-Path $env:USERPROFILE 'miniconda3\envs\quant\python.exe'
& $quantPython -u (Join-Path $PSScriptRoot 'scripts\run_m2.py')
if ($LASTEXITCODE -ne 0) { throw 'M2 failed; inspect the printed run folder.' }
