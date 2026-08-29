param(
  [string]$Destination = (Join-Path $env:LOCALAPPDATA 'BusyCoordinator')
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonDir = Join-Path $Destination 'python'
$rustDir = Join-Path $Destination 'rust'
New-Item -ItemType Directory -Force -Path $pythonDir,$rustDir | Out-Null
Copy-Item (Join-Path $root 'python\busy.py') (Join-Path $pythonDir 'busy.py') -Force
Copy-Item (Join-Path $root 'python\busy.py') (Join-Path $Destination 'busy.py') -Force
$rustManifest = Join-Path $root 'rust\Cargo.toml'
cargo build --release --manifest-path $rustManifest
Copy-Item (Join-Path $root 'rust\target\release\busy-coordinator.exe') (Join-Path $rustDir 'busy-coordinator.exe') -Force
@"
@echo off
python "%LOCALAPPDATA%\BusyCoordinator\python\busy.py" %*
"@ | Set-Content -Encoding ascii (Join-Path $Destination 'busy-python.cmd')
@"
@echo off
"%LOCALAPPDATA%\BusyCoordinator\rust\busy-coordinator.exe" %*
"@ | Set-Content -Encoding ascii (Join-Path $Destination 'busy-rust.cmd')
Write-Output "INSTALLED=$Destination"
Write-Output "PYTHON=$(Join-Path $pythonDir 'busy.py')"
Write-Output "RUST=$(Join-Path $rustDir 'busy-coordinator.exe')"
