"""Extração de eventos estruturados com o LLM generativo.

O LLM apenas extrai eventos; nunca decide compra ou venda.
Cada evento aceito precisa ter `trecho_fonte` presente literalmente no texto
original (após normalizar espaços, maiúsculas e acentos).
"""

import json
import logging
import re
from collections.abc import Callable

from src import config, llm
from src.matching import normalizar

logger = logging.getLogger(__name__)

VERSAO_PROMPT_EXTRACAO = "PROMPT_EXTRACAO_V1"
TEMPERATURA_EXTRACAO = 0.0
MAX_PALAVRAS_RESUMO = 30

TIPOS_EVENTO = {
    "dividendo", "resultado", "guidance", "troca_executivo",
    "investigacao", "fusao_aquisicao", "outro",
}
IMPACTOS = {"positivo", "negativo", "neutro"}
CAMPOS = ("ticker", "tipo_evento", "resumo", "impacto_declarado", "confirmado", "trecho_fonte")

PROMPT_EXTRACAO_V1 = """[PROMPT_EXTRACAO_V1]
Você é um extrator de eventos corporativos. Leia o texto abaixo e liste os
eventos que afetam diretamente as empresas destes tickers: {tickers}.

Responda APENAS com JSON válido, sem comentários, no formato:
{{"eventos": [
  {{"ticker": "<um dos tickers acima>",
    "tipo_evento": "<dividendo|resultado|guidance|troca_executivo|investigacao|fusao_aquisicao|outro>",
    "resumo": "<até 30 palavras, em português>",
    "impacto_declarado": "<positivo|negativo|neutro>",
    "confirmado": <true se o texto afirma que o evento ocorreu ou foi oficialmente anunciado; false se é rumor, expectativa ou especulação>,
    "trecho_fonte": "<trecho copiado LITERALMENTE do texto que sustenta o evento>"}}
]}}

Regras:
- "impacto_declarado" é o impacto que o próprio texto atribui ao evento; não opine.
- Não invente eventos. Se não houver evento, responda {{"eventos": []}}.
- "trecho_fonte" deve ser cópia exata de uma parte do texto, sem paráfrase.

<<<TEXTO>>>
{texto}
<<<FIM_TEXTO>>>
"""


class EventoInvalido(ValueError):
    """Evento fora do esquema esperado."""


def montar_prompt(texto: str, tickers: list[str] | None = None) -> str:
    tickers = config.CARTEIRA if tickers is None else tickers
    return PROMPT_EXTRACAO_V1.format(tickers=", ".join(tickers), texto=texto)


def trecho_existe(trecho: str, texto: str) -> bool:
    """O trecho existe literalmente no texto após normalizar espaços, caixa e acentos."""
    trecho_n = normalizar(trecho)
    return bool(trecho_n) and trecho_n in normalizar(texto)


def validar_evento(evento: dict, tickers: list[str] | None = None) -> dict:
    """Valida o evento contra o esquema. Levanta EventoInvalido se inválido."""
    tickers = config.CARTEIRA if tickers is None else tickers
    if not isinstance(evento, dict):
        raise EventoInvalido("evento não é objeto JSON")
    faltando = [c for c in CAMPOS if c not in evento]
    if faltando:
        raise EventoInvalido(f"campos ausentes: {faltando}")
    if evento["ticker"] not in tickers:
        raise EventoInvalido(f"ticker fora da carteira: {evento['ticker']!r}")
    if evento["tipo_evento"] not in TIPOS_EVENTO:
        raise EventoInvalido(f"tipo_evento inválido: {evento['tipo_evento']!r}")
    if evento["impacto_declarado"] not in IMPACTOS:
        raise EventoInvalido(f"impacto_declarado inválido: {evento['impacto_declarado']!r}")
    if not isinstance(evento["confirmado"], bool):
        raise EventoInvalido("confirmado deve ser booleano")
    if not isinstance(evento["resumo"], str) or not evento["resumo"].strip():
        raise EventoInvalido("resumo vazio")
    if len(evento["resumo"].split()) > MAX_PALAVRAS_RESUMO:
        raise EventoInvalido(f"resumo com mais de {MAX_PALAVRAS_RESUMO} palavras")
    if not isinstance(evento["trecho_fonte"], str) or not evento["trecho_fonte"].strip():
        raise EventoInvalido("trecho_fonte vazio")
    return {c: evento[c] for c in CAMPOS}


def _interpretar_json(resposta: str) -> list:
    """Converte a resposta em lista de eventos. Levanta ValueError se não for JSON válido."""
    texto = resposta.strip()
    # Tolera cerca de código markdown em volta do JSON.
    texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto)
    dados = json.loads(texto)
    if isinstance(dados, dict) and isinstance(dados.get("eventos"), list):
        return dados["eventos"]
    if isinstance(dados, list):
        return dados
    raise ValueError("JSON sem lista 'eventos'")


def extrair_eventos(
    texto: str,
    metadados: dict | None = None,
    chamar: Callable[..., str] | None = None,
    tickers: list[str] | None = None,
) -> list[dict]:
    """Extrai eventos válidos do texto.

    `metadados` (ex.: id, tipo_fonte, fonte, url, timestamp_publicacao) é
    copiado para cada evento, para registrar a origem.
    JSON inválido: no máximo uma nova tentativa; depois, descarte com log.
    Evento inválido ou com trecho_fonte inexistente: descarte com log.
    """
    chamar = chamar or llm.chamar_llm
    prompt = montar_prompt(texto, tickers)

    brutos = None
    for tentativa in (1, 2):
        resposta = chamar(prompt, temperatura=TEMPERATURA_EXTRACAO)
        try:
            brutos = _interpretar_json(resposta)
            break
        except (ValueError, TypeError) as erro:
            logger.warning("JSON inválido na extração (tentativa %d/2): %s", tentativa, erro)
    if brutos is None:
        logger.warning("Extração descartada após 2 tentativas com JSON inválido (%s)",
                       (metadados or {}).get("url", "sem url"))
        return []

    modelo = llm.modelo_atual()
    logger.info("Extração com modelo=%s prompt=%s", modelo, VERSAO_PROMPT_EXTRACAO)
    eventos = []
    for bruto in brutos:
        try:
            evento = validar_evento(bruto, tickers)
        except EventoInvalido as erro:
            logger.warning("Evento descartado (esquema): %s | %r", erro, bruto)
            continue
        if not trecho_existe(evento["trecho_fonte"], texto):
            logger.warning("Evento descartado (trecho_fonte inexistente no texto): %r",
                           evento["trecho_fonte"])
            continue
        evento.update({
            "modelo": modelo,
            "versao_prompt": VERSAO_PROMPT_EXTRACAO,
            "temperatura": TEMPERATURA_EXTRACAO,
        })
        if metadados:
            evento["origem"] = dict(metadados)
        eventos.append(evento)
    return eventos
