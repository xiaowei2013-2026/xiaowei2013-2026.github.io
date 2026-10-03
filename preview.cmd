@echo off
"%~dp0.tools\hugo\hugo.exe" server --source "%~dp0." --port 1313 --environment production --minify --disableFastRender
exit /b %errorlevel%
