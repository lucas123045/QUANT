"""Métricas de risco de uma carteira, no padrão usado por gestores.

- Retorno por risco contra o CDI (a taxa livre de risco brasileira), não contra
  zero: com o CDI perto de 14% ao ano, ganhar 10% em ações é perder para a
  renda fixa correndo risco.
  Sharpe = média(r - CDI) / desvio(r) * raiz(252);
  Sortino = média(r - CDI) / desvio só das quedas * raiz(252).
- Maior queda (do pico ao vale) e quantos pregões levou para recuperar.
- Beta e correlação com o Ibovespa.
- Por operação: taxa de acerto, ganho médio, perda média, payoff (ganho médio /
  perda média) e fator de lucro (soma dos ganhos / soma das perdas).

Com menos de MINIMO_PREGOES_ANUALIZAR pregões, as métricas anualizadas não são
mostradas: anualizar uma semana gera números absurdos.
"""

import math

import pandas as pd

MINIMO_PREGOES_ANUALIZAR = 60
PREGOES_ANO = 252


def _drawdown(patrimonio: pd.Series) -> dict:
    pico = patrimonio.cummax()
    queda = patrimonio / pico - 1
    fundo = queda.idxmin() if len(queda) else None
    maior = float(queda.min()) if len(queda) else 0.0
    duracao, recuperado = None, None
    if fundo is not None and maior < 0:
        inicio = patrimonio.loc[:fundo].idxmax()
        depois = patrimonio.loc[fundo:]
        volta = depois[depois >= patrimonio.at[inicio]]
        recuperado = not volta.empty
        fim = volta.index[0] if recuperado else patrimonio.index[-1]
        duracao = int(patrimonio.index.get_loc(fim) - patrimonio.index.get_loc(inicio))
    return {"drawdown_maximo": maior, "drawdown_pregoes": duracao, "drawdown_recuperado": recuperado}


def metricas(patrimonio: pd.Series, cdi_diario: pd.Series | None = None,
             ibovespa: pd.Series | None = None, operacoes: list[dict] | None = None) -> dict:
    """Métricas de uma série de patrimônio (índice de pregões).

    `cdi_diario`: taxa do CDI por dia (fração); a taxa do dia d remunera de d ao
    pregão seguinte, então o retorno livre de risco do pregão t é a taxa de t-1.
    """
    patrimonio = patrimonio.dropna()
    r = patrimonio.pct_change().dropna()
    n = len(patrimonio)
    resultado = {"pregoes": n, "retorno_acumulado": float(patrimonio.iloc[-1] / patrimonio.iloc[0] - 1) if n else None,
                 "anualizadas_confiaveis": n >= MINIMO_PREGOES_ANUALIZAR, **_drawdown(patrimonio)}
    vol = float(r.std(ddof=1)) if len(r) > 1 else None
    resultado["volatilidade_anualizada"] = vol * math.sqrt(PREGOES_ANO) if vol is not None else None

    livre = pd.Series(0.0, index=r.index)
    if cdi_diario is not None and len(cdi_diario):
        taxas = cdi_diario.reindex(patrimonio.index, method="ffill").shift(1)
        livre = taxas.reindex(r.index).fillna(0.0)
    excesso = r - livre
    if n >= MINIMO_PREGOES_ANUALIZAR and vol:
        resultado["retorno_anualizado"] = float((1 + resultado["retorno_acumulado"]) ** (PREGOES_ANO / (n - 1)) - 1)
        resultado["sharpe"] = float(excesso.mean() / vol * math.sqrt(PREGOES_ANO))
        quedas = excesso[excesso < 0]
        desvio_quedas = float(math.sqrt((quedas ** 2).sum() / len(excesso))) if len(excesso) else 0.0
        resultado["sortino"] = float(excesso.mean() / desvio_quedas * math.sqrt(PREGOES_ANO)) if desvio_quedas else None
    else:
        resultado.update({"retorno_anualizado": None, "sharpe": None, "sortino": None})

    if ibovespa is not None:
        m = ibovespa.reindex(patrimonio.index).pct_change().reindex(r.index)
        juntos = pd.concat([r, m], axis=1).dropna()
        if len(juntos) > 2 and juntos.iloc[:, 1].var() > 0 and juntos.iloc[:, 0].var() > 0:
            resultado["beta"] = float(juntos.cov().iloc[0, 1] / juntos.iloc[:, 1].var())
            resultado["correlacao_ibovespa"] = float(juntos.corr().iloc[0, 1])
        else:
            resultado.update({"beta": None, "correlacao_ibovespa": None})

    if operacoes is not None:
        resultado.update(por_operacao(operacoes))
    return resultado


def por_operacao(operacoes: list[dict]) -> dict:
    retornos = [float(o["retorno"]) for o in operacoes]
    resultados = [float(o.get("resultado", 0.0)) for o in operacoes]
    ganhos = [v for v in retornos if v > 0]
    perdas = [v for v in retornos if v <= 0]
    soma_ganhos = sum(v for v in resultados if v > 0)
    soma_perdas = -sum(v for v in resultados if v < 0)
    return {
        "n_operacoes": len(retornos),
        "taxa_acerto": len(ganhos) / len(retornos) if retornos else None,
        "ganho_medio": sum(ganhos) / len(ganhos) if ganhos else None,
        "perda_media": sum(perdas) / len(perdas) if perdas else None,
        "payoff": (sum(ganhos) / len(ganhos)) / abs(sum(perdas) / len(perdas))
        if ganhos and perdas and sum(perdas) else None,
        "fator_lucro": soma_ganhos / soma_perdas if soma_perdas else None,
    }


def correlacoes(precos: pd.DataFrame, tickers: list[str], janela: int = 120) -> dict:
    """Correlação dos retornos diários das ações nos últimos `janela` pregões."""
    disponiveis = [t for t in tickers if t in precos.columns]
    rets = precos[disponiveis].pct_change(fill_method=None).iloc[-janela:].dropna(how="all")
    if len(rets) < 20:
        return {"pregoes": len(rets), "tickers": disponiveis, "matriz": None}
    matriz = rets.corr()
    return {"pregoes": len(rets), "tickers": disponiveis,
            "matriz": [[None if pd.isna(matriz.at[a, b]) else round(float(matriz.at[a, b]), 3)
                        for b in disponiveis] for a in disponiveis]}
