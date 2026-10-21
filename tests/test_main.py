import json
import os
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
        assert set(op) == set(auditoria.CAMPOS) | set(auditoria.CAMPOS_OPCIONAIS)
        assert op["versao_regra"] == "REGRA_V2"
        # Justificativa passo a passo: cada critério da regra, cumprido, para uma compra/venda.
        assert op["criterios"] and all(c["ok"] for c in op["criterios"])
        assert op["evento"]["trecho_fonte"]
        assert op["evento"]["origem"]["tipo_fonte"] == "noticia"
        assert op["versao_prompt"] == "PROMPT_EXTRACAO_V2"
        assert op["modelo"].startswith("falso:")
        assert op["explicacao"].startswith("Decisão já tomada pela regra")

    relatorio = (pasta / "relatorio.txt").read_text(encoding="utf-8")
    assert "Operações (2):" in relatorio
    assert relatorio.startswith("*** MODO DE TESTE")


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
    evento = {"id": "x-0", "ticker": "PETR4", "confirmado": True, "tipo_evento": "resultado",
              "versao_prompt": "PROMPT_EXTRACAO_V2",
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


def test_eventos_do_prompt_antigo_nao_entram_na_regra(tmp_path):
    """Com o PROMPT_EXTRACAO_V1, resumos de cotação saíam como "outro": a REGRA_V2 não
    pode tratá-los como fatos, nem como histórico do filtro de evento oposto."""
    anterior = tmp_path / "execucoes" / "2026-10-14"
    anterior.mkdir(parents=True)
    evento = {"id": "x-0", "ticker": "PETR4", "confirmado": True, "tipo_evento": "outro",
              "versao_prompt": "PROMPT_EXTRACAO_V1",
              "origem": {"timestamp_publicacao": "2026-10-14T10:00:00-03:00"}}
    (anterior / "03_extracao.json").write_text(json.dumps({"x": [evento]}), encoding="utf-8")
    (anterior / "04_classificacao.json").write_text(
        json.dumps({"x-0": {"sentimento": "negativo", "probabilidade": 0.9}}), encoding="utf-8")
    assert main.carregar_historico(tmp_path / "execucoes", "2026-10-15") == []
    resumo = main.executar(agora=AGORA, teste=True, dir_data=tmp_path)
    assert resumo["operacoes"] == 2  # o negativo antigo (V1) não bloqueou a compra de PETR4


def test_noticias_coletadas_antes_do_pipeline_ainda_passam_pela_ia(tmp_path):
    """Coletar (botão da interface ou `archive --coletar`) e depois rodar o pipeline
    no mesmo dia: as notícias já arquivadas não podem ficar sem extração."""
    from src import archive

    archive.arquivar(main.itens_de_exemplo(AGORA), pasta=tmp_path / "arquivo", agora=AGORA)
    resumo = main.executar(agora=AGORA, teste=True, dir_data=tmp_path)
    assert resumo["novos_arquivados"] == 0
    assert resumo["ja_arquivados_sem_extracao"] == 2  # o "Vale a pena" não menciona a carteira
    assert resumo["eventos_validos"] == 2
    assert resumo["operacoes"] == 2


def test_noticia_ja_extraida_em_dia_anterior_nao_e_extraida_de_novo(tmp_path, contador_llm):
    """O feed traz as últimas 24 h: a mesma notícia aparece em duas coletas seguidas."""
    from datetime import timedelta

    main.executar(agora=AGORA, teste=True, dir_data=tmp_path)
    antes = len(contador_llm)
    resumo = main.executar(agora=AGORA + timedelta(hours=12), teste=True, dir_data=tmp_path)
    assert resumo["ja_arquivados_sem_extracao"] == 0 and resumo["eventos_validos"] == 0
    assert not any("PROMPT_EXTRACAO" in c for c in contador_llm[antes:])


def test_execucoes_a_cada_hora_somam_so_o_que_e_novo(tmp_path, monkeypatch, contador_llm):
    """Rodando de hora em hora: a 2ª execução do dia coleta de novo e só analisa a notícia nova."""
    from datetime import timedelta

    exemplos = main.itens_de_exemplo(AGORA)
    lotes = [exemplos[:1], exemplos]  # às 20h só a da Petrobras; às 21h, as três
    monkeypatch.setattr(main, "itens_de_exemplo", lambda agora: lotes.pop(0))

    primeira = main.executar(agora=AGORA, teste=True, dir_data=tmp_path)
    assert (primeira["coletados"], primeira["eventos_validos"], primeira["operacoes"]) == (1, 1, 1)
    antes = len(contador_llm)

    segunda = main.executar(agora=AGORA + timedelta(hours=1), teste=True, dir_data=tmp_path)
    assert (segunda["coletados"], segunda["novos_arquivados"]) == (3, 3)
    assert (segunda["eventos_validos"], segunda["operacoes"]) == (2, 2)
    extracoes = [c for c in contador_llm[antes:] if "PROMPT_EXTRACAO" in c]
    assert len(extracoes) == 1  # só a notícia da Vale foi para o LLM
    assert len(auditoria.ler_operacoes(tmp_path / "operacoes.jsonl")) == 2  # sem duplicar a compra


def test_trava_impede_duas_execucoes_ao_mesmo_tempo(tmp_path):
    import os
    import time

    trava = tmp_path / ".pipeline.lock"
    trava.write_text("123")
    with pytest.raises(main.PipelineEmExecucao):
        main.executar(agora=AGORA, teste=True, dir_data=tmp_path)
    # Trava esquecida por uma execução que morreu: expira e não bloqueia para sempre.
    velho = time.time() - (main.VALIDADE_TRAVA_HORAS + 1) * 3600
    os.utime(trava, (velho, velho))
    assert main.executar(agora=AGORA, teste=True, dir_data=tmp_path)["eventos_validos"] == 2
    assert not trava.exists()  # liberada no fim


def test_backup_no_maximo_a_cada_seis_horas(tmp_path, monkeypatch):
    from datetime import timedelta
    from pathlib import Path

    monkeypatch.setattr(news, "baixar_url", lambda url: b"<rss></rss>")  # feeds vazios, sem rede
    destino = Path(os.environ["QUANT_BACKUP_DIR"])
    for horas in (0, 1, 2):
        r = main.executar(agora=AGORA + timedelta(hours=horas), teste=False, dir_data=tmp_path / "data")
    assert len(list(destino.glob("quant-dados-*.zip"))) == 1
    assert r["backup"].startswith("mantido")
    r = main.executar(agora=AGORA + timedelta(hours=7), teste=False, dir_data=tmp_path / "data")
    assert len(list(destino.glob("quant-dados-*.zip"))) == 2


def test_rodar_de_novo_sem_novidade_nao_chama_o_llm(tmp_path, contador_llm):
    """Agendado a cada 30 min: sem notícia nova, nenhuma chamada paga (nem o resumo do relatório)."""
    from datetime import timedelta

    main.executar(agora=AGORA, teste=True, dir_data=tmp_path)
    antes = len(contador_llm)
    main.executar(agora=AGORA + timedelta(minutes=30), teste=True, dir_data=tmp_path)
    assert contador_llm[antes:] == []
    assert (tmp_path / "execucoes" / "2026-10-15" / "relatorio.txt").exists()
