#!/usr/bin/env bash
# Agenda o QUANT no cron (macOS e Linux). Equivalente ao agendar-windows.ps1.
#   scripts/agendar-unix.sh              pipeline a cada 30 min + vitrine às 20h
#   scripts/agendar-unix.sh 60           a cada hora (aceita 5, 10, 15, 20, 30 ou 60)
#   scripts/agendar-unix.sh 30 --so-coleta   só coleta, sem LLM e sem custo
#   scripts/agendar-unix.sh 30 --sincronizar com a coleta na nuvem: só traz os dados para data/
#   scripts/agendar-unix.sh --remover    desfaz
# O log fica em data/agendamento.log (o próprio Python grava, em UTF-8).
# No macOS, o cron pode precisar de "Acesso Total ao Disco" se o projeto estiver
# em Documentos/Mesa (Ajustes > Privacidade e Segurança).
set -euo pipefail
cd "$(dirname "$0")/.."
RAIZ="$(pwd)"
MARCA="# QUANT (scripts/agendar-unix.sh)"
PY="$RAIZ/.venv/bin/python"

atuais="$(crontab -l 2>/dev/null | grep -vF "$MARCA" || true)"
if [ "${1:-}" = "--remover" ]; then
  printf '%s\n' "$atuais" | crontab -
  echo "Agendamento removido."; exit 0
fi
[ -x "$PY" ] || { echo "Python da .venv não encontrado em $PY (rode: bash instalar.sh)"; exit 1; }

INTERVALO="${1:-30}"
TAREFA="pipeline"
[ "${2:-}" = "--so-coleta" ] && TAREFA="coleta"
[ "${2:-}" = "--sincronizar" ] && TAREFA="sincronizar"   # coleta na nuvem: este computador só traz os dados
case "$INTERVALO" in
  5|10|15|20|30) MINUTO="*/$INTERVALO" ;;
  60) MINUTO="0" ;;
  *) echo "Intervalo inválido: use 5, 10, 15, 20, 30 ou 60 minutos."; exit 1 ;;
esac

linha_hora="$MINUTO * * * * cd '$RAIZ' && '$PY' -m src.agendado $TAREFA >/dev/null 2>&1 $MARCA"
linha_vitrine="0 20 * * * cd '$RAIZ' && '$PY' -m src.agendado vitrine >/dev/null 2>&1 $MARCA"
[ "$TAREFA" = "sincronizar" ] && linha_vitrine=""   # a nuvem já gera a vitrine
{ [ -n "$atuais" ] && printf '%s\n' "$atuais"; printf '%s\n' "$linha_hora"; [ -n "$linha_vitrine" ] && printf '%s\n' "$linha_vitrine"; } | crontab -

echo "Agendado: $TAREFA a cada $INTERVALO min$([ -n "$linha_vitrine" ] && echo ' e vitrine todo dia às 20h') (cron)."
echo "Log em data/agendamento.log. Para desfazer: scripts/agendar-unix.sh --remover"
