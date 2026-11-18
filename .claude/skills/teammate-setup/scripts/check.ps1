# Read-only check of everything a teammate's computer needs for Bodek Hacham.
# Changes nothing. Prints one JSON object (no emails, no student data).
# Usage: powershell -NoProfile -ExecutionPolicy Bypass -File check.ps1 [-Since "2026-11-05 15:52:00"]
param([string]$Since = "")
[Console]::OutputEncoding = [Text.Encoding]::UTF8
$ErrorActionPreference = 'SilentlyContinue'
$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')
$BGU_TENANT = '49470515-677a-4fbe-8686-afae308fe867'
$HOME_TENANT = '474cbbe4-ab8e-40ae-a518-715ca4c0ba5a'
$ONEDRIVE_CLIENT = 'ab9b8c07-8f02-4f72-87fa-80105867a763'
function Ver($cmd) { try { (& $cmd --version 2>$null | Select-Object -First 1) } catch { $null } }

$r = [ordered]@{}

# 1. Software
$r.software = [ordered]@{
  git      = Ver git
  py3      = $(try { (py -3 --version 2>$null) } catch { $null })
  sevenZip = Test-Path 'C:\Program Files\7-Zip\7z.exe'
  claude   = Ver claude
  claudeExe = Test-Path "$env:USERPROFILE\.local\bin\claude.exe"
  gh       = $(try { (gh --version 2>$null | Select-Object -First 1) } catch { $null })
}

# 2. Clones of the repo, and which one the Startup shortcut runs
$cands = @("$env:USERPROFILE\Bodek Hacham", "$env:USERPROFILE\Desktop", "$env:USERPROFILE\Documents", $env:USERPROFILE)
Get-ChildItem $env:USERPROFILE -Directory -Filter 'OneDrive*' | ForEach-Object { $cands += "$($_.FullName)\Desktop"; $cands += "$($_.FullName)\Documents" }
$clones = @()
foreach ($c in ($cands | Select-Object -Unique)) {
  $p = Join-Path $c 'assignment-checker'
  if (Test-Path "$p\.git") {
    $remote = git -C $p remote get-url origin 2>$null
    if ($remote -match 'matanravitsky-crypto/assignment-checker') {
      $clones += [ordered]@{ path = $p; branch = (git -C $p branch --show-current); head = (git -C $p log -1 --format=%h); dirty = [bool](git -C $p status --porcelain) }
    }
  }
}
$r.clones = $clones
$lnk = Get-ChildItem "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup" -Filter '*.lnk' | Where-Object { $_.Name -like 'Bodek*' } | Select-Object -First 1
$r.autostartRuns = $null
if ($lnk) { $s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk.FullName); $r.autostartRuns = $s.Arguments.Trim('"', ' ') }
$r.dashboardProcesses = @(Get-CimInstance Win32_Process -Filter "Name like 'python%'" | Where-Object { $_.CommandLine -like '*dashboard serve*' } | ForEach-Object { $_.ExecutablePath })

# 3. Server
try { $r.health = (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8765/api/health -TimeoutSec 5).Content | ConvertFrom-Json } catch { $r.health = $null }

# 4. OneDrive
$b = Get-ItemProperty 'HKCU:\Software\Microsoft\OneDrive\Accounts\Business1'
$r.onedrive = [ordered]@{
  running        = [bool](Get-Process OneDrive)
  version        = (Get-Item "$env:ProgramFiles\Microsoft OneDrive\OneDrive.exe").VersionInfo.ProductVersion
  business1      = [bool]$b
  business1Domain = $(if ($b.UserEmail) { ($b.UserEmail -split '@')[1] } else { $null })
  business1Tenant = $b.ConfiguredTenantId
  firstRunDone   = [bool]($b.PSObject.Properties['FirstRun'] -or $b.PSObject.Properties['ClientFirstSignInTimestamp'])
  hasHomeOneDriveEndpoint = [bool]$b.SPOResourceId
  yallaMounts    = @(Get-ChildItem 'HKCU:\Software\SyncEngines\Providers\OneDrive' | ForEach-Object { Get-ItemProperty $_.PSPath } |
                     Where-Object { $_.MountPoint -like '*YallaLinearit*' } | ForEach-Object { $_.MountPoint } | Select-Object -Unique)
}

# 5. Sign-in failures of OneDrive in the AAD log
$from = if ($Since) { [datetime]$Since } else { (Get-Date).AddHours(-24) }
$ev = Get-WinEvent -LogName 'Microsoft-Windows-AAD/Operational' -MaxEvents 2000 | Where-Object { $_.TimeCreated -gt $from -and $_.Message -match $ONEDRIVE_CLIENT }
$r.aad = [ordered]@{
  since = $from.ToString('yyyy-MM-dd HH:mm:ss')
  mfaRequiredBgu  = @($ev | Where-Object { $_.Message -match 'AADSTS50076' -and $_.Message -match $BGU_TENANT }).Count
  mfaRequiredHome = @($ev | Where-Object { $_.Message -match 'AADSTS50076' -and $_.Message -match $HOME_TENANT }).Count
  lastMfaRequired = $(($ev | Where-Object { $_.Message -match 'AADSTS50076' } | Select-Object -First 1).TimeCreated | ForEach-Object { $_.ToString('yyyy-MM-dd HH:mm:ss') })
  otherCodes = @($ev | Where-Object { $_.LevelDisplayName -eq 'Error' -and $_.Message -notmatch 'AADSTS50076' } |
                 ForEach-Object { [regex]::Match($_.Message, 'AADSTS\d+|0x[0-9A-F]{8}').Value } | Group-Object | ForEach-Object { "$($_.Name) x$($_.Count)" })
}

# 6. Grader name
$envFile = if ($r.autostartRuns) { Join-Path (Split-Path $r.autostartRuns) '.env' } elseif ($clones) { Join-Path $clones[0].path '.env' } else { $null }
$r.graderNameSet = [bool]($envFile -and (Select-String -Path $envFile -Pattern '^GRADER_NAME=.+' -Quiet))
$r.rootOverride = [bool]($envFile -and (Select-String -Path $envFile -Pattern '^(ASSIGNMENT_CHECKER_ROOT|ASSIGNMENT_DATA)=' -Quiet))

# 7. Up to date with GitHub: the code the running server loaded against main (2026-11-18: a server on code from
# 15.11 failed every grading with "cannot import name ..." after Claude had already graded, ~$0.9 each)
$serverClone = if ($r.autostartRuns) { Split-Path $r.autostartRuns } elseif ($clones) { $clones[0].path } else { $null }
$sc = $clones | Where-Object { $_.path -eq $serverClone } | Select-Object -First 1
$mainHead = $(try { ((git ls-remote https://github.com/matanravitsky-crypto/assignment-checker refs/heads/main 2>$null) -split '\s')[0] } catch { $null })
$running = if ($r.health) { $r.health.version } else { $null }
$r.update = [ordered]@{
  mainOnGitHub  = $(if ($mainHead) { $mainHead.Substring(0, 7) } else { $null })
  serverRuns    = $running
  upToDate      = [bool]($mainHead -and $running -and $mainHead.StartsWith($running))
  cloneOnMain   = [bool]($sc -and $sc.branch -eq 'main')
  cloneDirty    = [bool]($sc -and $sc.dirty)
  autoUpdateOff = [bool]($envFile -and (Select-String -Path $envFile -Pattern '^AUTO_UPDATE=(off|0|false|no)\s*$' -Quiet))
  watchdog      = [bool]$lnk
  gradingNow    = [bool]($r.health -and $r.health.checking)
}

# 8. Which Claude account grades here: each teammate on their own seat, never a shared sign-in (every seat has its
# own usage limits). Domain, organization and plan only, never the email itself
$a = $(try { (claude auth status --json 2>$null | Out-String) | ConvertFrom-Json } catch { $null })
$r.claudeAccount = [ordered]@{
  loggedIn     = [bool]($a -and $a.loggedIn)
  emailDomain  = $(if ($a -and $a.email) { ($a.email -split '@')[1] } else { $null })
  orgName      = $(if ($a) { $a.orgName } else { $null })
  subscription = $(if ($a) { $a.subscriptionType } else { $null })
  modelOverride = $null  # GRADING_MODEL in .env: anything set there replaces the system's own model (Opus 5.5)
}
if ($envFile) {
  $m = Select-String -Path $envFile -Pattern '^GRADING_MODEL=(.+)$' | Select-Object -First 1
  if ($m) { $r.claudeAccount.modelOverride = [string]$m.Matches[0].Groups[1].Value.Trim() }
}

$r | ConvertTo-Json -Depth 5
