"""API da interface web, com dados em pasta temporária (sem rede, sem LLM real)."""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from src import config, main
from src.web import api

AGORA = datetime(2026, 10, 15, 20, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DIR_DATA", tmp_path)
    monkeypatch.setattr(api, "_tarefas", {})
    monkeypatch.setattr(api, "_em_execucao", None)
    return TestClient(api.app)


@pytest.fixture
def com_execucao_de_teste(tmp_path):
    main.executar(agora=AGORA, teste=True, dir_data=tmp_path / "teste")


def test_status_nao_expoe_chave(cliente, monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "sk-segredo-que-nao-pode-vazar")
    monkeypatch.setenv("LLM_PROVEDOR", "openai")
    monkeypatch.setenv("LLM_MODELO", "modelo-x")
    resposta = cliente.get("/api/status")
    assert resposta.status_code == 200
    assert "sk-segredo" not in resposta.text
    dados = resposta.json()
    assert dados["chave_configurada"] is True
    assert dados["modelo"] == "openai:modelo-x"
    assert dados["periodos"] == {"treino": None, "validacao": None, "teste": None}
    assert "Aprovar o período de teste" in dados["pendencias"]
    assert [c["ticker"] for c in dados["carteira"]] == config.CARTEIRA


def test_config_somente_leitura(cliente):
    dados = cliente.get("/api/config").json()
    assert dados["regra"]["LIMIAR_PROBABILIDADE"] == 0.7
    assert dados["criterio"] == {"versao": "CRITERIO_V2", "ALFA_CRITERIO": 0.05}
    assert cliente.post("/api/config", json={}).status_code == 405


def test_base_invalida(cliente):
    assert cliente.get("/api/funil?base=../../etc").status_code == 400


def test_leitura_dos_dados_de_teste(cliente, com_execucao_de_teste):
    noticias = cliente.get("/api/noticias?base=teste").json()
    assert noticias["total"] == 3
    assert cliente.get("/api/noticias?base=teste&so_carteira=true").json()["total"] == 2
    assert cliente.get("/api/noticias?base=teste&ticker=VALE3").json()["total"] == 1
    assert cliente.get("/api/noticias?base=teste&q=cdb").json()["total"] == 1

    execucoes = cliente.get("/api/execucoes?base=teste").json()
    assert [e["data"] for e in execucoes] == ["2026-10-15"]
    detalhe = cliente.get("/api/execucoes/2026-10-15?base=teste").json()
    assert len(detalhe["decisoes"]) == 2
    assert detalhe["relatorio"].startswith("*** MODO DE TESTE")

    assert len(cliente.get("/api/operacoes?base=teste").json()) == 2
    assert cliente.get("/api/funil?base=teste").json()["operacoes"] == 2
    # Os dados reais continuam vazios.
    assert cliente.get("/api/noticias?base=real").json()["total"] == 0


def test_execucao_inexistente_e_data_invalida(cliente):
    assert cliente.get("/api/execucoes/2026-01-01?base=teste").status_code == 404
    assert cliente.get("/api/execucoes/..%2F..?base=teste").status_code in (400, 404)


def _esperar(cliente, tarefa_id, limite=30):
    fim = time.time() + limite
    while time.time() < fim:
        tarefa = cliente.get(f"/api/tarefas/{tarefa_id}").json()
        if tarefa["estado"] != "executando":
            return tarefa
        time.sleep(0.05)
    raise AssertionError("tarefa não terminou")


def test_tarefa_pipeline_teste(cliente, tmp_path):
    criada = cliente.post("/api/tarefas", json={"tipo": "pipeline_teste"})
    assert criada.status_code == 202
    tarefa = _esperar(cliente, criada.json()["id"])
    assert tarefa["estado"] == "concluida", tarefa["erro"]
    assert tarefa["resultado"]["operacoes"] == 2
    assert any("Arquivados" in linha for linha in tarefa["logs"])
    assert (tmp_path / "teste" / "operacoes.jsonl").exists()
    assert cliente.get("/api/tarefas").json()[0]["id"] == tarefa["id"]


def test_tarefa_erro_e_mostrado(cliente, monkeypatch):
    def falha():
        raise OSError("rede fora do ar")
    monkeypatch.setattr(api.news, "coletar_noticias", falha)
    tarefa = _esperar(cliente, cliente.post("/api/tarefas", json={"tipo": "coletar"}).json()["id"])
    assert tarefa["estado"] == "erro"
    assert "rede fora do ar" in tarefa["erro"]


def test_uma_tarefa_por_vez_e_tipo_invalido(cliente, monkeypatch):
    monkeypatch.setattr(api, "_em_execucao", "outra")
    assert cliente.post("/api/tarefas", json={"tipo": "coletar"}).status_code == 409
    monkeypatch.setattr(api, "_em_execucao", None)
    assert cliente.post("/api/tarefas", json={"tipo": "apagar_tudo"}).status_code == 400
