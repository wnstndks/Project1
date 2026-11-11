# Back up the SQLite ledger with backend/scripts/backup_db.py (online backup, integrity check,
# keeps the newest N copies). Safe while the server is running. ASCII only on purpose:
# Windows PowerShell 5.1 misreads UTF-8 files without a BOM.
#
#   .\scripts\backup-db.ps1                                  # app database -> %USERPROFILE%\asset-manager-backups
#   .\scripts\backup-db.ps1 -DestDir D:\backups -Keep 30
#   .\scripts\backup-db.ps1 -Source C:\path\to\other.db
#
# The default destination is outside the repository on purpose: backups hold the real ledger.
param(
    [string]$DestDir = (Join-Path $env:USERPROFILE 'asset-manager-backups'),
    [ValidateRange(1, 100000)]
    [int]$Keep = 14,
    [string]$Source = ''
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$backend = Join-Path $root 'backend'

# The script runs from backend/, so relative paths are made absolute against the folder
# the caller is in (works for a destination that does not exist yet).
$paths = $ExecutionContext.SessionState.Path
$DestDir = $paths.GetUnresolvedProviderPathFromPSPath($DestDir)

# `py -3.11 -m uv`: with VIRTUAL_ENV set in the shell, `py -m uv` fails (ISSUE-032).
$uvArgs = @('-3.11', '-m', 'uv', 'run', 'python', 'scripts/backup_db.py', '--dest-dir', $DestDir, '--keep', "$Keep")
if ($Source) {
    # A sqlite:/// URL is passed through as it is; a file path is made absolute.
    if ($Source -notmatch '://') {
        $Source = $paths.GetUnresolvedProviderPathFromPSPath($Source)
    }
    $uvArgs += @('--source', $Source)
}

Push-Location $backend
try {
    & py @uvArgs
    $code = $LASTEXITCODE
}
finally {
    Pop-Location
}
exit $code
