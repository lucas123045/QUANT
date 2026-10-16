"""Carteira simulada com preços sintéticos de resultado conhecido (sem rede)."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src import config, main, simulacao
from src.web import api

SP = ZoneInfo("America/Sao_Paulo")
DIAS = pd.DatetimeIndex(["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"])
SERIES = {
    "PETR4.SA": [10.0, 10.0, 11.0, 12.0, 13.0],
    "^BVSP": [100.0, 100.0, 101.0, 102.0, 103.0],
}


def baixar(simbolo, inicio, fim):
    valores = SERIES.get(simbolo, [50.0] * 5)
    serie = pd.Series(valores, index=DIAS)
    return serie[(serie.index >= inicio) & (serie.index <= fim)]


@pytest.fixture
def dados(tmp_path):
    # Pipeline de teste na segunda 05/10 às 20h: compra PETR4 e venda VALE3
    # (notícias publicadas às 18h); execução no fechamento de terça 06/10.
    pasta = tmp_path / "teste"  # mesma estrutura da base "teste" da API
    main.executar(agora=datetime(2026, 10, 5, 20, 0, tzinfo=SP), teste=True, dir_data=pasta)
    return pasta


def test_resultado_conhecido(dados):
    r = simulacao.calcular(dados, agora=datetime(2026, 10, 9, 20, 0, tzinfo=SP), baixar=baixar,
                           capital=100_000.0)
    assert r["estado"] == "ok"
    assert r["inicio"] == "2026-10-05" and r["ultimo_fechamento"] == "2026-10-09"
    # Compra 20% (20.000) de PETR4 a 10 em 06/10; vale 13 em 09/10: +30% -> +6.000.
    assert r["carteiras"]["estrategia"]["patrimonio"] == pytest.approx(106_000)
    assert r["carteiras"]["ibovespa"]["patrimonio"] == pytest.approx(103_000)
    assert r["carteiras"]["baseline_1"]["patrimonio"] == pytest.approx(106_000)

    posicao = r["posicoes_abertas"][0]
    assert posicao["ticker"] == "PETR4" and posicao["entrada"] == "2026-10-06"
    assert posicao["preco_entrada"] == 10.0 and posicao["preco_saida"] == 13.0
    assert posicao["retorno"] == pytest.approx(0.30)
    assert posicao["origem"]["trecho_fonte"]  # rastro até a notícia
    assert "Decisão já tomada pela regra" in posicao["origem"]["explicacao"]

    # A venda de VALE3 não tinha posição: aparece como ignorada, com o motivo.
    assert [(i["ticker"], i["razao"]) for i in r["ordens_ignoradas"]] == [("VALE3", "sem posição para vender")]
    assert [p["data"] for p in r["serie"]] == [d.date().isoformat() for d in DIAS]
    assert r["serie"][0]["estrategia"] == 100_000
    assert "não substitui o período de teste" in r["aviso"]


def test_ordem_pendente_ate_o_proximo_pregao(dados):
    r = simulacao.calcular(dados, agora=datetime(2026, 10, 5, 20, 0, tzinfo=SP), baixar=baixar,
                           capital=100_000.0)
    assert r["estado"] == "ok"
    assert {p["ticker"] for p in r["pendentes"]} == {"PETR4", "VALE3"}
    assert r["carteiras"]["estrategia"]["patrimonio"] == pytest.approx(100_000)


def test_preco_parcial_do_dia_e_ignorado(dados):
    r = simulacao.calcular(dados, agora=datetime(2026, 10, 9, 15, 0, tzinfo=SP), baixar=baixar,
                           capital=100_000.0)
    assert r["ultimo_fechamento"] == "2026-10-08"
    assert r["carteiras"]["estrategia"]["patrimonio"] == pytest.approx(104_000)


def test_sem_dados(tmp_path):
    assert simulacao.calcular(tmp_path, baixar=baixar)["estado"] == "sem_dados"


def test_endpoint(dados, monkeypatch):
    monkeypatch.setattr(config, "DIR_DATA", dados.parent)
    original = simulacao.calcular
    monkeypatch.setattr(simulacao, "calcular", lambda d: original(
        d, agora=datetime(2026, 10, 9, 20, 0, tzinfo=SP), baixar=baixar, capital=100_000.0))
    resposta = TestClient(api.app).get("/api/simulacao?base=teste")
    assert resposta.status_code == 200
    assert resposta.json()["carteiras"]["estrategia"]["patrimonio"] == pytest.approx(106_000)


def test_endpoint_falha_de_rede_vira_503(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DIR_DATA", tmp_path)

    def falha(d):
        raise OSError("sem internet")

    monkeypatch.setattr(simulacao, "calcular", falha)
    resposta = TestClient(api.app).get("/api/simulacao?base=real")
    assert resposta.status_code == 503
    assert "sem internet" in resposta.json()["detail"]


def test_painel_fintech(dados):
    r = simulacao.calcular(dados, agora=datetime(2026, 10, 9, 20, 0, tzinfo=SP), baixar=baixar,
                           capital=100_000.0)
    # Alocação: 20.000 viraram 26.000 em PETR4; 80.000 em caixa.
    assert r["alocacao"]["caixa"] == pytest.approx(80_000)
    assert r["alocacao"]["acoes"] == [{"ticker": "PETR4", "valor": pytest.approx(26_000)}]

    ativos = {a["ticker"]: a for a in r["ativos"]}
    assert list(ativos) == config.CARTEIRA
    petr = ativos["PETR4"]
    assert petr["situacao"] == "na_carteira"
    assert petr["preco"] == 13.0
    assert petr["variacao_dia"] == pytest.approx(13 / 12 - 1)
    assert petr["variacao_30d"] == pytest.approx(0.30)
    assert [p["preco"] for p in petr["minigrafico"]] == SERIES["PETR4.SA"]
    assert petr["ultima_decisao"]["decisao"] == "compra"
    assert petr["ultima_decisao"]["trecho_fonte"]
    assert petr["ultima_decisao"]["motivo"].startswith("evento positivo confirmado")
    assert ativos["VALE3"]["situacao"] == "sem_posicao"
    assert ativos["VALE3"]["ultima_decisao"]["decisao"] == "venda"
    assert ativos["ITUB4"]["ultima_decisao"] is None

    assert [(l["tipo"], l["ticker"], l["data"]) for l in r["extrato"]] == [("compra", "PETR4", "2026-10-06")]
    assert r["extrato"][0]["quantidade"] == pytest.approx(2000)

    h = r["historico_regra"]
    assert h["n"] == 1 and h["media"] == pytest.approx(0.30)
    assert h["intervalo_aproximado_95"] is None  # uma decisão só: sem margem de incerteza
    assert h["taxa_acerto"] == 1.0


def test_ativos_aparecem_mesmo_aguardando_pregao(dados):
    r = simulacao.calcular(dados, agora=datetime(2026, 10, 5, 17, 0, tzinfo=SP), baixar=baixar,
                           capital=100_000.0)
    assert r["estado"] == "aguardando_pregao"
    ativos = {a["ticker"]: a for a in r["ativos"]}
    assert ativos["PETR4"]["situacao"] == "compra_agendada"
    assert ativos["VALE3"]["situacao"] == "venda_agendada"


def test_produtos_e_maturidade(dados):
    r = simulacao.calcular(dados, agora=datetime(2026, 10, 9, 20, 0, tzinfo=SP), baixar=baixar,
                           capital=100_000.0)
    ibov = r["carteiras"]["ibovespa"]
    assert ibov["dias_positivos_pct"] == 1.0          # 100→100→101→102→103: só subiu
    assert ibov["volatilidade_anualizada"] is not None
    assert ibov["oscilacao"] in ("baixa", "média", "alta")
    m = r["maturidade"]
    assert (m["pregoes"], m["decisoes"], m["nivel"]) == (5, 1, "muito_cedo")
    assert "quase só sorte" in m["texto"]


@pytest.mark.parametrize("pregoes,decisoes,nivel", [
    (5, 1, "muito_cedo"), (60, 9, "muito_cedo"), (60, 10, "inicial"),
    (126, 29, "inicial"), (126, 30, "razoavel"),
])
def test_niveis_de_maturidade(pregoes, decisoes, nivel):
    assert simulacao.maturidade(pregoes, decisoes)["nivel"] == nivel


@pytest.mark.parametrize("vol,nivel", [(None, None), (0.05, "baixa"), (0.10, "média"),
                                       (0.249, "média"), (0.25, "alta")])
def test_nivel_oscilacao(vol, nivel):
    assert simulacao.nivel_oscilacao(vol) == nivel


def test_preco_parcial_nao_fica_no_cache_como_fechamento(dados):
    """Abrir a carteira às 15h não pode congelar o preço parcial do dia no cache."""
    precos_do_dia = {"PETR4.SA": 12.5}  # cotação no meio do pregão de 09/10

    def baixar_ao_vivo(simbolo, inicio, fim):
        serie = baixar(simbolo, inicio, fim).copy()
        if simbolo in precos_do_dia and pd.Timestamp("2026-10-09") in serie.index:
            serie[pd.Timestamp("2026-10-09")] = precos_do_dia[simbolo]
        return serie

    simulacao.calcular(dados, agora=datetime(2026, 10, 9, 15, 0, tzinfo=SP), baixar=baixar_ao_vivo,
                       capital=100_000.0)
    precos_do_dia.clear()  # depois do fechamento, a fonte já traz o preço final (13)
    r = simulacao.calcular(dados, agora=datetime(2026, 10, 9, 20, 0, tzinfo=SP), baixar=baixar_ao_vivo,
                           capital=100_000.0)
    assert r["ultimo_fechamento"] == "2026-10-09"
    assert r["carteiras"]["estrategia"]["patrimonio"] == pytest.approx(106_000)


def test_sensibilidade_a_custos_na_carteira(dados):
    """Compra R$ 20.000 de PETR4 a 10 e marca a 13: com custo c na compra, vale 26.000 × (1 − c)."""
    r = simulacao.calcular(dados, agora=datetime(2026, 10, 9, 20, 0, tzinfo=SP), baixar=baixar,
                           capital=100_000.0)
    sens = r["sensibilidade_custos"]
    assert [s["custo"] for s in sens] == [0.001, 0.0025, 0.005]
    for s in sens:
        assert s["retorno_acumulado"] == pytest.approx((80_000 + 26_000 * (1 - s["custo"])) / 100_000 - 1)
    assert r["carteiras"]["estrategia"]["retorno_acumulado"] == pytest.approx(0.06)  # sem custo, inalterado
