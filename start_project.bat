@echo off
setlocal

cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Set-ExecutionPolicy -Scope Process Bypass; & '.\start_project.ps1'"

endlocal
