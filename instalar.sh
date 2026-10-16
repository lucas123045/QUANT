#!/usr/bin/env bash
# Instalador do QUANT para macOS e Linux. Pode rodar de novo quando quiser.
#   bash instalar.sh                 instala, pergunta a chave e se quer agendar
#   bash instalar.sh --sem-perguntas sem perguntas (não agenda; .env fica para preencher)
set -euo pipefail
cd "$(dirname "$0")"
RAIZ="$(pwd)"
PERGUNTAR=1
[ "${1:-}" = "--sem-perguntas" ] && PERGUNTAR=0

passo() { printf '\n\033[33m==> %s\033[0m\n' "$1"; }
ok()    { printf '    \033[32m%s\033[0m\n' "$1"; }
falha() { printf '\n\033[31mERRO: %s\033[0m\n' "$1"; exit 1; }

passo "1/7 Python 3.11 ou mais novo"
PY=""
for c in python3.13 python3.12 python3.11 python3 python; do
  if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PY="$(command -v "$c")"; break
  fi
done
if [ -z "$PY" ]; then
  case "$(uname)" in
    Darwin) falha "Python 3.11+ não encontrado. Instale com: brew install python@3.12  (ou em https://www.python.org/downloads/) e rode de novo." ;;
    *)      falha "Python 3.11+ não encontrado. Ubuntu/Debian: sudo apt install python3.12 python3.12-venv  — e rode de novo." ;;
  esac
fi
ok "$("$PY" --version) ($PY)"

passo "2/7 Node.js 18 ou mais novo"
if ! command -v node >/dev/null 2>&1 || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 18 ]; then
  case "$(uname)" in
    Darwin) falha "Node.js 18+ não encontrado. Instale com: brew install node  (ou a versão LTS em https://nodejs.org/) e rode de novo." ;;
    *)      falha "Node.js 18+ não encontrado. Instale a versão LTS (https://nodejs.org/ ou o gerenciador da sua distribuição) e rode de novo." ;;
  esac
fi
ok "Node.js $(node --version)"

passo "3/7 Ambiente Python (.venv) e dependências"
if [ -x .venv/bin/python ] && ! .venv/bin/python -c 'pass' 2>/dev/null; then
  echo "    .venv quebrada: recriando..."; rm -rf .venv
fi
[ -x .venv/bin/python ] || "$PY" -m venv .venv || falha "não foi possível criar a .venv (no Ubuntu/Debian: sudo apt install python3-venv)"
.venv/bin/python -m pip install --disable-pip-version-check -q --upgrade pip
.venv/bin/python -m pip install --disable-pip-version-check -q -r requirements.txt || falha "pip install falhou (sem internet?)"
ok "dependências Python instaladas"

passo "4/7 Dependências do site (npm install)"
npm install --no-fund --no-audit || falha "npm install falhou (sem internet?)"
ok "dependências do site instaladas"

passo "5/7 Configuração (.env)"
if [ ! -f .env ]; then cp .env.example .env; ok ".env criado a partir do .env.example"; else ok ".env já existe (mantido)"; fi
if ! grep -qE '^LLM_API_KEY=[^[:space:]]' .env; then
  if [ "$PERGUNTAR" = 1 ]; then
    echo "    Sem a chave do LLM o QUANT coleta notícias, mas não analisa."
    read -r -p "    Cole a chave da API (OpenAI, começa com sk-) ou aperte Enter para pular: " CHAVE
    if [ -n "${CHAVE// /}" ]; then
      # Troca a linha da chave sem depender do sed do macOS ou do GNU.
      "$PY" - "$CHAVE" <<'EOF'
import sys
from pathlib import Path
p = Path(".env"); chave = sys.argv[1].strip()
linhas = [f"LLM_API_KEY={chave}" if l.startswith("LLM_API_KEY=") else l
          for l in p.read_text(encoding="utf-8-sig").splitlines()]
p.write_text("\n".join(linhas) + "\n", encoding="utf-8")
EOF
      chmod 600 .env
      ok "chave gravada no .env (fica só neste computador; o .env não vai para o git)"
    fi
  fi
  grep -qE '^LLM_API_KEY=[^[:space:]]' .env || printf '    \033[33mLembrete: para a IA funcionar, preencha LLM_API_KEY no arquivo .env.\033[0m\n'
else
  ok "chave do LLM configurada"
fi

passo "6/7 Conferindo a instalação (testes automáticos, sem internet e sem custo)"
if .venv/bin/python -m pytest -q -p no:cacheprovider | tail -n 1; then ok "tudo certo"; else
  printf '    \033[33mAlgum teste falhou: a instalação pode ter problema. Veja: .venv/bin/python -m pytest\033[0m\n'; fi

passo "7/7 Coleta automática"
if crontab -l 2>/dev/null | grep -q "# QUANT"; then
  ok "já está agendada neste computador"
elif [ "$PERGUNTAR" = 1 ]; then
  read -r -p "    Ativar a coleta automática a cada 30 minutos (enquanto o computador estiver ligado)? [S/n] " R
  case "$R" in [nN]*) echo "    Para ativar depois: bash scripts/agendar-unix.sh" ;; *) bash scripts/agendar-unix.sh ;; esac
else
  echo "    Para ativar: bash scripts/agendar-unix.sh"
fi

printf '\n\033[32mPronto! Para abrir o QUANT: bash QUANT.sh  (abre o navegador em http://127.0.0.1:5173)\033[0m\n'
