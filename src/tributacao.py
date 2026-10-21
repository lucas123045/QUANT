"""Imposto de renda sobre ganhos com ações em operações comuns (swing trade).

Regras (config.py, seção da camada prática, com as fontes):
- o imposto é apurado por mês: 15% sobre o lucro líquido do mês;
- o mês é isento se o TOTAL VENDIDO em ações não passar de R$ 20 mil. A
  isenção olha o valor vendido, não o lucro, e é "tudo ou nada": um real acima
  do limite torna tributável todo o lucro do mês;
- prejuízo de um mês fica acumulado e abate o lucro de meses tributáveis
  seguintes (num mês isento, o lucro não consome o prejuízo acumulado);
- custos de compra e venda entram no custo e no valor líquido da venda.

Usado só pela camada prática (src/pratica.py). Não é orientação tributária.
"""

from collections import defaultdict
from datetime import date

import pandas as pd

from src import config


def _mes(dia) -> str:
    return pd.Timestamp(dia).strftime("%Y-%m")


def apurar(vendas: list[dict], aliquota: float | None = None, isencao: float | None = None) -> dict:
    """Apuração mês a mês.

    `vendas`: [{"data", "valor" (valor bruto vendido), "lucro" (líquido de custos)}].
    Devolve {"meses": [...], "imposto_total", "prejuizo_a_compensar"}.
    """
    aliquota = config.PRATICA_IR_ALIQUOTA if aliquota is None else aliquota
    isencao = config.PRATICA_IR_ISENCAO_VENDAS_MES if isencao is None else isencao
    por_mes: dict[str, dict] = defaultdict(lambda: {"vendas": 0.0, "lucro": 0.0, "n": 0})
    for v in vendas:
        m = por_mes[_mes(v["data"])]
        m["vendas"] += float(v["valor"])
        m["lucro"] += float(v["lucro"])
        m["n"] += 1

    prejuizo = 0.0
    meses = []
    for mes in sorted(por_mes):
        m = por_mes[mes]
        linha = {"mes": mes, "n_vendas": m["n"], "vendas": m["vendas"], "lucro": m["lucro"],
                 "isento": False, "prejuizo_usado": 0.0, "base": 0.0, "imposto": 0.0}
        if m["lucro"] < 0:
            prejuizo += -m["lucro"]
            linha["situacao"] = "prejuízo: fica para abater lucros futuros"
        elif m["vendas"] <= isencao:
            linha["isento"] = True
            linha["situacao"] = f"isento: vendas do mês até R$ {isencao:,.0f}".replace(",", ".")
        else:
            usado = min(prejuizo, m["lucro"])
            prejuizo -= usado
            linha["prejuizo_usado"] = usado
            linha["base"] = m["lucro"] - usado
            linha["imposto"] = aliquota * linha["base"]
            linha["situacao"] = "tributável" + (" (com prejuízo compensado)" if usado else "")
            if linha["imposto"] > 0:
                linha["vencimento_darf"] = vencimento_darf(mes).isoformat()
        linha["prejuizo_acumulado"] = prejuizo
        meses.append(linha)
    return {"meses": meses, "imposto_total": sum(l["imposto"] for l in meses),
            "prejuizo_a_compensar": prejuizo, "aliquota": aliquota, "isencao_vendas_mes": isencao}


def provisao_diaria(vendas: list[dict], pregoes: pd.DatetimeIndex, **kwargs) -> pd.Series:
    """Imposto devido acumulado em cada pregão, contando o mês em curso até aquele dia.

    Subtrair isso do patrimônio dá o patrimônio líquido de imposto: o DARF sai
    do caixa no mês seguinte, mas o dinheiro já não é do investidor.
    """
    ordenadas = sorted(vendas, key=lambda v: pd.Timestamp(v["data"]))
    valores = []
    for dia in pregoes:
        ate = [v for v in ordenadas if pd.Timestamp(v["data"]) <= dia]
        valores.append(apurar(ate, **kwargs)["imposto_total"] if ate else 0.0)
    return pd.Series(valores, index=pregoes, dtype=float)


def vencimento_darf(mes: str) -> date:
    """Último dia útil (seg-sex, sem feriados) do mês seguinte ao da apuração."""
    inicio = pd.Timestamp(f"{mes}-01") + pd.offsets.MonthBegin(1)
    fim = inicio + pd.offsets.MonthEnd(0)
    return pd.bdate_range(inicio, fim)[-1].date()
