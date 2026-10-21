"""Estudo de evento: o preço reage às notícias que a IA classificou? Quando?

Para cada evento classificado (positivo ou negativo, que não seja só a variação
da cotação), mede o retorno ANORMAL da ação, isto é, o que ela andou além do
explicado pelo Ibovespa no mesmo dia:

    retorno anormal = r_ação - (alfa + beta * r_Ibovespa)

com alfa e beta estimados nos 120 pregões anteriores à notícia (modelo de
mercado; mínimo de 60 pregões). Somado numa janela, vira o CAR (retorno
anormal acumulado). Duas janelas, com o sinal ajustado ao sentimento (positivo:
+CAR; negativo: -CAR, para que "a favor da classificação" seja sempre positivo):

- reação: do fechamento antes do dia da notícia ao fechamento anterior à
  execução. É o que o mercado já andou antes de o QUANT poder agir;
- dia da execução: do fechamento anterior à execução ao fechamento de execução.
  Fato divulgado depois do fechamento (comum na CVM) é negociado justamente
  nesse dia, e o QUANT só compra no fim dele: é o custo do atraso;
- depois da execução: do fechamento de execução (primeiro pregão depois do dia
  da notícia, a convenção do backtest) até 1, 5 e 20 pregões à frente. É o que
  ainda havia para capturar.

Notícias do mesmo fato em vários portais (mesma ação, mesmo dia, mesmo
sentimento) contam UMA vez: senão a amostra fica inflada com observações que
não são independentes. Com poucos eventos, nada aqui é conclusivo, e a página
diz isso.

Também mede a calibração da confiança da IA (a direção prevista acertou?) e o
atraso da coleta. Não muda nenhuma decisão: é evidência para o autor.
"""

import logging
import math
import statistics
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src import archive, auditoria, backtest, config
from src.estatistica import media_com_intervalo
from src.strategy import TIPO_COTACAO, VERSAO_REGRA

logger = logging.getLogger(__name__)
FUSO = ZoneInfo(config.FUSO_REFERENCIA)

JANELA_ESTIMACAO = 120
MINIMO_ESTIMACAO = 60
HORIZONTES = (1, 5, 20)
# Abaixo disto, um grupo aparece, mas sem leitura estatística.
MINIMO_GRUPO = 10
FAIXAS_CONFIANCA = ((0.5, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0001))
HORARIO_PREGAO = (10, 17)  # aproximação: sessão regular da B3 em horário de Brasília


# ---------------------------------------------------------------------------
# Retorno anormal (também usado pela camada prática)
# ---------------------------------------------------------------------------

def retornos(precos: pd.DataFrame) -> pd.DataFrame:
    return precos.pct_change(fill_method=None)


def modelo_de_mercado(rets: pd.DataFrame, ticker: str, fim: int,
                      janela: int = JANELA_ESTIMACAO, minimo: int = MINIMO_ESTIMACAO) -> dict | None:
    """Alfa, beta e desvio do resíduo nos `janela` pregões que terminam antes da posição `fim`."""
    if ticker not in rets.columns or fim <= 0:
        return None
    trecho = rets.iloc[max(0, fim - janela):fim][[ticker, config.BENCHMARK]].dropna()
    if len(trecho) < minimo:
        return None
    r, m = trecho[ticker], trecho[config.BENCHMARK]
    variancia = float(m.var(ddof=1))
    if variancia == 0:
        return None
    beta = float(((r - r.mean()) * (m - m.mean())).sum() / (len(trecho) - 1) / variancia)
    alfa = float(r.mean() - beta * m.mean())
    residuos = r - (alfa + beta * m)
    desvio = float(residuos.std(ddof=2))
    return {"alfa": alfa, "beta": beta, "desvio": desvio, "n": len(trecho)} if desvio > 0 else None


def car(rets: pd.DataFrame, ticker: str, modelo: dict, de: int, ate: int) -> float | None:
    """Retorno anormal acumulado nos pregões das posições (de, ate]."""
    if ate <= de:
        return 0.0
    trecho = rets.iloc[de + 1:ate + 1][[ticker, config.BENCHMARK]]
    if trecho.isna().any().any():
        return None
    return float((trecho[ticker] - (modelo["alfa"] + modelo["beta"] * trecho[config.BENCHMARK])).sum())


def posicoes_do_evento(instante: str, pregoes: pd.DatetimeIndex) -> tuple[int, int, int]:
    """(último pregão antes do dia da notícia, último pregão até o dia, pregão de execução).

    As posições podem ficar fora do índice (-1 ou len): sem preço ainda.
    """
    dia = backtest.data_local(instante)
    antes = int(pregoes.searchsorted(dia, side="left")) - 1
    execucao = int(pregoes.searchsorted(dia, side="right"))
    return antes, execucao - 1, execucao


def reacao_do_mercado(ticker: str, instante: str, precos: pd.DataFrame,
                      rets: pd.DataFrame | None = None) -> dict | None:
    """O que a ação já andou (além do Ibovespa) entre a notícia e a véspera da execução.

    `z` = CAR da reação / (desvio diário do resíduo * raiz do nº de pregões).
    Notícia de fim de semana ou de feriado: nenhum pregão entre a notícia e a
    execução, z = 0 (o mercado ainda não teve como reagir).
    """
    rets = retornos(precos) if rets is None else rets
    antes, ate, _ = posicoes_do_evento(instante, precos.index)
    if antes < 0:
        return None
    modelo = modelo_de_mercado(rets, ticker, antes + 1)
    if modelo is None:
        return None
    # Pregão do dia da notícia ainda sem fechamento: mede só até o último disponível.
    incompleta = ate > len(precos.index) - 1
    ate = min(ate, len(precos.index) - 1)
    valor = car(rets, ticker, modelo, antes, ate)
    if valor is None:
        return None
    n = ate - antes
    z = valor / (modelo["desvio"] * math.sqrt(n)) if n > 0 else 0.0
    return {"car": valor, "z": z, "n_pregoes": n, "incompleta": incompleta,
            "beta": modelo["beta"], "desvio_diario": modelo["desvio"],
            "de": precos.index[antes].date().isoformat(), "ate": precos.index[ate].date().isoformat()}


def leitura_reacao(z: float, direcao: int, corte: float | None = None) -> str:
    """'a favor', 'contra' ou 'neutra' (|z| <= corte), relativa à direção da notícia."""
    corte = config.PRATICA_Z_REACAO if corte is None else corte
    assinado = z * direcao
    return "a favor" if assinado > corte else "contra" if assinado < -corte else "neutra"


# ---------------------------------------------------------------------------
# Estudo
# ---------------------------------------------------------------------------

def _candidatos(eventos: list[dict], tickers: set[str] | None = None) -> list[dict]:
    """Eventos com direção, um por (ação, dia, sentimento), em ordem cronológica.

    `tickers`: as ações aceitas (padrão: a carteira; o estudo histórico usa o universo ampliado).
    """
    tickers = set(config.CARTEIRA) if tickers is None else tickers
    vistos, lista = set(), []
    for e in sorted(eventos, key=lambda e: backtest.instante_do_evento(e) or ""):
        classificacao = e.get("classificacao") or {}
        sentimento = classificacao.get("sentimento")
        instante = backtest.instante_do_evento(e)
        if (sentimento not in ("positivo", "negativo") or not instante
                or e.get("tipo_evento") == TIPO_COTACAO or e.get("ticker") not in tickers):
            continue
        chave = (e["ticker"], backtest.data_local(instante), sentimento)
        if chave in vistos:
            continue
        vistos.add(chave)
        lista.append(e)
    return lista


def observacoes(eventos: list[dict], precos: pd.DataFrame, operados: set[str] | None = None) -> list[dict]:
    """Uma linha por evento: reação e CAR depois da execução, com o sinal da classificação."""
    rets = retornos(precos)
    operados = operados or set()
    linhas = []
    tickers = {c for c in precos.columns if c != config.BENCHMARK}
    for e in _candidatos(eventos, tickers):
        classificacao = e["classificacao"]
        direcao = 1 if classificacao["sentimento"] == "positivo" else -1
        instante = backtest.instante_do_evento(e)
        antes, _, execucao = posicoes_do_evento(instante, precos.index)
        modelo = modelo_de_mercado(rets, e["ticker"], antes + 1) if antes >= 0 else None
        linha = {
            "id": e.get("id"), "ticker": e["ticker"], "data": backtest.data_local(instante).date().isoformat(),
            "tipo_evento": e.get("tipo_evento"), "confirmado": bool(e.get("confirmado")),
            "sentimento": classificacao["sentimento"], "probabilidade": classificacao.get("probabilidade"),
            "tipo_fonte": backtest.tipo_fonte_do_evento(e), "resumo": e.get("resumo"),
            "url": (e.get("origem") or {}).get("url"), "operado": e.get("id") in operados,
            "na_carteira": e["ticker"] in config.CARTEIRA,
            "reacao": None, "reacao_z": None, "leitura_reacao": None, "dia_execucao": None,
            **{f"car_{h}": None for h in HORIZONTES},
            # Quando cada janela termina: o portão de evidência da prática só usa
            # eventos cuja janela já acabou antes do dia da decisão.
            **{f"fim_{h}": (precos.index[execucao + h].date().isoformat()
                            if 0 <= execucao and execucao + h < len(precos.index) else None) for h in HORIZONTES},
        }
        if modelo is not None:
            reacao = reacao_do_mercado(e["ticker"], instante, precos, rets)
            if reacao:
                linha["reacao"] = direcao * reacao["car"]
                linha["reacao_z"] = direcao * reacao["z"]
                linha["leitura_reacao"] = leitura_reacao(reacao["z"], direcao)
            _, ate, _ = posicoes_do_evento(instante, precos.index)
            if 0 <= ate < execucao < len(precos.index):
                valor = car(rets, e["ticker"], modelo, ate, execucao)
                linha["dia_execucao"] = None if valor is None else direcao * valor
            for h in HORIZONTES:
                if execucao + h < len(precos.index):
                    valor = car(rets, e["ticker"], modelo, execucao, execucao + h)
                    linha[f"car_{h}"] = None if valor is None else direcao * valor
        linhas.append(linha)
    return linhas


def _resumo(linhas: list[dict], nome: str) -> dict:
    """Médias com intervalo de 95% para a reação e cada horizonte."""
    resumo = {"grupo": nome, "n": len(linhas)}
    for campo in ("reacao", "dia_execucao", *(f"car_{h}" for h in HORIZONTES)):
        valores = [l[campo] for l in linhas if l[campo] is not None]
        estat = media_com_intervalo(valores)
        resumo[campo] = {"n": estat["n"], "media": estat["media"], "intervalo": estat["intervalo"],
                         "p_valor": estat["p_valor_bilateral"]}
    resumo["leitura"] = _leitura_grupo(resumo)
    return resumo


def _eventos(n: int) -> str:
    return f"{n} evento" if n == 1 else f"{n} eventos"


def _pct(valor: float, sinal: bool = True) -> str:
    """0.0123 -> "+1,23%" (formato brasileiro)."""
    return f"{valor * 100:{'+' if sinal else ''}.2f}%".replace(".", ",")


def _leitura_grupo(r: dict) -> str:
    depois = r["car_5"]
    if depois["n"] < MINIMO_GRUPO:
        return (f"Só {_eventos(depois['n'])} com 5 pregões de histórico: amostra pequena demais "
                f"para concluir (mínimo de {MINIMO_GRUPO}).")
    media = depois["media"]
    if depois["p_valor"] is not None and depois["p_valor"] < 0.05:
        sentido = "a favor" if media > 0 else "contra"
        p = f"{depois['p_valor']:.3f}".replace(".", ",")
        return (f"Depois da execução, a ação andou em média {_pct(abs(media), False)} {sentido} da "
                f"classificação em 5 pregões, além do Ibovespa (p = {p}).")
    return (f"Depois da execução, a média em 5 pregões ({_pct(media)}) não se distingue de zero: "
            "não há evidência de que ainda houvesse algo a capturar.")


def grupos(linhas: list[dict]) -> list[dict]:
    """Recortes da amostra. Um recorte vazio, ou com exatamente os mesmos eventos de
    um anterior (comum com amostra pequena), não aparece: repetiria a mesma leitura."""
    candidatos = [("Todos os eventos", linhas),
                  ("Operados pela regra", [l for l in linhas if l["operado"]]),
                  ("Fatos confirmados", [l for l in linhas if l["confirmado"]]),
                  ("Não confirmados (expectativas)", [l for l in linhas if not l["confirmado"]]),
                  ("Notícias de portal", [l for l in linhas if l["tipo_fonte"] == "noticia"]),
                  ("Fatos relevantes (CVM)", [l for l in linhas if l["tipo_fonte"] == "fato_relevante"]),
                  ("5 ações originais", [l for l in linhas if l["ticker"] in config.CARTEIRA_ORIGINAL]),
                  ("19 ações adicionadas em 21/10", [l for l in linhas if l["ticker"] not in config.CARTEIRA_ORIGINAL])]
    candidatos += [(f"Reação {r} antes da execução", [l for l in linhas if l["leitura_reacao"] == r])
                   for r in ("a favor", "neutra", "contra")]
    candidatos += [(f"Tipo: {t}", [l for l in linhas if l["tipo_evento"] == t])
                   for t in sorted({l["tipo_evento"] for l in linhas if l["tipo_evento"]})]
    lista, vistos = [], set()
    for nome, membros in candidatos:
        chave = frozenset(id(l) for l in membros)
        if nome != "Todos os eventos" and (not membros or chave in vistos):
            continue
        vistos.add(chave)
        lista.append(_resumo(membros, nome))
    return lista


def calibracao(linhas: list[dict]) -> dict:
    """A confiança declarada pela IA bate com a frequência de acerto da direção (5 pregões)?"""
    validas = [l for l in linhas if l["car_5"] is not None and l["probabilidade"] is not None]
    faixas = []
    for inicio, fim in FAIXAS_CONFIANCA:
        dentro = [l for l in validas if inicio <= l["probabilidade"] < fim]
        faixas.append({
            "faixa": [inicio, min(fim, 1.0)], "n": len(dentro),
            "confianca_media": statistics.fmean(l["probabilidade"] for l in dentro) if dentro else None,
            "taxa_acerto": sum(l["car_5"] > 0 for l in dentro) / len(dentro) if dentro else None,
        })
    brier = (statistics.fmean((l["probabilidade"] - (l["car_5"] > 0)) ** 2 for l in validas)
             if validas else None)
    return {"n": len(validas), "faixas": faixas, "brier": brier,
            "leitura": ("Amostra pequena: a calibração ainda não diz nada." if len(validas) < 30 else
                        "Compare, em cada faixa, a confiança média com a taxa de acerto: num classificador "
                        "calibrado, as duas ficam próximas.")}


def latencia(dir_arquivo: Path) -> dict:
    """Quanto tempo a notícia leva do portal ao arquivo, e quando ela sai.

    Só conta notícia publicada DEPOIS de alguma coleta anterior à que a arquivou.
    Na primeira coleta (e depois de um período com o computador desligado), o
    QUANT arquiva de uma vez o que saiu nas últimas 24 h: esse atraso é da
    agenda, não do portal, e distorceria a medida.
    """
    registros = []
    for r in archive.carregar_arquivo(dir_arquivo):
        if not r.get("tickers") or r.get("tipo_fonte") != "noticia":
            continue
        try:
            registros.append((r, datetime.fromisoformat(r["timestamp_publicacao"]).astimezone(FUSO),
                              datetime.fromisoformat(r["timestamp_coleta"]).astimezone(FUSO)))
        except (KeyError, TypeError, ValueError):
            continue
    coletas = sorted({c for _, _, c in registros})
    por_fonte: dict[str, list[float]] = {}
    no_pregao = fora = fora_da_medida = 0
    for r, publicado, coletado in registros:
        if publicado.weekday() < 5 and HORARIO_PREGAO[0] <= publicado.hour < HORARIO_PREGAO[1]:
            no_pregao += 1
        else:
            fora += 1
        anteriores = [c for c in coletas if c < coletado]
        if not anteriores or publicado < anteriores[-1] - timedelta(hours=2):
            # Acúmulo: saiu antes da coleta anterior (com 2 h de folga para o
            # portal que demora a pôr a notícia no feed) e não havia coleta antes.
            fora_da_medida += 1
            continue
        por_fonte.setdefault(r["fonte"], []).append(max(0.0, (coletado - publicado).total_seconds() / 60))

    def quantil(valores, q):
        ordenados = sorted(valores)
        return ordenados[min(len(ordenados) - 1, int(q * len(ordenados)))]

    fontes = [{"fonte": f, "n": len(v), "mediana_min": statistics.median(v), "p90_min": quantil(v, 0.9)}
              for f, v in sorted(por_fonte.items()) if v]
    total = no_pregao + fora
    intervalos = [(b - a).total_seconds() / 60 for a, b in zip(coletas, coletas[1:])]
    return {"fontes": fontes, "publicadas_no_pregao": no_pregao, "publicadas_fora": fora,
            "fracao_no_pregao": no_pregao / total if total else None,
            "fora_da_medida": fora_da_medida,
            "intervalo_mediano_coletas_min": statistics.median(intervalos) if intervalos else None,
            "nota": ("Atraso medido entre a hora de publicação no portal e a hora em que o QUANT arquivou "
                     "a notícia (a coleta roda a cada 30 minutos). O atraso do próprio portal em relação ao "
                     "fato não é observável sem a hora do fato na fonte primária.")}


def _ids_operados(dir_data: Path) -> set[str]:
    ids = set()
    for op in auditoria.ler_operacoes(dir_data / "operacoes.jsonl"):
        if auditoria.versao_regra(op) == VERSAO_REGRA:
            ids.add((op.get("evento") or {}).get("id"))
    return ids


def estudar(dir_data: Path | None = None, agora: datetime | None = None, baixar=None) -> dict:
    """Estudo completo para a base (data/ ou data/teste/)."""
    from src import simulacao  # import local: simulacao importa daqui indiretamente

    dir_data = Path(dir_data or config.DIR_DATA)
    agora = (agora or datetime.now(FUSO)).astimezone(FUSO)
    eventos = simulacao.eventos_classificados(dir_data)
    aceitos = set(config.CARTEIRA) | {t for t, _ in config.UNIVERSO_ESTUDO.values()}
    candidatos = _candidatos(eventos, aceitos)
    base = {"metodo": {"janela_estimacao": JANELA_ESTIMACAO, "minimo_estimacao": MINIMO_ESTIMACAO,
                       "horizontes": list(HORIZONTES), "minimo_grupo": MINIMO_GRUPO,
                       "corte_reacao_z": config.PRATICA_Z_REACAO},
            "latencia": latencia(dir_data / "arquivo")}
    if not candidatos:
        return {**base, "estado": "sem_eventos", "n_eventos": 0, "observacoes": [], "grupos": [],
                "calibracao": calibracao([]),
                "mensagem": "Ainda não há eventos positivos ou negativos classificados para estudar."}

    primeiro = min(backtest.data_local(backtest.instante_do_evento(e)) for e in candidatos)
    hoje = agora.date()
    ultimo_dia = hoje if agora.time() >= simulacao.HORARIO_FECHAMENTO_CONFIAVEL else hoje - timedelta(days=1)
    # ~120 pregões antes do primeiro evento para estimar o beta.
    inicio = (primeiro - pd.Timedelta(days=200)).date()
    tickers = sorted({e["ticker"] for e in candidatos})
    precos = backtest.carregar_precos(inicio.isoformat(), ultimo_dia.isoformat(), tickers + [config.BENCHMARK],
                                      pasta=dir_data / "estudos" / "precos", baixar=baixar)
    precos = simulacao._sem_preco_parcial(precos.dropna(how="all"), agora)
    linhas = observacoes(eventos, precos, _ids_operados(dir_data))
    return {**base, "estado": "ok", "n_eventos": len(linhas),
            "ultimo_fechamento": precos.index[-1].date().isoformat() if len(precos) else None,
            "observacoes": linhas, "grupos": grupos(linhas), "calibracao": calibracao(linhas),
            "leitura_atraso": _leitura_atraso(linhas)}


def _leitura_atraso(linhas: list[dict]) -> dict:
    """Do movimento a favor da notícia, quanto acontece antes da execução e quanto depois?

    Só afirma algo com significância (5%): "a média é positiva" sem isso é ruído.
    """
    validas = [l for l in linhas if l["reacao"] is not None and l["car_5"] is not None]
    if len(validas) < MINIMO_GRUPO:
        return {"n": len(validas), "texto": (f"Só {_eventos(len(validas))} com reação e 5 pregões depois: ainda "
                                             "não dá para dizer quanto do movimento chega antes do QUANT.")}
    antes = media_com_intervalo([l["reacao"] + (l["dia_execucao"] or 0.0) for l in validas])
    depois = media_com_intervalo([l["car_5"] for l in validas])
    sig = lambda r: r["p_valor_bilateral"] is not None and r["p_valor_bilateral"] < 0.05
    texto = (f"Com {_eventos(len(validas))}: até a execução (inclusive o dia dela), a ação andou em média "
             f"{_pct(antes['media'])} a favor da classificação, além do Ibovespa; nos 5 pregões seguintes, "
             f"{_pct(depois['media'])}.")
    if sig(antes) and antes["media"] > 0 and not (sig(depois) and depois["media"] > 0):
        texto += " O movimento acontece antes de o QUANT conseguir agir: a notícia chega tarde."
    elif sig(depois) and depois["media"] > 0:
        texto += " Ainda havia movimento a capturar depois da execução."
    elif not sig(antes) and not sig(depois):
        texto += (" Nenhuma das duas médias se distingue de zero: o preço não anda a favor da classificação "
                  "nem antes nem depois. O problema não é o atraso: a classificação não indica a direção.")
    return {"n": len(validas), "reacao_media": antes["media"], "depois_media": depois["media"], "texto": texto}
