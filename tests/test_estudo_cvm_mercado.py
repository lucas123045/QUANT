"""Estudo de evento, fatos relevantes da CVM, contexto de mercado e alertas (sem rede)."""
import io
import json
import zipfile
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import pytest

from src import alertas, config, cvm, estudo_evento, mercado

SP = ZoneInfo("America/Sao_Paulo")


# ---------------------------------------------------------------- estudo de evento

def mercado_com_beta(beta=0.5, n=200, semente=3):
    """Ação = beta x Ibovespa + ruído pequeno: o modelo de mercado tem de recuperar o beta."""
    gerador = np.random.default_rng(semente)
    dias = pd.bdate_range("2026-01-01", periods=n)
    m = gerador.normal(0, 0.01, n)
    colunas = {config.BENCHMARK: 100 * np.cumprod(1 + m)}
    for t in config.CARTEIRA:
        colunas[t] = 50 * np.cumprod(1 + beta * m + gerador.normal(0, 0.004, n))
    return pd.DataFrame(colunas, index=dias)


def evento(ticker, dia, sentimento="positivo", prob=0.9, tipo="resultado", confirmado=True, id_=None):
    return {"id": id_ or f"{ticker}-{dia}", "ticker": ticker, "tipo_evento": tipo, "confirmado": confirmado,
            "resumo": "x", "classificacao": {"sentimento": sentimento, "probabilidade": prob},
            "origem": {"tipo_fonte": "noticia", "timestamp_publicacao": f"{dia}T11:00:00-03:00", "url": "u"}}


def test_modelo_de_mercado_recupera_o_beta():
    precos = mercado_com_beta(beta=0.5)
    modelo = estudo_evento.modelo_de_mercado(estudo_evento.retornos(precos), "PETR4", 150)
    assert modelo["beta"] == pytest.approx(0.5, abs=0.06) and modelo["n"] == 120


def test_car_depois_da_execucao_com_o_sinal_da_classificacao():
    precos = mercado_com_beta()
    dia = precos.index[150].date().isoformat()
    i_exec = 151
    # Depois da execução, VALE3 cai 1% ao dia além do mercado por 5 pregões.
    for k in range(i_exec + 1, i_exec + 6):
        precos.iloc[k:, precos.columns.get_loc("VALE3")] *= 0.99
    linhas = estudo_evento.observacoes([evento("VALE3", dia, "negativo")], precos)
    assert linhas[0]["car_5"] == pytest.approx(0.05, abs=0.01)  # negativo que caiu: +5% a favor
    assert linhas[0]["car_1"] == pytest.approx(0.01, abs=0.006)


def test_mesmo_fato_em_varios_portais_conta_uma_vez_e_cotacao_fica_de_fora():
    precos = mercado_com_beta()
    dia = precos.index[150].date().isoformat()
    eventos = [evento("PETR4", dia, id_="a"), evento("PETR4", dia, id_="b"),
               evento("PETR4", dia, "negativo", id_="c"), evento("ITUB4", dia, tipo="cotacao", id_="d")]
    linhas = estudo_evento.observacoes(eventos, precos)
    assert [l["id"] for l in linhas] == ["a", "c"]


def test_reacao_contra_e_a_favor():
    precos = mercado_com_beta()
    i = 150
    precos.iloc[i:, precos.columns.get_loc("ABEV3")] *= 0.94  # -6% no dia da notícia
    instante = f"{precos.index[i].date().isoformat()}T11:00:00-03:00"
    reacao = estudo_evento.reacao_do_mercado("ABEV3", instante, precos)
    assert reacao["n_pregoes"] == 1 and reacao["z"] < -5
    assert estudo_evento.leitura_reacao(reacao["z"], 1) == "contra"
    assert estudo_evento.leitura_reacao(reacao["z"], -1) == "a favor"
    # Notícia de sábado: nenhum pregão entre ela e a execução.
    sabado = precos.index[i] + pd.offsets.Week(weekday=5)
    assert estudo_evento.reacao_do_mercado("ABEV3", f"{sabado.date()}T11:00:00-03:00", precos)["n_pregoes"] == 0


def test_grupos_e_calibracao_com_amostra_pequena_nao_concluem():
    precos = mercado_com_beta()
    eventos = [evento(t, precos.index[150 + k].date().isoformat()) for k, t in enumerate(config.CARTEIRA_ORIGINAL)]
    linhas = estudo_evento.observacoes(eventos, precos)
    grupos = estudo_evento.grupos(linhas)
    assert grupos[0]["grupo"] == "Todos os eventos" and grupos[0]["n"] == 5
    assert "amostra pequena" in grupos[0]["leitura"]
    assert "Amostra pequena" in estudo_evento.calibracao(linhas)["leitura"]


def test_latencia_ignora_o_acumulo_da_primeira_coleta(tmp_path):
    def registro(pub, coleta, url):
        return {"id": url, "url": url, "fonte": "Portal", "tipo_fonte": "noticia", "tickers": ["PETR4"],
                "timestamp_publicacao": pub, "timestamp_coleta": coleta}
    linhas = [
        registro("2026-10-19T08:00:00-03:00", "2026-10-20T10:00:00-03:00", "a"),  # acúmulo da 1ª coleta
        registro("2026-10-20T10:10:00-03:00", "2026-10-20T10:30:00-03:00", "b"),  # 20 min
        registro("2026-10-20T10:20:00-03:00", "2026-10-20T11:00:00-03:00", "c"),  # 40 min
    ]
    (tmp_path / "2026-10-20.jsonl").write_text("\n".join(json.dumps(l) for l in linhas), encoding="utf-8")
    r = estudo_evento.latencia(tmp_path)
    assert r["fora_da_medida"] == 1 and r["fontes"][0]["n"] == 2
    assert r["fontes"][0]["mediana_min"] == pytest.approx(30)


# ---------------------------------------------------------------- CVM

def pdf_com_texto(texto: str) -> bytes:
    """PDF mínimo válido, com uma linha de texto (para o pypdf extrair)."""
    conteudo = f"BT /F1 12 Tf 20 100 Td ({texto}) Tj ET".encode("latin-1")
    objetos = [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
               b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 200] /Contents 4 0 R "
               b"/Resources << /Font << /F1 5 0 R >> >> >>",
               b"<< /Length %d >>\nstream\n" % len(conteudo) + conteudo + b"\nendstream",
               b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    saida, posicoes = io.BytesIO(), []
    saida.write(b"%PDF-1.4\n")
    for n, obj in enumerate(objetos, 1):
        posicoes.append(saida.tell())
        saida.write(b"%d 0 obj\n" % n + obj + b"\nendobj\n")
    xref = saida.tell()
    saida.write(b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1))
    for p in posicoes:
        saida.write(b"%010d 00000 n \n" % p)
    saida.write(b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, xref))
    return saida.getvalue()


def zip_ipe(linhas: list[dict]) -> bytes:
    colunas = ["CNPJ_Companhia", "Nome_Companhia", "Codigo_CVM", "Data_Referencia", "Categoria", "Tipo",
               "Especie", "Assunto", "Data_Entrega", "Tipo_Apresentacao", "Protocolo_Entrega", "Versao",
               "Link_Download"]
    texto = ";".join(colunas) + "\n" + "\n".join(";".join(l.get(c, "") for c in colunas) for l in linhas) + "\n"
    saida = io.BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        z.writestr("ipe_cia_aberta_2026.csv", texto.encode("latin-1"))
    return saida.getvalue()


def linha_cvm(cnpj="33.000.167/0001-01", categoria="Fato Relevante", entrega="2026-10-19", versao="1", n="1"):
    return {"CNPJ_Companhia": cnpj, "Nome_Companhia": "PETRÓLEO BRASILEIRO S.A. - PETROBRAS",
            "Categoria": categoria, "Assunto": "Petrobras informa sobre descoberta", "Data_Entrega": entrega,
            "Versao": versao, "Link_Download": f"https://www.rad.cvm.gov.br/doc?n={n}&v={versao}"}


def test_cvm_filtra_por_cnpj_categoria_versao_e_janela(tmp_path):
    conteudo = zip_ipe([
        linha_cvm(n="1"),                                   # entra
        linha_cvm(n="1", versao="2"),                        # reapresentação: fora
        linha_cvm(n="2", categoria="Comunicado ao Mercado"),  # outra categoria: fora
        linha_cvm(n="3", cnpj="00.000.000/0001-00"),         # fora da carteira
        linha_cvm(n="4", entrega="2026-09-01"),              # fora da janela de 10 dias
    ])
    pdfs = []

    def baixar_documento(url):
        pdfs.append(url)
        return pdf_com_texto("A Petrobras informa a descoberta de petroleo no pre-sal.")

    agora = datetime(2026, 10, 21, 9, 0, tzinfo=SP)
    itens = cvm.coletar(agora=agora, dir_data=tmp_path, baixar=lambda url: conteudo,
                        baixar_documento=baixar_documento)
    assert len(itens) == 1
    item = itens[0]
    assert item["tipo_fonte"] == "fato_relevante" and item["titulo"].startswith("Petrobras: ")
    assert "descoberta de petroleo" in item["texto"]
    assert item["timestamp_publicacao"] == "2026-10-19T23:59:00-03:00"  # data sem hora: fim do dia

    # Já arquivado: não baixa o PDF de novo.
    from src import archive
    archive.arquivar(itens, pasta=tmp_path / "arquivo", agora=agora)
    assert cvm.coletar(agora=agora, dir_data=tmp_path, baixar=lambda url: conteudo,
                       baixar_documento=baixar_documento) == []
    assert len(pdfs) == 1
    assert archive.carregar_arquivo(tmp_path / "arquivo")[0]["tickers"] == ["PETR4"]


def test_cvm_sem_pdf_legivel_usa_o_assunto(tmp_path):
    def falha(url):
        raise OSError("fora do ar")
    itens = cvm.coletar(agora=datetime(2026, 10, 21, tzinfo=SP), dir_data=tmp_path,
                        baixar=lambda url: zip_ipe([linha_cvm()]), baixar_documento=falha)
    assert itens[0]["texto"] == "Petrobras informa sobre descoberta"


# ---------------------------------------------------------------- mercado

class FontesFalsas(mercado.Fontes):
    def __init__(self):
        self.chamadas = 0

    def sgs(self, serie, inicio):
        self.chamadas += 1
        if serie == 432:  # meta Selic: com datas futuras, como a API real
            return [{"data": "10/09/2026", "valor": "14.00"}, {"data": "17/09/2026", "valor": "13.75"},
                    {"data": "21/10/2026", "valor": "13.75"}, {"data": "04/11/2026", "valor": "13.75"}]
        if serie == 13522:
            raise TimeoutError("sem resposta")
        return [{"data": "18/09/2026", "valor": "5.20"}, {"data": "20/10/2026", "valor": "5.00"}]

    def diario(self, simbolos):
        dias = pd.bdate_range("2026-08-01", periods=40)
        return {s: pd.Series(np.linspace(100, 110, 40), index=dias) for s in simbolos}

    def intradiario(self, simbolos):
        utc = ZoneInfo("UTC")
        fechamento = pd.Timestamp("2026-10-20 20:00", tz=utc)  # 17h em Brasília
        depois = pd.Timestamp("2026-10-20 23:30", tz=utc)
        series = {}
        for s in simbolos:
            if s.endswith(".SA"):
                series[s] = pd.Series([50.0], index=[fechamento])
            elif s == "BRL=X":
                series[s] = pd.Series([5.0, 5.05], index=[fechamento, depois])  # dólar +1%
            else:
                series[s] = pd.Series([10.0, 10.2], index=[fechamento, depois])  # ADR +2%
        return series

    def calendario(self, simbolo):
        return {"Earnings Date": [date(2026, 10, 29)], "Ex-Dividend Date": date(2026, 8, 1)}


def test_contexto_de_mercado(tmp_path):
    fontes = FontesFalsas()
    agora = datetime(2026, 10, 21, 8, 0, tzinfo=SP)
    r = mercado.contexto(tmp_path, agora, fontes)
    selic = r["macro"]["indicadores"]["selic"]
    assert selic["valor"] == 13.75 and selic["data"] == "2026-10-21"  # ignora 04/11 (futuro)
    assert selic["desde"] == "2026-09-17" and selic["anterior"] == 14.0
    assert "ipca_12m" not in r["macro"]["indicadores"] and r["macro"]["avisos"]
    item = r["nova_york"]["itens"][0]
    assert item["implicita"] == pytest.approx(1.02 * 1.01 - 1) and not item["b3_aberta"]
    tipos = [e["tipo"] for e in r["agenda"]["eventos"]]
    assert "provento" not in tipos  # data-ex no passado fica de fora
    assert tipos.count("resultado") == len(config.CARTEIRA) and "copom" in tipos
    # Dentro da validade, não consulta as fontes de novo.
    antes = fontes.chamadas
    mercado.contexto(tmp_path, agora + timedelta(minutes=5), fontes)
    assert fontes.chamadas == antes


# ---------------------------------------------------------------- alertas

REGISTRO = {"decisao": "compra", "ticker": "PETR4", "motivo": "evento positivo confirmado",
            "criterios": [{"criterio": "O evento está confirmado (não é rumor)", "ok": True}],
            "evento": {"resumo": "Produção recorde no trimestre.",
                       "origem": {"fonte": "InfoMoney", "url": "https://portal/x"}}}


def test_sem_canal_configurado_nada_e_enviado(monkeypatch):
    enviados = []
    monkeypatch.setattr(alertas, "_postar", lambda *a: enviados.append(a))
    assert alertas.enviar([REGISTRO]) == {"enviados": 0, "falhas": 0, "canais": []}
    assert enviados == []


def test_ntfy_em_json_com_acentos_e_telegram(monkeypatch):
    enviados = []
    monkeypatch.setattr(alertas, "_postar", lambda url, corpo, cab: enviados.append((url, json.loads(corpo))))
    monkeypatch.setenv("QUANT_NTFY_TOPICO", "quant-teste-xyz")
    monkeypatch.setenv("QUANT_TELEGRAM_TOKEN", "123:abc")
    monkeypatch.setenv("QUANT_TELEGRAM_CHAT", "42")
    assert alertas.enviar([REGISTRO])["enviados"] == 2
    (url_ntfy, ntfy), (url_tg, tg) = enviados
    assert url_ntfy == "https://ntfy.sh" and ntfy["topic"] == "quant-teste-xyz"
    assert ntfy["title"] == "QUANT: COMPRA PETR4 (Petrobras)" and ntfy["click"] == "https://portal/x"
    assert "✓ O evento está confirmado" in ntfy["message"]
    assert url_tg.endswith("/bot123:abc/sendMessage") and tg["chat_id"] == "42"


def test_falha_no_alerta_nao_vaza_o_token(monkeypatch, caplog):
    def falha(url, corpo, cab):
        raise OSError(f"erro em {url}")
    monkeypatch.setattr(alertas, "_postar", falha)
    monkeypatch.setenv("QUANT_TELEGRAM_TOKEN", "123:segredo")
    monkeypatch.setenv("QUANT_TELEGRAM_CHAT", "42")
    assert alertas.enviar([REGISTRO]) == {"enviados": 0, "falhas": 1, "canais": ["telegram"]}
    assert "segredo" not in caplog.text
