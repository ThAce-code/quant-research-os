$ErrorActionPreference = 'Stop'
$quantPython = Join-Path $env:USERPROFILE 'miniconda3\envs\quant\python.exe'
& $quantPython -u (Join-Path $PSScriptRoot 'scripts\run_quarterly.py')
if ($LASTEXITCODE -ne 0) { throw 'Quarterly run failed; cached requests are retained for resumption.' }
