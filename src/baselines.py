"""Baselines de comparação.

1. Comprar qualquer notícia positiva: mesmos eventos classificados, mesma
   execução (próximo pregão) e mesma saída da estratégia (vende em evento
   negativo), mas sem os filtros da regra (confirmação, limiar, evento oposto
   recente).
2. Sorteio: mesma quantidade de operações e mesmas durações da estratégia,
   com tickers e datas de entrada sorteados; semente fixa e registrada.
3. Comprar e segurar o Ibovespa: backtest.comprar_e_segurar.
"""

import numpy as np
import pandas as pd

from src import config
from src.backtest import Simulacao, instante_do_evento, simular, tipo_fonte_do_evento
from src.strategy import COMPRA, VENDA


def sinais_baseline_1(eventos: list[dict], fracao: float | None = None) -> list[dict]:
    """Compra em todo evento classificado positivo; vende em todo negativo."""
    fracao = config.MAX_POSICAO_PCT if fracao is None else fracao
    sinais = []
    for evento in sorted(eventos, key=lambda e: instante_do_evento(e) or ""):
        sentimento = (evento.get("classificacao") or {}).get("sentimento")
        if sentimento not in ("positivo", "negativo"):
            continue
        sinais.append({
            "ticker": evento["ticker"],
            "decisao": COMPRA if sentimento == "positivo" else VENDA,
            "fracao_alvo": fracao if sentimento == "positivo" else 0.0,
            "instante": instante_do_evento(evento),
            "tipo_fonte": tipo_fonte_do_evento(evento),
            "motivo": f"baseline 1: notícia {sentimento}",
        })
    return sinais


def _retorno(sim: Simulacao) -> float:
    return float(sim.patrimonio.iloc[-1] / sim.patrimonio.iloc[0] - 1)


def baseline_sorteio(
    operacoes_estrategia: list[dict],
    precos: pd.DataFrame,
    tickers: list[str] | None = None,
    n_simulacoes: int | None = None,
    semente: int | None = None,
    retorno_estrategia: float | None = None,
    capital: float | None = None,
    custo: float | None = None,
    fracao: float | None = None,
) -> dict:
    """Distribuição do retorno acumulado com operações sorteadas.

    Para cada operação da estratégia (duração em pregões preservada), sorteia
    ticker e pregão de entrada. Operação que ficou aberta na estratégia
    também fica aberta no sorteio.
    """
    tickers = config.CARTEIRA if tickers is None else tickers
    n_simulacoes = config.N_SIMULACOES_BASELINE_2 if n_simulacoes is None else n_simulacoes
    semente = config.SEMENTE_BASELINE_2 if semente is None else semente
    fracao = config.MAX_POSICAO_PCT if fracao is None else fracao
    pregoes = precos.index
    n = len(pregoes)
    if n < 2:
        raise ValueError("série de preços curta demais para o sorteio")

    duracoes = []
    for op in operacoes_estrategia:
        duracao = pregoes.get_loc(op["saida"]) - pregoes.get_loc(op["entrada"])
        duracoes.append((min(duracao, n - 1), op.get("aberta", False)))

    gerador = np.random.default_rng(semente)
    retornos = []
    for _ in range(n_simulacoes):
        ordens = []
        for duracao, aberta in duracoes:
            ticker = tickers[gerador.integers(len(tickers))]
            entrada = int(gerador.integers(0, n - duracao)) if not aberta else n - 1 - duracao
            ordens.append({"ticker": ticker, "decisao": COMPRA, "fracao_alvo": fracao,
                           "data_execucao": pregoes[entrada]})
            if not aberta:
                ordens.append({"ticker": ticker, "decisao": VENDA, "fracao_alvo": 0.0,
                               "data_execucao": pregoes[entrada + duracao]})
        retornos.append(_retorno(simular(ordens, precos, capital, custo)))

    distribuicao = np.array(retornos)
    resultado = {
        "semente": semente,
        "n_simulacoes": n_simulacoes,
        "n_operacoes": len(duracoes),
        "retornos": retornos,
        "media": float(distribuicao.mean()),
        "desvio": float(distribuicao.std(ddof=1)) if n_simulacoes > 1 else 0.0,
        "p05": float(np.percentile(distribuicao, 5)),
        "p50": float(np.percentile(distribuicao, 50)),
        "p95": float(np.percentile(distribuicao, 95)),
    }
    if retorno_estrategia is not None:
        # p-valor empírico: fração dos sorteios que empatam ou superam a estratégia.
        resultado["fracao_sorteios_maior_ou_igual"] = float((distribuicao >= retorno_estrategia).mean())
    return resultado
