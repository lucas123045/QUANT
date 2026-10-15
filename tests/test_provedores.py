"""Provedor Anthropic com cliente falso (sem rede, sem chave real)."""
from types import SimpleNamespace

import anthropic
import pytest

from src import extract, llm, provedores


class ClienteFalso:
    def __init__(self, resposta):
        self.chamadas = []
        resposta_fixa = resposta

        class Mensagens:
            def create(inner, **kwargs):
                self.chamadas.append(kwargs)
                return resposta_fixa

        self.beta = SimpleNamespace(messages=Mensagens())


def resposta(texto="ok", modelo="claude-opus-5-5", stop_reason="end_turn", categoria=None):
    return SimpleNamespace(
        content=[SimpleNamespace(type="thinking", thinking=""),
                 SimpleNamespace(type="text", text=texto)],
        model=modelo, stop_reason=stop_reason,
        stop_details=SimpleNamespace(category=categoria) if categoria else None,
    )


@pytest.fixture
def anthropic_falso(monkeypatch):
    def instalar(resp):
        cliente = ClienteFalso(resp)
        monkeypatch.setattr(anthropic, "Anthropic", lambda api_key=None: cliente)
        monkeypatch.setenv("LLM_PROVEDOR", "anthropic")
        monkeypatch.setenv("LLM_API_KEY", "chave-ficticia")
        return cliente
    return instalar


def test_requisicao_e_resposta(anthropic_falso):
    cliente = anthropic_falso(resposta("texto da resposta"))
    assert llm.chamar_llm("oi", temperatura=0.0) == "texto da resposta"
    pedido = cliente.chamadas[0]
    assert pedido["model"] == "claude-opus-5-5"            # padrão
    assert pedido["output_config"] == {"effort": "medium"}
    assert pedido["fallbacks"] == "default"
    assert pedido["betas"] == ["server-side-fallback-2026-07-01"]
    assert "temperature" not in pedido                       # não suportado pelos modelos atuais
    assert pedido["messages"] == [{"role": "user", "content": "oi"}]
    assert llm.modelo_atual() == "anthropic:claude-opus-5-5"
    assert llm.modelo_da_ultima_chamada() == "anthropic:claude-opus-5-5"
    assert llm.temperatura_efetiva(0.0) is None


def test_modelo_configuravel(anthropic_falso, monkeypatch):
    cliente = anthropic_falso(resposta(modelo="claude-sonnet-5-5"))
    monkeypatch.setenv("LLM_MODELO", "claude-sonnet-5-5")
    llm.chamar_llm("oi")
    assert cliente.chamadas[0]["model"] == "claude-sonnet-5-5"


def test_fallback_registra_modelo_que_respondeu(anthropic_falso, caplog):
    anthropic_falso(resposta(modelo="claude-opus-5"))
    llm.chamar_llm("oi")
    assert llm.modelo_da_ultima_chamada() == "anthropic:claude-opus-5"
    assert "fallback" in caplog.text


def test_recusa_levanta_erro(anthropic_falso):
    anthropic_falso(resposta(texto="", stop_reason="refusal", categoria="cyber"))
    with pytest.raises(provedores.RecusaDoModelo, match="cyber"):
        llm.chamar_llm("oi")


def test_extracao_registra_modelo_servido_e_temperatura_nula(anthropic_falso):
    import json
    evento = {"ticker": "PETR4", "tipo_evento": "dividendo", "resumo": "Dividendos.",
              "impacto_declarado": "positivo", "confirmado": True,
              "trecho_fonte": "aprovou dividendos"}
    anthropic_falso(resposta(json.dumps({"eventos": [evento]}), modelo="claude-opus-5"))
    eventos = extract.extrair_eventos("A Petrobras aprovou dividendos.")
    assert eventos[0]["modelo"] == "anthropic:claude-opus-5"
    assert eventos[0]["temperatura"] is None


def test_sem_chave(monkeypatch):
    monkeypatch.setenv("LLM_PROVEDOR", "anthropic")
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        llm.chamar_llm("oi")
