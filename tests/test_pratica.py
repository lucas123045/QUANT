"""Camada prática: imposto, surpresa no texto, risco e a carteira prática (sem rede)."""
import math

import numpy as np
import pandas as pd
import pytest

from src import config, pratica, risco, surpresa, tributacao

TICKERS = config.CARTEIRA + [config.BENCHMARK]


def precos_sinteticos(n=200, vols=None, semente=7) -> pd.DataFrame:
    """Passeio aleatório com volatilidade fixa por ação (índice de pregões úteis)."""
    vols = {t: 0.012 for t in TICKERS} | (vols or {})
    gerador = np.random.default_rng(semente)
    dias = pd.bdate_range("2026-01-01", periods=n)
    colunas = {}
    for t in TICKERS:
        colunas[t] = 50.0 * np.cumprod(1 + gerador.normal(0, vols[t], n))
    return pd.DataFrame(colunas, index=dias)


def sinal(ticker, dia, decisao="compra", meta=None):
    return {"ticker": ticker, "decisao": decisao, "fracao_alvo": 0.2 if decisao == "compra" else 0.0,
            "instante": f"{pd.Timestamp(dia).date().isoformat()}T11:00:00-03:00", "tipo_fonte": "noticia",
            "meta": meta or {"resumo": "fato positivo", "trecho_fonte": "a empresa informou"}}


def calmo(precos, ticker, dia):
    """Ação e Ibovespa sem variação no dia da notícia: reação neutra."""
    i = precos.index.get_loc(pd.Timestamp(dia))
    for coluna in (ticker, config.BENCHMARK):
        precos.iloc[i, precos.columns.get_loc(coluna)] = precos.iloc[i - 1, precos.columns.get_loc(coluna)]
    return precos


# ---------------------------------------------------------------- imposto

def test_isencao_olha_o_valor_vendido_e_e_tudo_ou_nada():
    abaixo = tributacao.apurar([{"data": "2026-03-10", "valor": 19_000, "lucro": 3_000}])
    assert abaixo["imposto_total"] == 0 and abaixo["meses"][0]["isento"]
    acima = tributacao.apurar([{"data": "2026-03-10", "valor": 20_001, "lucro": 3_000}])
    assert acima["imposto_total"] == pytest.approx(450.0)  # 15% de todo o lucro do mês


def test_prejuizo_compensa_lucro_tributavel_seguinte_mas_nao_e_gasto_em_mes_isento():
    vendas = [
        {"data": "2026-01-15", "valor": 30_000, "lucro": -1_000},  # prejuízo guardado
        {"data": "2026-02-15", "valor": 10_000, "lucro": 800},     # mês isento: não consome o prejuízo
        {"data": "2026-03-15", "valor": 25_000, "lucro": 1_500},   # tributável: abate 1.000
    ]
    r = tributacao.apurar(vendas)
    marco = r["meses"][2]
    assert r["meses"][1]["isento"] and r["meses"][1]["prejuizo_acumulado"] == 1_000
    assert marco["prejuizo_usado"] == 1_000 and marco["imposto"] == pytest.approx(75.0)
    assert r["prejuizo_a_compensar"] == 0


def test_provisao_diaria_e_vencimento_do_darf():
    dias = pd.bdate_range("2026-03-01", "2026-04-30")
    provisao = tributacao.provisao_diaria([{"data": "2026-03-10", "valor": 25_000, "lucro": 1_000}], dias)
    assert provisao.loc[:"2026-03-09"].eq(0).all() and provisao.loc["2026-03-10"] == pytest.approx(150)
    assert tributacao.vencimento_darf("2026-03").isoformat() == "2026-04-30"


# ---------------------------------------------------------------- surpresa

@pytest.mark.parametrize("texto, esperado", [
    ("O volume ficou acima dos 2,77 milhões de barris por dia considerados pelo consenso.", "acima"),
    ("Lucro veio abaixo das estimativas dos analistas", "abaixo"),
    ("O resultado frustrou investidores", "abaixo"),
    ("Receita em linha com o esperado", "em_linha"),
    ("A ação fechou acima de R$ 50, segundo analistas.", None),
    ("Vale a pena investir em CDB?", None),
    ("Receita acima do esperado, mas o lucro frustrou", "mista"),
])
def test_surpresa_no_texto(texto, esperado):
    assert surpresa.detectar(texto)["surpresa"] == esperado


def test_surpresa_contradiz_so_no_sentido_oposto():
    assert surpresa.contradiz("abaixo", "positivo") and surpresa.contradiz("acima", "negativo")
    assert not surpresa.contradiz("acima", "positivo") and not surpresa.contradiz("mista", "positivo")


# ---------------------------------------------------------------- risco

def test_metricas_de_risco_contra_o_cdi():
    dias = pd.bdate_range("2026-01-01", periods=100)
    patrimonio = pd.Series(100_000 * 1.001 ** np.arange(100), index=dias)
    cdi = pd.Series(0.0005, index=dias)
    m = risco.metricas(patrimonio, cdi)
    assert m["anualizadas_confiaveis"] and m["drawdown_maximo"] == 0
    # Sobe 0,1% ao dia sem oscilar: volatilidade ~0 -> Sharpe indefinido em vez de infinito.
    assert m["volatilidade_anualizada"] == pytest.approx(0, abs=1e-12)


def test_metricas_anualizadas_somem_com_pouco_historico_e_drawdown_tem_duracao():
    dias = pd.bdate_range("2026-01-01", periods=6)
    patrimonio = pd.Series([100, 110, 99, 105, 111, 112], index=dias, dtype=float)
    m = risco.metricas(patrimonio)
    assert m["sharpe"] is None and m["retorno_anualizado"] is None
    assert m["drawdown_maximo"] == pytest.approx(99 / 110 - 1)
    assert m["drawdown_pregoes"] == 3 and m["drawdown_recuperado"]


def test_estatisticas_por_operacao():
    ops = [{"retorno": 0.10, "resultado": 1_000}, {"retorno": -0.05, "resultado": -500},
           {"retorno": 0.02, "resultado": 200}]
    r = risco.por_operacao(ops)
    assert r["taxa_acerto"] == pytest.approx(2 / 3)
    assert r["payoff"] == pytest.approx(0.06 / 0.05) and r["fator_lucro"] == pytest.approx(1_200 / 500)


# ---------------------------------------------------------------- carteira prática

def test_peso_pelo_risco():
    referencia = config.PRATICA_VOL_REFERENCIA_ANUAL / math.sqrt(252)
    assert pratica.peso_pelo_risco(referencia)[0] == pytest.approx(config.MAX_POSICAO_PCT)
    assert pratica.peso_pelo_risco(2 * referencia)[0] == pytest.approx(config.MAX_POSICAO_PCT / 2)
    assert pratica.peso_pelo_risco(referencia / 2)[0] == pytest.approx(config.MAX_POSICAO_PCT)  # teto da regra
    assert pratica.peso_pelo_risco(None)[0] == config.MAX_POSICAO_PCT


def test_compra_pesada_pelo_risco_custos_e_saida_por_prazo():
    precos = precos_sinteticos(vols={"PETR4": 0.03})  # ~48% ao ano: peso perto de 10%
    inicio = precos.index[130]
    dia_noticia = precos.index[131]
    precos = calmo(precos, "PETR4", dia_noticia)
    # Sem queda forte durante a posição (o teste é do prazo, não do stop).
    i_exec = 132
    precos.loc[precos.index[i_exec]:, "PETR4"] = precos["PETR4"].iloc[i_exec]
    r = pratica.simular([sinal("PETR4", dia_noticia)], precos, inicio, 100_000.0)

    operacao = r["operacoes"][0]
    assert operacao["entrada"] == precos.index[i_exec].date().isoformat()
    assert 0.05 < operacao["peso"] < 0.15
    assert operacao["motivo_saida"] == "prazo" and operacao["pregoes"] == config.PRATICA_PRAZO_MAXIMO_PREGOES
    investido = operacao["investido"]
    assert r["custos_pagos"] == pytest.approx(investido * config.PRATICA_EMOLUMENTOS * (1 + (1 - config.PRATICA_EMOLUMENTOS)), rel=1e-6)
    assert [c["criterio"] for c in operacao["checagens"]][:2] == [
        "O mercado não reagiu com força contra a notícia", "O texto não diz que veio abaixo do esperado"]


def test_stop_vende_na_queda_fora_do_comum():
    precos = precos_sinteticos()
    dia_noticia = precos.index[131]
    precos = calmo(precos, "VALE3", dia_noticia)
    preco_entrada = precos["VALE3"].iloc[132]
    precos.loc[precos.index[133]:, "VALE3"] = preco_entrada * 0.6  # despenca 40% e fica
    r = pratica.simular([sinal("VALE3", dia_noticia)], precos, precos.index[130], 100_000.0)
    assert r["operacoes"][0]["motivo_saida"] == "perda máxima"
    assert r["operacoes"][0]["saida"] == precos.index[133].date().isoformat()


def test_nao_compra_quando_o_mercado_reage_contra_ou_o_texto_contradiz():
    precos = precos_sinteticos()
    dia = precos.index[131]
    i = precos.index.get_loc(dia)
    precos.iloc[i, precos.columns.get_loc("ITUB4")] = precos["ITUB4"].iloc[i - 1] * 0.90  # -10% no dia
    precos.iloc[i, precos.columns.get_loc(config.BENCHMARK)] = precos[config.BENCHMARK].iloc[i - 1]
    precos = calmo(precos, "ABEV3", dia)
    meta_ruim = {"resumo": "lucro recorde", "trecho_fonte": "o lucro veio abaixo do consenso"}
    r = pratica.simular([sinal("ITUB4", dia), sinal("ABEV3", dia, meta=meta_ruim)], precos, precos.index[130], 100_000.0)
    razoes = {d["ticker"]: d["razao"] for d in r["descartados"]}
    assert razoes == {"ITUB4": "mercado discordou", "ABEV3": "texto contradiz"}
    assert not r["operacoes"] and not r["abertas"]


def test_limite_por_setor_nos_bancos():
    precos = precos_sinteticos(vols={"ITUB4": 0.01, "BBDC4": 0.01})  # volatilidade baixa: pedem 20% cada
    dia = precos.index[131]
    precos = calmo(calmo(precos, "ITUB4", dia), "BBDC4", dia)
    r = pratica.simular([sinal("ITUB4", dia), sinal("BBDC4", dia)], precos, precos.index[130], 100_000.0)
    pesos = {o["ticker"]: o["peso"] for o in r["operacoes"] + r["abertas"]}
    assert pesos["BBDC4"] == pytest.approx(0.20, abs=0.002)  # ordem alfabética: BBDC4 primeiro
    assert pesos["BBDC4"] + pesos["ITUB4"] == pytest.approx(config.PRATICA_LIMITE_SETOR, abs=0.003)


def test_caixa_rende_cdi_e_imposto_sai_do_patrimonio_liquido():
    precos = precos_sinteticos()
    dias = precos.index[130:]
    taxas = pd.Series(0.0005, index=dias)
    r = pratica.simular([], precos, dias[0], 100_000.0, taxas)
    assert r["bruto"].iloc[-1] == pytest.approx(100_000 * 1.0005 ** (len(dias) - 1))
    assert r["juros_caixa"] == pytest.approx(r["bruto"].iloc[-1] - 100_000)

    # Lucro numa venda acima de R$ 20 mil: 15% sai do patrimônio líquido.
    precos = precos_sinteticos(vols={"PETR4": 0.012})
    dia = precos.index[131]
    precos = calmo(precos, "PETR4", dia)
    precos.loc[precos.index[133]:, "PETR4"] = precos["PETR4"].iloc[132] * 1.5
    r = pratica.simular([sinal("PETR4", dia)], precos, precos.index[130], 200_000.0)
    operacao = r["operacoes"][0]
    assert operacao["motivo_saida"] == "prazo" and operacao["resultado"] > 0
    assert r["ir"]["imposto_total"] == pytest.approx(0.15 * operacao["resultado"])
    assert r["bruto"].iloc[-1] - r["liquido"].iloc[-1] == pytest.approx(r["ir"]["imposto_total"])


# ---------------------------------------------------------------- integração

def test_quantil_t_e_intervalo():
    from src.estatistica import media_com_intervalo, quantil_t
    assert quantil_t(0.975, 10) == pytest.approx(2.2281, abs=1e-4)
    r = media_com_intervalo([0.01, 0.02, -0.005, 0.03])
    assert r["intervalo"][0] < r["media"] < r["intervalo"][1] and 0 < r["p_valor_bilateral"] < 1
    assert media_com_intervalo([0.01])["intervalo"] is None


def test_pipeline_registra_e_alerta_so_decisoes_novas(tmp_path, monkeypatch):
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from src import alertas, main
    enviados = []
    monkeypatch.setattr(alertas, "enviar", lambda registros: enviados.append(len(registros)) or {})
    pasta = tmp_path / "execucoes" / "2026-10-15"
    pasta.mkdir(parents=True)
    decisao = {"ticker": "PETR4", "decisao": "compra", "motivo": "m", "versao_regra": "REGRA_V2", "criterios": []}
    evento = {"id": "e-0", "ticker": "PETR4", "trecho_fonte": "t", "modelo": "x", "versao_prompt": "v",
              "classificacao": {"sentimento": "positivo", "probabilidade": 0.9}}
    novos = []
    main.etapa_registrar(pasta, [{"evento": evento, "decisao": decisao}], {}, tmp_path / "ops.jsonl", "2026-10-15", novos)
    assert len(novos) == 1 and novos[0]["ticker"] == "PETR4"
    novos.clear()
    main.etapa_registrar(pasta, [{"evento": evento, "decisao": decisao}], {}, tmp_path / "ops.jsonl", "2026-10-15", novos)
    assert novos == []  # mesmo evento: não registra nem alerta de novo
    # No modo de teste, nunca manda alerta.
    main.executar(agora=datetime(2026, 10, 15, 20, 0, tzinfo=ZoneInfo("America/Sao_Paulo")), teste=True,
                  dir_data=tmp_path / "teste")
    assert enviados == []
