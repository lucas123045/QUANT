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
    """Trava contra alterações acidentais.

    Este teste FALHA DE PROPÓSITO no dia do congelamento (DATA_CONGELAMENTO
    deixa de ser None) ou se algum parâmetro mudar. Atualizá-lo é um ato
    deliberado, que deve entrar no mesmo commit da mudança aprovada.
    """
    assert config.LIMIAR_PROBABILIDADE == 0.7
    assert config.MAX_POSICAO_PCT == 0.20
    assert config.CAPITAL_INICIAL == 100_000.0
    assert config.JANELA_EVENTO_RECENTE_DIAS == 5
    assert config.ALFA_CRITERIO == 0.05
    assert config.SEMENTE_BASELINE_2 == 20261015
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


FORTE = [0.05, 0.06, 0.04, 0.05, 0.07, 0.03, 0.05, 0.06]     # excessos claramente > 0
FRACO_B1 = [0.00, 0.01, -0.01, 0.00, 0.02, -0.02, 0.01, -0.01]


def criterio(estr=0.20, b1=0.10, ibov=0.05, exc_estr=FORTE, exc_b1=FRACO_B1):
    return avaliar_criterio({"retorno_acumulado": estr}, {"retorno_acumulado": b1},
                            {"retorno_acumulado": ibov}, exc_estr, exc_b1, alfa=0.05)


def test_criterio_demonstrado_quando_tudo_passa():
    r = criterio()
    assert r["sinal_demonstrado"] is True and r["conclusao"] == "sinal demonstrado"
    assert r["versao"] == "CRITERIO_V2"
    assert r["teste_vs_ibovespa"]["p_valor"] < 0.05
    assert r["teste_vs_baseline_1"]["p_valor"] < 0.05


@pytest.mark.parametrize("alteracao,motivo", [
    ({"b1": 0.25}, "direção: perde do baseline 1 no acumulado"),
    ({"ibov": 0.30}, "direção: perde do Ibovespa no acumulado"),
    ({"exc_estr": [0.01, -0.01, 0.02, -0.02, 0.01, 0.0]}, "excesso vs Ibovespa não significativo"),
    ({"exc_b1": FORTE}, "não supera o baseline 1 por operação"),
    ({"exc_estr": [0.05]}, "uma operação: teste indefinido"),
    ({"exc_estr": [0.02, 0.02, 0.02]}, "variância zero: teste indefinido"),
])
def test_criterio_nao_demonstrado(alteracao, motivo):
    assert criterio(**alteracao)["sinal_demonstrado"] is False, motivo


def test_criterio_v2_corrige_o_defeito_do_v1():
    """Contraexemplo da revisão: 50 operações, média 0,2% e desvio 3% por operação.

    O CRITERIO_V1 (diferença de retorno acumulado > erro padrão por operação)
    aprovaria com t ≈ 0,5, que não é significativo. O V2 não aprova.
    """
    import numpy as np
    gerador = np.random.default_rng(1)
    bruto = gerador.normal(0, 1, 50)
    excessos = list(0.002 + 0.03 * (bruto - bruto.mean()) / bruto.std(ddof=1))  # média e desvio exatos
    retorno_acumulado = 0.2 * 50 * 0.002  # sizing de 20%, ≈ 2%
    erro_padrao = 0.03 / 50 ** 0.5        # ≈ 0,42%

    criterio_v1_aprovaria = retorno_acumulado - 0.0 > erro_padrao
    assert criterio_v1_aprovaria

    r = avaliar_criterio({"retorno_acumulado": retorno_acumulado}, {"retorno_acumulado": 0.0},
                         {"retorno_acumulado": 0.0}, excessos, [0.0, 0.001, -0.001], alfa=0.05)
    assert r["teste_vs_ibovespa"]["t"] == pytest.approx(0.002 / erro_padrao)  # ≈ 0,47
    assert r["sinal_demonstrado"] is False


def test_contaminacao(monkeypatch):
    inicio = pd.Timestamp("2025-01-01")
    assert backtest.verificar_contaminacao(inicio).startswith("NAO_AVALIADO")
    monkeypatch.setattr(config, "DATA_CORTE_CONHECIMENTO_MODELO", "2025-06-30")
    assert backtest.verificar_contaminacao(inicio).startswith("RISCO")
    assert backtest.verificar_contaminacao(pd.Timestamp("2025-07-01")).startswith("OK")


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


# --- revisão metodológica: excesso, exposição, hash, calibração ---------------

def test_backtest_anota_excesso_exposicao_e_contaminacao():
    eventos = [evento("PETR4", "positivo", "2026-03-02T19:00:00-03:00"),
               evento("PETR4", "negativo", "2026-03-09T12:00:00-03:00")]
    r = rodar_backtest(eventos, PRECOS, PERIODO, "noticia", capital=100_000.0, custo=0.0)
    op = r["operacoes_estrategia"][0]
    # Ibovespa de 03/03 (100) a 10/03 (105): +5%; operação +50% -> excesso 45 p.p.
    assert op["retorno_ibovespa"] == pytest.approx(0.05)
    assert op["excesso"] == pytest.approx(0.45)
    assert 0 < r["estrategia"]["exposicao_media"] < 0.25
    assert "retorno_por_volatilidade" in r["estrategia"]
    assert r["ibovespa_mesma_exposicao"]["retorno_acumulado"] < r["ibovespa"]["retorno_acumulado"]
    assert r["contaminacao_llm"].startswith("NAO_AVALIADO")
    assert r["criterio"]["versao"] == "CRITERIO_V2"


def test_ibovespa_mesma_exposicao_resultado_conhecido():
    serie = pd.Series([100.0, 110.0, 121.0])
    exposicao = pd.Series([0.5, 0.5, 0.0])
    patrimonio = backtest.ibovespa_mesma_exposicao(serie, exposicao, capital=100.0)
    assert list(patrimonio.round(6)) == [100.0, 105.0, 110.25]


def _baixar_fixo(valores):
    def baixar(simbolo, inicio, fim):
        return pd.Series(valores, index=pd.DatetimeIndex(["2026-03-02", "2026-03-03"]))
    return baixar


def test_hash_de_precos_registrado_e_conferido(tmp_path):
    carregar_precos("2026-03-02", "2026-03-03", ["PETR4"], tmp_path, _baixar_fixo([1.0, 2.0]))
    registro = json.loads((tmp_path / "downloads.jsonl").read_text().splitlines()[0])
    assert len(registro["sha256"]) == 64

    arquivo = tmp_path / "PETR4.SA_2026-03-02_2026-03-03.csv"
    arquivo.write_text(arquivo.read_text().replace("2.0", "2.5"))  # cache adulterado
    with pytest.raises(backtest.PrecosAlterados, match="hash diferente"):
        carregar_precos("2026-03-02", "2026-03-03", ["PETR4"], tmp_path, _baixar_fixo([1.0, 2.0]))


def test_novo_download_diferente_e_recusado(tmp_path):
    carregar_precos("2026-03-02", "2026-03-03", ["PETR4"], tmp_path, _baixar_fixo([1.0, 2.0]))
    (tmp_path / "PETR4.SA_2026-03-02_2026-03-03.csv").unlink()
    # Ajuste retroativo por proventos: o yfinance agora devolve outros números.
    with pytest.raises(backtest.PrecosAlterados, match="ajuste retroativo"):
        carregar_precos("2026-03-02", "2026-03-03", ["PETR4"], tmp_path, _baixar_fixo([0.9, 1.8]))
    # Mesmo conteúdo: aceito.
    carregar_precos("2026-03-02", "2026-03-03", ["PETR4"], tmp_path, _baixar_fixo([1.0, 2.0]))


def test_hash_dos_precos_muda_com_o_conteudo(tmp_path):
    carregar_precos("2026-03-02", "2026-03-03", ["PETR4"], tmp_path, _baixar_fixo([1.0, 2.0]))
    antes = backtest.hash_dos_precos(tmp_path)
    assert antes == backtest.hash_dos_precos(tmp_path)
    (tmp_path / "PETR4.SA_2026-03-02_2026-03-03.csv").write_text("x")
    assert backtest.hash_dos_precos(tmp_path) != antes


@pytest.mark.parametrize("sentimento,quando,esperado", [
    ("positivo", "2026-03-03T12:00:00-03:00", True),    # PETR4 de 02/03 (10) a 04/03 (11)
    ("negativo", "2026-03-03T12:00:00-03:00", False),
    ("neutro", "2026-03-03T12:00:00-03:00", None),
    ("positivo", "2026-03-02T12:00:00-03:00", None),    # sem pregão anterior na série
])
def test_acerto_direcional(sentimento, quando, esperado):
    assert backtest.acerto_direcional(evento("PETR4", sentimento, quando), PRECOS) is esperado


def test_carregamentos_simultaneos_nao_corrompem_o_cache(tmp_path):
    """Dois pedidos ao mesmo tempo (a interface em modo de desenvolvimento faz isso)
    não podem baixar e gravar o mesmo CSV juntos: se os downloads diferirem, o hash
    registrado deixa de bater e todo carregamento seguinte falharia."""
    import threading
    import time

    chamadas = []

    def baixar(simbolo, inicio, fim):
        chamadas.append(simbolo)
        valor = 10.0 + len(chamadas)  # cada download devolve um número diferente
        time.sleep(0.05)  # alarga a janela da corrida
        return pd.Series([valor, valor], index=pd.DatetimeIndex(["2026-10-05", "2026-10-06"]))

    erros = []

    def carregar():
        try:
            backtest.carregar_precos("2026-10-05", "2026-10-06", ["PETR4"], tmp_path, baixar)
        except Exception as erro:  # noqa: BLE001
            erros.append(erro)

    threads = [threading.Thread(target=carregar) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not erros
    assert chamadas == ["PETR4.SA"]  # o segundo pedido leu o cache do primeiro
    backtest.carregar_precos("2026-10-05", "2026-10-06", ["PETR4"], tmp_path, baixar)  # sem PrecosAlterados


def test_sensibilidade_a_custos():
    """Compra R$ 20.000 a 10 e vende a 15; com custo c em cada ponta, sobra 30.000 × (1 − c)²."""
    eventos = [evento("PETR4", "positivo", "2026-03-02T19:00:00-03:00"),
               evento("PETR4", "negativo", "2026-03-09T12:00:00-03:00")]
    linhas = backtest.sensibilidade_custos(eventos, PRECOS, PERIODO, "noticia", capital=100_000.0)
    assert [l["custo"] for l in linhas] == [0.0, 0.001, 0.0025, 0.005]
    for l in linhas:
        esperado = (30_000 * (1 - l["custo"]) ** 2 - 20_000) / 100_000
        assert l["retorno_estrategia"] == pytest.approx(esperado)
        assert l["retorno_ibovespa"] == pytest.approx(0.10)  # o índice não paga custo por operação
    retornos = [l["retorno_estrategia"] for l in linhas]
    assert retornos == sorted(retornos, reverse=True)


def test_sensibilidade_respeita_a_trava_de_periodo():
    with pytest.raises(PeriodoPendente):
        backtest.sensibilidade_custos([], PRECOS, None, "noticia")
