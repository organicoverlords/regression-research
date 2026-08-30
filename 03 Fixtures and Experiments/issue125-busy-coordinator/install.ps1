param(
  [string]$Destination = (Join-Path $env:LOCALAPPDATA 'BusyCoordinator')
)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonDir = Join-Path $Destination 'python'
$rustDir = Join-Path $Destination 'rust'
$rustSrcDir = Join-Path $rustDir 'src'
New-Item -ItemType Directory -Force -Path $pythonDir,$rustDir,$rustSrcDir | Out-Null
Copy-Item (Join-Path $root 'python\busy.py') (Join-Path $pythonDir 'busy.py') -Force
Copy-Item (Join-Path $root 'python\busy.py') (Join-Path $Destination 'busy.py') -Force
Copy-Item (Join-Path $root 'python\audit_wrapper.py') (Join-Path $Destination 'audit_wrapper.py') -Force
Copy-Item (Join-Path $root 'coordinator-contract.json') (Join-Path $Destination 'coordinator-contract.json') -Force
$rustManifest = Join-Path $root 'rust\Cargo.toml'
cargo build --release --manifest-path $rustManifest
Copy-Item (Join-Path $root 'rust\target\release\busy-coordinator.exe') (Join-Path $rustDir 'busy-coordinator.exe') -Force
Copy-Item (Join-Path $root 'rust\Cargo.toml') (Join-Path $rustDir 'Cargo.toml') -Force
Copy-Item (Join-Path $root 'rust\Cargo.lock') (Join-Path $rustDir 'Cargo.lock') -Force
Copy-Item (Join-Path $root 'rust\src\main.rs') (Join-Path $rustSrcDir 'main.rs') -Force
@"
@echo off
python "%~dp0audit_wrapper.py" --impl python %*
"@ | Set-Content -Encoding ascii (Join-Path $Destination 'busy-python.cmd')
@"
@echo off
python "%~dp0audit_wrapper.py" --impl rust %*
"@ | Set-Content -Encoding ascii (Join-Path $Destination 'busy-rust.cmd')
Write-Output "INSTALLED=$Destination"
Write-Output "PYTHON=$(Join-Path $pythonDir 'busy.py')"
Write-Output "RUST=$(Join-Path $rustDir 'busy-coordinator.exe')"
Write-Output "CONTRACT=$(Join-Path $Destination 'coordinator-contract.json')"
Write-Output "AUDIT_WRAPPER=$(Join-Path $Destination 'audit_wrapper.py')"
