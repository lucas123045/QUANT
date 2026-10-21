@echo off
rem Abre o QUANT: sobe a API e o site e abre o navegador. Feche esta janela para parar.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo O QUANT ainda nao foi instalado neste computador. Abrindo o instalador...
  call "%~dp0instalar.cmd"
)
if not exist "node_modules" call npm.cmd install --no-fund --no-audit
rem Traz o que a coleta na nuvem gravou (se ela estiver ligada); sem internet, segue com os dados locais.
".venv\Scripts\python.exe" -m src.sincronizar
call npm.cmd run dev
pause
