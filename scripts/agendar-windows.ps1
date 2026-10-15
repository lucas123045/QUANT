# Agenda o pipeline diário do QUANT no Agendador de Tarefas do Windows.
# NÃO roda sozinho: execute este script uma vez, quando decidir agendar.
#
#   powershell -ExecutionPolicy Bypass -File scripts\agendar-windows.ps1              # pipeline + vitrine, 20h
#   powershell -ExecutionPolicy Bypass -File scripts\agendar-windows.ps1 -Publicar    # ... e também git push
#   powershell -ExecutionPolicy Bypass -File scripts\agendar-windows.ps1 -Remover     # desfaz o agendamento
#
# Por que agendar: esquecer de rodar em alguns dias abre buracos na série, e se
# os esquecimentos se concentram em dias "sem graça" isso vira viés de seleção.
param(
  [string]$Horario = "20:00",
  [switch]$Publicar,
  [switch]$Remover
)

$nome = "QUANT - pipeline diario"
$raiz = Split-Path -Parent $PSScriptRoot

if ($Remover) {
  Unregister-ScheduledTask -TaskName $nome -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "Agendamento removido."
  exit 0
}

$python = Join-Path $raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { Write-Error "Python da .venv não encontrado em $python"; exit 1 }

$passos = @(
  "Set-Location '$raiz'",
  "& '$python' -m src.main *>> data\agendamento.log",
  "npm run vitrine *>> data\agendamento.log"
)
if ($Publicar) {
  $passos += "git add web/public/dados; git commit -m 'Atualiza vitrine (agendado)'; git push *>> data\agendamento.log"
}
$comando = $passos -join "; "

$acao = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -Command `"$comando`""
$gatilho = New-ScheduledTaskTrigger -Daily -At $Horario
$opcoes = New-ScheduledTaskSettingsSet -StartWhenAvailable -DontStopOnIdleEnd -ExecutionTimeLimit (New-TimeSpan -Hours 1)
Register-ScheduledTask -TaskName $nome -Action $acao -Trigger $gatilho -Settings $opcoes -Force | Out-Null

Write-Host "Agendado: '$nome' todo dia às $Horario."
Write-Host "Log em data\agendamento.log. Se o computador estiver desligado no horário, roda quando ligar."
