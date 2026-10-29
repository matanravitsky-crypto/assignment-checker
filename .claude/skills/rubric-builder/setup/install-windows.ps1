# install-windows.ps1 - install MiKTeX + everything needed to compile the Hebrew XeLaTeX
# rubric, then run check.ps1. Safe to run again: every step skips what is already in place.
# No administrator rights needed (MiKTeX is installed for this user; Perl is optional).
# Run:  powershell -NoProfile -ExecutionPolicy Bypass -File install-windows.ps1 [-NoPerl] [-NoUpdate] [-VSCode]
#   -NoPerl    skip Strawberry Perl (its installer asks for admin rights); build_pdf.py then runs xelatex twice
#   -NoUpdate  skip step 3 (updating every installed MiKTeX package; a fresh install is recent enough)
#   -VSCode    also install the LaTeX Workshop extension for VS Code
param([switch]$NoPerl, [switch]$NoUpdate, [switch]$VSCode)

$ErrorActionPreference = "Continue"
$skillDir = $PSScriptRoot
function Step($msg) { Write-Host "`n=== $msg" -ForegroundColor Cyan }
function Die($msg)  { Write-Host "STOPPED: $msg" -ForegroundColor Red; exit 1 }

function Find-TeXBin {
  $cmd = Get-Command xelatex.exe -ErrorAction SilentlyContinue
  if ($cmd) { return (Split-Path -Parent $cmd.Source) }
  foreach ($c in @("$env:LOCALAPPDATA\Programs\MiKTeX\miktex\bin\x64",
                   "$env:ProgramFiles\MiKTeX\miktex\bin\x64")) {
    if (Test-Path "$c\xelatex.exe") { return $c }
  }
  return $null
}

$hasWinget = [bool](Get-Command winget.exe -ErrorAction SilentlyContinue)

# 1. MiKTeX
Step "0. Python 3"
if (-not (Get-Command python.exe -ErrorAction SilentlyContinue) -or ((python --version 2>&1) -notmatch "Python 3")) {
  if ($hasWinget) { winget install --id Python.Python.3.12 -e --scope user --silent --accept-package-agreements --accept-source-agreements }
  else { Write-Host "Install Python 3 from https://www.python.org/downloads/ (tick 'Add to PATH'), then run again." -ForegroundColor Yellow }
} else { Write-Host "Python present: $(python --version)" }
try { python -m pip install -q pymupdf pillow } catch {}

Step "1. MiKTeX"
$bin = Find-TeXBin
if ($bin -and ($bin -notmatch "MiKTeX")) {
  Die "a different TeX distribution is already installed ($bin). Ask the user whether to keep it (then install only the fonts/packages) or remove it before installing MiKTeX."
}
if ($bin) {
  Write-Host "MiKTeX already installed: $bin"
} else {
  if (-not $hasWinget) { Die "winget is not available. Install MiKTeX by hand from https://miktex.org/download (choose 'only for me'), then run this script again." }
  Write-Host "Installing MiKTeX with winget (a few minutes)..."
  winget install --id MiKTeX.MiKTeX -e --scope user --silent --accept-package-agreements --accept-source-agreements
  $bin = Find-TeXBin
  if (-not $bin) {
    Write-Host "Retrying without --scope user..."
    winget install --id MiKTeX.MiKTeX -e --silent --accept-package-agreements --accept-source-agreements
    $bin = Find-TeXBin
  }
  if (-not $bin) { Die "MiKTeX did not install. Install it by hand from https://miktex.org/download ('only for me'), then run this script again." }
  Write-Host "MiKTeX installed: $bin"
}
# The installer adds MiKTeX to PATH for NEW terminals only; use the full path here.
$env:PATH = "$bin;$env:PATH"
$miktex = Join-Path $bin "miktex.exe"
$initexmf = Join-Path $bin "initexmf.exe"

# 2. Never ask before installing a missing package (a question would stall Claude Code).
Step "2. Automatic installation of missing packages"
& $initexmf --set-config-value="[MPM]AutoInstall=1"
Write-Host ("AutoInstall = " + (& $initexmf --show-config-value="[MPM]AutoInstall"))

# 3. Bring MiKTeX up to date (a fresh install can be months old; mixed old/new
#    packages are the usual cause of strange errors).
Step "3. Updating MiKTeX packages (can take several minutes)"
& $miktex packages update-package-database
if ($NoUpdate) { Write-Host "Skipped (-NoUpdate)." }
else {
  & $miktex packages update
  if ($LASTEXITCODE -ne 0) {
    Write-Host "Update reported an error; this is normal right after MiKTeX updated itself. Running it once more..."
    & $miktex packages update
  }
}

# 4. The packages the course documents use, including the Culmus Hebrew fonts.
Step "4. Installing the course packages (packages.txt)"
& $miktex packages require --package-id-file (Join-Path $skillDir "packages.txt")
if ($LASTEXITCODE -ne 0) { Write-Host "Some packages failed to install; the test compile below will show whether it matters." -ForegroundColor Yellow }

# 5. Refresh the file name database and the font cache so XeTeX finds "David CLM".
Step "5. Refreshing file and font caches"
& $initexmf --update-fndb
$fc = Join-Path $bin "miktex-fc-cache.exe"
if (Test-Path $fc) { & $fc -f | Out-Null }

# 6. latexmk is a Perl script; MiKTeX does not ship Perl.
Step "6. Perl (needed by latexmk; optional)"
$perl = Get-Command perl.exe -ErrorAction SilentlyContinue
if ($NoPerl -and -not $perl) { Write-Host "Skipped (-NoPerl): build_pdf.py runs xelatex twice instead of latexmk."; $perl = $true }
if (-not $perl -and (Test-Path "C:\Strawberry\perl\bin\perl.exe")) { $env:PATH = "C:\Strawberry\perl\bin;C:\Strawberry\c\bin;$env:PATH"; $perl = $true }
if ($perl) { Write-Host "Perl found." }
elseif ($hasWinget) {
  winget install --id StrawberryPerl.StrawberryPerl -e --silent --accept-package-agreements --accept-source-agreements
  $env:PATH = "C:\Strawberry\perl\bin;C:\Strawberry\c\bin;$env:PATH"
} else { Write-Host "Perl missing and winget unavailable: install Strawberry Perl from https://strawberryperl.com" -ForegroundColor Yellow }

# 7. Optional: VS Code LaTeX Workshop (the repo's .vscode/settings.json has the xelatex recipe).
if ($VSCode) {
  Step "7. VS Code LaTeX Workshop extension"
  if (Get-Command code -ErrorAction SilentlyContinue) { code --install-extension James-Yu.latex-workshop }
  else { Write-Host "'code' command not found; install the extension 'LaTeX Workshop' from inside VS Code." -ForegroundColor Yellow }
}

# 8. Verify.
Step "Verifying"
& powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot "check.ps1")
$rc = $LASTEXITCODE
Write-Host "`nOpen a NEW terminal so that xelatex is on PATH there."
exit $rc
