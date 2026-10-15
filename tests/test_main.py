import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src import auditoria, llm, main, news

AGORA = datetime(2026, 10, 15, 20, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


@pytest.fixture
def contador_llm(monkeypatch):
    """Conta chamadas ao LLM (provedor falso) sem rede."""
    chamadas = []
    original = llm.resposta_falsa

    def contar(prompt):
        chamadas.append(prompt[:40])
        return original(prompt)

    monkeypatch.setattr(llm, "resposta_falsa", contar)
    return chamadas


def test_pipeline_modo_teste_ponta_a_ponta(tmp_path, monkeypatch, contador_llm):
    monkeypatch.setattr(news, "baixar_url", lambda url: pytest.fail("rede chamada em modo de teste"))
    resumo = main.executar(agora=AGORA, teste=True, dir_data=tmp_path)

    assert resumo["coletados"] == 3
    assert resumo["novos_arquivados"] == 3
    assert resumo["eventos_validos"] == 2              # "Vale a pena" não gera evento
    assert resumo["operacoes"] == 2                    # compra PETR4, venda VALE3
    assert "PENDENTES DE APROVAÇÃO" in resumo["backtest"]

    pasta = tmp_path / "execucoes" / "2026-10-15"
    for nome in ("01_coleta.json", "02_arquivo.json", "03_extracao.json", "04_classificacao.json",
                 "05_decisoes.json", "06_explicacoes.json", "07_registro.json",
                 "relatorio.txt", "resumo.json"):
        assert (pasta / nome).exists(), nome

    operacoes = auditoria.ler_operacoes(tmp_path / "operacoes.jsonl")
    assert sorted((o["ticker"], o["decisao"]) for o in operacoes) == [("PETR4", "compra"),
                                                                     ("VALE3", "venda")]
    for op in operacoes:
        assert set(op) == set(auditoria.CAMPOS)
        assert op["evento"]["trecho_fonte"]
        assert op["evento"]["origem"]["tipo_fonte"] == "noticia"
        assert op["versao_prompt"] == "PROMPT_EXTRACAO_V1"
        assert op["modelo"].startswith("falso:")
        assert op["explicacao"].startswith("Decisão já tomada pela regra")

    relatorio = (pasta / "relatorio.txt").read_text(encoding="utf-8")
    assert "Operações (2):" in relatorio


def test_pipeline_retomavel_sem_novas_chamadas_ao_llm(tmp_path, contador_llm):
    main.executar(agora=AGORA, teste=True, dir_data=tmp_path)
    chamadas_primeira = len(contador_llm)
    assert chamadas_primeira > 0

    # Simula interrupção: apaga só os passos finais.
    pasta = tmp_path / "execucoes" / "2026-10-15"
    (pasta / "05_decisoes.json").unlink()
    (pasta / "relatorio.txt").unlink()
    main.executar(agora=AGORA, teste=True, dir_data=tmp_path)

    # Só o resumo do relatório diário é pedido de novo; extração, classificação
    # e explicações vêm dos arquivos gravados.
    novas = contador_llm[chamadas_primeira:]
    assert all("PROMPT_RELATORIO" in c for c in novas)
    assert len(auditoria.ler_operacoes(tmp_path / "operacoes.jsonl")) == 2  # sem duplicar


def test_retomada_apos_falha_parcial_na_extracao(tmp_path, monkeypatch):
    from src import extract
    original = extract.extrair_eventos
    estado = {"falhar": True}

    def instavel(texto, metadados=None, **kw):
        if estado["falhar"] and "Vale" in texto:
            raise RuntimeError("LLM fora do ar")
        return original(texto, metadados, **kw)

    monkeypatch.setattr(extract, "extrair_eventos", instavel)
    primeiro = main.executar(agora=AGORA, teste=True, dir_data=tmp_path)
    assert primeiro["eventos_validos"] == 1

    estado["falhar"] = False
    segundo = main.executar(agora=AGORA, teste=True, dir_data=tmp_path)
    assert segundo["eventos_validos"] == 2


def test_fonte_indisponivel_nao_derruba_pipeline(tmp_path, monkeypatch, caplog):
    """Execução real com todos os feeds fora do ar (rede mockada) e CVM bloqueada."""
    def rede_fora(url):
        raise OSError("rede indisponível")

    monkeypatch.setattr(news, "baixar_url", rede_fora)
    resumo = main.executar(agora=AGORA, teste=False, dir_data=tmp_path)
    assert resumo["coletados"] == 0 and resumo["operacoes"] == 0
    assert (tmp_path / "execucoes" / "2026-10-15" / "relatorio.txt").exists()
    assert "Falha ao coletar InfoMoney" in caplog.text
    assert "Fonte CVM indisponível" in caplog.text


def test_historico_de_execucoes_anteriores_e_usado(tmp_path):
    anterior = tmp_path / "execucoes" / "2026-10-14"
    anterior.mkdir(parents=True)
    evento = {"id": "x-0", "ticker": "PETR4", "confirmado": True,
              "origem": {"timestamp_publicacao": "2026-10-14T10:00:00-03:00"}}
    (anterior / "03_extracao.json").write_text(json.dumps({"x": [evento]}), encoding="utf-8")
    (anterior / "04_classificacao.json").write_text(
        json.dumps({"x-0": {"sentimento": "negativo", "probabilidade": 0.9}}), encoding="utf-8")

    resumo = main.executar(agora=AGORA, teste=True, dir_data=tmp_path)
    decisoes = json.loads((tmp_path / "execucoes" / "2026-10-15" / "05_decisoes.json")
                          .read_text(encoding="utf-8"))
    petr4 = next(d for d in decisoes if d["decisao"]["ticker"] == "PETR4")
    assert petr4["decisao"]["decisao"] == "manter"   # negativo recente bloqueia a compra
    assert resumo["operacoes"] == 1
