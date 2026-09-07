param(
    [ValidateSet('Start','Status','Stop')][string]$Action = 'Status',
    [string]$ServerPath,
    [string]$ModelPath
)
$ErrorActionPreference = 'Stop'
$taskRoot = Split-Path -Parent $PSScriptRoot
$taskRuntime = Join-Path $taskRoot 'data/m3_local_llm'
$taskState = Join-Path $taskRuntime 'service.json'
$taskPort = 18341
New-Item -ItemType Directory -Force -Path $taskRuntime | Out-Null

function Get-OwnedModel {
    if (-not (Test-Path -LiteralPath $taskState)) { return $null }
    $saved = Get-Content -LiteralPath $taskState -Raw | ConvertFrom-Json
    $process = Get-Process -Id $saved.pid -ErrorAction SilentlyContinue
    if ($null -eq $process) { return $null }
    if ($process.Path -ne $saved.executable -or $process.StartTime.ToUniversalTime().Ticks -ne ([datetime]$saved.process_start_utc).ToUniversalTime().Ticks) {
        throw 'Saved process identity does not match; refusing to control another process.'
    }
    return $process
}

$taskProcess = Get-OwnedModel
if ($Action -eq 'Stop') {
    if ($null -ne $taskProcess) {
        Stop-Process -InputObject $taskProcess
        if (-not $taskProcess.WaitForExit(5000)) { throw 'Owned process has not exited yet.' }
    }
    Write-Output 'Owned model service stopped; model files and evidence retained.'
    exit 0
}
if ($Action -eq 'Start' -and $null -eq $taskProcess) {
    if (-not $ServerPath -or -not $ModelPath) { throw 'Start requires explicit -ServerPath and -ModelPath; no automatic download.' }
    $taskServer = (Resolve-Path -LiteralPath $ServerPath).Path
    $taskModel = (Resolve-Path -LiteralPath $ModelPath).Path
    if ((Get-Item -LiteralPath $taskServer).PSIsContainer -or (Get-Item -LiteralPath $taskModel).PSIsContainer) { throw 'Paths must identify files.' }
    if (Get-NetTCPConnection -LocalPort $taskPort -State Listen -ErrorAction SilentlyContinue) { throw 'Port is already in use; no existing service will be replaced.' }
    $taskArguments = @('-m', ('"' + $taskModel + '"'), '--host', '127.0.0.1', '--port', "$taskPort",
        '--alias', 'm3-gemma4-e4b', '-c', '8192', '-np', '1', '-ngl', 'auto', '-ctk', 'q8_0', '-ctv', 'q8_0', '--reasoning', 'off')
    $taskProcess = Start-Process -FilePath $taskServer -ArgumentList $taskArguments -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $taskRuntime 'service.stdout.log') -RedirectStandardError (Join-Path $taskRuntime 'service.stderr.log')
    @{ pid=$taskProcess.Id; executable=$taskServer; model=$taskModel; arguments=$taskArguments;
       process_start_utc=$taskProcess.StartTime.ToUniversalTime().ToString('o') } | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $taskState -Encoding utf8
    $taskDeadline = (Get-Date).AddSeconds(45)
    do {
        if ($taskProcess.HasExited) { throw 'Model service exited; inspect service.stderr.log.' }
        try { $taskHealth = Invoke-RestMethod "http://127.0.0.1:$taskPort/health" -TimeoutSec 2; break }
        catch { Start-Sleep -Milliseconds 500 }
    } while ((Get-Date) -lt $taskDeadline)
}
if ($null -eq $taskProcess) { Write-Output 'Owned model service is not running.'; exit 0 }
$taskHealth = Invoke-RestMethod "http://127.0.0.1:$taskPort/health" -TimeoutSec 3
$taskProbe = @{model='m3-gemma4-e4b'; messages=@(@{role='user';content='Return only {"status":"ok"}.'});
    max_tokens=32; temperature=0; response_format=@{type='json_object'}} | ConvertTo-Json -Depth 5
$taskResponse = Invoke-RestMethod "http://127.0.0.1:$taskPort/v1/chat/completions" -Method Post -ContentType 'application/json' -Body $taskProbe -TimeoutSec 30
if ($taskResponse.choices[0].finish_reason -ne 'stop' -or (($taskResponse.choices[0].message.content | ConvertFrom-Json).status -ne 'ok')) { throw 'Inference probe failed.' }
@{state='READY';pid=$taskProcess.Id;health=$taskHealth;inference='PASS';purpose='Connectivity probe; no research hypotheses or numerical evaluation'} | ConvertTo-Json -Depth 5
