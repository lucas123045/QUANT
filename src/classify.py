"""Classificação de eventos: sentimento e probabilidade.

Interface única: `classificar(evento)`. Dois caminhos, mesmo formato de saída:
- Jev (opcional): adaptador bloqueado até haver especificação da API;
- LLM generativo: caminho previsto e normal quando o Jev não está disponível.

Nenhum dos dois decide compra ou venda; isso é feito só por strategy.py.
"""

import json
import logging
import re
from collections.abc import Callable

from src import config, llm

logger = logging.getLogger(__name__)

VERSAO_PROMPT_CLASSIFICACAO = "PROMPT_CLASSIFICACAO_V1"
SENTIMENTOS = {"positivo", "negativo", "neutro"}

PROMPT_CLASSIFICACAO_V1 = """[PROMPT_CLASSIFICACAO_V1]
Classifique o efeito provável do evento abaixo sobre o preço da ação {ticker}
no próximo pregão. Responda APENAS com JSON válido:
{{"sentimento": "<positivo|negativo|neutro>", "probabilidade": <número entre 0 e 1>}}
"probabilidade" é a sua confiança de que o sentimento está correto.

Evento:
- tipo: {tipo_evento}
- resumo: {resumo}
- impacto declarado pelo texto: {impacto_declarado}
- confirmado: {confirmado}
- trecho da fonte: "{trecho_fonte}"
"""


class ClassificacaoInvalida(ValueError):
    """Saída de classificador fora do formato padronizado."""


def padronizar(bruto: dict, classificador: str, modelo: str, versao: str | None) -> dict:
    """Valida e devolve a saída no formato único da interface."""
    sentimento = bruto.get("sentimento") if isinstance(bruto, dict) else None
    probabilidade = bruto.get("probabilidade") if isinstance(bruto, dict) else None
    if sentimento not in SENTIMENTOS:
        raise ClassificacaoInvalida(f"sentimento inválido: {sentimento!r}")
    if isinstance(probabilidade, bool) or not isinstance(probabilidade, (int, float)):
        raise ClassificacaoInvalida(f"probabilidade não numérica: {probabilidade!r}")
    if not 0.0 <= float(probabilidade) <= 1.0:
        raise ClassificacaoInvalida(f"probabilidade fora de [0, 1]: {probabilidade}")
    return {
        "sentimento": sentimento,
        "probabilidade": float(probabilidade),
        "classificador": classificador,
        "modelo": modelo,
        "versao_prompt": versao,
    }


def _interpretar_json(resposta: str):
    """JSON da resposta, tolerando cerca de código markdown em volta (como na extração)."""
    return json.loads(re.sub(r"^```(?:json)?\s*|\s*```$", "", resposta.strip()))


def classificar_jev(evento: dict) -> dict:
    """Adaptador do Jev. Bloqueado: sem especificação de API no repositório."""
    raise NotImplementedError("API do Jev não especificada no repositório.")


def classificar_llm(evento: dict, chamar: Callable[..., str] | None = None) -> dict | None:
    """Classifica com o LLM generativo. JSON inválido: uma nova tentativa, depois None."""
    chamar = chamar or llm.chamar_llm
    prompt = PROMPT_CLASSIFICACAO_V1.format(**{k: evento[k] for k in (
        "ticker", "tipo_evento", "resumo", "impacto_declarado", "confirmado", "trecho_fonte")})
    for tentativa in (1, 2):
        resposta = chamar(prompt, temperatura=0.0)
        try:
            return padronizar(_interpretar_json(resposta), "llm", llm.modelo_da_ultima_chamada(),
                              VERSAO_PROMPT_CLASSIFICACAO)
        except (ValueError, TypeError) as erro:
            logger.warning("Classificação LLM inválida (tentativa %d/2): %s", tentativa, erro)
    logger.warning("Evento sem classificação após 2 tentativas: %s", evento.get("resumo"))
    return None


def classificar(
    evento: dict,
    usar_jev: bool | None = None,
    chamar: Callable[..., str] | None = None,
    jev: Callable[[dict], dict] | None = None,
) -> dict | None:
    """Devolve {sentimento, probabilidade, classificador, modelo, versao_prompt} ou None.

    Com Jev habilitado e disponível, usa o Jev; caso contrário, usa o LLM,
    que é o fluxo normal enquanto o acesso ao Jev não estiver confirmado.
    """
    usar_jev = config.USAR_JEV if usar_jev is None else usar_jev
    if usar_jev:
        try:
            bruto = (jev or classificar_jev)(evento)
            return padronizar(bruto, "jev", "jev", None)
        except NotImplementedError as erro:
            logger.info("Jev indisponível (%s); usando o LLM generativo.", erro)
        except ClassificacaoInvalida as erro:
            logger.warning("Saída do Jev inválida (%s); usando o LLM generativo.", erro)
    return classificar_llm(evento, chamar)
