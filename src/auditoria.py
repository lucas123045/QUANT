"""Log de auditoria append-only das operações (data/operacoes.jsonl)."""

import json
from pathlib import Path

from src import config

CAMPOS = ("data", "ticker", "evento", "classificacao", "modelo", "versao_prompt",
          "decisao", "motivo", "explicacao")


def registrar_operacao(registro: dict, caminho: Path | None = None) -> dict:
    """Acrescenta uma linha ao log. Exige todos os campos e o trecho_fonte do evento."""
    faltando = [c for c in CAMPOS if c not in registro]
    if faltando:
        raise ValueError(f"registro de auditoria sem campos: {faltando}")
    if not (registro["evento"] or {}).get("trecho_fonte"):
        raise ValueError("registro de auditoria sem evento.trecho_fonte")
    caminho = Path(caminho or config.ARQUIVO_OPERACOES)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "a", encoding="utf-8") as f:  # "a": nunca sobrescreve
        f.write(json.dumps(registro, ensure_ascii=False, default=str) + "\n")
    return registro


def ler_operacoes(caminho: Path | None = None) -> list[dict]:
    caminho = Path(caminho or config.ARQUIVO_OPERACOES)
    if not caminho.exists():
        return []
    with open(caminho, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]
