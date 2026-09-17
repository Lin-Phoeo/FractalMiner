#Requires -RunAsAdministrator
[CmdletBinding()]
param([switch]$UseLauncher)

$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent $PSScriptRoot
$gameDirectory = Split-Path -Parent $projectDirectory
$captureTool = Join-Path $gameDirectory 'EndfieldUnpacker\_tools\renderdoc\1.46\RenderDoc_1.46_64\renderdoccmd.exe'
$gameExecutable = Join-Path $gameDirectory 'Endfield.exe'
$captureDirectory = Join-Path $projectDirectory 'Validation\Captures'

if (!(Test-Path -LiteralPath $captureTool)) { throw 'Official RenderDoc portable tool is missing.' }
if ((Get-AuthenticodeSignature -LiteralPath $captureTool).Status -ne 'Valid') {
    throw 'RenderDoc signature validation failed.'
}
if (!(Test-Path -LiteralPath $gameExecutable)) { throw 'Endfield executable not found.' }
if (Get-Process Endfield -ErrorAction SilentlyContinue) {
    throw 'Close Endfield normally before starting a Vulkan capture session. No process was terminated.'
}

# Official registration command. No protection, security or game files are changed.
& $captureTool vulkanlayer --register --system
if ($LASTEXITCODE -ne 0) { throw 'RenderDoc Vulkan registration did not succeed.' }
New-Item -ItemType Directory -Force -Path $captureDirectory | Out-Null
$capturePrefix = Join-Path $captureDirectory ('typhoeus-details-' + (Get-Date -Format 'yyyyMMdd-HHmmss'))

if ($UseLauncher) {
    $launcherDirectory = Split-Path -Parent (Split-Path -Parent $gameDirectory)
    $launcherExecutable = Join-Path $launcherDirectory 'Launcher.exe'
    if (!(Test-Path -LiteralPath $launcherExecutable)) { throw 'Official launcher not found.' }
    & $captureTool capture --opt-hook-children -c $capturePrefix -d $launcherDirectory $launcherExecutable
}
else {
    & $captureTool capture -c $capturePrefix -d $gameDirectory $gameExecutable
}
if ($LASTEXITCODE -ne 0) { throw 'Normal RenderDoc launch failed. Keep the error for diagnosis; do not bypass game protections.' }
Write-Output "Capture prefix: $capturePrefix"
Write-Output 'Open Typhoeus details. Capture only if the RenderDoc overlay confirms an active connection.'
Write-Output 'Reference frames and captures stay local and are ignored by Git.'
