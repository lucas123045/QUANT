# Agenda o QUANT no Agendador de Tarefas do Windows.
# NAO roda sozinho: execute este script uma vez, quando decidir agendar.
#
#   powershell -ExecutionPolicy Bypass -File scripts\agendar-windows.ps1              # pipeline a cada 30 min + vitrine as 20h
#   powershell -ExecutionPolicy Bypass -File scripts\agendar-windows.ps1 -IntervaloMinutos 60   # a cada hora
#   powershell -ExecutionPolicy Bypass -File scripts\agendar-windows.ps1 -SoColeta    # so coleta (sem LLM, sem custo)
#   powershell -ExecutionPolicy Bypass -File scripts\agendar-windows.ps1 -Publicar    # ... e a vitrine tambem faz git push
#   powershell -ExecutionPolicy Bypass -File scripts\agendar-windows.ps1 -Remover     # desfaz o agendamento
#
# Duas tarefas:
#   "QUANT - coleta automatica" (padrao: a cada 30 min): roda o pipeline (coleta, arquiva e analisa com o LLM so
#     o que e novo; decisoes pela regra). Os feeds RSS mostram so as 10 noticias mais
#     recentes (no InfoMoney, ~1 hora de noticias): coletar com frequencia evita perder noticias.
#     O LLM so e chamado para noticia nova, entao coletar mais vezes nao aumenta o custo.
#   "QUANT - vitrine diaria": gera a versao online (somente leitura) uma vez por dia.
# Se o computador estiver desligado ou dormindo, a tarefa roda quando ele voltar.
# Log em data\agendamento.log, em UTF-8 (renomeado para .old ao passar de 5 MB).
param(
  [int]$IntervaloMinutos = 30,
  [string]$HorarioVitrine = "20:00",
  [switch]$SoColeta,
  [switch]$Publicar,
  [switch]$Remover
)

$nomeHora = "QUANT - coleta automatica"
$nomeVitrine = "QUANT - vitrine diaria"
$nomeAntigo = "QUANT - pipeline diario"  # versao anterior deste script (uma vez por dia)
$raiz = Split-Path -Parent $PSScriptRoot

foreach ($n in @($nomeHora, $nomeVitrine, $nomeAntigo)) {
  Unregister-ScheduledTask -TaskName $n -Confirm:$false -ErrorAction SilentlyContinue
}
if ($Remover) {
  Write-Host "Agendamento removido."
  exit 0
}

# pythonw: sem janela piscando a cada execucao. O proprio Python grava o log
# (src/agendado.py), em UTF-8; o redirecionamento do PowerShell 5.1 gravava UTF-16
# e dava codigo de erro falso sempre que o Python escrevia no stderr.
$pythonw = Join-Path $raiz ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) { Write-Error "Python da .venv nao encontrado em $pythonw"; exit 1 }
New-Item -ItemType Directory -Force (Join-Path $raiz "data") | Out-Null
$log = "data\agendamento.log"

function Acao($tarefa) {
  New-ScheduledTaskAction -Execute $pythonw -Argument "-m src.agendado $tarefa" -WorkingDirectory $raiz
}
$acoesHora = @(Acao $(if ($SoColeta) { "coleta" } else { "pipeline" }))
$acoesVitrine = @(Acao "vitrine")
if ($Publicar) {
  # Acoes seguidas: commit sem mudancas falha sem efeito, e o push nao tem o que enviar.
  $git = (Get-Command git.exe -ErrorAction Stop).Source
  $acoesVitrine += New-ScheduledTaskAction -Execute $git -Argument "add web/public/dados" -WorkingDirectory $raiz
  $acoesVitrine += New-ScheduledTaskAction -Execute $git -Argument "commit -m `"Atualiza vitrine (agendado)`"" -WorkingDirectory $raiz
  $acoesVitrine += New-ScheduledTaskAction -Execute $git -Argument "push" -WorkingDirectory $raiz
}

# Notebook na bateria tambem roda; nunca duas execucoes ao mesmo tempo (o pipeline
# tambem tem trava propria); cada execucao tem no maximo 50 minutos.
$opcoes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
  -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 50)

# Comeca no proximo minuto e repete indefinidamente no intervalo pedido.
$inicio = (Get-Date).AddMinutes(1)
$gatilhoHora = New-ScheduledTaskTrigger -Once -At $inicio -RepetitionInterval (New-TimeSpan -Minutes $IntervaloMinutos)
Register-ScheduledTask -TaskName $nomeHora -Action $acoesHora -Trigger $gatilhoHora -Settings $opcoes `
  -Description "QUANT: coleta noticias e analisa as novas a cada $IntervaloMinutos minutos." | Out-Null

$gatilhoVitrine = New-ScheduledTaskTrigger -Daily -At $HorarioVitrine
Register-ScheduledTask -TaskName $nomeVitrine -Action $acoesVitrine -Trigger $gatilhoVitrine -Settings $opcoes `
  -Description "QUANT: gera a vitrine online (somente leitura) uma vez por dia." | Out-Null

$oque = if ($SoColeta) { "coleta (sem LLM)" } else { "pipeline completo (coleta + LLM nas noticias novas)" }
Write-Host "Agendado: '$nomeHora' - $oque a cada $IntervaloMinutos min, a partir de $($inicio.ToString('HH:mm'))."
Write-Host "Agendado: '$nomeVitrine' - todo dia as $HorarioVitrine$(if ($Publicar) { ', com git push' })."
Write-Host "Log em $log. Para desfazer: powershell -ExecutionPolicy Bypass -File scripts\agendar-windows.ps1 -Remover"
