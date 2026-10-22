' Bodek Hacham (the checking system): keeps start.bat running with no window, so the site works as soon as someone opens the link.
' install-autostart.bat puts a shortcut to this file in the Windows Startup folder.
' Every minute it asks the system whether it is up (http://127.0.0.1:8765/api/health); if not, it starts it again.
' What start.bat prints goes to %TEMP%\bodek-hacham.log.
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
here = fso.GetParentFolderName(WScript.ScriptFullName)
logFile = shell.ExpandEnvironmentStrings("%TEMP%") & "\bodek-hacham.log"
shell.CurrentDirectory = here

Function SystemIsUp()
  On Error Resume Next
  Set http = CreateObject("MSXML2.ServerXMLHTTP.6.0")
  http.setTimeouts 3000, 3000, 5000, 10000
  http.open "GET", "http://127.0.0.1:8765/api/health", False
  http.send
  SystemIsUp = (Err.Number = 0 And http.status = 200)
End Function

Do
  If Not SystemIsUp() Then
    ' Waits until the system stops (it runs until the computer shuts down, or crashes)
    shell.Run "cmd /c """"" & here & "\start.bat"" background > """ & logFile & """ 2>&1""", 0, True
  End If
  WScript.Sleep 60000
Loop
