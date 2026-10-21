"""Arquivo append-only de notícias e fatos relevantes coletados.

Cada item vira uma linha JSON em data/arquivo/AAAA-MM-DD.jsonl, onde a data é
a da COLETA no fuso de referência (assim um dia já fechado nunca é reaberto).
Nada é sobrescrito nem apagado. Deduplicação por URL em todo o arquivo.

Uso: python -m src.archive --coletar   (roda uma vez; não agenda nada)
"""

import argparse
import hashlib
import json
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src import config
from src.matching import identificar_tickers

logger = logging.getLogger(__name__)

FUSO = ZoneInfo(config.FUSO_REFERENCIA)
CAMPOS_OBRIGATORIOS = ("tipo_fonte", "fonte", "url", "titulo", "texto",
                       "timestamp_publicacao", "timestamp_coleta")
TIPOS_FONTE = {"noticia", "fato_relevante"}
# Fora do padrão *.jsonl de propósito: não é registro do arquivo, só a marca da última coleta.
ARQUIVO_ULTIMA_COLETA = "_ultima_coleta.json"
# Histórico curto das coletas (uma linha por coleta), para medir se a agenda está em dia.
ARQUIVO_COLETAS = "_coletas.log"
MAX_COLETAS = 500  # ~10 dias a cada 30 minutos


def _sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def carregar_arquivo(pasta: Path | None = None) -> list[dict]:
    """Lê todos os registros arquivados, em ordem de arquivo e de linha."""
    pasta = Path(pasta or config.DIR_ARQUIVO)
    registros = []
    for caminho in sorted(pasta.glob("*.jsonl")):
        with open(caminho, encoding="utf-8") as f:
            registros.extend(json.loads(linha) for linha in f if linha.strip())
    return registros


def montar_registro(item: dict) -> dict:
    """Completa o item com id, hash do conteúdo e tickers identificados."""
    faltando = [c for c in CAMPOS_OBRIGATORIOS if c not in item]
    if faltando:
        raise ValueError(f"item sem campos obrigatórios: {faltando}")
    if item["tipo_fonte"] not in TIPOS_FONTE:
        raise ValueError(f"tipo_fonte inválido: {item['tipo_fonte']!r}")
    return {
        "id": _sha256(item["url"])[:16],
        "timestamp_publicacao": item["timestamp_publicacao"],
        "timestamp_coleta": item["timestamp_coleta"],
        "tipo_fonte": item["tipo_fonte"],
        "fonte": item["fonte"],
        "url": item["url"],
        "titulo": item["titulo"],
        "texto": item["texto"],
        # O estudo histórico já sabe a empresa (pelo CNPJ na CVM); a coleta casa pelo texto.
        "tickers": item.get("tickers") or identificar_tickers(f"{item['titulo']}\n{item['texto']}"),
        "hash_conteudo": _sha256(f"{item['titulo']}\n{item['texto']}"),
    }


def arquivar(itens: list[dict], pasta: Path | None = None, agora: datetime | None = None) -> list[dict]:
    """Acrescenta ao arquivo os itens cuja URL ainda não foi arquivada.

    Devolve apenas os registros novos. Itens sem URL são descartados com log,
    porque a URL é a chave de deduplicação.
    """
    pasta = Path(pasta or config.DIR_ARQUIVO)
    pasta.mkdir(parents=True, exist_ok=True)
    agora = (agora or datetime.now(FUSO)).astimezone(FUSO)
    urls_vistas = {r["url"] for r in carregar_arquivo(pasta)}

    novos = []
    for item in itens:
        if not item.get("url"):
            logger.warning("Item sem URL descartado: %r", item.get("titulo"))
            continue
        if item["url"] in urls_vistas:
            continue
        registro = montar_registro(item)
        urls_vistas.add(item["url"])
        novos.append(registro)

    if novos:
        caminho = pasta / f"{agora.date().isoformat()}.jsonl"
        with open(caminho, "a", encoding="utf-8") as f:  # "a": nunca sobrescreve
            for registro in novos:
                f.write(json.dumps(registro, ensure_ascii=False) + "\n")
    # Marca a coleta mesmo sem nada novo: a interface mostra quando foi a última.
    marca = json.dumps({"quando": agora.isoformat(), "coletados": len(itens), "novos": len(novos)})
    (pasta / ARQUIVO_ULTIMA_COLETA).write_text(marca, encoding="utf-8")
    historico = pasta / ARQUIVO_COLETAS
    linhas = historico.read_text(encoding="utf-8").splitlines() if historico.exists() else []
    historico.write_text("\n".join((linhas + [marca])[-MAX_COLETAS:]) + "\n", encoding="utf-8")
    logger.info("Arquivados %d novos de %d coletados", len(novos), len(itens))
    return novos


def coletas(pasta: Path | None = None) -> list[datetime]:
    """Instantes das coletas registradas (as mais antigas saem depois de MAX_COLETAS)."""
    caminho = Path(pasta or config.DIR_ARQUIVO) / ARQUIVO_COLETAS
    if not caminho.exists():
        return []
    instantes = []
    for linha in caminho.read_text(encoding="utf-8").splitlines():
        try:
            instantes.append(datetime.fromisoformat(json.loads(linha)["quando"]))
        except (ValueError, KeyError, TypeError):
            continue
    return sorted(instantes)


def ultima_coleta(pasta: Path | None = None) -> dict | None:
    """Horário e contagens da coleta mais recente (None se nunca houve)."""
    caminho = Path(pasta or config.DIR_ARQUIVO) / ARQUIVO_ULTIMA_COLETA
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Arquivo de notícias (append-only).")
    parser.add_argument("--coletar", action="store_true", help="coleta os feeds uma vez e arquiva")
    args = parser.parse_args(argv)
    if not args.coletar:
        parser.print_help()
        return 1

    from src import news

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    novos = arquivar(news.coletar_noticias())
    com_ticker = sum(bool(r["tickers"]) for r in novos)
    print(f"{len(novos)} itens novos arquivados ({com_ticker} mencionam a carteira).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
