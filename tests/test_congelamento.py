"""Congelamento: checklist, impressão digital, registro só pelo autor e verificação."""
from datetime import date

import pytest

from src import config, congelamento


def test_impressao_digital_muda_com_qualquer_parametro_da_regra(monkeypatch):
    antes = congelamento.impressao_digital()
    assert antes == congelamento.impressao_digital()  # determinística
    monkeypatch.setattr(config, "LIMIAR_PROBABILIDADE", 0.71)
    assert congelamento.impressao_digital() != antes
    monkeypatch.setattr(config, "LIMIAR_PROBABILIDADE", 0.7)
    monkeypatch.setattr(config, "MATERIALIDADE_MINIMA", "alta")
    assert congelamento.impressao_digital() != antes


def test_checklist_mostra_o_que_falta_com_a_sugestao_do_corte(monkeypatch):
    monkeypatch.setenv("LLM_PROVEDOR", "openai")
    monkeypatch.setenv("LLM_MODELO", "gpt-4.1-2025-04-14")
    c = congelamento.checklist(date(2026, 10, 21))
    pendentes = {i["item"]: i for i in c["itens"] if not i["ok"]}
    assert not c["pronto_para_congelar"]
    assert "2024-06-01" in pendentes["Corte de conhecimento do modelo registrado"]["acao"]
    assert "Período de teste aprovado" in pendentes


def test_congelar_exige_o_autor_e_os_pre_requisitos(tmp_path):
    with pytest.raises(PermissionError):
        congelamento.congelar(False, arquivo=tmp_path / "c.json")
    with pytest.raises(RuntimeError, match="Pré-requisitos pendentes"):
        congelamento.congelar(True, arquivo=tmp_path / "c.json")
    assert not (tmp_path / "c.json").exists()


def test_congelar_registra_e_a_verificacao_detecta_mudanca(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_PROVEDOR", "openai")
    monkeypatch.setenv("LLM_MODELO", "gpt-4.1-2025-04-14")
    monkeypatch.setattr(config, "DATA_CORTE_CONHECIMENTO_MODELO", "2024-06-01")
    monkeypatch.setattr(config, "PERIODO_TREINO", ("2025-01-01", "2025-12-31"))
    monkeypatch.setattr(config, "PERIODO_VALIDACAO", ("2026-01-01", "2026-10-21"))
    monkeypatch.setattr(config, "PERIODO_TESTE", ("2026-10-22", "2027-04-22"))
    copia = tmp_path / "config.py"
    copia.write_text("X = 1\nDATA_CONGELAMENTO = None    # pendente\n", encoding="utf-8")
    registro = congelamento.congelar(True, date(2026, 10, 22), arquivo=tmp_path / "c.json", caminho_config=copia)
    assert registro["data"] == "2026-10-22" and registro["modelo"] == "gpt-4.1-2025-04-14"
    assert 'DATA_CONGELAMENTO = "2026-10-22"' in copia.read_text(encoding="utf-8")

    monkeypatch.setattr(config, "DATA_CONGELAMENTO", "2026-10-22")
    assert congelamento.verificar(tmp_path / "c.json")["estado"] == "integra"
    monkeypatch.setattr(config, "JANELA_REPETICAO_HORAS", 12)  # alguém mexeu na regra depois
    v = congelamento.verificar(tmp_path / "c.json")
    assert v["estado"] == "alterada" and "mudaram" in v["problemas"][0]


def test_estudo_historico_recusa_inicio_antes_do_corte_do_modelo(monkeypatch):
    from src import historico
    monkeypatch.setattr(config, "DATA_CORTE_CONHECIMENTO_MODELO", "2024-06-01")
    with pytest.raises(ValueError, match="posterior ao corte"):
        historico.executar(date(2024, 5, 1), estimar=True)
