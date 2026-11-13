# Installs the exercise-grader skill from its ZIP into the user's Claude skills folder.
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1 -Zip <path to exercise-grader.zip> [-Skills <folder>]
# Creates the skills folder if missing. An existing exercise-grader is moved to ..\skill-backups\exercise-grader-<date>,
# never deleted.
param(
  [Parameter(Mandatory = $true)][string]$Zip,
  [string]$Skills = (Join-Path $env:USERPROFILE '.claude\skills')
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Zip)) { Write-Output "ERROR: zip not found: $Zip"; exit 1 }

$tmp = Join-Path $env:TEMP ("exercise-grader-install-" + [guid]::NewGuid().ToString('N').Substring(0, 8))
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
  Expand-Archive -LiteralPath $Zip -DestinationPath $tmp -Force
  $src = Get-ChildItem -LiteralPath $tmp -Recurse -Filter 'SKILL.md' | Where-Object { $_.Directory.Name -eq 'exercise-grader' } | Select-Object -First 1
  if (-not $src) { Write-Output "ERROR: no exercise-grader\SKILL.md inside the zip"; exit 1 }

  New-Item -ItemType Directory -Force -Path $Skills | Out-Null
  $dest = Join-Path $Skills 'exercise-grader'
  if (Test-Path -LiteralPath $dest) {
    # Outside the skills folder: a copy inside it would show up as a second skill with the same name
    $bak = Join-Path (Split-Path $Skills -Parent) 'skill-backups'
    New-Item -ItemType Directory -Force -Path $bak | Out-Null
    $old = Join-Path $bak ('exercise-grader-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))
    Move-Item -LiteralPath $dest -Destination $old
    Write-Output "kept the previous version as: $old"
  }
  Copy-Item -LiteralPath $src.Directory.FullName -Destination $dest -Recurse
  Write-Output "installed: $dest"
} finally {
  Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
