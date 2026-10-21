"""Testes de refutação com séries sintéticas de resultado conhecido."""
import pandas as pd
import pytest

from src import refutacao
from src.backtest import PeriodoPendente

PREGOES = pd.bdate_range("2026-03-02", periods=12)
# PETR4 sobe forte logo após 03/03 e depois fica parada: o "sinal" mora nos primeiros dias.
PRECOS = pd.DataFrame({
    "PETR4": [10, 10, 12, 13, 13, 13, 13, 13, 13, 13, 13, 13],
    "VALE3": [50, 50, 48, 46, 46, 46, 46, 46, 46, 46, 46, 46],
    "ITUB4": [30.0] * 12, "BBDC4": [15.0] * 12, "ABEV3": [12.0] * 12,
    "^BVSP": [100.0] * 12,
}, index=PREGOES, dtype=float)
PERIODO = ("2026-03-02", "2026-03-17")


def evento(ticker, sentimento, quando, prob=0.9):
    return {"ticker": ticker, "tipo_evento": "outro", "confirmado": True,
            "origem": {"timestamp_publicacao": quando, "tipo_fonte": "noticia"},
            "classificacao": {"sentimento": sentimento, "probabilidade": prob, "materialidade": "alta"}}


EVENTOS = [
    evento("PETR4", "positivo", "2026-03-02T19:00:00-03:00"),   # compra a 10 em 03/03
    evento("VALE3", "negativo", "2026-03-02T19:30:00-03:00"),   # venda sem posição: ignorada
]


def test_placebo_resultado_conhecido():
    r = refutacao.placebo(EVENTOS, PRECOS, PERIODO, "noticia", n=50, semente=1)
    assert r["retorno_real"] == pytest.approx(20_000 * 0.3 / 100_000)
    # Trocar as classificações faz a compra cair em VALE3 (que cai) ou sumir: nunca melhor.
    assert max(r["placebos"]) <= r["retorno_real"] + 1e-12
    assert 0 < r["p_valor"] <= 1
    assert r["n"] == 50 and r["semente"] == 1
    assert r == refutacao.placebo(EVENTOS, PRECOS, PERIODO, "noticia", n=50, semente=1)  # reprodutível


def test_defasagem_ganho_cai_com_atraso():
    linhas = refutacao.defasagem(EVENTOS, PRECOS, PERIODO, "noticia", atrasos=(0, 1, 2, 5))
    por_atraso = {l["atraso_pregoes"]: l["excesso_medio_por_operacao"] for l in linhas}
    assert por_atraso[0] == pytest.approx(0.30)        # 10 -> 13
    assert por_atraso[1] == pytest.approx(13 / 12 - 1)  # 12 -> 13
    assert por_atraso[2] == pytest.approx(0.0)          # 13 -> 13
    assert por_atraso[5] == pytest.approx(0.0)


def test_defasagem_maior_que_a_serie_descarta_a_ordem():
    linhas = refutacao.defasagem(EVENTOS, PRECOS, PERIODO, "noticia", atrasos=(50,))
    assert linhas[0]["n_operacoes"] == 0 and linhas[0]["excesso_medio_por_operacao"] is None


def test_calibracao():
    eventos = [evento("PETR4", "positivo", "2026-03-03T12:00:00-03:00", 0.9),   # acertou (10->13)
               evento("VALE3", "positivo", "2026-03-03T12:00:00-03:00", 0.85),  # errou (50->46)
               evento("ITUB4", "neutro", "2026-03-03T12:00:00-03:00", 0.6)]    # sem desfecho
    r = refutacao.calibracao(eventos, PRECOS, PERIODO, "noticia")
    assert r["n"] == 2 and r["n_sem_desfecho"] == 1
    assert r["faixas"][4]["taxa_acerto"] == 0.5


def test_travas():
    with pytest.raises(PeriodoPendente):
        refutacao.placebo(EVENTOS, PRECOS, None, "noticia")
    with pytest.raises(ValueError, match="fontes misturadas"):
        refutacao.defasagem([{**EVENTOS[0], "origem": {**EVENTOS[0]["origem"], "tipo_fonte": "fato_relevante"}}],
                            PRECOS, PERIODO, "noticia")


def test_calibracao_exige_periodo_aprovado_e_fonte_unica():
    with pytest.raises(PeriodoPendente):
        refutacao.calibracao(EVENTOS, PRECOS, None, "noticia")
    mistos = [EVENTOS[0], {**EVENTOS[1], "origem": {**EVENTOS[1]["origem"],
                                                        "tipo_fonte": "fato_relevante"}}]
    with pytest.raises(ValueError, match="fontes misturadas"):
        refutacao.calibracao(mistos, PRECOS, PERIODO, "noticia")


def test_executar_entrega_os_tres_diagnosticos():
    r = refutacao.executar(EVENTOS, PRECOS, PERIODO, "noticia", n_placebos=10, semente=7)
    assert set(r) == {"periodo", "tipo_fonte", "placebo", "defasagem", "calibracao"}
    assert [linha["atraso_pregoes"] for linha in r["defasagem"]] == [0, 1, 2, 5, 10]
    assert r["calibracao"]["periodo"] == ["2026-03-02", "2026-03-17"]


def test_placebo_recusa_zero_simulacoes_e_defasagem_recusa_atraso_negativo():
    with pytest.raises(ValueError, match="n precisa"):
        refutacao.placebo(EVENTOS, PRECOS, PERIODO, "noticia", n=0)
    with pytest.raises(ValueError, match="não negativos"):
        refutacao.defasagem(EVENTOS, PRECOS, PERIODO, "noticia", atrasos=(0, -1))
