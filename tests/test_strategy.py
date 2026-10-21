import pytest

from src.strategy import COMPRA, MANTER, VENDA, decidir


def evento(ticker="PETR4", confirmado=True, quando="2026-10-15T10:00:00-03:00", sentimento=None):
    e = {"ticker": ticker, "tipo_evento": "dividendo", "confirmado": confirmado,
         "origem": {"timestamp_publicacao": quando, "tipo_fonte": "noticia"}}
    if sentimento:
        e["classificacao"] = {"sentimento": sentimento, "probabilidade": 0.9}
    return e


def cls(sentimento="positivo", probabilidade=0.9):
    return {"sentimento": sentimento, "probabilidade": probabilidade}


def test_compra_positivo_confirmado_acima_do_limiar():
    d = decidir(evento(), cls())
    assert d.decisao == COMPRA
    assert d.fracao_alvo == 0.20
    assert "0.90 > 0.70" in d.motivo


def test_venda_negativo_confirmado_acima_do_limiar():
    d = decidir(evento(), cls("negativo"))
    assert d.decisao == VENDA
    assert d.fracao_alvo == 0.0


def test_sem_classificacao_mantem():
    assert decidir(evento(), None).decisao == MANTER


def test_nao_confirmado_mantem():
    d = decidir(evento(confirmado=False), cls())
    assert d.decisao == MANTER and "não confirmado" in d.motivo


def test_neutro_mantem():
    assert decidir(evento(), cls("neutro", 0.99)).decisao == MANTER


@pytest.mark.parametrize("probabilidade,esperado", [
    (0.69, MANTER),
    (0.70, MANTER),      # borda: precisa ser ESTRITAMENTE acima
    (0.7000001, COMPRA),
    (0.71, COMPRA),
    (1.0, COMPRA),
])
def test_bordas_do_limiar(probabilidade, esperado):
    assert decidir(evento(), cls("positivo", probabilidade)).decisao == esperado


def test_bordas_do_limiar_na_venda():
    assert decidir(evento(), cls("negativo", 0.70)).decisao == MANTER
    assert decidir(evento(), cls("negativo", 0.71)).decisao == VENDA


def test_positivo_com_negativo_recente_mantem():
    historico = [evento(quando="2026-10-12T10:00:00-03:00", sentimento="negativo")]
    d = decidir(evento(), cls(), historico)
    assert d.decisao == MANTER and "negativo" in d.motivo


def test_negativo_com_positivo_recente_mantem():
    historico = [evento(quando="2026-10-14T10:00:00-03:00", sentimento="positivo")]
    assert decidir(evento(), cls("negativo"), historico).decisao == MANTER


def test_evento_oposto_fora_da_janela_nao_bloqueia():
    historico = [evento(quando="2026-10-10T09:59:00-03:00", sentimento="negativo")]  # > 5 dias
    assert decidir(evento(), cls(), historico).decisao == COMPRA


def test_evento_oposto_na_borda_da_janela_bloqueia():
    historico = [evento(quando="2026-10-10T10:00:00-03:00", sentimento="negativo")]  # = 5 dias
    assert decidir(evento(), cls(), historico).decisao == MANTER


def test_evento_oposto_de_outro_ticker_nao_bloqueia():
    historico = [evento(ticker="VALE3", quando="2026-10-14T10:00:00-03:00", sentimento="negativo")]
    assert decidir(evento(), cls(), historico).decisao == COMPRA


def test_evento_oposto_posterior_nao_bloqueia():
    # Sem olhar o futuro: só eventos anteriores contam.
    historico = [evento(quando="2026-10-16T10:00:00-03:00", sentimento="negativo")]
    assert decidir(evento(), cls(), historico).decisao == COMPRA


def test_mesmo_sentimento_recente_nao_bloqueia():
    historico = [evento(quando="2026-10-14T10:00:00-03:00", sentimento="positivo")]
    assert decidir(evento(), cls(), historico).decisao == COMPRA


def test_deterministico():
    resultados = {decidir(evento(), cls()).como_dict().__repr__() for _ in range(20)}
    assert len(resultados) == 1


# --- REGRA_V2: notícia que só descreve a cotação + justificativa passo a passo ---

def test_v2_noticia_de_cotacao_nao_opera():
    """"Ações da Petrobras sobem 3%": seguir o preço não é reagir a uma notícia."""
    e = {**evento(), "tipo_evento": "cotacao"}
    for sentimento in ("positivo", "negativo"):
        d = decidir(e, cls(sentimento, 0.95))
        assert d.decisao == MANTER
        assert "variação da cotação" in d.motivo


def test_v2_criterios_mostram_por_que_comprou():
    d = decidir(evento(), cls("positivo", 0.9))
    assert d.versao_regra == "REGRA_V2"
    assert [c["ok"] for c in d.criterios] == [True] * 6
    assert any("0,90" in c["detalhe"] for c in d.criterios)  # o valor que decidiu


def test_v2_criterios_mostram_o_que_barrou():
    d = decidir(evento(confirmado=False), cls("positivo", 0.6))
    barrados = [c["criterio"] for c in d.criterios if c["ok"] is False]
    assert any("confirmado" in b for b in barrados) and any("Confiança" in b for b in barrados)
    assert d.decisao == MANTER and "não confirmado" in d.motivo  # o primeiro que falha vira o motivo


def test_v2_criterios_sem_classificacao():
    d = decidir(evento(), None)
    assert d.criterios[0]["ok"] is False and len(d.criterios) == 3
    assert d.como_dict()["criterios"] == list(d.criterios)  # vai para o JSON como lista


def test_v2_previa_ou_cotacao_recente_nao_bloqueia_um_fato():
    """Caso real (20/10/2026): o aumento de capital do Bradesco (fato, negativo) foi barrado
    por uma prévia "deve lucrar mais" (não confirmada). Na V2, só fato confirmado bloqueia."""
    fato = {**evento(quando="2026-10-20T10:00:00-03:00"), "ticker": "BBDC4"}
    previa = {**evento(quando="2026-10-19T10:00:00-03:00", confirmado=False, sentimento="positivo"), "ticker": "BBDC4"}
    cotacao = {**evento(quando="2026-10-19T11:00:00-03:00", sentimento="positivo"), "ticker": "BBDC4", "tipo_evento": "cotacao"}
    assert decidir(fato, cls("negativo"), [previa, cotacao]).decisao == VENDA
    confirmado = {**evento(quando="2026-10-19T12:00:00-03:00", sentimento="positivo"), "ticker": "BBDC4"}
    assert decidir(fato, cls("negativo"), [confirmado]).decisao == MANTER  # fato contrário confirmado ainda bloqueia
