"""CDI (renda fixa) como referência da simulação, sem rede."""
from datetime import date, datetime
from zoneinfo import ZoneInfo

import pandas as pd
import pytest

from src import cdi, main, simulacao

SP = ZoneInfo("America/Sao_Paulo")
# A original, antes de o conftest trocá-la por uma que simula a rede fora do ar.
BAIXAR_BCB_ORIGINAL = cdi.baixar_bcb
DIAS = pd.DatetimeIndex(["2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08", "2026-10-09"])


def bcb_falso(taxa_pct="0.05"):
    """Resposta no formato da série 12 do SGS: taxa em % ao dia, data dd/mm/aaaa."""
    def baixar(inicio, fim):
        return [{"data": d.strftime("%d/%m/%Y"), "valor": taxa_pct} for d in DIAS
                if inicio <= d.date() <= fim]
    return baixar


def baixar_precos(simbolo, inicio, fim):
    valores = {"PETR4.SA": [10.0, 10.0, 11.0, 12.0, 13.0], "^BVSP": [100.0, 100.0, 101.0, 102.0, 103.0]}
    serie = pd.Series(valores.get(simbolo, [50.0] * 5), index=DIAS)
    return serie[(serie.index >= inicio) & (serie.index <= fim)]


def test_patrimonio_cdi_acumula_so_os_dias_anteriores():
    taxas = pd.Series([0.001] * 5, index=DIAS)
    patrimonio = cdi.patrimonio_cdi(DIAS, taxas, 1000.0)
    # A taxa do dia d remunera de d até o próximo dia útil: no primeiro pregão, nada rendeu.
    assert patrimonio.iloc[0] == pytest.approx(1000.0)
    assert patrimonio.iloc[1] == pytest.approx(1001.0)
    assert patrimonio.iloc[-1] == pytest.approx(1000.0 * 1.001 ** 4)


def test_carregar_cdi_usa_o_cache(tmp_path):
    chamadas = []

    def baixar(inicio, fim):
        chamadas.append((inicio, fim))
        return bcb_falso()(inicio, fim)

    a = cdi.carregar_cdi(date(2026, 10, 5), date(2026, 10, 9), tmp_path, baixar)
    b = cdi.carregar_cdi(date(2026, 10, 5), date(2026, 10, 9), tmp_path, baixar)
    assert len(chamadas) == 1
    assert a.equals(b) and a.iloc[0] == pytest.approx(0.0005)


def test_carregar_cdi_nao_guarda_erro_nem_periodo_recente(tmp_path):
    # O BC responde "Value(s) not found" (um objeto, não uma lista) para dias ainda sem taxa.
    erro_bcb = {"erro": {"statusCode": 404, "detail": "Value(s) not found"}}
    hoje = date.today()
    assert cdi.carregar_cdi(hoje, hoje, tmp_path, lambda i, f: erro_bcb).empty
    assert not list(tmp_path.iterdir())  # nem o erro nem o dia de hoje vão para o cache

    # Cache antigo que guardou uma resposta de erro: é ignorado e baixado de novo.
    (tmp_path / "cdi_2026-10-05_2026-10-09.json").write_text('{"erro": {}}', encoding="utf-8")
    taxas = cdi.carregar_cdi(date(2026, 10, 5), date(2026, 10, 9), tmp_path, bcb_falso())
    assert len(taxas) == 5


@pytest.fixture
def dados(tmp_path):
    pasta = tmp_path / "teste"
    main.executar(agora=datetime(2026, 10, 5, 20, 0, tzinfo=SP), teste=True, dir_data=pasta)
    return pasta


def test_simulacao_traz_renda_fixa(dados):
    r = simulacao.calcular(dados, agora=datetime(2026, 10, 9, 20, 0, tzinfo=SP), baixar=baixar_precos,
                           capital=100_000.0, baixar_cdi=bcb_falso("0.05"))
    renda_fixa = r["carteiras"]["cdi"]
    assert renda_fixa["patrimonio"] == pytest.approx(100_000 * 1.0005 ** 4)
    assert renda_fixa["drawdown_maximo"] == 0.0
    assert renda_fixa["oscilacao"] == "baixa"
    assert r["serie"][0]["cdi"] == pytest.approx(100_000)
    assert "cdi_indisponivel" not in r
    # O CDI é só referência: não muda a estratégia.
    assert r["carteiras"]["estrategia"]["patrimonio"] == pytest.approx(106_000)


def test_simulacao_segue_sem_o_cdi_quando_a_fonte_falha(dados):
    # Sem baixar_cdi, usa o Banco Central, que o conftest deixa "fora do ar".
    r = simulacao.calcular(dados, agora=datetime(2026, 10, 9, 20, 0, tzinfo=SP), baixar=baixar_precos,
                           capital=100_000.0)
    assert r["estado"] == "ok"
    assert "cdi" not in r["carteiras"]
    assert "Banco Central" in r["cdi_indisponivel"]
    assert all(p["cdi"] is None for p in r["serie"])



def test_firewall_do_bc_vira_erro_claro(monkeypatch):
    """O BC às vezes responde com uma página HTML de bloqueio: vira um erro claro, não JSONDecodeError."""
    from src import rede
    monkeypatch.setattr(rede, "baixar", lambda *a, **k: b'<?xml version="1.0"?><html>Requisicao invalida</html>')
    with pytest.raises(ConnectionError, match="recusou"):
        BAIXAR_BCB_ORIGINAL(date(2026, 10, 1), date(2026, 10, 20))
