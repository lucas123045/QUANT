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

VERSAO_PROMPT_EXTRACAO = "PROMPT_EXTRACAO_V2"
TEMPERATURA_EXTRACAO = 0.0  # pedida; o efetivamente aplicado vai em cada evento
MAX_PALAVRAS_RESUMO = 30
# Só o começo do texto vai ao LLM (algumas matérias passam de 25 mil caracteres):
# o fato principal está no início, e o custo cresce com o tamanho. O trecho_fonte
# continua sendo conferido contra o texto completo.
MAX_CARACTERES_TEXTO = 8000

TIPOS_EVENTO = {
    "dividendo", "resultado", "guidance", "troca_executivo",
    "investigacao", "fusao_aquisicao", "outro",
    # V2: produção, vendas, contratos; decisões de governo e agências reguladoras
    # (na primeira execução real, o LLM usou "producao", fora da lista, e o fato
    # da produção trimestral da Petrobras foi descartado).
    "operacional", "regulatorio",
    "cotacao",  # V2: a notícia só relata a variação do preço (a regra não opera)
}
IMPACTOS = {"positivo", "negativo", "neutro"}
CAMPOS = ("ticker", "tipo_evento", "resumo", "impacto_declarado", "confirmado", "trecho_fonte")

# V1 → V2: com a V1, todos os eventos dos primeiros dias reais foram resumos de
# fechamento ("ações da Petrobras sobem 3%"); a V2 os separa como "cotacao".
PROMPT_EXTRACAO_V2 = """[PROMPT_EXTRACAO_V2]
Você é um extrator de eventos corporativos. Leia o texto abaixo e liste os
eventos que afetam diretamente as empresas destes tickers: {tickers}.

Responda APENAS com JSON válido, sem comentários, no formato:
{{"eventos": [
  {{"ticker": "<um dos tickers acima>",
    "tipo_evento": "<dividendo|resultado|guidance|troca_executivo|investigacao|fusao_aquisicao|operacional|regulatorio|outro|cotacao>",
    "resumo": "<até 30 palavras, em português>",
    "impacto_declarado": "<positivo|negativo|neutro>",
    "confirmado": <true se o texto afirma que o evento ocorreu ou foi oficialmente anunciado; false se é rumor, expectativa ou especulação>,
    "trecho_fonte": "<trecho copiado LITERALMENTE do texto que sustenta o evento>"}}
]}}

Regras:
- Um evento é um FATO sobre a empresa: resultado, dividendo, projeção da própria
  empresa (guidance), troca de executivos, investigação, fusão ou aquisição.
  Produção, vendas, contratos e preços de produtos: "operacional". Decisões de
  governo, agências ou tribunais sobre a empresa: "regulatorio". Use só os tipos
  da lista; se nenhum servir, "outro".
- A simples variação da cotação da ação ("PETR4 sobe 3%", "Vale cai 1,4%",
  "ações fecham em alta") NÃO é um fato novo sobre a empresa. Se o texto, para
  uma empresa, só relata o movimento do preço da ação ou do índice, use
  "tipo_evento": "cotacao". Se o texto cita um fato que explica o movimento
  (ex.: "sobe após anunciar dividendos"), extraia o fato, com o tipo dele.
- Prévias e projeções sobre algo que ainda não aconteceu ("o que esperar do
  balanço", "analistas esperam lucro maior", "resultado sai dia 29") são
  expectativa: "confirmado": false. Só é confirmado o que o texto diz que já
  aconteceu ou foi anunciado oficialmente pela empresa.
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
    return PROMPT_EXTRACAO_V2.format(tickers=", ".join(tickers), texto=texto[:MAX_CARACTERES_TEXTO])


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

    modelo = llm.modelo_da_ultima_chamada()
    temperatura = llm.temperatura_efetiva(TEMPERATURA_EXTRACAO)
    logger.info("Extração com modelo=%s prompt=%s temperatura=%s", modelo,
                VERSAO_PROMPT_EXTRACAO, temperatura)
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
            "temperatura": temperatura,
        })
        if metadados:
            evento["origem"] = dict(metadados)
        eventos.append(evento)
    return eventos
