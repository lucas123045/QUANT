@echo off
rem Liga a coleta automatica (a cada 30 min) e a vitrine diaria no Agendador de Tarefas.
rem   agendar.cmd                      liga
rem   agendar.cmd -IntervaloMinutos 60 a cada hora
rem   agendar.cmd -SoColeta            so coleta, sem LLM
rem   agendar.cmd -Remover             desliga
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\agendar-windows.ps1" %*
echo.
pause
