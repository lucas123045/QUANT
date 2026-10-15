import csv
from datetime import datetime
from zoneinfo import ZoneInfo

from src import avaliacao, funil, main

AGORA = datetime(2026, 10, 15, 20, 0, tzinfo=ZoneInfo("America/Sao_Paulo"))


def test_funil_apos_pipeline_de_teste(tmp_path):
    main.executar(agora=AGORA, teste=True, dir_data=tmp_path)
    f = funil.medir_funil(tmp_path)
    assert f["dias_de_coleta"] == 1
    assert f["noticias_arquivadas"] == 3
    assert f["noticias_com_mencao"] == 2          # "Vale a pena..." fica de fora
    assert f["mencoes_por_ticker"] == {"PETR4": 1, "VALE3": 1}
    assert f["eventos_extraidos"] == 2
    assert f["eventos_confirmados"] == 2
    assert f["eventos_acima_do_limiar"] == 2
    assert f["operacoes"] == 2
    assert f["projecao_operacoes_por_semestre"] == 2 * 126


def test_funil_sem_dados(tmp_path):
    f = funil.medir_funil(tmp_path)
    assert f["noticias_arquivadas"] == 0 and f["projecao_operacoes_por_semestre"] is None


def test_avaliacao_matching(tmp_path):
    main.executar(agora=AGORA, teste=True, dir_data=tmp_path)
    csv_saida = tmp_path / "amostra.csv"
    assert avaliacao.exportar_amostra_matching(csv_saida, n=10, dir_arquivo=tmp_path / "arquivo") == 3

    # Rotulagem simulada: o matching acertou PETR4, acertou VALE3 e o "vale a pena".
    with open(csv_saida, encoding="utf-8", newline="") as f:
        linhas = list(csv.DictReader(f))
    for l in linhas:
        l["tickers_corretos"] = l["tickers_previstos"]
    # ... e um erro plantado: suponha que o rotulador diz que o CDB fala do Itaú (falso negativo).
    cdb = next(l for l in linhas if "CDB" in l["titulo"])
    cdb["tickers_corretos"] = "ITUB4"
    with open(csv_saida, "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=linhas[0].keys())
        escritor.writeheader()
        escritor.writerows(linhas)

    r = avaliacao.medir_matching(csv_saida)
    assert r["n_noticias"] == 3
    assert r["total"] == {"vp": 2, "fp": 0, "fn": 1, "precisao": 1.0, "revocacao": 2 / 3}
    assert r["por_ticker"]["ITUB4"]["revocacao"] == 0.0
    assert r["por_ticker"]["ABEV3"]["precisao"] is None


def test_avaliacao_extracao(tmp_path):
    main.executar(agora=AGORA, teste=True, dir_data=tmp_path)
    saida = tmp_path / "eventos.csv"
    assert avaliacao.exportar_eventos(saida, tmp_path / "execucoes") == 2
    with open(saida, encoding="utf-8", newline="") as f:
        linhas = list(csv.DictReader(f))
    linhas[0]["evento_correto"], linhas[1]["evento_correto"] = "sim", "nao"
    with open(saida, "w", encoding="utf-8", newline="") as f:
        escritor = csv.DictWriter(f, fieldnames=linhas[0].keys())
        escritor.writeheader()
        escritor.writerows(linhas)
    assert avaliacao.medir_extracao(saida) == {"n_rotulados": 2, "n_sem_rotulo": 0, "precisao": 0.5}


def test_amostra_reprodutivel(tmp_path):
    main.executar(agora=AGORA, teste=True, dir_data=tmp_path)
    a, b = tmp_path / "a.csv", tmp_path / "b.csv"
    avaliacao.exportar_amostra_matching(a, n=2, dir_arquivo=tmp_path / "arquivo")
    avaliacao.exportar_amostra_matching(b, n=2, dir_arquivo=tmp_path / "arquivo")
    assert a.read_text(encoding="utf-8") == b.read_text(encoding="utf-8")
