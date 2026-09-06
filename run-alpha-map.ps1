$ErrorActionPreference = 'Stop'
$quantPython = Join-Path $env:USERPROFILE 'miniconda3\envs\quant\python.exe'
& $quantPython -u (Join-Path $PSScriptRoot 'scripts\run_alpha_map.py')
if ($LASTEXITCODE -ne 0) { throw 'Alpha158 map failed; inspect the printed run directory.' }
