@echo off
setlocal
set DISTRO=multi-star-sim
set WSL_USER=msim

rem Resolve this checkout's location inside the WSL distribution.
for /f "usebackq delims=" %%P in (`wsl.exe -d %DISTRO% -u %WSL_USER% -- wslpath -a "%~dp0."`) do set "PROJECT_WSL=%%P"
if not defined PROJECT_WSL (
  echo Failed to resolve the project path inside WSL.
  exit /b 1
)
if not "%PROJECT_WSL:~0,1%"=="/" (
  echo Unexpected WSL path: %PROJECT_WSL%
  exit /b 1
)

wsl.exe -d %DISTRO% -u %WSL_USER% -- bash "%PROJECT_WSL%/scripts/start_all.sh"
if errorlevel 1 (
  echo Multi-Star startup failed. Check the messages above.
  exit /b 1
)

echo.
echo Multi-Star dashboard: http://127.0.0.1:18082
echo Keep this window open. Use stop.cmd to stop only this simulation.
wsl.exe -d %DISTRO% -u %WSL_USER% -- bash "%PROJECT_WSL%/scripts/keep_runtime_alive.sh"
