@echo off
rem Instala o QUANT neste computador (Windows). Pode rodar de novo quando quiser.
rem Contorna o bloqueio de scripts do PowerShell so para este instalador.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\instalar.ps1" %*
echo.
pause
