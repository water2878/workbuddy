$gitExe = "C:\Program Files\Git\bin\git.exe"
$repoDir = "C:\Users\Lenovo\WorkBuddy\Claw"
$logFile = "$repoDir\logs\git_sync.log"

$timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"

function Log($msg) {
    Add-Content -Path $logFile -Value "[$timestamp] $msg" -Encoding UTF8
}

Log "=== Sync started ==="

Set-Location $repoDir

$hasChanges = & $gitExe status --porcelain 2>&1
if ($LASTEXITCODE -ne 0) {
    Log "ERROR: git status failed"
    exit 1
}

if (-not $hasChanges) {
    Log "No changes to commit"
} else {
    & $gitExe add --all -- ':!nul' 2>&1 | ForEach-Object { Log $_ }
    $commitMsg = "auto-sync: $timestamp"
    & $gitExe commit -m $commitMsg 2>&1 | ForEach-Object { Log $_ }
    if ($LASTEXITCODE -eq 0) {
        Log "Committed: $commitMsg"
    } else {
        Log "Nothing to commit (possibly empty)"
    }
}

& $gitExe push origin HEAD 2>&1 | ForEach-Object { Log $_ }
if ($LASTEXITCODE -eq 0) {
    Log "Push succeeded"
} else {
    Log "ERROR: Push failed"
}

Log "=== Sync finished ==="
