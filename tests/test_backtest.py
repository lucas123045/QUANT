import json

import pandas as pd
import pytest

from src import backtest, config
from src.backtest import (CongelamentoPendente, PeriodoPendente, avaliar_criterio,
                          calcular_metricas, carregar_precos, periodo_do_config,
                          rodar_backtest, validar_periodo)

PREGOES = pd.bdate_range("2026-03-02", periods=10)  # seg 02/03 a sex 13/03
PRECOS = pd.DataFrame({
    "PETR4": [10.0, 10, 11, 12, 13, 14, 15, 16, 17, 18],
    "VALE3": [50.0, 50, 50, 45, 40, 40, 40, 40, 40, 40],
    "ITUB4": [30.0] * 10,
    "BBDC4": [15.0] * 10,
    "ABEV3": [12.0] * 10,
    "^BVSP": [100.0, 100, 101, 102, 103, 104, 105, 106, 107, 110],
}, index=PREGOES)
PERIODO = ("2026-03-02", "2026-03-13")


def evento(ticker, sentimento, quando, confirmado=True, prob=0.9, fonte="noticia"):
    return {"ticker": ticker, "tipo_evento": "outro", "confirmado": confirmado,
            "origem": {"timestamp_publicacao": quando, "tipo_fonte": fonte},
            "classificacao": {"sentimento": sentimento, "probabilidade": prob}}


# --- travas de período -------------------------------------------------------

def test_periodo_none_recusado_com_explicacao():
    with pytest.raises(PeriodoPendente, match="PENDENTE DE APROVAÇÃO"):
        validar_periodo(None, "período de teste")


@pytest.mark.parametrize("nome", ["treino", "validacao", "teste"])
def test_periodos_do_config_estao_pendentes(nome):
    with pytest.raises(PeriodoPendente):
        periodo_do_config(nome)


def test_teste_exige_data_de_congelamento(monkeypatch):
    monkeypatch.setattr(config, "PERIODO_TESTE", ("2026-01-01", "2026-06-30"))
    with pytest.raises(CongelamentoPendente, match="DATA_CONGELAMENTO"):
        periodo_do_config("teste")
    monkeypatch.setattr(config, "DATA_CONGELAMENTO", "2026-01-01")
    assert periodo_do_config("teste")[0] == pd.Timestamp("2026-01-01")


def test_treino_nao_exige_congelamento(monkeypatch):
    monkeypatch.setattr(config, "PERIODO_TREINO", ("2025-01-01", "2025-12-31"))
    assert periodo_do_config("treino")[1] == pd.Timestamp("2025-12-31")


def test_periodo_invertido():
    with pytest.raises(ValueError, match="posterior"):
        validar_periodo(("2026-02-01", "2026-01-01"))


def test_rodar_backtest_recusa_periodo_none():
    with pytest.raises(PeriodoPendente):
        rodar_backtest([], PRECOS, None, "noticia")


def test_parametros_congelaveis_nao_foram_alterados():
    assert config.LIMIAR_PROBABILIDADE == 0.7
    assert config.MAX_POSICAO_PCT == 0.20
    assert config.CAPITAL_INICIAL == 100_000.0
    assert (config.CORRETAGEM, config.EMOLUMENTOS, config.SLIPPAGE) == (0.0, 0.0, 0.0)
    assert config.DATA_CONGELAMENTO is None


# --- métricas -----------------------------------------------------------------

def test_metricas_serie_conhecida():
    patrimonio = pd.Series([100.0, 110.0, 99.0, 108.9])
    m = calcular_metricas(patrimonio, [{"retorno": 0.10}, {"retorno": -0.02}, {"retorno": 0.04}])
    assert m["retorno_acumulado"] == pytest.approx(0.089)
    assert m["drawdown_maximo"] == pytest.approx(-0.10)
    retornos = pd.Series([0.10, -0.10, 0.10])
    assert m["volatilidade_diaria"] == pytest.approx(retornos.std(ddof=1))
    assert m["volatilidade_anualizada"] == pytest.approx(retornos.std(ddof=1) * 252 ** 0.5)
    assert m["n_operacoes"] == 3
    assert m["taxa_acerto"] == pytest.approx(2 / 3)
    assert m["retorno_medio_operacao"] == pytest.approx(0.04)
    # desvio amostral de (0.10, -0.02, 0.04) = 0.06 -> EP = 0.06 / raiz(3)
    assert m["erro_padrao_operacao"] == pytest.approx(0.06 / 3 ** 0.5)


def test_erro_padrao_indefinido_com_menos_de_duas_operacoes():
    m = calcular_metricas(pd.Series([1.0, 1.1]), [{"retorno": 0.1}])
    assert m["erro_padrao_operacao"] is None
    assert calcular_metricas(pd.Series([1.0, 1.0]), [])["taxa_acerto"] is None


@pytest.mark.parametrize("estr,b1,ibov,ep,esperado", [
    (0.20, 0.10, 0.05, 0.02, True),
    (0.20, 0.19, 0.05, 0.02, False),   # não supera baseline 1 por mais que o EP
    (0.20, 0.10, 0.19, 0.02, False),   # não supera Ibovespa por mais que o EP
    (0.20, 0.10, 0.05, None, False),   # EP indefinido: não demonstrado
])
def test_criterio_de_decisao(estr, b1, ibov, ep, esperado):
    r = avaliar_criterio({"retorno_acumulado": estr, "erro_padrao_operacao": ep},
                         {"retorno_acumulado": b1}, {"retorno_acumulado": ibov})
    assert r["sinal_demonstrado"] is esperado
    assert r["conclusao"] == ("sinal demonstrado" if esperado else "sinal não demonstrado")


# --- backtest completo com série sintética ------------------------------------

def test_backtest_resultado_conhecido():
    eventos = [
        # Compra PETR4 no fechamento de 03/03 (10) ...
        evento("PETR4", "positivo", "2026-03-02T19:00:00-03:00"),
        # ... e vende no fechamento de 10/03 (15): +50% na operação.
        evento("PETR4", "negativo", "2026-03-09T12:00:00-03:00"),
        # Rumor positivo de VALE3: só o baseline 1 compra (03/03 a 50, fica aberta a 40).
        evento("VALE3", "positivo", "2026-03-02T12:00:00-03:00", confirmado=False),
    ]
    r = rodar_backtest(eventos, PRECOS, PERIODO, "noticia", capital=100_000.0, custo=0.0)

    assert r["estrategia"]["retorno_acumulado"] == pytest.approx(20_000 * 0.5 / 100_000)
    assert r["estrategia"]["n_operacoes"] == 1
    # Baseline 1: PETR4 +50% e VALE3 -20%, cada uma com 20% do patrimônio do dia.
    assert r["baseline_1"]["n_operacoes"] == 2
    assert r["baseline_1"]["retorno_acumulado"] == pytest.approx((20_000 * 0.5 - 20_000 * 0.2) / 100_000)
    assert r["ibovespa"]["retorno_acumulado"] == pytest.approx(0.10)
    assert r["criterio"]["conclusao"] == "sinal não demonstrado"  # 1 operação: EP indefinido
    assert r["tipo_fonte"] == "noticia"
    assert r["custo_por_operacao"] == 0.0


def test_backtest_com_custo_reduz_retorno():
    eventos = [evento("PETR4", "positivo", "2026-03-02T19:00:00-03:00"),
               evento("PETR4", "negativo", "2026-03-09T12:00:00-03:00")]
    sem = rodar_backtest(eventos, PRECOS, PERIODO, "noticia", custo=0.0)
    com = rodar_backtest(eventos, PRECOS, PERIODO, "noticia", custo=0.005)
    assert com["estrategia"]["retorno_acumulado"] < sem["estrategia"]["retorno_acumulado"]


def test_backtest_recusa_fontes_misturadas():
    eventos = [evento("PETR4", "positivo", "2026-03-02T19:00:00-03:00"),
               evento("VALE3", "positivo", "2026-03-02T19:00:00-03:00", fonte="fato_relevante")]
    with pytest.raises(ValueError, match="fontes misturadas"):
        rodar_backtest(eventos, PRECOS, PERIODO, "noticia")


def test_backtest_so_executa_dentro_do_periodo():
    eventos = [evento("PETR4", "positivo", "2026-03-10T12:00:00-03:00")]
    r = rodar_backtest(eventos, PRECOS, ("2026-03-02", "2026-03-06"), "noticia")
    assert r["estrategia"]["n_operacoes"] == 0
    assert r["estrategia"]["retorno_acumulado"] == 0.0


# --- carregamento de preços com cache -----------------------------------------

def test_carregar_precos_usa_cache_e_registra_download(tmp_path):
    chamadas = []

    def baixar(simbolo, inicio, fim):
        chamadas.append(simbolo)
        indice = pd.DatetimeIndex(["2026-03-02", "2026-03-03"], tz="America/Sao_Paulo")
        return pd.Series([1.0, 2.0], index=indice)

    precos = carregar_precos("2026-03-02", "2026-03-03", ["PETR4", "^BVSP"], tmp_path, baixar)
    assert chamadas == ["PETR4.SA", "^BVSP"]
    assert list(precos.columns) == ["PETR4", "^BVSP"]
    assert precos.index.tz is None

    de_novo = carregar_precos("2026-03-02", "2026-03-03", ["PETR4", "^BVSP"], tmp_path, baixar)
    assert chamadas == ["PETR4.SA", "^BVSP"]  # nada baixado de novo
    pd.testing.assert_frame_equal(precos, de_novo, check_freq=False)

    registros = [json.loads(l) for l in (tmp_path / "downloads.jsonl").read_text().splitlines()]
    assert [r["simbolo"] for r in registros] == ["PETR4.SA", "^BVSP"]
    assert all("data_download" in r for r in registros)


def test_simbolo_yfinance():
    assert backtest.simbolo_yfinance("PETR4") == "PETR4.SA"
    assert backtest.simbolo_yfinance("^BVSP") == "^BVSP"
