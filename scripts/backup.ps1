# Backs up the job-trailers-resume data that only lives on this machine:
# the SQLite history, CSV export, and every generated resume/cover-letter/mail-draft
# folder. Run manually, or schedule via Windows Task Scheduler.
#
# Usage: powershell -File scripts\backup.ps1

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$BackupRoot = "D:\JobTrailerBackups"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$DestDir = Join-Path $BackupRoot $Timestamp

$SourcePaths = @(
    (Join-Path $ProjectRoot "backend\data"),
    (Join-Path $ProjectRoot "backend\original"),
    (Join-Path $ProjectRoot "backend\trailerd"),
    (Join-Path $ProjectRoot "backend\online-platform")
)

New-Item -ItemType Directory -Force -Path $BackupRoot | Out-Null
New-Item -ItemType Directory -Force -Path $DestDir | Out-Null

foreach ($src in $SourcePaths) {
    if (Test-Path $src) {
        $name = Split-Path -Leaf $src
        Copy-Item -Path $src -Destination (Join-Path $DestDir $name) -Recurse -Force
        Write-Host "Copied $src"
    } else {
        Write-Host "Skipped (not found): $src"
    }
}

# Compress into a single zip and drop the loose folder copy, so each backup is one file.
$ZipPath = "$DestDir.zip"
Compress-Archive -Path (Join-Path $DestDir "*") -DestinationPath $ZipPath -Force
Remove-Item -Path $DestDir -Recurse -Force

Write-Host "Backup written to $ZipPath"

# Keep only the most recent 14 backups so this doesn't grow forever.
$KeepCount = 14
$AllBackups = Get-ChildItem -Path $BackupRoot -Filter "*.zip" | Sort-Object LastWriteTime -Descending
if ($AllBackups.Count -gt $KeepCount) {
    $ToDelete = $AllBackups | Select-Object -Skip $KeepCount
    foreach ($old in $ToDelete) {
        Remove-Item $old.FullName -Force
        Write-Host "Removed old backup: $($old.Name)"
    }
}
