"""CDI diário (Banco Central, SGS série 12) para o produto "Renda fixa (CDI)".

No Brasil, a alternativa óbvia a investir em ações é deixar o dinheiro na
renda fixa rendendo perto do CDI. Sem essa referência, a comparação da
simulação fica incompleta (e o caixa da estratégia, que rende 0%, parece
"seguro" quando na verdade está perdendo para a renda fixa).

Fonte: https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados (taxa em % ao dia,
um valor por dia útil). Convenção: a taxa do dia d remunera de d até o
próximo dia útil.
"""

import json
from collections.abc import Callable
from datetime import date
from pathlib import Path

import pandas as pd

from src import rede

URL_SGS = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json"
           "&dataInicial={inicio}&dataFinal={fim}")
DIAS_ATE_FECHAR = 5  # depois disso, a série do período não muda mais: pode ir para o cache


def baixar_bcb(inicio: date, fim: date) -> list[dict]:
    url = URL_SGS.format(inicio=inicio.strftime("%d/%m/%Y"), fim=fim.strftime("%d/%m/%Y"))
    return json.loads(rede.baixar(url, 30, "quant-academico/1.0"))


def carregar_cdi(inicio: date, fim: date, pasta: Path,
                 baixar: Callable[[date, date], list[dict]] | None = None) -> pd.Series:
    """Taxa diária do CDI (fração, ex.: 0.00050788), indexada por data. Com cache."""
    pasta.mkdir(parents=True, exist_ok=True)
    caminho = pasta / f"cdi_{inicio.isoformat()}_{fim.isoformat()}.json"
    bruto = json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else None
    if not isinstance(bruto, list):  # sem cache, ou cache antigo que guardou uma resposta de erro
        bruto = (baixar or baixar_bcb)(inicio, fim)
        # Período sem taxa publicada (o BC publica o dia seguinte) vem como erro, não como lista.
        bruto = bruto if isinstance(bruto, list) else []
        # Só guarda período fechado: os últimos dias ainda podem ganhar taxa.
        if bruto and (date.today() - fim).days > DIAS_ATE_FECHAR:
            caminho.write_text(json.dumps(bruto), encoding="utf-8")
    serie = pd.Series({pd.Timestamp(pd.to_datetime(i["data"], dayfirst=True)): float(i["valor"]) / 100
                       for i in bruto}, dtype=float)
    return serie.sort_index()


def patrimonio_cdi(pregoes: pd.DatetimeIndex, taxas: pd.Series, capital: float) -> pd.Series:
    """Valor de `capital` aplicado no CDI desde o primeiro pregão, em cada pregão.

    No pregão t, acumula as taxas dos dias d com primeiro_pregao <= d < t.
    """
    fator = (1 + taxas).cumprod()
    antes = lambda dia: float(fator[fator.index < dia].iloc[-1]) if (fator.index < dia).any() else 1.0
    base = antes(pregoes[0])
    return pd.Series([capital * antes(t) / base for t in pregoes], index=pregoes, dtype=float)
