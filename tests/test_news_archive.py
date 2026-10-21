import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from src import archive, news

SP = ZoneInfo("America/Sao_Paulo")
AGORA = datetime(2026, 10, 15, 20, 0, tzinfo=SP)  # 23:00 UTC

FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Portal Teste</title>
<item>
  <title>Petrobras anuncia dividendos</title>
  <link>https://portal.teste/petrobras-dividendos</link>
  <pubDate>Thu, 15 Oct 2026 21:30:00 +0000</pubDate>
  <description>&lt;p&gt;A Petrobras aprovou dividendos de R$ 2,00 por ação.&lt;/p&gt;</description>
</item>
<item>
  <title>Vale a pena investir em CDB?</title>
  <link>https://portal.teste/cdb</link>
  <pubDate>Thu, 15 Oct 2026 12:00:00 +0000</pubDate>
  <description>Especialistas comparam renda fixa.</description>
</item>
<item>
  <title>Notícia antiga da Ambev</title>
  <link>https://portal.teste/antiga</link>
  <pubDate>Mon, 12 Oct 2026 12:00:00 +0000</pubDate>
  <description>Ambev fora da janela.</description>
</item>
<item>
  <title>Sem data</title>
  <link>https://portal.teste/sem-data</link>
  <description>Bradesco sem data.</description>
</item>
</channel></rss>"""

FONTES = [{"nome": "Portal A", "url": "https://a.teste/feed"},
          {"nome": "Portal B", "url": "https://b.teste/feed"}]


def baixar_falso(respostas):
    def baixar(url):
        valor = respostas[url]
        if isinstance(valor, Exception):
            raise valor
        return valor.encode("utf-8")
    return baixar


def test_coleta_filtra_janela_e_converte_fuso():
    itens = news.coletar_noticias(FONTES[:1], agora=AGORA,
                                  baixar=baixar_falso({FONTES[0]["url"]: FEED}))
    assert [i["url"] for i in itens] == ["https://portal.teste/petrobras-dividendos",
                                        "https://portal.teste/cdb"]
    primeiro = itens[0]
    assert primeiro["tipo_fonte"] == "noticia"
    assert primeiro["timestamp_publicacao"] == "2026-10-15T18:30:00-03:00"
    assert primeiro["texto"] == "A Petrobras aprovou dividendos de R$ 2,00 por ação."


def test_falha_de_rede_em_uma_fonte_nao_derruba_coleta(caplog):
    baixar = baixar_falso({FONTES[0]["url"]: OSError("timeout"), FONTES[1]["url"]: FEED})
    itens = news.coletar_noticias(FONTES, agora=AGORA, baixar=baixar)
    assert {i["fonte"] for i in itens} == {"Portal B"}
    assert "Falha ao coletar Portal A" in caplog.text


def test_feed_invalido_registrado(caplog):
    baixar = baixar_falso({FONTES[0]["url"]: "<html>erro 500", FONTES[1]["url"]: FEED})
    itens = news.coletar_noticias(FONTES, agora=AGORA, baixar=baixar)
    assert {i["fonte"] for i in itens} == {"Portal B"}


def _itens():
    return news.coletar_noticias(FONTES[:1], agora=AGORA,
                                 baixar=baixar_falso({FONTES[0]["url"]: FEED}))


def test_arquivar_grava_registro_completo(tmp_path):
    novos = archive.arquivar(_itens(), pasta=tmp_path, agora=AGORA)
    assert len(novos) == 2
    arquivo = tmp_path / "2026-10-15.jsonl"
    linhas = [json.loads(l) for l in arquivo.read_text(encoding="utf-8").splitlines()]
    registro = linhas[0]
    assert set(registro) == {"id", "timestamp_publicacao", "timestamp_coleta", "tipo_fonte",
                             "fonte", "url", "titulo", "texto", "tickers", "hash_conteudo"}
    assert registro["tickers"] == ["PETR4"]
    assert linhas[1]["tickers"] == []  # "Vale a pena" não é VALE3


def test_arquivar_deduplica_por_url_e_so_acrescenta(tmp_path):
    archive.arquivar(_itens(), pasta=tmp_path, agora=AGORA)
    arquivo = tmp_path / "2026-10-15.jsonl"
    conteudo_antes = arquivo.read_text(encoding="utf-8")

    item_novo = dict(_itens()[0], url="https://portal.teste/nova", titulo="Ambev nova")
    item_repetido_alterado = dict(_itens()[0], texto="texto alterado")  # mesma URL
    novos = archive.arquivar([item_repetido_alterado, item_novo, item_novo], pasta=tmp_path,
                             agora=AGORA)

    assert [n["url"] for n in novos] == ["https://portal.teste/nova"]
    conteudo_depois = arquivo.read_text(encoding="utf-8")
    assert conteudo_depois.startswith(conteudo_antes)  # nada sobrescrito
    assert len(archive.carregar_arquivo(tmp_path)) == 3


def test_dedup_vale_entre_dias(tmp_path):
    archive.arquivar(_itens(), pasta=tmp_path, agora=AGORA)
    amanha = datetime(2026, 10, 16, 9, 0, tzinfo=SP)
    assert archive.arquivar(_itens(), pasta=tmp_path, agora=amanha) == []
    assert not (tmp_path / "2026-10-16.jsonl").exists()


def test_item_invalido(tmp_path):
    with pytest.raises(ValueError, match="tipo_fonte"):
        archive.arquivar([dict(_itens()[0], tipo_fonte="blog")], pasta=tmp_path, agora=AGORA)
    assert archive.arquivar([dict(_itens()[0], url="")], pasta=tmp_path, agora=AGORA) == []


def test_cli_sem_argumento_retorna_erro(capsys):
    assert archive.main([]) == 1


def test_cli_coletar(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(archive.config, "DIR_ARQUIVO", tmp_path)
    itens = _itens()
    monkeypatch.setattr(news, "coletar_noticias", lambda: itens)
    assert archive.main(["--coletar"]) == 0
    assert "2 itens novos arquivados (1 mencionam a carteira)" in capsys.readouterr().out


def test_mesma_noticia_em_dois_feeds_entra_uma_vez():
    """A notícia sai no feed geral e no feed da empresa: deve ser coletada uma vez só."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    rss = (b"<?xml version=\"1.0\"?><rss version=\"2.0\"><channel><item><title>Petrobras paga dividendos</title>"
           b"<link>https://portal.exemplo/petrobras-dividendos</link><description>Texto.</description>"
           b"<pubDate>Tue, 20 Oct 2026 15:00:00 -0300</pubDate></item></channel></rss>")
    fontes = [{"nome": "Portal", "feed": "geral", "url": "u1"}, {"nome": "Portal", "feed": "PETR4", "url": "u2"}]
    itens = news.coletar_noticias(fontes, agora=datetime(2026, 10, 20, 18, 0, tzinfo=ZoneInfo("America/Sao_Paulo")),
                                  baixar=lambda url: rss)
    assert [i["url"] for i in itens] == ["https://portal.exemplo/petrobras-dividendos"]
