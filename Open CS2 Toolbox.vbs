Option Explicit
Dim shell, files, projectRoot, pythonPath, command
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
projectRoot = files.GetParentFolderName(WScript.ScriptFullName)
pythonPath = shell.ExpandEnvironmentStrings("%USERPROFILE%") & "\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe"
If files.FileExists(pythonPath) Then
    command = """" & pythonPath & """"
Else
    command = "pyw -3"
End If
shell.CurrentDirectory = projectRoot
shell.Run command & " """ & projectRoot & "\app\desktop\main.py""", 1, False
