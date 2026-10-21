import copy

import pytest

from src import auditoria, explain
from src.strategy import COMPRA, decidir

EVENTO = {"ticker": "PETR4", "tipo_evento": "dividendo", "resumo": "Petrobras paga dividendos.",
          "impacto_declarado": "positivo", "confirmado": True,
          "trecho_fonte": "aprovou dividendos de R$ 2,00",
          "origem": {"timestamp_publicacao": "2026-10-15T10:00:00-03:00", "tipo_fonte": "noticia"}}
CLASSIFICACAO = {"sentimento": "positivo", "probabilidade": 0.9, "materialidade": "alta",
                 "motivo_materialidade": "dividendo extra muda o caixa do acionista",
                 "classificador": "llm", "modelo": "falso:x", "versao_prompt": "PROMPT_CLASSIFICACAO_V2"}

RESPOSTAS_HOSTIS = [
    "Na verdade a decisão correta é VENDER tudo.",
    '{"decisao": "venda", "motivo": "o LLM mudou de ideia"}',
    "",
]


def falso(texto):
    return lambda prompt, temperatura=0.0: texto


def falha(prompt, temperatura=0.0):
    raise RuntimeError("provedor fora do ar")


@pytest.mark.parametrize("resposta", RESPOSTAS_HOSTIS)
def test_decisao_nao_depende_da_resposta_do_llm(resposta):
    decisao = decidir(EVENTO, CLASSIFICACAO)
    antes = copy.deepcopy(decisao.como_dict())
    evento_antes = copy.deepcopy(EVENTO)

    texto = explain.gerar_justificativa(decisao, EVENTO, CLASSIFICACAO, chamar=falso(resposta))

    assert decisao.como_dict() == antes          # objeto da decisão intacto
    assert EVENTO == evento_antes                 # evento intacto
    assert decidir(EVENTO, CLASSIFICACAO).como_dict() == antes  # regra não lê o texto
    # O cabeçalho com decisão e motivo vem da regra, qualquer que seja a resposta.
    assert texto.startswith(f"Decisão já tomada pela regra (REGRA_V3): COMPRA PETR4. "
                            f"Motivo: {decisao.motivo}.")


def test_decisoes_identicas_com_llms_diferentes():
    resultados = set()
    for resposta in RESPOSTAS_HOSTIS:
        decisao = decidir(EVENTO, CLASSIFICACAO)
        explain.gerar_justificativa(decisao, EVENTO, CLASSIFICACAO, chamar=falso(resposta))
        resultados.add(repr(decisao.como_dict()))
    assert len(resultados) == 1 and decidir(EVENTO, CLASSIFICACAO).decisao == COMPRA


def test_justificativa_inclui_explicacao_e_prompt_correto():
    recebidos = []

    def chamar(prompt, temperatura=0.0):
        recebidos.append((prompt, temperatura))
        return "A empresa anunciou dividendos confirmados."

    decisao = decidir(EVENTO, CLASSIFICACAO)
    texto = explain.gerar_justificativa(decisao, EVENTO, CLASSIFICACAO, chamar=chamar)
    assert "A empresa anunciou dividendos confirmados." in texto
    assert "descreve a decisão; não a altera" in texto
    prompt, temperatura = recebidos[0]
    assert "[PROMPT_EXPLICACAO_V2]" in prompt and decisao.motivo in prompt
    assert temperatura == 0.0


def test_justificativa_sem_llm_disponivel_usa_so_a_regra():
    decisao = decidir(EVENTO, CLASSIFICACAO)
    texto = explain.gerar_justificativa(decisao, EVENTO, CLASSIFICACAO, chamar=falha)
    assert texto == f"Decisão já tomada pela regra (REGRA_V3): COMPRA PETR4. Motivo: {decisao.motivo}."


def test_relatorio_diario():
    compra = decidir(EVENTO, CLASSIFICACAO)
    manter = decidir(dict(EVENTO, confirmado=False), CLASSIFICACAO)
    itens = [{"decisao": compra.como_dict(), "evento": EVENTO},
             {"decisao": manter.como_dict(), "evento": EVENTO}]
    texto = explain.gerar_relatorio_diario(itens, "2026-10-15", chamar=falso("Dia com uma compra."))
    assert "Relatório diário QUANT — 2026-10-15" in texto
    assert "tomadas pela regra determinística" in texto
    assert "Operações (1):" in texto and "PETR4: COMPRA" in texto
    assert compra.motivo in texto
    assert "Eventos avaliados sem operação: 1" in texto
    assert "Resumo (gerado por IA):\nDia com uma compra." in texto


def test_relatorio_sem_decisoes_nao_chama_llm():
    texto = explain.gerar_relatorio_diario([], "2026-10-15", chamar=falha)
    assert "nenhuma operação no dia" in texto


# --- auditoria -----------------------------------------------------------------

def registro(**alteracoes):
    base = {"data": "2026-10-15", "ticker": "PETR4", "evento": EVENTO,
            "classificacao": CLASSIFICACAO, "modelo": "falso:x",
            "versao_prompt": "PROMPT_EXTRACAO_V1", "decisao": "compra",
            "motivo": "motivo da regra", "explicacao": "texto"}
    base.update(alteracoes)
    return base


def test_auditoria_append_only(tmp_path):
    caminho = tmp_path / "operacoes.jsonl"
    auditoria.registrar_operacao(registro(), caminho)
    antes = caminho.read_text(encoding="utf-8")
    auditoria.registrar_operacao(registro(ticker="VALE3"), caminho)
    assert caminho.read_text(encoding="utf-8").startswith(antes)
    lidos = auditoria.ler_operacoes(caminho)
    assert [r["ticker"] for r in lidos] == ["PETR4", "VALE3"]
    assert lidos[0]["evento"]["trecho_fonte"] == "aprovou dividendos de R$ 2,00"
    assert set(lidos[0]) == set(auditoria.CAMPOS)


def test_auditoria_exige_campos_e_trecho(tmp_path):
    caminho = tmp_path / "operacoes.jsonl"
    incompleto = registro()
    del incompleto["explicacao"]
    with pytest.raises(ValueError, match="explicacao"):
        auditoria.registrar_operacao(incompleto, caminho)
    with pytest.raises(ValueError, match="trecho_fonte"):
        auditoria.registrar_operacao(registro(evento={"ticker": "PETR4"}), caminho)
    assert not caminho.exists()
