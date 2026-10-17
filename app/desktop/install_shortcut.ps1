$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..'))
$pythonWindowless = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonWindowless)) {
    $pythonWindowless = (Get-Command pythonw.exe -ErrorAction Stop).Source
}
$desktopPath = [Environment]::GetFolderPath('Desktop')
$shortcutPath = Join-Path $desktopPath 'CS2 Toolbox.lnk'
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $pythonWindowless
$shortcut.Arguments = '"' + (Join-Path $PSScriptRoot 'main.py') + '"'
$shortcut.WorkingDirectory = $projectRoot
$shortcut.Description = 'CS2 demo extraction and replay utilities'
$shortcut.IconLocation = (Join-Path $PSScriptRoot 'toolbox.ico') + ',0'
$shortcut.Save()
Write-Output ('Created shortcut: ' + $shortcutPath)
