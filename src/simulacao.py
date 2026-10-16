"""Carteira simulada (paper trading) com dinheiro fictício e preços reais.

Segue, daqui para frente, as compras e vendas registradas no log de auditoria
(data/operacoes.jsonl), decididas pela regra determinística. A execução usa o
mesmo motor do backtest: fechamento do primeiro pregão estritamente posterior
ao dia da notícia, até MAX_POSICAO_PCT do patrimônio, custos de config.py.

Lado a lado, com o mesmo capital:
- baseline 1 (comprar toda notícia positiva, sem os filtros da regra);
- Ibovespa comprado e segurado.

É uma validação prospectiva: o futuro ainda não aconteceu quando a decisão
é registrada, então não há como ajustar nada olhando o resultado. Enquanto a
regra não estiver congelada (DATA_CONGELAMENTO), o resultado é exploratório e
não substitui o período de teste. Não é recomendação de investimento.
"""

import json
import logging
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src import auditoria, backtest, cdi, config
from src.baselines import sinais_baseline_1
from src.estatistica import teste_t_uma_amostra
from src.strategy import COMPRA

logger = logging.getLogger(__name__)

FUSO = ZoneInfo(config.FUSO_REFERENCIA)
# Antes deste horário, o "fechamento" de hoje ainda é um preço parcial.
HORARIO_FECHAMENTO_CONFIAVEL = time(18, 30)
# Dias corridos de preços antes do início, só para os minigráficos dos ativos.
DIAS_CONTEXTO = 60
# Faixas de oscilação (volatilidade anualizada) para a leitura de leigos.
LIMITES_OSCILACAO = (0.10, 0.25)
# Maturidade da simulação: (pregões, decisões) para "inicial" e "razoável".
# Referência grosseira: ~3 meses e ~6 meses de pregões, com amostra mínima.
MATURIDADE_INICIAL = (60, 10)
MATURIDADE_RAZOAVEL = (126, 30)


def _ler(caminho: Path, padrao):
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else padrao


def eventos_classificados(dir_data: Path) -> list[dict]:
    """Todos os eventos extraídos e classificados nas execuções gravadas."""
    eventos = []
    for pasta in sorted(p for p in (dir_data / "execucoes").glob("*") if p.is_dir()):
        classificacoes = _ler(pasta / "04_classificacao.json", {})
        for lista in _ler(pasta / "03_extracao.json", {}).values():
            for evento in lista:
                eventos.append({**evento, "classificacao": classificacoes.get(evento["id"])})
    return eventos


def _meta(evento: dict, motivo: str | None = None, explicacao: str | None = None) -> dict:
    origem = evento.get("origem") or {}
    return {"resumo": evento.get("resumo"), "trecho_fonte": evento.get("trecho_fonte"),
            "url": origem.get("url"), "fonte": origem.get("fonte"),
            "publicado": origem.get("timestamp_publicacao"), "motivo": motivo,
            "explicacao": explicacao}


def sinais_do_log(dir_data: Path) -> list[dict]:
    """Compras e vendas do log de auditoria, como sinais para o simulador."""
    sinais = []
    for op in auditoria.ler_operacoes(dir_data / "operacoes.jsonl"):
        evento = op["evento"]
        sinais.append({
            "ticker": op["ticker"],
            "decisao": op["decisao"],
            "fracao_alvo": config.MAX_POSICAO_PCT if op["decisao"] == COMPRA else 0.0,
            "instante": backtest.instante_do_evento(evento),
            "tipo_fonte": backtest.tipo_fonte_do_evento(evento),
            "meta": _meta(evento, op.get("motivo"), op.get("explicacao")),
        })
    return sinais


def _inicio(dir_data: Path, sinais: list[dict]) -> date | None:
    dias = [p.name for p in (dir_data / "execucoes").glob("*") if p.is_dir()]
    dias += [backtest.data_local(s["instante"]).date().isoformat() for s in sinais if s.get("instante")]
    return date.fromisoformat(min(dias)) if dias else None


def _sem_preco_parcial(precos: pd.DataFrame, agora: datetime) -> pd.DataFrame:
    hoje = pd.Timestamp(agora.date())
    if agora.time() < HORARIO_FECHAMENTO_CONFIAVEL:
        return precos[precos.index < hoje]
    return precos


def _posicao(op: dict, precos: pd.DataFrame) -> dict:
    preco_entrada = float(precos.at[op["entrada"], op["ticker"]])
    preco_saida = float(precos.at[op["saida"], op["ticker"]])
    return {
        "ticker": op["ticker"],
        "entrada": op["entrada"].date().isoformat(),
        "saida": op["saida"].date().isoformat(),
        "preco_entrada": preco_entrada,
        "preco_saida": preco_saida,
        "investido": op["investido"],
        "valor": op["recebido"],
        "resultado": op["recebido"] - op["investido"],
        "retorno": op["retorno"],
        "pregoes": int(precos.index.get_loc(op["saida"]) - precos.index.get_loc(op["entrada"])),
        "aberta": op["aberta"],
        "origem": op.get("meta"),
        "origem_saida": op.get("meta_saida"),
    }


def ultimas_decisoes(dir_data: Path) -> dict[str, dict]:
    """Última decisão da regra (inclusive MANTER) para cada ticker, com o evento."""
    por_ticker: dict[str, dict] = {}
    for pasta in sorted(p for p in (dir_data / "execucoes").glob("*") if p.is_dir()):
        for item in _ler(pasta / "05_decisoes.json", []):
            evento, decisao = item["evento"], item["decisao"]
            atual = por_ticker.get(decisao["ticker"])
            instante = backtest.instante_do_evento(evento) or ""
            if atual is None or instante >= atual["publicado"]:
                classificacao = evento.get("classificacao") or {}
                por_ticker[decisao["ticker"]] = {
                    **_meta(evento),
                    "decisao": decisao["decisao"], "motivo": decisao["motivo"],
                    "sentimento": classificacao.get("sentimento"),
                    "probabilidade": classificacao.get("probabilidade"),
                    "confirmado": evento.get("confirmado"), "tipo_evento": evento.get("tipo_evento"),
                    "publicado": instante,
                }
    return por_ticker


def _ativos(precos: pd.DataFrame, decisoes: dict, abertas: list[dict], pendentes: list[dict]) -> list[dict]:
    """Cartão de cada ação da carteira: preço, variações, minigráfico e situação."""
    ativos = []
    for ticker in config.CARTEIRA:
        serie = precos[ticker].dropna() if ticker in precos.columns else pd.Series(dtype=float)
        posicao = next((p for p in abertas if p["ticker"] == ticker), None)
        pendente = next((p for p in reversed(pendentes) if p["ticker"] == ticker), None)
        if pendente:
            situacao = f"{pendente['decisao']}_agendada"
        elif posicao:
            situacao = "na_carteira"
        else:
            situacao = "sem_posicao"
        ativo = {"ticker": ticker, "empresa": config.NOMES_EMPRESAS[ticker], "situacao": situacao,
                 "posicao": posicao, "pendente": pendente, "ultima_decisao": decisoes.get(ticker),
                 "preco": None, "variacao_dia": None, "variacao_30d": None, "minigrafico": []}
        if len(serie):
            ativo["preco"] = float(serie.iloc[-1])
            if len(serie) >= 2:
                ativo["variacao_dia"] = float(serie.iloc[-1] / serie.iloc[-2] - 1)
            janela = serie.iloc[-22:]  # ~30 dias corridos
            ativo["variacao_30d"] = float(janela.iloc[-1] / janela.iloc[0] - 1) if len(janela) >= 2 else None
            ativo["minigrafico"] = [{"data": d.date().isoformat(), "preco": float(v)} for d, v in janela.items()]
        ativos.append(ativo)
    return ativos


def _extrato(operacoes: list[dict], custo: float) -> list[dict]:
    """Movimentações da carteira simulada, da mais recente para a mais antiga."""
    linhas = []
    for o in operacoes:
        linhas.append({"data": o["entrada"], "tipo": "compra", "ticker": o["ticker"],
                       "preco": o["preco_entrada"], "valor": o["investido"],
                       "quantidade": o["investido"] * (1 - custo) / o["preco_entrada"],
                       "origem": o["origem"]})
        if not o["aberta"]:
            linhas.append({"data": o["saida"], "tipo": "venda", "ticker": o["ticker"],
                           "preco": o["preco_saida"], "valor": o["valor"],
                           "resultado": o["resultado"], "origem": o["origem_saida"]})
    return sorted(linhas, key=lambda l: (l["data"], l["tipo"] == "compra"), reverse=True)


def _historico_regra(operacoes: list[dict]) -> dict:
    """O que as decisões da regra renderam até agora (não é previsão)."""
    retornos = [o["retorno"] for o in operacoes]
    teste = teste_t_uma_amostra(retornos)
    intervalo = None
    if teste["erro_padrao"] is not None:
        intervalo = [teste["media"] - 2 * teste["erro_padrao"], teste["media"] + 2 * teste["erro_padrao"]]
    return {
        "n": len(retornos),
        "media": teste["media"],
        "intervalo_aproximado_95": intervalo,
        "taxa_acerto": sum(r > 0 for r in retornos) / len(retornos) if retornos else None,
        "melhor": max(retornos) if retornos else None,
        "pior": min(retornos) if retornos else None,
    }


def nivel_oscilacao(volatilidade_anualizada: float | None) -> str | None:
    """Classificação simples para leigos (volatilidade anualizada do patrimônio).

    Referência: o Ibovespa costuma oscilar em torno de 20% a 25% ao ano.
    """
    if volatilidade_anualizada is None:
        return None
    if volatilidade_anualizada < LIMITES_OSCILACAO[0]:
        return "baixa"
    return "média" if volatilidade_anualizada < LIMITES_OSCILACAO[1] else "alta"


def _produto(patrimonio: pd.Series, metricas: dict) -> dict:
    """Números de uma carteira apresentada como 'produto' de investimento."""
    diarios = patrimonio.pct_change().dropna()
    movimentos = diarios[diarios != 0]
    vol = metricas["volatilidade_anualizada"] if len(diarios) > 1 else None
    return {
        "patrimonio": float(patrimonio.iloc[-1]),
        "retorno_acumulado": metricas["retorno_acumulado"],
        "drawdown_maximo": metricas["drawdown_maximo"],
        "volatilidade_anualizada": vol,
        "oscilacao": nivel_oscilacao(vol),
        # Dias com variação: fração em que o patrimônio subiu (dias parados não contam).
        "dias_positivos_pct": float((movimentos > 0).mean()) if len(movimentos) else None,
    }


def maturidade(pregoes: int, decisoes: int) -> dict:
    """Quão cedo é para tirar conclusões da simulação (não é teste estatístico)."""
    if pregoes >= MATURIDADE_RAZOAVEL[0] and decisoes >= MATURIDADE_RAZOAVEL[1]:
        nivel, texto = "razoavel", ("Já há histórico razoável, mas resultado passado, mesmo real, "
                                     "não garante resultado futuro.")
    elif pregoes >= MATURIDADE_INICIAL[0] and decisoes >= MATURIDADE_INICIAL[1]:
        nivel, texto = "inicial", ("Histórico ainda curto: os números já dizem algo, mas podem mudar "
                                    "bastante com mais algumas semanas.")
    else:
        nivel, texto = "muito_cedo", ("Com tão poucos dias e decisões, lucro ou prejuízo ainda é "
                                       "quase só sorte. Continue acompanhando antes de confiar.")
    return {"pregoes": pregoes, "decisoes": decisoes, "nivel": nivel, "texto": texto,
            "meta": {"pregoes": MATURIDADE_RAZOAVEL[0], "decisoes": MATURIDADE_RAZOAVEL[1]}}


def _renda_fixa(pregoes: pd.DatetimeIndex, capital: float, dir_data: Path, baixar_cdi) -> pd.Series | None:
    """Capital aplicado a 100% do CDI desde o primeiro pregão (sem impostos nem taxas).

    É a referência que falta ao lado do Ibovespa: no Brasil, a alternativa óbvia
    às ações é a renda fixa. Fonte fora do ar: devolve None e a simulação segue
    sem esse produto (o CDI é comparação, não entra em nenhuma decisão).
    """
    try:
        taxas = cdi.carregar_cdi(pregoes[0].date(), pregoes[-1].date(),
                                 dir_data / "simulacao" / "cdi", baixar=baixar_cdi)
        if taxas.empty:
            return None
        return cdi.patrimonio_cdi(pregoes, taxas, capital)
    except Exception as erro:  # rede, BCB fora do ar, resposta inesperada
        logger.warning("CDI indisponível: %s", erro)
        return None


def calcular(dir_data: Path | None = None, agora: datetime | None = None,
             baixar=None, capital: float | None = None, baixar_cdi=None) -> dict:
    """Estado da carteira simulada até o último fechamento confiável."""
    dir_data = Path(dir_data or config.DIR_DATA)
    agora = (agora or datetime.now(FUSO)).astimezone(FUSO)
    capital = config.CAPITAL_INICIAL if capital is None else capital

    sinais = [s for s in sinais_do_log(dir_data) if s["tipo_fonte"] == "noticia"]
    eventos = [e for e in eventos_classificados(dir_data)
               if backtest.tipo_fonte_do_evento(e) == "noticia"]
    sinais_b1 = sinais_baseline_1(eventos)
    decisoes = ultimas_decisoes(dir_data)

    base = {
        "capital_inicial": capital,
        "congelada": config.DATA_CONGELAMENTO is not None,
        "aviso": ("Simulação com dinheiro fictício e preços reais. Não é recomendação de investimento. "
                  + ("Regra congelada: resultado prospectivo válido."
                     if config.DATA_CONGELAMENTO else
                     "A regra ainda não foi congelada: resultado exploratório, não substitui o período de teste.")),
        "custo_por_operacao": backtest.custo_total(),
        "parametros": {"max_posicao_pct": config.MAX_POSICAO_PCT,
                       "limiar_probabilidade": config.LIMIAR_PROBABILIDADE,
                       "janela_evento_recente_dias": config.JANELA_EVENTO_RECENTE_DIAS},
    }
    inicio = _inicio(dir_data, sinais)
    hoje = agora.date()
    # O cache de preços é por intervalo de datas: antes do fechamento confiável,
    # pedir até hoje gravaria o preço parcial no arquivo de hoje, e ele seria
    # reaproveitado como fechamento mais tarde. Por isso o pedido vai só até ontem.
    ultimo_dia = hoje if agora.time() >= HORARIO_FECHAMENTO_CONFIAVEL else hoje - timedelta(days=1)
    # Preços com contexto anterior ao início, para os minigráficos dos ativos.
    precos_todos = backtest.carregar_precos(
        ((inicio or hoje) - timedelta(days=DIAS_CONTEXTO)).isoformat(), ultimo_dia.isoformat(),
        pasta=dir_data / "simulacao" / "precos", baixar=baixar)
    precos_todos = _sem_preco_parcial(precos_todos.dropna(how="all"), agora)
    precos = precos_todos[precos_todos.index >= pd.Timestamp(inicio)] if inicio else precos_todos.iloc[0:0]

    pendentes = [{"ticker": s["ticker"], "decisao": s["decisao"], "publicado": s["instante"],
                  "origem": s["meta"]}
                 for s in sinais if not len(precos) or backtest.proximo_pregao(s["instante"], precos.index) is None]

    if inicio is None or len(precos) < 1:
        return {**base, "estado": "sem_dados" if inicio is None else "aguardando_pregao",
                "inicio": inicio.isoformat() if inicio else None, "pendentes": pendentes,
                "ativos": _ativos(precos_todos, decisoes, [], pendentes),
                "mensagem": ("Ainda não há execuções do pipeline." if inicio is None else
                             "Ainda não há fechamento de pregão desde o início da simulação.")}

    resultado = {**base, "estado": "ok", "inicio": inicio.isoformat(),
                 "ultimo_fechamento": precos.index[-1].date().isoformat(), "pendentes": pendentes}

    simulacoes = {}
    for nome, lista in (("estrategia", sinais), ("baseline_1", sinais_b1)):
        ordens = backtest.sinais_para_ordens(lista, precos.index)
        simulacoes[nome] = backtest.simular(ordens, precos, capital)
    ibov = backtest.comprar_e_segurar(precos[config.BENCHMARK], capital)
    renda_fixa = _renda_fixa(precos.index, capital, dir_data, baixar_cdi)
    if renda_fixa is None:
        resultado["cdi_indisponivel"] = ("Não foi possível obter o CDI no Banco Central agora; "
                                         "a comparação com a renda fixa aparece quando a fonte responder.")

    resultado["serie"] = [
        {"data": d.date().isoformat(),
         "estrategia": float(simulacoes["estrategia"].patrimonio.at[d]),
         "baseline_1": float(simulacoes["baseline_1"].patrimonio.at[d]),
         "ibovespa": float(ibov.at[d]) if d in ibov.index else None,
         "cdi": float(renda_fixa.at[d]) if renda_fixa is not None else None}
        for d in precos.index
    ]
    resultado["carteiras"] = {}
    for nome, sim in simulacoes.items():
        metricas = backtest.calcular_metricas(sim.patrimonio, sim.operacoes, sim.exposicao)
        resultado["carteiras"][nome] = {
            **_produto(sim.patrimonio, metricas),
            "caixa_investido_pct": float(sim.exposicao.iloc[-1]),
            **{k: metricas[k] for k in ("n_operacoes", "taxa_acerto", "exposicao_media")},
        }
    resultado["carteiras"]["ibovespa"] = {
        **_produto(ibov, backtest.calcular_metricas(ibov)),
        "caixa_investido_pct": 1.0, "n_operacoes": None, "taxa_acerto": None, "exposicao_media": 1.0,
    }
    if renda_fixa is not None:
        resultado["carteiras"]["cdi"] = {
            **_produto(renda_fixa, backtest.calcular_metricas(renda_fixa)),
            "caixa_investido_pct": 0.0, "n_operacoes": None, "taxa_acerto": None, "exposicao_media": 0.0,
        }
    n_decisoes = len(simulacoes["estrategia"].operacoes)
    resultado["maturidade"] = maturidade(len(precos), n_decisoes)

    operacoes = [_posicao(op, precos) for op in simulacoes["estrategia"].operacoes]
    resultado["posicoes_abertas"] = [o for o in operacoes if o["aberta"]]
    resultado["operacoes_encerradas"] = [o for o in operacoes if not o["aberta"]]
    patrimonio = resultado["carteiras"]["estrategia"]["patrimonio"]
    investido = sum(p["valor"] for p in resultado["posicoes_abertas"])
    resultado["alocacao"] = {
        "caixa": patrimonio - investido,
        "acoes": [{"ticker": p["ticker"], "valor": p["valor"]} for p in resultado["posicoes_abertas"]],
    }
    resultado["ativos"] = _ativos(precos_todos, decisoes, resultado["posicoes_abertas"], pendentes)
    resultado["extrato"] = _extrato(operacoes, backtest.custo_total())
    resultado["historico_regra"] = _historico_regra(operacoes)
    resultado["ordens_ignoradas"] = [
        {"ticker": i["ticker"], "decisao": i["decisao"], "razao": i["razao"],
         "data": pd.Timestamp(i["data_execucao"]).date().isoformat(), "origem": i.get("meta")}
        for i in simulacoes["estrategia"].ignoradas
    ]
    return resultado
