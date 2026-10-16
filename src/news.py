"""Coleta de notícias de portal (RSS) e interface para fatos relevantes (CVM).

Cada item coletado traz `tipo_fonte` ("noticia" ou "fato_relevante") para que
as duas fontes nunca sejam misturadas sem registro de origem.
"""

import calendar
import html
import logging
import re
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import feedparser

from src import config, rede

logger = logging.getLogger(__name__)

FUSO = ZoneInfo(config.FUSO_REFERENCIA)
TIMEOUT_SEGUNDOS = 20
USER_AGENT = "quant-academico/1.0 (+coleta de RSS)"


def baixar_url(url: str) -> bytes:
    """Baixa o conteúdo bruto de uma URL (com timeout e certificados do sistema)."""
    return rede.baixar(url, TIMEOUT_SEGUNDOS, USER_AGENT)


def limpar_html(texto: str) -> str:
    sem_tags = re.sub(r"<[^>]+>", " ", texto or "")
    return re.sub(r"\s+", " ", html.unescape(sem_tags)).strip()


def _data_publicacao(entrada) -> datetime | None:
    estrutura = entrada.get("published_parsed") or entrada.get("updated_parsed")
    if not estrutura:
        return None
    # feedparser devolve struct_time em UTC.
    return datetime.fromtimestamp(calendar.timegm(estrutura), tz=timezone.utc).astimezone(FUSO)


def _texto(entrada) -> str:
    conteudo = entrada.get("content")
    if conteudo:
        return limpar_html(conteudo[0].get("value", ""))
    return limpar_html(entrada.get("summary") or entrada.get("description") or "")


def coletar_noticias(
    fontes: list[dict] | None = None,
    agora: datetime | None = None,
    janela_horas: int | None = None,
    baixar: Callable[[str], bytes] | None = None,
) -> list[dict]:
    """Coleta itens dos feeds RSS publicados nas últimas `janela_horas`.

    Falha de rede ou feed inválido em uma fonte é registrada e a coleta segue
    para a próxima. Itens sem data de publicação são descartados (com log),
    porque o corte temporal depende dela.
    """
    fontes = config.FONTES_RSS if fontes is None else fontes
    baixar = baixar or baixar_url
    agora = (agora or datetime.now(FUSO)).astimezone(FUSO)
    janela = timedelta(hours=config.JANELA_COLETA_HORAS if janela_horas is None else janela_horas)

    itens = []
    for fonte in fontes:
        try:
            feed = feedparser.parse(baixar(fonte["url"]))
        except Exception as erro:  # rede, timeout, HTTP: registra e segue
            logger.error("Falha ao coletar %s (%s): %s", fonte["nome"], fonte["url"], erro)
            continue
        if feed.get("bozo") and not feed.get("entries"):
            logger.error("Feed inválido em %s: %s", fonte["nome"], feed.get("bozo_exception"))
            continue

        for entrada in feed.entries:
            publicado = _data_publicacao(entrada)
            if publicado is None:
                logger.warning("Item sem data descartado (%s): %s", fonte["nome"], entrada.get("link"))
                continue
            if not (agora - janela <= publicado <= agora + timedelta(minutes=5)):
                continue
            itens.append({
                "tipo_fonte": "noticia",
                "fonte": fonte["nome"],
                "url": entrada.get("link", ""),
                "titulo": limpar_html(entrada.get("title", "")),
                "texto": _texto(entrada),
                "timestamp_publicacao": publicado.isoformat(),
                "timestamp_coleta": agora.isoformat(),
            })
        logger.info("%s: %d itens na janela", fonte["nome"], sum(i["fonte"] == fonte["nome"] for i in itens))
    return itens


def coletar_fatos_relevantes(tickers: list[str] | None = None, **kwargs) -> list[dict]:
    """Interface para fatos relevantes da CVM (itens com tipo_fonte="fato_relevante").

    Bloqueado: a cobertura da CVM para a carteira, o formato dos dados e a
    confiabilidade da data de entrega ainda não foram verificados.
    """
    raise NotImplementedError(
        "Fatos relevantes da CVM: verificar formato e cobertura antes de implementar."
    )
