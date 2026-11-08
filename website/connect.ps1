# Bodek Hacham (the checking system): connects this computer in one step, so the site's buttons run here,
# through this person's own Claude.
#   In PowerShell:  irm https://bodek-hacham.vercel.app/connect.ps1 | iex
# Once per computer. Running it again only adds what is missing and opens the site.
#   1. Installs what the system needs, if it is missing: Git, Python 3.12, 7-Zip (winget) and Claude Code
#      (Anthropic's own installer, the same one the site's "install Claude Code" button runs).
#   2. Downloads the system from GitHub to %USERPROFILE%\Bodek Hacham\assignment-checker (a computer that already
#      has it, from install-autostart.bat, keeps its own folder).
#   3. install-autostart.bat: the system starts by itself, hidden, whenever Windows starts. It starts now too.
#   4. Opens the site connected to this computer. The first "pull" there signs Claude Code in to this person's
#      account and checks the Claude in Chrome extension, so every pull runs through their own Claude and Chrome.
# No passwords go through this script. Messages are in English: Hebrew prints backwards in a PowerShell window.
& {
  # Continue, not Stop: git and winget write progress to stderr, which Windows PowerShell would turn into an error.
  # Every step checks its own result instead
  $ErrorActionPreference = 'Continue'
  $ProgressPreference = 'SilentlyContinue'
  $repo = 'https://github.com/matanravitsky-crypto/assignment-checker'
  $site = 'https://bodek-hacham.vercel.app/#/pull'  # the site talks to the system on this computer; Chrome asks once to allow it
  $health = 'http://127.0.0.1:8765/api/health'
  $link = Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs\Startup\Bodek Hacham.lnk'  # as in install-autostart.bat
  $waitMinutes = 8  # the first start installs Python packages and updates Claude Code (up to 2 minutes)

  function Say($text) { Write-Host "  $text" }
  function Step($text) { Write-Host ''; Write-Host "> $text" -ForegroundColor Cyan }
  function Fail($text) { Write-Host ''; Write-Host "  $text" -ForegroundColor Yellow }
  function Have($cmd) { [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }
  function RefreshPath {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' + [Environment]::GetEnvironmentVariable('Path', 'User')
  }
  function Health {
    try { Invoke-RestMethod -UseBasicParsing -TimeoutSec 5 $health } catch { $null }
  }
  function HasPython {
    if (Have 'py') { return $true }
    $p = Get-Command python -ErrorAction SilentlyContinue
    return [bool]($p -and $p.Source -notlike '*\WindowsApps\*')  # the Store's python.exe only opens the Store
  }
  function Has7Zip {
    (Have '7z') -or (Test-Path "$env:ProgramFiles\7-Zip\7z.exe") -or (Test-Path "${env:ProgramFiles(x86)}\7-Zip\7z.exe")
  }
  function HasClaude {
    (Have 'claude') -or (Test-Path "$env:USERPROFILE\.local\bin\claude.exe")
  }
  function Install($id, $name, $check) {
    if (& $check) { Say "$name - ok"; return $true }
    if (-not (Have 'winget')) {
      Fail "$name is missing, and winget is not on this computer. Install 'App Installer' from the Microsoft Store and run this again."
      return $false
    }
    Say "$name - installing..."
    & winget install -e --id $id --silent --accept-package-agreements --accept-source-agreements | Out-Null
    RefreshPath
    if (& $check) { Say "$name - installed"; return $true }
    Fail "$name did not install. Run 'winget install -e --id $id' in this window, then run this again."
    return $false
  }

  Write-Host ''
  Write-Host 'Bodek Hacham: connecting this computer' -ForegroundColor Green

  Step 'What the system needs'
  $ok = (Install 'Git.Git' 'Git' { Have 'git' })
  $ok = (Install 'Python.Python.3.12' 'Python' { HasPython }) -and $ok
  $ok = (Install '7zip.7zip' '7-Zip' { Has7Zip }) -and $ok
  if (HasClaude) { Say 'Claude Code - ok' } else {
    Say 'Claude Code - installing (Anthropic installer)...'
    & powershell -NoProfile -ExecutionPolicy Bypass -Command 'irm https://claude.ai/install.ps1 | iex' | Out-Null
    RefreshPath
    if (HasClaude) { Say 'Claude Code - installed' } else { Say 'Claude Code - not installed yet: the site offers to install it on the first pull.' }
  }
  if (-not $ok) { return }

  $up = Health
  if ($up) {
    Step 'The system is already running on this computer'
  } else {
    Step 'The system'
    $dir = $null
    if (Test-Path $link) {  # install-autostart.bat already ran here: keep that folder, never a second copy
      $wd = (New-Object -ComObject WScript.Shell).CreateShortcut($link).WorkingDirectory
      if ($wd -and (Test-Path (Join-Path $wd 'start.bat'))) { $dir = $wd.TrimEnd('\') }
    }
    if (-not $dir) { $dir = Join-Path $env:USERPROFILE 'Bodek Hacham\assignment-checker' }
    if (Test-Path (Join-Path $dir '.git')) {
      Say "Folder: $dir (already here)"
    } elseif (Test-Path $dir) {
      Fail "$dir exists but is not the system's folder. Move it away and run this again."
      return
    } else {
      Say "Downloading to $dir ..."
      & git clone -q $repo $dir
      if (-not (Test-Path (Join-Path $dir 'start.bat'))) { Fail "Could not download the system from $repo. Check the internet connection and run this again."; return }
    }

    Step 'Starting it, and with Windows from now on'
    $watching = Get-CimInstance Win32_Process -Filter "Name='wscript.exe'" | Where-Object { $_.CommandLine -like '*autostart.vbs*' }
    if ($watching -and (Test-Path $link)) {
      Say 'Already set to start with Windows, and starting now.'
    } else {
      & cmd.exe /c (Join-Path $dir 'install-autostart.bat') quiet | Out-Null
      if (-not (Test-Path $link)) { Fail 'Could not add the system to Windows startup.'; return }
    }
    Say "The first start installs what it needs. This can take a few minutes"
    $until = (Get-Date).AddMinutes($waitMinutes)
    while (-not $up -and (Get-Date) -lt $until) {
      Start-Sleep -Seconds 5
      Write-Host -NoNewline '.'
      $up = Health
    }
    Write-Host ''
    if (-not $up) {
      Fail "The system did not answer within $waitMinutes minutes. What it printed is in $env:TEMP\bodek-hacham.log"
      Fail 'Run this command again in a few minutes, or send that file to the team.'
      return
    }
    Say 'Running.'
  }

  if (-not $up.root) {
    Fail "The course's OneDrive folder was not found on this computer, so the site has nothing to show yet."
    Fail 'In the browser, open the YallaLinearit folder the lecturer shared and click "Add shortcut to My files";'
    Fail 'in the OneDrive app, sign in with the university account. The site explains it too.'
  }

  Step 'Opening the site'
  Start-Process $site
  Say 'Chrome asks once whether the site may access apps and services on this device: click "Allow".'
  Say 'In the site press "pull". The first time, it signs Claude Code in to YOUR Claude account and checks'
  Say 'the Claude in Chrome extension; after that every pull runs through your own Claude, in your own Chrome.'
  Write-Host ''
}
