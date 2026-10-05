@echo off
setlocal
set "EDITOR_PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%EDITOR_PYTHON%" (
  "%EDITOR_PYTHON%" "%~dp0editor\server.py"
  exit /b
)
where py >nul 2>nul
if not errorlevel 1 (
  py -3 "%~dp0editor\server.py"
  exit /b
)
python "%~dp0editor\server.py"
exit /b %errorlevel%
