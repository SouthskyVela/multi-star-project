@echo off
setlocal
set DISTRO=multi-star-sim
set WSL_USER=msim

for /f "usebackq delims=" %%P in (`wsl.exe -d %DISTRO% -u %WSL_USER% -- wslpath -a "%~dp0."`) do set "PROJECT_WSL=%%P"
if not defined PROJECT_WSL (
  echo Failed to resolve the project path inside WSL.
  exit /b 1
)
if not "%PROJECT_WSL:~0,1%"=="/" (
  echo Unexpected WSL path: %PROJECT_WSL%
  exit /b 1
)

wsl.exe -d %DISTRO% -u root -- bash "%PROJECT_WSL%/scripts/stop_all.sh"
wsl.exe --terminate %DISTRO%
echo Multi-Star simulation stopped. Cluster data and images are preserved.
