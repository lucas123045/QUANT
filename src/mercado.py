"""Contexto de mercado para quem decide: macro, commodities, Nova York e agenda.

Nada daqui entra na regra: é o painel que um gestor olha antes de agir.

- Macro (Banco Central, SGS): meta Selic (e desde quando), IPCA em 12 meses,
  dólar PTAX. A série da Selic traz datas FUTURAS (repete a meta até a próxima
  reunião): vale o último valor até hoje. O SGS às vezes recusa consultas (o
  firewall do BC responde com uma página HTML): cada indicador tem uma fonte
  alternativa oficial (histórico do Copom no site do BC, IPCA no IBGE/SIDRA,
  PTAX na API Olinda do BC) e, se tudo falhar, o último valor bom, com a data
  em que foi lido (arquivo macro_ultimo.json, guardado também na nuvem).
- Commodities e câmbio (yfinance): Brent, minério de ferro, dólar à vista.
  Em PETR4 e VALE3, o preço da commodity pesa mais que quase qualquer notícia.
- Sinal de Nova York: PETR4, VALE3, ITUB4, BBDC4 e ABEV3 têm ADRs na NYSE, que
  seguem negociando depois que a B3 fecha (inclusive no pré e no pós-mercado).
  Em reais, o ADR vale ADR(US$) x dólar, então a variação implícita para a ação
  local desde o último negócio na B3 é:
      (1 + variação do ADR) x (1 + variação do dólar) - 1,
  as duas medidas a partir do horário do último negócio da ação na B3. A
  proporção de ações por ADR não importa (é uma variação). Só tem sentido com a
  B3 fechada; aberta, o preço local já diz tudo.
- Agenda: reuniões do Copom (config.COPOM_2026) e, do Yahoo, datas de resultado
  e de data-ex de proventos (podem mudar; confira no RI da empresa).

Cada parte falha sozinha: fonte fora do ar vira aviso, nunca erro da página.
"""

import json
import logging
import math
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src import config, rede

logger = logging.getLogger(__name__)
FUSO = ZoneInfo(config.FUSO_REFERENCIA)
URL_SGS = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie}/dados?formato=json&dataInicial={inicio}"
URL_COPOM = "https://www.bcb.gov.br/api/servico/sitebcb/historicotaxasjuros"
URL_SIDRA_IPCA = "https://apisidra.ibge.gov.br/values/t/1737/n1/all/v/2265/p/last%201?formato=json"
URL_PTAX = ("https://olinda.bcb.gov.br/olinda/servico/PTAX/versao/v1/odata/CotacaoDolarPeriodo("
            "dataInicial=@i,dataFinalCotacao=@f)?@i='{inicio}'&@f='{fim}'&$format=json&$select=cotacaoVenda,dataHoraCotacao")
ARQUIVO_ULTIMO = "macro_ultimo.json"  # fora de mercado/ (que não vai para o ramo "dados")
VALIDADE_MINUTOS = 15
# Último negócio na B3 há menos que isto: pregão em andamento, sinal de NY não se aplica.
PREGAO_EM_ANDAMENTO = timedelta(minutes=20)


class Fontes:
    """Acesso às fontes externas (os testes trocam por uma versão falsa, sem rede)."""

    def sgs(self, serie: int, inicio: date) -> list[dict]:
        url = URL_SGS.format(serie=serie, inicio=inicio.strftime("%d/%m/%Y"))
        ultimo_erro = None
        for _ in range(2):  # a API do BC às vezes demora: uma nova tentativa resolve quase sempre
            try:
                return json.loads(rede.baixar(url, 20, "quant-academico/1.0"))
            except Exception as erro:  # noqa: BLE001
                ultimo_erro = erro
        raise ultimo_erro

    def json(self, url: str):
        return json.loads(rede.baixar(url, 20, "quant-academico/1.0"))

    def diario(self, simbolos: list[str]) -> dict[str, pd.Series]:
        import yfinance  # import local: testes não usam rede

        dados = yfinance.download(simbolos, period="3mo", interval="1d", auto_adjust=False,
                                  group_by="ticker", progress=False, threads=False)
        return {s: dados[s]["Close"].dropna() for s in simbolos if s in dados.columns.get_level_values(0)}

    def intradiario(self, simbolos: list[str]) -> dict[str, pd.Series]:
        import yfinance

        dados = yfinance.download(simbolos, period="5d", interval="5m", prepost=True, auto_adjust=False,
                                  group_by="ticker", progress=False, threads=False)
        return {s: dados[s]["Close"].dropna() for s in simbolos if s in dados.columns.get_level_values(0)}

    def calendario(self, simbolo: str) -> dict:
        import yfinance

        return yfinance.Ticker(simbolo).calendar or {}


def _numero(valor) -> float | None:
    try:
        numero = float(str(valor).replace(",", "."))
    except (TypeError, ValueError):
        return None
    return numero if math.isfinite(numero) else None


def _serie_sgs(bruto: list[dict], hoje: date) -> list[tuple[date, float]]:
    pontos = []
    for item in bruto:
        try:
            dia = datetime.strptime(item["data"], "%d/%m/%Y").date()
        except (KeyError, ValueError):
            continue
        valor = _numero(item.get("valor"))
        if valor is not None and dia <= hoje:  # a meta Selic vem com datas futuras
            pontos.append((dia, valor))
    return sorted(pontos)


def _data_iso(texto: str) -> date:
    """'2026-09-17T03:00:00Z' (meia-noite de Brasília em UTC) -> 2026-09-17."""
    return datetime.fromisoformat(texto.replace("Z", "+00:00")).astimezone(FUSO).date()


def _selic_copom(fontes: Fontes, hoje: date) -> dict:
    """Meta Selic pelo histórico das reuniões do Copom (site do Banco Central)."""
    reunioes = [r for r in fontes.json(URL_COPOM)["conteudo"]
                if r.get("MetaSelic") is not None and r.get("DataInicioVigencia")
                and _data_iso(r["DataInicioVigencia"]) <= hoje]
    reunioes.sort(key=lambda r: r["DataInicioVigencia"], reverse=True)
    atual = reunioes[0]
    anterior = next((r["MetaSelic"] for r in reunioes[1:] if r["MetaSelic"] != atual["MetaSelic"]), None)
    return {"valor": float(atual["MetaSelic"]), "data": hoje.isoformat(),
            "desde": _data_iso(atual["DataInicioVigencia"]).isoformat(),
            "anterior": float(anterior) if anterior is not None else None,
            "fonte": "Banco Central (histórico do Copom)"}


def _ipca_sidra(fontes: Fontes, hoje: date) -> dict:
    """IPCA acumulado em 12 meses pelo IBGE (SIDRA, tabela 1737, variável 2265)."""
    linha = fontes.json(URL_SIDRA_IPCA)[-1]
    periodo = linha["D3C"]  # AAAAMM
    return {"valor": float(linha["V"]), "data": f"{periodo[:4]}-{periodo[4:]}-01", "fonte": "IBGE (SIDRA)"}


def _ptax_olinda(fontes: Fontes, hoje: date) -> dict:
    """Dólar PTAX de venda pela API Olinda do Banco Central (com a variação em 30 dias)."""
    url = URL_PTAX.format(inicio=(hoje - timedelta(days=45)).strftime("%m-%d-%Y"), fim=hoje.strftime("%m-%d-%Y"))
    pontos = sorted((date.fromisoformat(v["dataHoraCotacao"][:10]), float(v["cotacaoVenda"]))
                    for v in fontes.json(url)["value"])
    dia, valor = pontos[-1]
    mes_atras = [v for d, v in pontos if d <= dia - timedelta(days=30)]
    return {"valor": valor, "data": dia.isoformat(), "variacao_30d": valor / mes_atras[-1] - 1 if mes_atras else None,
            "fonte": "Banco Central (PTAX, Olinda)"}


ALTERNATIVAS = {"selic": _selic_copom, "ipca_12m": _ipca_sidra, "dolar_ptax": _ptax_olinda}
NOMES = {"selic": "Selic", "ipca_12m": "IPCA", "dolar_ptax": "dólar PTAX"}


def _pelo_sgs(fontes: Fontes, chave: str, serie: int, hoje: date) -> dict:
    inicio = hoje - timedelta(days=500 if chave == "ipca_12m" else 400)
    pontos = _serie_sgs(fontes.sgs(serie, inicio), hoje)
    if not pontos:
        raise ValueError("série sem dados")
    dia, valor = pontos[-1]
    item = {"valor": valor, "data": dia.isoformat(), "serie_sgs": serie, "fonte": "Banco Central (SGS)"}
    if chave == "selic":
        desde = dia
        for d, v in reversed(pontos):
            if v != valor:
                break
            desde = d
        item["desde"] = desde.isoformat()
        anteriores = [v for d, v in pontos if d < desde]
        item["anterior"] = anteriores[-1] if anteriores else None
    if chave == "dolar_ptax":
        mes_atras = [v for d, v in pontos if d <= dia - timedelta(days=30)]
        item["variacao_30d"] = valor / mes_atras[-1] - 1 if mes_atras else None
    return item


def macro(fontes: Fontes, hoje: date, ultimos: dict | None = None) -> dict:
    """Cada indicador: SGS; se falhar, a fonte alternativa oficial; se falhar, o último valor bom."""
    resultado, avisos = {}, []
    ultimos = ultimos or {}
    for chave, serie in config.SERIES_BCB.items():
        tentativas = [lambda: _pelo_sgs(fontes, chave, serie, hoje), lambda: ALTERNATIVAS[chave](fontes, hoje)]
        for tentar in tentativas:
            try:
                resultado[chave] = tentar()
                break
            except Exception:  # noqa: BLE001 - a próxima fonte resolve
                continue
        if chave in resultado:
            continue
        if chave in ultimos:
            resultado[chave] = {**ultimos[chave], "desatualizado": True}
            avisos.append(f"{NOMES[chave]}: fontes sem resposta agora; valor da última leitura "
                          f"({ultimos[chave].get('lido_em', '?')[:10]})")
        else:
            avisos.append(f"{NOMES[chave]}: Banco Central e fonte alternativa sem resposta")
    return {"indicadores": resultado, "avisos": avisos}


def _variacoes(serie: pd.Series) -> dict:
    serie = serie.dropna()
    if serie.empty:
        return {"valor": None}
    ultimo = float(serie.iloc[-1])
    return {"valor": ultimo, "data": pd.Timestamp(serie.index[-1]).date().isoformat(),
            "variacao_dia": float(ultimo / serie.iloc[-2] - 1) if len(serie) > 1 else None,
            "variacao_30d": float(ultimo / serie.iloc[-22] - 1) if len(serie) > 22 else None}


def commodities(fontes: Fontes) -> dict:
    simbolos = {**config.COMMODITIES, "dolar": "BRL=X"}
    try:
        dados = fontes.diario(list(simbolos.values()))
    except Exception as erro:  # noqa: BLE001
        return {"itens": {}, "avisos": [f"Yahoo Finance não respondeu ({type(erro).__name__})"]}
    itens = {nome: {"simbolo": s, **_variacoes(dados.get(s, pd.Series(dtype=float)))} for nome, s in simbolos.items()}
    return {"itens": itens, "avisos": [f"{n}: sem cotação" for n, i in itens.items() if i["valor"] is None]}


def _ate(serie: pd.Series, instante) -> float | None:
    anteriores = serie[serie.index <= instante]
    return float(anteriores.iloc[-1]) if len(anteriores) else None


def sinal_nova_york(fontes: Fontes, agora: datetime) -> dict:
    """Variação implícita para cada ação local desde o último negócio na B3 (ver o módulo)."""
    simbolos = [t + config.SUFIXO_B3 for t in config.CARTEIRA] + list(config.ADRS.values()) + ["BRL=X"]
    try:
        dados = fontes.intradiario(simbolos)
    except Exception as erro:  # noqa: BLE001
        return {"itens": [], "avisos": [f"Yahoo Finance (intradiário) não respondeu ({type(erro).__name__})"]}
    cambio = dados.get("BRL=X", pd.Series(dtype=float))
    itens, avisos = [], []
    for ticker, adr in config.ADRS.items():
        local, serie_adr = dados.get(ticker + config.SUFIXO_B3), dados.get(adr)
        if local is None or local.empty or serie_adr is None or serie_adr.empty or cambio.empty:
            avisos.append(f"{ticker}: sem cotação intradiária de {ticker} ou de {adr}")
            continue
        fechamento_b3 = local.index[-1]
        adr_ref, adr_agora = _ate(serie_adr, fechamento_b3), float(serie_adr.iloc[-1])
        fx_ref, fx_agora = _ate(cambio, fechamento_b3), float(cambio.iloc[-1])
        b3_aberta = pd.Timestamp(agora) - fechamento_b3 < PREGAO_EM_ANDAMENTO
        item = {"ticker": ticker, "adr": adr, "preco_local": float(local.iloc[-1]),
                "ultimo_negocio_b3": fechamento_b3.isoformat(), "adr_atualizado": serie_adr.index[-1].isoformat(),
                "b3_aberta": bool(b3_aberta), "variacao_adr": None, "variacao_dolar": None, "implicita": None}
        if adr_ref and fx_ref and serie_adr.index[-1] > fechamento_b3:
            item["variacao_adr"] = adr_agora / adr_ref - 1
            item["variacao_dolar"] = fx_agora / fx_ref - 1
            item["implicita"] = (1 + item["variacao_adr"]) * (1 + item["variacao_dolar"]) - 1
            item["preco_implicito"] = item["preco_local"] * (1 + item["implicita"])
        itens.append(item)
    return {"itens": itens, "avisos": avisos}


def _datas(valor) -> list[date]:
    if valor is None:
        return []
    lista = valor if isinstance(valor, (list, tuple)) else [valor]
    datas = []
    for v in lista:
        try:
            datas.append(pd.Timestamp(v).date())
        except (TypeError, ValueError):
            continue
    return datas


def agenda(fontes: Fontes, hoje: date) -> dict:
    eventos = [{"data": d, "tipo": "copom", "titulo": "Decisão do Copom (juros)", "ticker": None,
                "fonte": "Banco Central (calendário 2026)"}
               for d in config.COPOM_2026 if date.fromisoformat(d) >= hoje]
    avisos = []
    for ticker in config.CARTEIRA:
        try:
            cal = fontes.calendario(ticker + config.SUFIXO_B3)
        except Exception as erro:  # noqa: BLE001
            avisos.append(f"{ticker}: calendário indisponível ({type(erro).__name__})")
            continue
        for d in _datas(cal.get("Earnings Date")):
            if d >= hoje:
                eventos.append({"data": d.isoformat(), "tipo": "resultado", "ticker": ticker,
                                "titulo": f"Resultado trimestral de {config.NOMES_EMPRESAS[ticker]}",
                                "fonte": "Yahoo Finance (estimada; confira no RI)"})
        for d in _datas(cal.get("Ex-Dividend Date")):
            if d >= hoje:
                eventos.append({"data": d.isoformat(), "tipo": "provento", "ticker": ticker,
                                "titulo": f"{config.NOMES_EMPRESAS[ticker]}: data-ex de proventos",
                                "fonte": "Yahoo Finance (confira no RI)"})
    return {"eventos": sorted(eventos, key=lambda e: e["data"]), "avisos": avisos}


def contexto(dir_data: Path | None = None, agora: datetime | None = None, fontes: Fontes | None = None,
             forcar: bool = False) -> dict:
    """Painel completo, com cache de alguns minutos (cada abertura da página não refaz tudo)."""
    dir_data = Path(dir_data or config.DIR_DATA)
    agora = (agora or datetime.now(FUSO)).astimezone(FUSO)
    caminho = dir_data / "mercado" / "contexto.json"
    if caminho.exists() and not forcar:
        try:
            guardado = json.loads(caminho.read_text(encoding="utf-8"))
            if agora - datetime.fromisoformat(guardado["gerado_em"]) < timedelta(minutes=VALIDADE_MINUTOS):
                return guardado
        except (ValueError, KeyError):
            pass
    fontes = fontes or Fontes()
    arquivo_ultimo = dir_data / ARQUIVO_ULTIMO
    try:
        ultimos = json.loads(arquivo_ultimo.read_text(encoding="utf-8")) if arquivo_ultimo.exists() else {}
    except ValueError:
        ultimos = {}
    painel_macro = macro(fontes, agora.date(), ultimos)
    novos = {k: {**v, "lido_em": agora.isoformat()} for k, v in painel_macro["indicadores"].items()
             if not v.get("desatualizado")}
    if novos:
        arquivo_ultimo.write_text(json.dumps({**ultimos, **novos}, ensure_ascii=False), encoding="utf-8")
    resultado = {"gerado_em": agora.isoformat(), "macro": painel_macro,
                 "commodities": commodities(fontes), "nova_york": sinal_nova_york(fontes, agora),
                 "agenda": agenda(fontes, agora.date())}
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(resultado, ensure_ascii=False, default=str), encoding="utf-8")
    return resultado
