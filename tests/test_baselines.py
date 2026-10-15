import pandas as pd
import pytest

from src import baselines
from src.backtest import comprar_e_segurar, proximo_pregao, simular, sinais_para_ordens

# 5 pregões (seg-sex). PETR4 sobe 10%/dia; VALE3 cai 10%/dia; ITUB4 constante.
PREGOES = pd.DatetimeIndex(["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"])
PRECOS = pd.DataFrame({
    "PETR4": [10.0, 11.0, 12.1, 13.31, 14.641],
    "VALE3": [100.0, 90.0, 81.0, 72.9, 65.61],
    "ITUB4": [30.0] * 5,
    "^BVSP": [100_000.0, 101_000.0, 102_010.0, 103_030.1, 104_060.401],
}, index=PREGOES)


def evento(ticker, sentimento, quando, confirmado=True, probabilidade=0.9):
    return {"ticker": ticker, "tipo_evento": "outro", "confirmado": confirmado,
            "origem": {"timestamp_publicacao": quando, "tipo_fonte": "noticia"},
            "classificacao": {"sentimento": sentimento, "probabilidade": probabilidade}}


# --- execução no próximo pregão ---------------------------------------------

@pytest.mark.parametrize("instante,esperado", [
    ("2026-10-05T10:00:00-03:00", "2026-10-06"),   # durante o pregão -> pregão seguinte
    ("2026-10-05T19:00:00-03:00", "2026-10-06"),   # após o fechamento -> pregão seguinte
    ("2026-10-06T01:30:00+00:00", "2026-10-06"),   # 22:30 de 05/10 em São Paulo
    ("2026-10-03T12:00:00-03:00", "2026-10-05"),   # sábado -> segunda
    ("2026-10-09T12:00:00-03:00", None),           # sem pregão posterior na série
])
def test_proximo_pregao(instante, esperado):
    resultado = proximo_pregao(instante, PREGOES)
    assert (resultado is None and esperado is None) or resultado == pd.Timestamp(esperado)


def test_sinal_sem_tipo_fonte_rejeitado():
    with pytest.raises(ValueError, match="tipo_fonte"):
        sinais_para_ordens([{"ticker": "PETR4", "decisao": "compra", "fracao_alvo": 0.2,
                             "instante": "2026-10-05T10:00:00-03:00"}], PREGOES)


# --- baseline 1 --------------------------------------------------------------

def test_baseline_1_compra_toda_noticia_positiva_sem_filtros():
    eventos = [
        evento("PETR4", "positivo", "2026-10-05T10:00:00-03:00", confirmado=False, probabilidade=0.1),
        evento("VALE3", "negativo", "2026-10-06T10:00:00-03:00"),
        evento("ITUB4", "neutro", "2026-10-06T11:00:00-03:00"),
    ]
    sinais = baselines.sinais_baseline_1(eventos)
    assert [(s["ticker"], s["decisao"]) for s in sinais] == [("PETR4", "compra"), ("VALE3", "venda")]
    assert sinais[0]["tipo_fonte"] == "noticia"


def test_baseline_1_resultado_conhecido():
    # Compra PETR4 no fechamento de 06/10 (11,0) e segura até 09/10 (14,641): +33,1%.
    eventos = [evento("PETR4", "positivo", "2026-10-05T10:00:00-03:00", confirmado=False)]
    ordens = sinais_para_ordens(baselines.sinais_baseline_1(eventos), PREGOES)
    sim = simular(ordens, PRECOS, capital=100_000.0, custo=0.0)
    assert sim.patrimonio.iloc[-1] == pytest.approx(80_000 + 20_000 * 1.331)
    assert sim.operacoes[0]["retorno"] == pytest.approx(0.331)
    assert sim.operacoes[0]["aberta"] is True


def test_simular_compra_e_venda_com_custo():
    ordens = [
        {"ticker": "PETR4", "decisao": "compra", "fracao_alvo": 0.2, "data_execucao": PREGOES[0]},
        {"ticker": "PETR4", "decisao": "venda", "fracao_alvo": 0.0, "data_execucao": PREGOES[1]},
        {"ticker": "VALE3", "decisao": "venda", "fracao_alvo": 0.0, "data_execucao": PREGOES[1]},
    ]
    sim = simular(ordens, PRECOS, capital=100_000.0, custo=0.01)
    # Compra 20.000: 19.800 em ações; vende com +10% e -1%: 19.800*1,1*0,99 = 21.562,2
    assert sim.operacoes[0]["recebido"] == pytest.approx(21_562.2)
    assert sim.operacoes[0]["retorno"] == pytest.approx(21_562.2 / 20_000 - 1)
    assert sim.patrimonio.iloc[-1] == pytest.approx(80_000 + 21_562.2)
    assert sim.ignoradas[0]["razao"] == "sem posição para vender"


def test_simular_respeita_max_posicao_e_nao_duplica():
    ordens = [{"ticker": t, "decisao": "compra", "fracao_alvo": 0.2, "data_execucao": PREGOES[0]}
              for t in ("PETR4", "PETR4", "ITUB4")]
    sim = simular(ordens, PRECOS, capital=100_000.0, custo=0.0)
    investidos = sorted(op["investido"] for op in sim.operacoes)
    assert investidos == pytest.approx([20_000.0, 20_000.0])
    assert [i["razao"] for i in sim.ignoradas] == ["já posicionado"]


def test_simular_limita_ao_caixa():
    tickers = ["PETR4", "VALE3", "ITUB4"]
    ordens = [{"ticker": t, "decisao": "compra", "fracao_alvo": 0.5, "data_execucao": PREGOES[0]}
              for t in tickers]
    sim = simular(ordens, PRECOS, capital=100_000.0, custo=0.0)
    assert sum(op["investido"] for op in sim.operacoes) == pytest.approx(100_000.0)
    assert [i["razao"] for i in sim.ignoradas] == ["sem caixa"]


# --- baseline 2 --------------------------------------------------------------

OPS_ESTRATEGIA = [{"ticker": "PETR4", "entrada": PREGOES[0], "saida": PREGOES[2], "aberta": False}]


def test_baseline_2_reprodutivel_com_semente():
    a = baselines.baseline_sorteio(OPS_ESTRATEGIA, PRECOS, ["PETR4", "VALE3"], 200, semente=7)
    b = baselines.baseline_sorteio(OPS_ESTRATEGIA, PRECOS, ["PETR4", "VALE3"], 200, semente=7)
    c = baselines.baseline_sorteio(OPS_ESTRATEGIA, PRECOS, ["PETR4", "VALE3"], 200, semente=8)
    assert a["retornos"] == b["retornos"]
    assert a["retornos"] != c["retornos"]
    assert a["semente"] == 7 and a["n_simulacoes"] == 200 and a["n_operacoes"] == 1


def test_baseline_2_resultado_conhecido_com_um_ticker():
    # Só ITUB4 (preço constante): todo sorteio rende exatamente 0.
    r = baselines.baseline_sorteio(OPS_ESTRATEGIA, PRECOS, ["ITUB4"], 50, semente=1,
                                   retorno_estrategia=0.01)
    assert set(r["retornos"]) == {0.0}
    assert r["fracao_sorteios_maior_ou_igual"] == 0.0


def test_baseline_2_valores_possiveis():
    # Duas pregões de duração, 20% da carteira: PETR4 +21% -> +4,2%; VALE3 -19% -> -3,8%.
    r = baselines.baseline_sorteio(OPS_ESTRATEGIA, PRECOS, ["PETR4", "VALE3"], 1000, semente=3)
    assert {round(x, 6) for x in r["retornos"]} == {0.042, -0.038}
    assert r["p05"] == pytest.approx(-0.038) and r["p95"] == pytest.approx(0.042)
    assert r["n_simulacoes"] == 1000


def test_baseline_2_usa_semente_do_config():
    r = baselines.baseline_sorteio(OPS_ESTRATEGIA, PRECOS, ["PETR4"], 10)
    assert r["semente"] == 20261015


# --- baseline 3 --------------------------------------------------------------

def test_baseline_3_comprar_e_segurar_ibovespa():
    serie = comprar_e_segurar(PRECOS["^BVSP"], capital=100_000.0)
    assert serie.iloc[-1] == pytest.approx(100_000 * 1.01 ** 4)
