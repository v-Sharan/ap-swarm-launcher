# Creates "AP SITL Swarm Launcher" shortcuts on the Desktop and in the Start
# menu that open the swarm launcher GUI, so it can be started from anywhere.
#
# Run from the repository root after `uv sync`:
#   powershell -ExecutionPolicy Bypass -File scripts\create_gui_shortcut.ps1

$ErrorActionPreference = "Stop"

$repo = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$target = Join-Path $repo ".venv\Scripts\ap-sitl-swarm-gui.exe"
if (-not (Test-Path $target)) {
    throw "$target not found. Run 'uv sync' in $repo first."
}

$icon = Join-Path $repo "bin\windows\ArduPlane\ArduPlane.exe"
$name = "AP SITL Swarm Launcher.lnk"
$shell = New-Object -ComObject WScript.Shell

foreach ($folder in @([Environment]::GetFolderPath("Desktop"), [Environment]::GetFolderPath("Programs"))) {
    $path = Join-Path $folder $name
    $lnk = $shell.CreateShortcut($path)
    $lnk.TargetPath = $target
    $lnk.WorkingDirectory = $repo
    $lnk.Description = "Launch an ArduPilot SITL swarm (QuadPlane / Copter)"
    if (Test-Path $icon) { $lnk.IconLocation = "$icon,0" }
    $lnk.Save()
    Write-Host "Created $path"
}
