# check.ps1 - diagnose the Hebrew XeLaTeX setup on Windows (MiKTeX) and compile the smoke test.
# Read-only except for build files written to a temp folder.
# Run:  powershell -NoProfile -ExecutionPolicy Bypass -File check.ps1
# Exit code 0 = everything passed, 1 = something failed (details printed).

$ErrorActionPreference = "Continue"
$skillDir = $PSScriptRoot
$failed = 0
function Ok($msg)   { Write-Host "[ OK ] $msg" -ForegroundColor Green }
function Bad($msg)  { Write-Host "[FAIL] $msg" -ForegroundColor Red; $script:failed++ }
function Info($msg) { Write-Host "[info] $msg" }

# 0. Python and the packages the scripts import.
$py = Get-Command python.exe -ErrorAction SilentlyContinue
if ($py) {
  $v = (& python --version 2>&1)
  if ("$v" -match "Python 3") { Ok "python: $v" } else { Bad "python is not Python 3 ($v)" }
  & python -c "import pymupdf, PIL" 2>$null
  if ($LASTEXITCODE -eq 0) { Ok "python packages pymupdf, pillow" }
  else { Bad "python packages missing. Fix: python -m pip install pymupdf pillow" }
} else { Bad "python not found. Fix: winget install Python.Python.3.12 (tick 'Add to PATH'), new terminal" }

# 1. Find the MiKTeX bin folder (PATH may not be refreshed in this shell yet).
$bin = $null
$cmd = Get-Command xelatex.exe -ErrorAction SilentlyContinue
if ($cmd) { $bin = Split-Path -Parent $cmd.Source }
if (-not $bin) {
  foreach ($c in @("$env:LOCALAPPDATA\Programs\MiKTeX\miktex\bin\x64",
                   "$env:ProgramFiles\MiKTeX\miktex\bin\x64")) {
    if (Test-Path "$c\xelatex.exe") { $bin = $c; break }
  }
}
if (-not $bin) { Bad "xelatex not found (not on PATH, not in the default MiKTeX folders). Fix: setup\install-windows.ps1 -NoPerl -NoUpdate"; exit 1 }
Info "TeX bin folder: $bin"
if ($bin -notmatch "MiKTeX") { Info "this is not MiKTeX (TeX Live?) - the MiKTeX-specific checks below are skipped" }
$env:PATH = "$bin;$env:PATH"

$v = (& "$bin\xelatex.exe" --version 2>$null | Select-Object -First 1)
if ($v) { Ok "xelatex: $v" } else { Bad "xelatex does not run" }

# 2. MiKTeX settings
if ($bin -match "MiKTeX") {
  $auto = (& "$bin\initexmf.exe" --show-config-value="[MPM]AutoInstall" 2>$null)
  if ("$auto".Trim() -eq "1") { Ok "MiKTeX installs missing packages automatically (AutoInstall=1)" }
  else { Bad "MiKTeX AutoInstall is '$auto' (needs 1, or compiles from Claude Code stall on missing packages). Fix: initexmf --set-config-value=[MPM]AutoInstall=1" }

  $info = (& "$bin\miktex.exe" packages info --template "{isInstalled}" culmus 2>$null)
  if ("$info".Trim() -eq "true") { Ok "MiKTeX package culmus (Hebrew fonts) installed" }
  else { Bad "MiKTeX package culmus not installed. Fix: miktex packages install culmus" }
}

# 3. Fonts visible to XeTeX by name
$fcmatch = Join-Path $bin "fc-match.exe"
if (Test-Path $fcmatch) {
  $m = (& $fcmatch "David CLM" 2>$null)
  if ("$m" -match "DavidCLM") { Ok "font 'David CLM' found: $m" }
  else { Bad "font 'David CLM' not visible to XeTeX (fc-match gives '$m'). Fix: miktex-fc-cache -f, or reinstall culmus" }
} else { Info "fc-match not available, the font is checked by the test compile instead" }

# 4. latexmk needs Perl. Optional: build_pdf.py runs xelatex twice without it.
$perl = Get-Command perl.exe -ErrorAction SilentlyContinue
if ($perl) { Ok "perl found: latexmk will be used" }
else { Info "perl not found: build_pdf.py runs xelatex twice instead of latexmk (fine)" }

# 5. Test compile. Pass = PDF produced AND no errors in the .log
function Compile($texPath, $label) {
  $out = Join-Path $env:TEMP ("hebrew-latex-check-" + [IO.Path]::GetFileNameWithoutExtension($texPath))
  if (Test-Path $out) { Remove-Item -Recurse -Force $out }
  New-Item -ItemType Directory -Force $out | Out-Null
  $name = [IO.Path]::GetFileNameWithoutExtension($texPath)
  Copy-Item $texPath $out
  Push-Location $out
  & "$bin\xelatex.exe" -interaction=nonstopmode -file-line-error "$name.tex" *> "$out\xelatex-console.txt"
  Pop-Location
  $pdf = Join-Path $out "$name.pdf"
  $log = Join-Path $out "$name.log"
  $errs = @()
  if (Test-Path $log) {
    $errs = Select-String -Path $log -Pattern '^(! |.*\.(tex|sty|cls|def|cfg):\d+: )' | Select-Object -First 5
  }
  if ((Test-Path $pdf) -and $errs.Count -eq 0) { Ok "$label compiles: $pdf" }
  else {
    Bad "$label did not compile cleanly (build folder: $out)"
    foreach ($e in $errs) { Write-Host "       $($e.Line)" }
    if (-not (Test-Path $log)) { Write-Host "       no .log produced; see $out\xelatex-console.txt" }
  }
}

Compile (Join-Path $skillDir "hebrew-smoke-test.tex") "smoke test"

if ($failed -eq 0) { Write-Host "`nALL CHECKS PASSED" -ForegroundColor Green; exit 0 }
Write-Host "`n$failed CHECK(S) FAILED" -ForegroundColor Red; exit 1
