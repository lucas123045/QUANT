"""Ponto de entrada das tarefas agendadas: log em UTF-8 e código de saída correto (sem rede)."""
import logging

import pytest

from src import agendado, config, news


@pytest.fixture
def dados(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DIR_DATA", tmp_path)
    monkeypatch.setattr(config, "DIR_ARQUIVO", tmp_path / "arquivo")
    raiz = logging.getLogger()
    antes = raiz.handlers[:]
    yield tmp_path
    for h in raiz.handlers[:]:  # devolve o logging como estava (o agendado troca os handlers)
        if h not in antes:
            h.close()
            raiz.removeHandler(h)
    for h in antes:
        if h not in raiz.handlers:
            raiz.addHandler(h)


def ler_log(pasta):
    return (pasta / "agendamento.log").read_text(encoding="utf-8")


def test_coleta_grava_log_em_utf8(dados, monkeypatch):
    monkeypatch.setattr(news, "coletar_noticias", lambda: [])
    assert agendado.main(["coleta"]) == 0
    log = ler_log(dados)
    assert "==== início: coleta" in log and "==== fim: coleta (ok)" in log  # acentos legíveis


def test_execucao_pulada_pela_trava_nao_e_falha(dados, monkeypatch):
    from src import main

    monkeypatch.setenv("LLM_API_KEY", "chave-de-teste")  # com chave: vai para o pipeline

    def ocupado(**kw):
        raise main.PipelineEmExecucao("Outra execução do pipeline está em andamento; esta foi pulada.")

    monkeypatch.setattr(main, "executar", ocupado)
    assert agendado.main(["pipeline"]) == 0
    assert "Outra execução do pipeline está em andamento" in ler_log(dados)


def test_falha_vai_para_o_log_com_codigo_1(dados, monkeypatch):
    def quebra():
        raise OSError("rede caiu")

    monkeypatch.setattr(news, "coletar_noticias", quebra)
    assert agendado.main(["coleta"]) == 1
    log = ler_log(dados)
    assert "(FALHOU)" in log and "rede caiu" in log


def test_log_grande_e_renomeado(dados, monkeypatch):
    monkeypatch.setattr(news, "coletar_noticias", lambda: [])
    (dados / "agendamento.log").write_bytes(b"x" * (agendado.LIMITE_LOG_BYTES + 1))
    agendado.main(["coleta"])
    assert (dados / "agendamento.log.old").stat().st_size > agendado.LIMITE_LOG_BYTES
    assert (dados / "agendamento.log").stat().st_size < 10_000


def test_sem_chave_so_coleta(dados, monkeypatch):
    """PC novo sem a chave no .env: a coleta automática continua, sem erro por notícia."""
    from src import main

    monkeypatch.setenv("LLM_PROVEDOR", "openai")
    monkeypatch.setattr(news, "coletar_noticias", lambda: [])
    monkeypatch.setattr(main, "executar", lambda **kw: pytest.fail("não deveria chamar o pipeline com LLM"))
    assert agendado.main(["pipeline"]) == 0
    log = ler_log(dados)
    assert "LLM_API_KEY não configurada" in log and "coleta: 0 novos" in log
