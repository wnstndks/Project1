# 개발용 백엔드 서버를 8001번 포트에서 (재)시작한다.
# 이미 8001번을 듣고 있는 프로세스가 있으면 먼저 끝낸다. 로그는 backend/.dev-backend.log 에 쌓인다.
# 사용: 프로젝트 루트에서  .\scripts\dev-backend.ps1
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'

$listening = Get-NetTCPConnection -LocalPort 8001 -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listening) {
    Write-Host "8001번을 쓰는 프로세스($($listening.OwningProcess))를 끝냅니다."
    Stop-Process -Id $listening.OwningProcess -Force -Confirm:$false
    Start-Sleep -Seconds 2
}

$log = Join-Path $backend '.dev-backend.log'
# 셸에 VIRTUAL_ENV가 잡혀 있으면 `py -m uv`가 실패하므로 `py -3.11 -m uv`를 쓴다(ISSUE-032).
Start-Process -FilePath 'py' `
    -ArgumentList '-3.11', '-m', 'uv', 'run', 'uvicorn', 'app.main:app', '--port', '8001' `
    -WorkingDirectory $backend `
    -RedirectStandardOutput $log `
    -RedirectStandardError (Join-Path $backend '.dev-backend.err.log') `
    -WindowStyle Hidden
Write-Host "백엔드를 시작했습니다: http://localhost:8001/docs (로그: $log)"
