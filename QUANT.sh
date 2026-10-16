#!/usr/bin/env bash
# Abre o QUANT (macOS/Linux): sobe a API e o site e abre o navegador. Ctrl+C para parar.
set -e
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { echo "O QUANT ainda não foi instalado neste computador. Rodando o instalador..."; bash ./instalar.sh; }
[ -d node_modules ] || npm install --no-fund --no-audit
npm run dev
