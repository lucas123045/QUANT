import pytest

from src import llm

CARREGAR_ENV_ORIGINAL = llm.carregar_env


@pytest.fixture(autouse=True)
def ambiente_isolado(monkeypatch):
    """Nenhum teste lê o .env real nem herda configuração de LLM do ambiente."""
    for nome in ("QUANT_MODO_TESTE", "LLM_PROVEDOR", "LLM_API_KEY", "LLM_MODELO"):
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setattr(llm, "carregar_env", lambda caminho=None: None)
    monkeypatch.setattr(llm, "_ultimo_modelo_servido", None)
    monkeypatch.setattr(llm, "_temperatura_informada", llm._NAO_INFORMADA)
