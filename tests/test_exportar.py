"""Vitrine estática: arquivos gerados a partir dos dados locais (sem rede)."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from src import config, main, simulacao
from src.web import exportar


def test_exporta_todos_os_arquivos_sem_expor_a_chave(tmp_path, monkeypatch):
    dados = tmp_path / "data"
    monkeypatch.setattr(config, "DIR_DATA", dados)
    monkeypatch.setenv("LLM_API_KEY", "sk-segredo-que-nao-pode-vazar")
    main.executar(agora=datetime(2026, 10, 15, 20, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
                  teste=True, dir_data=dados / "teste")
    # Sem rede: a simulação devolve um estado simples.
    monkeypatch.setattr(simulacao, "calcular", lambda d: {"estado": "sem_dados", "ativos": []})

    destino = tmp_path / "vitrine"
    (destino / "lixo-antigo.json").parent.mkdir(parents=True)
    (destino / "lixo-antigo.json").write_text("{}")
    resumo = exportar.exportar(destino)

    esperados = ["meta.json", "status.json", "config.json", "funil-real.json", "funil-teste.json",
                 "noticias-teste.json", "execucoes-teste.json", "execucoes-teste/2026-10-15.json",
                 "operacoes-teste.json", "simulacao-teste.json", "simulacao-real.json"]
    for nome in esperados:
        assert (destino / nome).exists(), nome
    assert not (destino / "lixo-antigo.json").exists()  # regenerada do zero

    tudo = "".join(p.read_text(encoding="utf-8") for p in destino.rglob("*.json"))
    assert "sk-segredo" not in tudo
    assert resumo["bases"]["teste"] == {"noticias": 3, "execucoes": 1, "operacoes": 2, "simulacao": "sem_dados"}
    noticias = json.loads((destino / "noticias-teste.json").read_text(encoding="utf-8"))
    assert all("tickers_atuais" in n for n in noticias["itens"])


def test_erro_da_api_vira_arquivo_de_erro(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DIR_DATA", tmp_path / "data")

    def falha(d):
        raise OSError("sem internet")

    monkeypatch.setattr(simulacao, "calcular", falha)
    exportar.exportar(tmp_path / "vitrine", bases=("real",))
    sim = json.loads((tmp_path / "vitrine" / "simulacao-real.json").read_text(encoding="utf-8"))
    assert sim["_erro"] == 503 and "sem internet" in sim["detail"]


def test_recusa_vitrine_que_encolheu(tmp_path, monkeypatch):
    """Gerar a vitrine num computador com data/ vazia não pode apagar a publicada."""
    import pytest

    monkeypatch.setattr(config, "DIR_DATA", tmp_path / "data")  # sem nenhuma notícia
    monkeypatch.setattr(simulacao, "calcular", lambda d: {"estado": "sem_dados", "ativos": []})
    destino = tmp_path / "vitrine"
    destino.mkdir()
    (destino / "meta.json").write_text(json.dumps({"bases": {"real": {"noticias": 28, "operacoes": 0}}}))
    (destino / "noticias-real.json").write_text("publicada")

    with pytest.raises(exportar.VitrineEncolheu, match="noticias 28 → 0"):
        exportar.exportar(destino, bases=("real",))
    assert (destino / "noticias-real.json").read_text() == "publicada"  # intacta
    assert not (tmp_path / "vitrine.novo").exists()

    exportar.exportar(destino, bases=("real",), forcar=True)  # decisão explícita
    assert json.loads((destino / "noticias-real.json").read_text(encoding="utf-8"))["total"] == 0
    assert not (tmp_path / "vitrine.antigo").exists()


def test_base_de_teste_vazia_nao_trava_a_vitrine(tmp_path, monkeypatch):
    """Computador que nunca rodou o modo de teste: a base de teste "encolheu", mas é descartável."""
    monkeypatch.setattr(config, "DIR_DATA", tmp_path / "data")
    monkeypatch.setattr(simulacao, "calcular", lambda d: {"estado": "sem_dados", "ativos": []})
    destino = tmp_path / "vitrine"
    destino.mkdir()
    (destino / "meta.json").write_text(json.dumps({"bases": {"teste": {"noticias": 3, "operacoes": 2}}}))
    exportar.exportar(destino)  # não levanta VitrineEncolheu
    assert json.loads((destino / "meta.json").read_text(encoding="utf-8"))["bases"]["teste"]["noticias"] == 0
