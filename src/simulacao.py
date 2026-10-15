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
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src import auditoria, backtest, config
from src.baselines import sinais_baseline_1
from src.strategy import COMPRA

FUSO = ZoneInfo(config.FUSO_REFERENCIA)
# Antes deste horário, o "fechamento" de hoje ainda é um preço parcial.
HORARIO_FECHAMENTO_CONFIAVEL = time(18, 30)


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


def calcular(dir_data: Path | None = None, agora: datetime | None = None,
             baixar=None, capital: float | None = None) -> dict:
    """Estado da carteira simulada até o último fechamento confiável."""
    dir_data = Path(dir_data or config.DIR_DATA)
    agora = (agora or datetime.now(FUSO)).astimezone(FUSO)
    capital = config.CAPITAL_INICIAL if capital is None else capital

    sinais = [s for s in sinais_do_log(dir_data) if s["tipo_fonte"] == "noticia"]
    eventos = [e for e in eventos_classificados(dir_data)
               if backtest.tipo_fonte_do_evento(e) == "noticia"]
    sinais_b1 = sinais_baseline_1(eventos)

    base = {
        "capital_inicial": capital,
        "congelada": config.DATA_CONGELAMENTO is not None,
        "aviso": ("Simulação com dinheiro fictício e preços reais. Não é recomendação de investimento. "
                  + ("Regra congelada: resultado prospectivo válido."
                     if config.DATA_CONGELAMENTO else
                     "A regra ainda não foi congelada: resultado exploratório, não substitui o período de teste.")),
        "custo_por_operacao": backtest.custo_total(),
    }
    inicio = _inicio(dir_data, sinais)
    if inicio is None:
        return {**base, "estado": "sem_dados", "mensagem": "Ainda não há execuções do pipeline."}

    precos = backtest.carregar_precos(inicio.isoformat(), agora.date().isoformat(),
                                      pasta=dir_data / "simulacao" / "precos", baixar=baixar)
    precos = _sem_preco_parcial(precos.dropna(how="all"), agora)
    pendentes = [{"ticker": s["ticker"], "decisao": s["decisao"], "publicado": s["instante"],
                  "origem": s["meta"]}
                 for s in sinais if not len(precos) or backtest.proximo_pregao(s["instante"], precos.index) is None]

    if len(precos) < 1:
        return {**base, "estado": "aguardando_pregao", "inicio": inicio.isoformat(),
                "pendentes": pendentes,
                "mensagem": "Ainda não há fechamento de pregão desde o início da simulação."}

    resultado = {**base, "estado": "ok", "inicio": inicio.isoformat(),
                 "ultimo_fechamento": precos.index[-1].date().isoformat(), "pendentes": pendentes}

    simulacoes = {}
    for nome, lista in (("estrategia", sinais), ("baseline_1", sinais_b1)):
        ordens = backtest.sinais_para_ordens(lista, precos.index)
        simulacoes[nome] = backtest.simular(ordens, precos, capital)
    ibov = backtest.comprar_e_segurar(precos[config.BENCHMARK], capital)

    resultado["serie"] = [
        {"data": d.date().isoformat(),
         "estrategia": float(simulacoes["estrategia"].patrimonio.at[d]),
         "baseline_1": float(simulacoes["baseline_1"].patrimonio.at[d]),
         "ibovespa": float(ibov.at[d]) if d in ibov.index else None}
        for d in precos.index
    ]
    resultado["carteiras"] = {}
    for nome, sim in simulacoes.items():
        metricas = backtest.calcular_metricas(sim.patrimonio, sim.operacoes, sim.exposicao)
        resultado["carteiras"][nome] = {
            "patrimonio": float(sim.patrimonio.iloc[-1]),
            "caixa_investido_pct": float(sim.exposicao.iloc[-1]),
            **{k: metricas[k] for k in ("retorno_acumulado", "drawdown_maximo", "n_operacoes",
                                        "taxa_acerto", "exposicao_media")},
        }
    metricas_ibov = backtest.calcular_metricas(ibov)
    resultado["carteiras"]["ibovespa"] = {
        "patrimonio": float(ibov.iloc[-1]), "caixa_investido_pct": 1.0,
        "retorno_acumulado": metricas_ibov["retorno_acumulado"],
        "drawdown_maximo": metricas_ibov["drawdown_maximo"],
        "n_operacoes": None, "taxa_acerto": None, "exposicao_media": 1.0,
    }

    operacoes = [_posicao(op, precos) for op in simulacoes["estrategia"].operacoes]
    resultado["posicoes_abertas"] = [o for o in operacoes if o["aberta"]]
    resultado["operacoes_encerradas"] = [o for o in operacoes if not o["aberta"]]
    resultado["ordens_ignoradas"] = [
        {"ticker": i["ticker"], "decisao": i["decisao"], "razao": i["razao"],
         "data": pd.Timestamp(i["data_execucao"]).date().isoformat(), "origem": i.get("meta")}
        for i in simulacoes["estrategia"].ignoradas
    ]
    return resultado
