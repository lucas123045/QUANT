"""Backtest contra o Ibovespa e cálculo de métricas.

Convenções:
- Preços: DataFrame com índice de pregões (datas sem fuso) e uma coluna por
  ticker da carteira (sem sufixo) e pelo benchmark (^BVSP).
- Execução: sinal publicado no dia D (fuso de referência) é executado no
  fechamento do primeiro pregão estritamente posterior a D.
- Tamanho: compra aloca até `fracao_alvo` (MAX_POSICAO_PCT) do patrimônio,
  limitado ao caixa. Ações fracionárias são permitidas (simplificação).
- Sem venda a descoberto: VENDA só zera posição existente.
- Custos: frações do valor negociado (config.py, zerados por padrão).
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from src import config
from src.strategy import COMPRA, VENDA, decidir

logger = logging.getLogger(__name__)

FUSO = ZoneInfo(config.FUSO_REFERENCIA)


def custo_total(custos: dict | None = None) -> float:
    """Custo proporcional por operação (corretagem + emolumentos + slippage)."""
    if custos is None:
        custos = {"corretagem": config.CORRETAGEM, "emolumentos": config.EMOLUMENTOS,
                  "slippage": config.SLIPPAGE}
    return float(sum(custos.values()))


# ---------------------------------------------------------------------------
# Calendário e sinais
# ---------------------------------------------------------------------------

def data_local(instante: str | datetime) -> pd.Timestamp:
    """Data (sem hora) do instante no fuso de referência."""
    if isinstance(instante, str):
        instante = datetime.fromisoformat(instante)
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=FUSO)
    return pd.Timestamp(instante.astimezone(FUSO).date())


def proximo_pregao(instante: str | datetime, pregoes: pd.DatetimeIndex) -> pd.Timestamp | None:
    """Primeiro pregão estritamente posterior ao dia local do instante."""
    posicao = pregoes.searchsorted(data_local(instante), side="right")
    return pregoes[posicao] if posicao < len(pregoes) else None


def instante_do_evento(evento: dict) -> str | None:
    return (evento.get("origem") or {}).get("timestamp_publicacao") or evento.get("timestamp_publicacao")


def tipo_fonte_do_evento(evento: dict) -> str | None:
    return (evento.get("origem") or {}).get("tipo_fonte") or evento.get("tipo_fonte")


def sinais_da_estrategia(eventos: list[dict]) -> list[dict]:
    """Aplica `decidir` a eventos classificados, em ordem cronológica.

    Cada evento precisa de "classificacao" e da origem (timestamp e tipo_fonte).
    Devolve só os sinais de compra/venda.
    """
    ordenados = sorted(eventos, key=lambda e: instante_do_evento(e) or "")
    sinais = []
    for i, evento in enumerate(ordenados):
        decisao = decidir(evento, evento.get("classificacao"), historico=ordenados[:i])
        if decisao.decisao in (COMPRA, VENDA):
            sinais.append({
                "ticker": decisao.ticker,
                "decisao": decisao.decisao,
                "fracao_alvo": decisao.fracao_alvo,
                "instante": instante_do_evento(evento),
                "tipo_fonte": tipo_fonte_do_evento(evento),
                "motivo": decisao.motivo,
            })
    return sinais


def sinais_para_ordens(sinais: list[dict], pregoes: pd.DatetimeIndex) -> list[dict]:
    """Converte sinais (com instante de publicação) em ordens datadas por pregão."""
    ordens = []
    for sinal in sinais:
        if not sinal.get("tipo_fonte"):
            raise ValueError("sinal sem tipo_fonte: a origem de cada evento precisa ser registrada")
        if not sinal.get("instante"):
            logger.warning("Sinal sem instante de publicação ignorado: %r", sinal)
            continue
        execucao = proximo_pregao(sinal["instante"], pregoes)
        if execucao is None:
            continue  # publicado depois do último pregão disponível
        ordens.append({**sinal, "data_execucao": execucao})
    return ordens


# ---------------------------------------------------------------------------
# Simulação
# ---------------------------------------------------------------------------

@dataclass
class Simulacao:
    patrimonio: pd.Series
    operacoes: list[dict] = field(default_factory=list)   # idas e voltas
    ignoradas: list[dict] = field(default_factory=list)


def simular(
    ordens: list[dict],
    precos: pd.DataFrame,
    capital: float | None = None,
    custo: float | None = None,
) -> Simulacao:
    """Executa as ordens no fechamento de `data_execucao` e marca a carteira a mercado.

    Posições abertas no último pregão são liquidadas teoricamente no último
    fechamento (com custo) para o cálculo do retorno por operação.
    """
    capital = config.CAPITAL_INICIAL if capital is None else capital
    custo = custo_total() if custo is None else custo
    pregoes = precos.index

    por_dia: dict[pd.Timestamp, list[dict]] = {}
    for ordem in ordens:
        por_dia.setdefault(pd.Timestamp(ordem["data_execucao"]), []).append(ordem)

    caixa = capital
    posicoes: dict[str, dict] = {}
    operacoes, ignoradas, patrimonio = [], [], []

    def valor_carteira(dia) -> float:
        return caixa + sum(p["quantidade"] * precos.at[dia, t] for t, p in posicoes.items())

    for dia in pregoes:
        # Vendas antes das compras; ordem alfabética para ser determinístico.
        do_dia = sorted(por_dia.get(dia, []), key=lambda o: (o["decisao"] != VENDA, o["ticker"]))
        for ordem in do_dia:
            ticker = ordem["ticker"]
            preco = precos.at[dia, ticker] if ticker in precos.columns else float("nan")
            if pd.isna(preco):
                ignoradas.append({**ordem, "razao": "sem preço no pregão"})
                continue
            if ordem["decisao"] == VENDA:
                if ticker not in posicoes:
                    ignoradas.append({**ordem, "razao": "sem posição para vender"})
                    continue
                pos = posicoes.pop(ticker)
                recebido = pos["quantidade"] * preco * (1 - custo)
                caixa += recebido
                operacoes.append({"ticker": ticker, "entrada": pos["entrada"], "saida": dia,
                                  "investido": pos["investido"], "recebido": recebido,
                                  "retorno": recebido / pos["investido"] - 1, "aberta": False})
            else:
                if ticker in posicoes:
                    ignoradas.append({**ordem, "razao": "já posicionado"})
                    continue
                valor = min(ordem["fracao_alvo"] * valor_carteira(dia), caixa)
                if valor <= 0:
                    ignoradas.append({**ordem, "razao": "sem caixa"})
                    continue
                caixa -= valor
                posicoes[ticker] = {"quantidade": valor * (1 - custo) / preco,
                                    "entrada": dia, "investido": valor}
        patrimonio.append(valor_carteira(dia))

    if len(pregoes):
        ultimo = pregoes[-1]
        for ticker, pos in posicoes.items():
            recebido = pos["quantidade"] * precos.at[ultimo, ticker] * (1 - custo)
            operacoes.append({"ticker": ticker, "entrada": pos["entrada"], "saida": ultimo,
                              "investido": pos["investido"], "recebido": recebido,
                              "retorno": recebido / pos["investido"] - 1, "aberta": True})

    return Simulacao(pd.Series(patrimonio, index=pregoes, dtype=float), operacoes, ignoradas)


def comprar_e_segurar(serie: pd.Series, capital: float | None = None) -> pd.Series:
    """Patrimônio de comprar e segurar uma série (baseline 3: Ibovespa)."""
    capital = config.CAPITAL_INICIAL if capital is None else capital
    serie = serie.dropna()
    return capital * serie / serie.iloc[0]
