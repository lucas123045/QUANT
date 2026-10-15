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
