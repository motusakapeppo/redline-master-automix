' Double-click this file to launch the app.
' Uses the venv's own pythonw.exe (not whatever "python" is on system PATH,
' which won't have pywebview/pedalboard/etc. installed and would crash
' instantly with a flashing console window) and runs with no console window.

Set fso = CreateObject("Scripting.FileSystemObject")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)

pythonw = scriptDir & "\.venv\Scripts\pythonw.exe"
mainScript = scriptDir & "\app\main.py"

Set shell = CreateObject("WScript.Shell")
shell.CurrentDirectory = scriptDir
shell.Run """" & pythonw & """ """ & mainScript & """", 0, False
