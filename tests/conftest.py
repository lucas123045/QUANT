import pytest

from src import backtest, cdi, llm, mercado, rede

CARREGAR_ENV_ORIGINAL = llm.carregar_env


@pytest.fixture(autouse=True)
def ambiente_isolado(monkeypatch, tmp_path_factory):
    """Nenhum teste lê o .env real nem herda configuração de LLM do ambiente."""
    # Nem canal de alerta: um teste nunca manda notificação de verdade.
    for nome in ("QUANT_MODO_TESTE", "LLM_PROVEDOR", "LLM_API_KEY", "LLM_MODELO", "QUANT_NTFY_TOPICO",
                 "QUANT_NTFY_SERVIDOR", "QUANT_TELEGRAM_TOKEN", "QUANT_TELEGRAM_CHAT"):
        monkeypatch.delenv(nome, raising=False)
    monkeypatch.setattr(llm, "carregar_env", lambda caminho=None: None)
    # Backups dos testes vão para uma pasta temporária, nunca para a real.
    monkeypatch.setenv("QUANT_BACKUP_DIR", str(tmp_path_factory.mktemp("backups")))
    monkeypatch.setattr(llm, "_ultimo_modelo_servido", None)
    monkeypatch.setattr(llm, "_temperatura_informada", llm._NAO_INFORMADA)
    # O CDI vem do Banco Central: nos testes, a fonte fica "fora do ar" (sem rede).
    def sem_rede(inicio, fim):
        raise OSError("rede desligada nos testes")
    monkeypatch.setattr(cdi, "baixar_bcb", sem_rede)

    # Rede bloqueada para todo teste: quem precisar simula a resposta (ex.: news.baixar_url).
    def rede_bloqueada(url, *args, **kwargs):
        raise OSError(f"rede desligada nos testes: {url}")
    monkeypatch.setattr(rede, "baixar", rede_bloqueada)

    # O yfinance acessa a rede por conta própria (não passa por rede.baixar).
    def yfinance_bloqueado(*args, **kwargs):
        raise OSError("yfinance desligado nos testes")
    monkeypatch.setattr(backtest, "_baixar_yfinance", yfinance_bloqueado)
    for metodo in ("diario", "intradiario", "calendario"):
        monkeypatch.setattr(mercado.Fontes, metodo, yfinance_bloqueado)
