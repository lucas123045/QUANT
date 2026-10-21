import json
import os

import pytest

from src import llm
from tests.conftest import CARREGAR_ENV_ORIGINAL


def test_provedor_nao_definido_levanta_not_implemented():
    with pytest.raises(NotImplementedError, match="não implementado"):
        llm.chamar_llm("oi")


def test_provedor_registrado_recebe_chave_do_ambiente_e_temperatura(monkeypatch):
    recebido = {}

    def provedor(prompt, temperatura, chave, modelo):
        recebido.update(prompt=prompt, temperatura=temperatura, chave=chave, modelo=modelo)
        return "ok"

    llm.registrar_provedor("teste", provedor)
    monkeypatch.setenv("LLM_PROVEDOR", "teste")
    monkeypatch.setenv("LLM_API_KEY", "chave-ficticia")
    monkeypatch.setenv("LLM_MODELO", "modelo-x")
    assert llm.chamar_llm("oi") == "ok"
    assert recebido == {"prompt": "oi", "temperatura": 0.0, "chave": "chave-ficticia",
                        "modelo": "modelo-x"}
    assert llm.modelo_atual() == "teste:modelo-x"


def test_provedor_registrado_sem_chave_falha(monkeypatch):
    llm.registrar_provedor("teste", lambda *a: "ok")
    monkeypatch.setenv("LLM_PROVEDOR", "teste")
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        llm.chamar_llm("oi")


def test_modo_teste(monkeypatch):
    monkeypatch.setenv("QUANT_MODO_TESTE", "1")
    assert llm.provedor_atual() == "falso"
    assert json.loads(llm.chamar_llm("[PROMPT_CLASSIFICACAO_V2] x")) == {
        "sentimento": "neutro", "probabilidade": 0.5, "materialidade": "baixa",
        "motivo_materialidade": "Materialidade simulada pelo provedor falso."}


def test_carregar_env_nao_sobrescreve(tmp_path, monkeypatch):
    arquivo = tmp_path / ".env"
    arquivo.write_text("# comentário\nQUANT_X=1\nQUANT_Y='dois'\n", encoding="utf-8")
    monkeypatch.setenv("QUANT_X", "ja_definido")
    monkeypatch.delenv("QUANT_Y", raising=False)
    CARREGAR_ENV_ORIGINAL(arquivo)
    assert os.environ["QUANT_X"] == "ja_definido"
    assert os.environ["QUANT_Y"] == "dois"
    monkeypatch.delenv("QUANT_Y")
