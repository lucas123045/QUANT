"""Backup dos dados e alerta de fonte sem notícias."""
import json
import zipfile
from datetime import datetime
from zoneinfo import ZoneInfo

from src import backup, main

SP = ZoneInfo("America/Sao_Paulo")


def test_backup_compacta_os_dados_sem_apagar_nada(tmp_path):
    dados = tmp_path / "data"
    (dados / "arquivo").mkdir(parents=True)
    (dados / "arquivo" / "2026-10-15.jsonl").write_text('{"id": 1}\n', encoding="utf-8")
    (dados / "operacoes.jsonl").write_text('{"op": 1}\n', encoding="utf-8")
    (dados / "teste").mkdir()
    (dados / "teste" / "x.json").write_text("{}")  # modo de teste fica de fora
    destino = tmp_path / "backups"

    primeiro = backup.fazer_backup(dados, destino, datetime(2026, 10, 15, 20, 0, tzinfo=SP))
    segundo = backup.fazer_backup(dados, destino, datetime(2026, 10, 16, 20, 0, tzinfo=SP))
    assert primeiro.exists() and segundo.exists() and primeiro != segundo
    with zipfile.ZipFile(primeiro) as z:
        assert sorted(z.namelist()) == ["arquivo/2026-10-15.jsonl", "operacoes.jsonl"]
    assert (dados / "operacoes.jsonl").exists()  # nada apagado


def test_backup_sem_dados(tmp_path):
    assert backup.fazer_backup(tmp_path / "vazio", tmp_path / "b") is None


def test_destino_padrao_prioriza_onedrive_e_nao_avisa_mesmo_volume(tmp_path, monkeypatch):
    onedrive = tmp_path / "OneDrive"
    onedrive.mkdir()
    monkeypatch.delenv("QUANT_BACKUP_DIR", raising=False)
    monkeypatch.setenv("OneDrive", str(onedrive))
    destino = backup.pasta_destino()
    assert destino == onedrive / "QUANT-backups"
    assert backup.aviso_destino(tmp_path / "data", destino) is None


def test_avisa_se_backup_local_ficar_no_mesmo_volume(tmp_path, monkeypatch):
    monkeypatch.delenv("OneDrive", raising=False)
    aviso = backup.aviso_destino(tmp_path / "data", tmp_path / "backups")
    assert aviso and "mesmo volume" in aviso


def _execucao(pasta, dia, por_fonte, teste=False):
    p = pasta / dia
    p.mkdir(parents=True)
    (p / "resumo.json").write_text(json.dumps({"por_fonte": por_fonte, "modo_teste": teste}), encoding="utf-8")


def test_fonte_muda_em_duas_execucoes_seguidas(tmp_path):
    _execucao(tmp_path, "2026-10-13", {"InfoMoney": 0, "Money Times": 9})
    _execucao(tmp_path, "2026-10-14", {"InfoMoney": 0, "Money Times": 0})
    _execucao(tmp_path, "2026-10-15", {"InfoMoney": 0, "Money Times": 12})
    assert main.fontes_mudas(tmp_path) == ["InfoMoney"]


def test_uma_execucao_so_nao_gera_alerta(tmp_path):
    _execucao(tmp_path, "2026-10-15", {"InfoMoney": 0})
    assert main.fontes_mudas(tmp_path) == []


def test_contagem_inclui_fonte_zerada():
    contagem = main.contar_por_fonte([{"fonte": "Money Times"}, {"fonte": "Money Times"}], teste=False)
    assert contagem == {"InfoMoney": 0, "Money Times": 2}


def test_pipeline_real_faz_backup(tmp_path, monkeypatch):
    from src import news
    monkeypatch.setattr(news, "baixar_url", lambda url: (_ for _ in ()).throw(OSError("sem rede")))
    destino = tmp_path / "bk"
    monkeypatch.setenv("QUANT_BACKUP_DIR", str(destino))
    (tmp_path / "data" / "operacoes.jsonl").parent.mkdir(parents=True)
    (tmp_path / "data" / "operacoes.jsonl").write_text("{}\n")
    resumo = main.executar(agora=datetime(2026, 10, 15, 20, 0, tzinfo=SP), dir_data=tmp_path / "data")
    assert resumo["backup"] and resumo["backup"].startswith(str(destino))
    assert resumo["por_fonte"] == {"InfoMoney": 0, "Money Times": 0}
