@echo off
rem Once per computer: the system starts by itself, hidden, every time Windows starts,
rem so https://bodek-hacham.vercel.app works right away. Starts it now too.
rem To undo: delete "Bodek Hacham.lnk" from the Startup folder (Win+R, shell:startup).
chcp 65001 >nul
cd /d "%~dp0"
set "LINK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Bodek Hacham.lnk"
powershell -NoProfile -Command "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:LINK); $s.TargetPath = 'wscript.exe'; $s.Arguments = '\"%~dp0autostart.vbs\"'; $s.WorkingDirectory = '%~dp0'; $s.Save()"
if not exist "%LINK%" (
  echo Could not add the system to Windows startup.
  pause
  exit /b 1
)
echo The system will now start by itself whenever Windows starts.
echo Starting it now...
start "" wscript.exe "%~dp0autostart.vbs"
echo Done. Open https://bodek-hacham.vercel.app in a minute (the first start installs what is needed).
pause
