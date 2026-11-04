# Downloads the prebuilt Windows (Cygwin) ArduPilot SITL binaries that
# Mission Planner uses, together with the Cygwin runtime DLLs they need.
#
# The files on the server are named *.elf but are really Windows PE
# executables; like Mission Planner, we save them as *.exe.
#
# Each vehicle goes into its own folder (bin\windows\<Vehicle>\) with its
# own copy of the DLLs, because the stable builds of different vehicles may
# ship different Cygwin DLL versions.
#
# Usage (from the repository root, in PowerShell):
#   powershell -ExecutionPolicy Bypass -File scripts\get_windows_sitl.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\get_windows_sitl.ps1 -Channel stable

param(
    [ValidateSet("master", "beta", "stable")]
    [string]$Channel = "master",
    [string[]]$Vehicles = @("ArduCopter", "ArduPlane"),
    [string]$OutDir = (Join-Path $PSScriptRoot "..\bin\windows")
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Invoke-WebRequest is very slow with the progress bar

$baseUrl = "https://firmware.ardupilot.org/Tools/MissionPlanner/sitl"
$dlls = @(
    "cygatomic-1.dll",
    "cyggcc_s-1.dll",
    "cyggcc_s-seh-1.dll",
    "cyggomp-1.dll",
    "cygiconv-2.dll",
    "cygintl-8.dll",
    "cygquadmath-0.dll",
    "cygssp-0.dll",
    "cygstdc%2B%2B-6.dll",
    "cygwin1.dll"
)

function Get-ChannelUrl([string]$vehicle) {
    switch ($Channel) {
        "master" { return "$baseUrl" }
        "beta" { return "$baseUrl/Beta" }
        "stable" {
            switch ($vehicle) {
                "ArduPlane" { return "$baseUrl/PlaneStable" }
                "ArduRover" { return "$baseUrl/RoverStable" }
                default { return "$baseUrl/CopterStable" }  # ArduCopter, ArduHeli
            }
        }
    }
}

foreach ($vehicle in $Vehicles) {
    $url = Get-ChannelUrl $vehicle
    $dir = Join-Path $OutDir $vehicle
    New-Item -ItemType Directory -Force -Path $dir | Out-Null

    Write-Host "Downloading $vehicle ($Channel) into $dir"
    Invoke-WebRequest -Uri "$url/$vehicle.elf" -OutFile (Join-Path $dir "$vehicle.exe")

    foreach ($dll in $dlls) {
        $name = [System.Uri]::UnescapeDataString($dll)
        Invoke-WebRequest -Uri "$url/$dll" -OutFile (Join-Path $dir $name)
    }

    try {
        Invoke-WebRequest -Uri "$url/git.txt" -OutFile (Join-Path $dir "git.txt")
    } catch {
        # git.txt is informational only
    }
}

Write-Host "Done."
