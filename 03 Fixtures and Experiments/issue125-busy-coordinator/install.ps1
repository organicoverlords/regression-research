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
Copy-Item (Join-Path $root 'python\lease_guard.py') (Join-Path $pythonDir 'lease_guard.py') -Force
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
set "_busy_cmd=%~1"
if /I "%_busy_cmd%"=="--store" set "_busy_cmd=%~3"
for %%C in (list sweep snapshot recover claim heartbeat release inspect) do if /I "%_busy_cmd%"=="%%C" goto core
python "%~dp0audit_wrapper.py" --impl python %*
exit /b %ERRORLEVEL%
:core
python "%~dp0python\busy.py" %*
"@ | Set-Content -Encoding ascii (Join-Path $Destination 'busy-python.cmd')
@"
@echo off
set "_busy_cmd=%~1"
if /I "%_busy_cmd%"=="--store" set "_busy_cmd=%~3"
for %%C in (list sweep snapshot recover claim heartbeat release inspect) do if /I "%_busy_cmd%"=="%%C" goto core
python "%~dp0audit_wrapper.py" --impl rust %*
exit /b %ERRORLEVEL%
:core
"%~dp0rust\busy-coordinator.exe" %*
"@ | Set-Content -Encoding ascii (Join-Path $Destination 'busy-rust.cmd')
@"
@echo off
python "%~dp0python\lease_guard.py" --impl python %*
"@ | Set-Content -Encoding ascii (Join-Path $Destination 'busy-run-python.cmd')
@"
@echo off
python "%~dp0python\lease_guard.py" --impl rust %*
"@ | Set-Content -Encoding ascii (Join-Path $Destination 'busy-run-rust.cmd')
Write-Output "INSTALLED=$Destination"
Write-Output "PYTHON=$(Join-Path $pythonDir 'busy.py')"
Write-Output "RUST=$(Join-Path $rustDir 'busy-coordinator.exe')"
Write-Output "CONTRACT=$(Join-Path $Destination 'coordinator-contract.json')"
Write-Output "AUDIT_WRAPPER=$(Join-Path $Destination 'audit_wrapper.py')"
Write-Output "LEASE_GUARD=$(Join-Path $pythonDir 'lease_guard.py')"
Write-Output "RUN_PYTHON=$(Join-Path $Destination 'busy-run-python.cmd')"
Write-Output "RUN_RUST=$(Join-Path $Destination 'busy-run-rust.cmd')"
