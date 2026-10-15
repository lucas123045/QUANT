import json
import logging

import pytest

from src import extract
from src.extract import EventoInvalido, extrair_eventos, trecho_existe, validar_evento

TEXTO = (
    "A Petrobras anunciou nesta quinta-feira o pagamento de dividendos de R$ 2,00 "
    "por ação. A estatal também confirmou a nova diretoria financeira."
)


def evento(**alteracoes):
    base = {
        "ticker": "PETR4",
        "tipo_evento": "dividendo",
        "resumo": "Petrobras anuncia dividendos de R$ 2,00 por ação.",
        "impacto_declarado": "positivo",
        "confirmado": True,
        "trecho_fonte": "anunciou nesta quinta-feira o pagamento de dividendos",
    }
    base.update(alteracoes)
    return base


class LLMFalso:
    """Devolve respostas em sequência e registra as chamadas."""

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def __call__(self, prompt, temperatura=0.0):
        self.chamadas.append({"prompt": prompt, "temperatura": temperatura})
        return self.respostas.pop(0)


def resposta(*eventos):
    return json.dumps({"eventos": list(eventos)}, ensure_ascii=False)


def test_json_valido():
    falso = LLMFalso(resposta(evento()))
    eventos = extrair_eventos(TEXTO, metadados={"tipo_fonte": "noticia", "url": "u"}, chamar=falso)
    assert len(eventos) == 1
    assert eventos[0]["tipo_evento"] == "dividendo"
    assert eventos[0]["versao_prompt"] == "PROMPT_EXTRACAO_V1"
    assert eventos[0]["modelo"]
    assert eventos[0]["origem"]["tipo_fonte"] == "noticia"
    assert len(falso.chamadas) == 1


def test_temperatura_zero_e_prompt_identificado():
    falso = LLMFalso(resposta())
    extrair_eventos(TEXTO, chamar=falso)
    assert falso.chamadas[0]["temperatura"] == 0.0
    assert "[PROMPT_EXTRACAO_V1]" in falso.chamadas[0]["prompt"]
    assert TEXTO in falso.chamadas[0]["prompt"]


def test_json_invalido_com_retry_bem_sucedido(caplog):
    falso = LLMFalso("isto não é json", resposta(evento()))
    with caplog.at_level(logging.WARNING):
        eventos = extrair_eventos(TEXTO, chamar=falso)
    assert len(eventos) == 1
    assert len(falso.chamadas) == 2
    assert "JSON inválido" in caplog.text


def test_json_invalido_sem_retry_bem_sucedido_descarta(caplog):
    falso = LLMFalso("{quebrado", "ainda quebrado", resposta(evento()))
    with caplog.at_level(logging.WARNING):
        eventos = extrair_eventos(TEXTO, chamar=falso)
    assert eventos == []
    assert len(falso.chamadas) == 2  # no máximo uma nova tentativa
    assert "descartada após 2 tentativas" in caplog.text


def test_json_com_cerca_markdown_aceito():
    falso = LLMFalso("```json\n" + resposta(evento()) + "\n```")
    assert len(extrair_eventos(TEXTO, chamar=falso)) == 1


def test_tipo_evento_invalido_levanta_erro():
    with pytest.raises(EventoInvalido, match="tipo_evento"):
        validar_evento(evento(tipo_evento="compra_recomendada"))


def test_tipo_evento_invalido_e_descartado_na_extracao(caplog):
    falso = LLMFalso(resposta(evento(tipo_evento="rumor"), evento()))
    with caplog.at_level(logging.WARNING):
        eventos = extrair_eventos(TEXTO, chamar=falso)
    assert len(eventos) == 1
    assert "tipo_evento inválido" in caplog.text


@pytest.mark.parametrize("alteracao,mensagem", [
    ({"ticker": "MGLU3"}, "ticker fora da carteira"),
    ({"impacto_declarado": "otimo"}, "impacto_declarado"),
    ({"confirmado": "sim"}, "booleano"),
    ({"resumo": " ".join(["palavra"] * 31)}, "30 palavras"),
    ({"trecho_fonte": ""}, "trecho_fonte vazio"),
])
def test_outras_violacoes_de_esquema(alteracao, mensagem):
    with pytest.raises(EventoInvalido, match=mensagem):
        validar_evento(evento(**alteracao))


def test_campo_ausente():
    bruto = evento()
    del bruto["confirmado"]
    with pytest.raises(EventoInvalido, match="campos ausentes"):
        validar_evento(bruto)


def test_trecho_inexistente_descartado_com_log(caplog):
    falso = LLMFalso(resposta(evento(trecho_fonte="lucro recorde de R$ 50 bilhões")))
    with caplog.at_level(logging.WARNING):
        eventos = extrair_eventos(TEXTO, chamar=falso)
    assert eventos == []
    assert "trecho_fonte inexistente" in caplog.text


def test_trecho_com_acento_e_espacos_diferentes_aceito():
    falso = LLMFalso(resposta(evento(trecho_fonte="a estatal tambem   confirmou a nova diretoria")))
    assert len(extrair_eventos(TEXTO, chamar=falso)) == 1
    assert trecho_existe("ANUNCIOU nesta  quinta-feira", TEXTO)
    assert trecho_existe("Petrobras anunciou", "A  PETROBRÁS\nanunciou")


def test_trecho_parafraseado_rejeitado():
    assert not trecho_existe("a Petrobras vai pagar dividendos", TEXTO)


def test_sem_eventos():
    assert extrair_eventos(TEXTO, chamar=LLMFalso(resposta())) == []


def test_modo_teste_usa_provedor_falso(monkeypatch):
    monkeypatch.setenv("QUANT_MODO_TESTE", "1")
    eventos = extract.extrair_eventos(TEXTO)
    assert [e["ticker"] for e in eventos] == ["PETR4"]
    assert eventos[0]["modelo"].startswith("falso:")
