' Bodek Hacham (the checking system): runs start.bat with no window, so the site works as soon as someone opens the link.
' install-autostart.bat puts a shortcut to this file in the Windows Startup folder.
' What start.bat prints goes to %TEMP%\bodek-hacham.log.
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
here = fso.GetParentFolderName(WScript.ScriptFullName)
logFile = shell.ExpandEnvironmentStrings("%TEMP%") & "\bodek-hacham.log"
shell.CurrentDirectory = here
shell.Run "cmd /c """"" & here & "\start.bat"" background > """ & logFile & """ 2>&1""", 0, False
