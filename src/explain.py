"""Explicação em linguagem natural de decisões JÁ tomadas por strategy.py.

O LLM só redige o texto. Ele recebe a decisão e o motivo prontos, e a saída
desta camada nunca é lida de volta pela regra. A decisão e o motivo exibidos
vêm sempre da regra, não do texto do LLM.
"""

import logging
from collections.abc import Callable

from src import llm
from src.strategy import Decisao

logger = logging.getLogger(__name__)

VERSAO_PROMPT_EXPLICACAO = "PROMPT_EXPLICACAO_V2"
VERSAO_PROMPT_RELATORIO = "PROMPT_RELATORIO_V1"
TEMPERATURA_EXPLICACAO = 0.0

# V1 → V2: a explicação recebe os critérios que a regra conferiu e precisa citar o
# fato da notícia e por que ele importa para a empresa (a V1 tendia a repetir
# "houve um evento positivo relevante", sem dizer qual nem por quê).
PROMPT_EXPLICACAO_V2 = """[PROMPT_EXPLICACAO_V2]
Uma regra determinística JÁ TOMOU a decisão abaixo. Não a altere, não a
questione e não recomende outra. Explique em português, em até 3 frases e
para um leitor leigo, por que a regra chegou a essa decisão, usando apenas
os dados fornecidos:
1. qual é o fato da notícia, em palavras simples;
2. por que esse fato tende a ser bom ou ruim para a empresa, segundo o próprio texto;
3. quais critérios da regra ele cumpriu.
Não invente números nem fatos que não estejam abaixo.

Ticker: {ticker}
Decisão da regra: {decisao}
Motivo registrado pela regra: {motivo}
Evento: {tipo_evento} | {resumo}
Trecho da fonte: "{trecho_fonte}"
Classificação: {sentimento} (probabilidade {probabilidade})
Critérios conferidos pela regra:
{criterios}
"""

PROMPT_RELATORIO_V1 = """[PROMPT_RELATORIO_V1]
As decisões abaixo JÁ FORAM TOMADAS por uma regra determinística. Escreva em
português um resumo do dia em até 4 frases, sem alterar nem recomendar
decisões e sem acrescentar informação que não esteja na lista.

{linhas}
"""


def _texto_llm(prompt: str, chamar: Callable[..., str] | None) -> str | None:
    try:
        texto = (chamar or llm.chamar_llm)(prompt, temperatura=TEMPERATURA_EXPLICACAO).strip()
        return texto or None
    except Exception as erro:  # explicação é auxiliar: falha não derruba nada
        logger.warning("Falha ao gerar explicação com o LLM: %s", erro)
        return None


def gerar_justificativa(
    decisao: Decisao,
    evento: dict,
    classificacao: dict | None,
    chamar: Callable[..., str] | None = None,
) -> str:
    """Texto da operação: cabeçalho fixo vindo da regra + explicação do LLM."""
    classificacao = classificacao or {}
    cabecalho = (f"Decisão já tomada pela regra ({decisao.versao_regra}): "
                 f"{decisao.decisao.upper()} {decisao.ticker}. Motivo: {decisao.motivo}.")
    criterios = "\n".join(
        f"- [{'sim' if c['ok'] else 'não' if c['ok'] is False else 'n/a'}] {c['criterio']} ({c['detalhe']})"
        for c in decisao.criterios) or "- (não informados)"
    prompt = PROMPT_EXPLICACAO_V2.format(
        ticker=decisao.ticker, decisao=decisao.decisao, motivo=decisao.motivo,
        tipo_evento=evento.get("tipo_evento"), resumo=evento.get("resumo"),
        trecho_fonte=evento.get("trecho_fonte"),
        sentimento=classificacao.get("sentimento", "sem classificação"),
        probabilidade=classificacao.get("probabilidade", "-"),
        criterios=criterios,
    )
    explicacao = _texto_llm(prompt, chamar)
    if explicacao is None:
        return cabecalho
    return f"{cabecalho}\nExplicação (gerada por IA, descreve a decisão; não a altera): {explicacao}"


def gerar_relatorio_diario(
    decisoes: list[dict],
    data: str,
    chamar: Callable[..., str] | None = None,
) -> str:
    """Relatório do dia. Cada item de `decisoes` tem "decisao" (dict de Decisao) e "evento".

    A lista de operações e os motivos são montados sem o LLM; o LLM só
    escreve o parágrafo de resumo.
    """
    linhas = []
    for item in decisoes:
        d = item["decisao"]
        evento = item.get("evento", {})
        linhas.append(f"- {d['ticker']}: {d['decisao'].upper()} | motivo da regra: {d['motivo']} "
                      f"| fonte: \"{evento.get('trecho_fonte', '')}\"")
    operacoes = [l for l, item in zip(linhas, decisoes) if item["decisao"]["decisao"] != "manter"]

    partes = [
        f"Relatório diário QUANT — {data}",
        "As decisões abaixo foram tomadas pela regra determinística (strategy.py). "
        "O texto gerado por IA apenas as descreve.",
        "",
        f"Operações ({len(operacoes)}):",
        *(operacoes or ["- nenhuma operação no dia"]),
        "",
        f"Eventos avaliados sem operação: {len(decisoes) - len(operacoes)}",
    ]
    if decisoes:
        resumo = _texto_llm(PROMPT_RELATORIO_V1.format(linhas="\n".join(linhas)), chamar)
        if resumo:
            partes += ["", "Resumo (gerado por IA):", resumo]
    return "\n".join(partes)
