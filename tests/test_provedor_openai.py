"""Provedor OpenAI com cliente falso (sem rede, sem chave real)."""
import json
from types import SimpleNamespace

import openai
import pytest

from src import extract, llm, provedores


def resposta(texto="ok", modelo="modelo-x-2026", finish_reason="stop", recusa=None):
    mensagem = SimpleNamespace(content=texto, refusal=recusa)
    return SimpleNamespace(model=modelo,
                           choices=[SimpleNamespace(message=mensagem, finish_reason=finish_reason)])


class ErroFalso400(openai.BadRequestError):
    """BadRequestError sem resposta HTTP real (o construtor do SDK exige uma)."""

    def __init__(self, mensagem):
        Exception.__init__(self, mensagem)


def erro_temperatura():
    return ErroFalso400("Unsupported value: 'temperature' does not support 0 with this model")


class ClienteFalso:
    def __init__(self, *respostas):
        self.chamadas = []
        fila = list(respostas)

        class Completions:
            def create(inner, **kwargs):
                self.chamadas.append(kwargs)
                item = fila.pop(0)
                if isinstance(item, Exception):
                    raise item
                return item

        self.chat = SimpleNamespace(completions=Completions())


@pytest.fixture
def openai_falso(monkeypatch):
    def instalar(*respostas, modelo="modelo-x"):
        cliente = ClienteFalso(*respostas)
        monkeypatch.setattr(openai, "OpenAI", lambda api_key=None: cliente)
        monkeypatch.setenv("LLM_PROVEDOR", "openai")
        monkeypatch.setenv("LLM_API_KEY", "chave-ficticia")
        if modelo:
            monkeypatch.setenv("LLM_MODELO", modelo)
        return cliente
    return instalar


def test_requisicao_com_temperatura_zero(openai_falso):
    cliente = openai_falso(resposta("texto"))
    assert llm.chamar_llm("oi", temperatura=0.0) == "texto"
    pedido = cliente.chamadas[0]
    assert pedido == {"model": "modelo-x", "messages": [{"role": "user", "content": "oi"}],
                      "temperature": 0.0}
    assert llm.temperatura_efetiva(0.0) == 0.0
    assert llm.modelo_da_ultima_chamada() == "openai:modelo-x-2026"


def test_modelo_que_rejeita_temperatura_repete_sem_ela(openai_falso, caplog):
    cliente = openai_falso(erro_temperatura(), resposta("texto"))
    assert llm.chamar_llm("oi", temperatura=0.0) == "texto"
    assert "temperature" in cliente.chamadas[0]
    assert "temperature" not in cliente.chamadas[1]
    assert llm.temperatura_efetiva(0.0) is None
    assert "não aceita temperature" in caplog.text


def test_outro_erro_400_nao_e_engolido(openai_falso):
    openai_falso(ErroFalso400("The model 'xyz' does not exist"))
    with pytest.raises(openai.BadRequestError):
        llm.chamar_llm("oi")


@pytest.mark.parametrize("resp", [
    resposta(texto=None, recusa="não posso ajudar"),
    resposta(texto="", finish_reason="content_filter"),
])
def test_recusa(openai_falso, resp):
    openai_falso(resp)
    with pytest.raises(provedores.RecusaDoModelo):
        llm.chamar_llm("oi")


def test_modelo_obrigatorio(openai_falso):
    openai_falso(resposta(), modelo=None)
    with pytest.raises(RuntimeError, match="defina LLM_MODELO"):
        llm.chamar_llm("oi")


def test_extracao_registra_modelo_e_temperatura(openai_falso):
    evento = {"ticker": "PETR4", "tipo_evento": "dividendo", "resumo": "Dividendos.",
              "impacto_declarado": "positivo", "confirmado": True,
              "trecho_fonte": "aprovou dividendos"}
    openai_falso(resposta(json.dumps({"eventos": [evento]})))
    eventos = extract.extrair_eventos("A Petrobras aprovou dividendos.")
    assert eventos[0]["modelo"] == "openai:modelo-x-2026"
    assert eventos[0]["temperatura"] == 0.0
