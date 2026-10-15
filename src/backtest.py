"""Backtest contra o Ibovespa e cálculo de métricas.

Convenções:
- Preços: DataFrame com índice de pregões (datas sem fuso) e uma coluna por
  ticker da carteira (sem sufixo) e pelo benchmark (^BVSP).
- Execução: sinal publicado no dia D (fuso de referência) é executado no
  fechamento do primeiro pregão estritamente posterior a D.
- Tamanho: compra aloca até `fracao_alvo` (MAX_POSICAO_PCT) do patrimônio,
  limitado ao caixa. Ações fracionárias são permitidas (simplificação).
- Sem venda a descoberto: VENDA só zera posição existente.
- Custos: frações do valor negociado (config.py, zerados por padrão).
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src import config
from src.strategy import COMPRA, VENDA, decidir

logger = logging.getLogger(__name__)

FUSO = ZoneInfo(config.FUSO_REFERENCIA)


def custo_total(custos: dict | None = None) -> float:
    """Custo proporcional por operação (corretagem + emolumentos + slippage)."""
    if custos is None:
        custos = {"corretagem": config.CORRETAGEM, "emolumentos": config.EMOLUMENTOS,
                  "slippage": config.SLIPPAGE}
    return float(sum(custos.values()))


# ---------------------------------------------------------------------------
# Calendário e sinais
# ---------------------------------------------------------------------------

def data_local(instante: str | datetime) -> pd.Timestamp:
    """Data (sem hora) do instante no fuso de referência."""
    if isinstance(instante, str):
        instante = datetime.fromisoformat(instante)
    if instante.tzinfo is None:
        instante = instante.replace(tzinfo=FUSO)
    return pd.Timestamp(instante.astimezone(FUSO).date())


def proximo_pregao(instante: str | datetime, pregoes: pd.DatetimeIndex) -> pd.Timestamp | None:
    """Primeiro pregão estritamente posterior ao dia local do instante."""
    posicao = pregoes.searchsorted(data_local(instante), side="right")
    return pregoes[posicao] if posicao < len(pregoes) else None


def instante_do_evento(evento: dict) -> str | None:
    return (evento.get("origem") or {}).get("timestamp_publicacao") or evento.get("timestamp_publicacao")


def tipo_fonte_do_evento(evento: dict) -> str | None:
    return (evento.get("origem") or {}).get("tipo_fonte") or evento.get("tipo_fonte")


def sinais_da_estrategia(eventos: list[dict]) -> list[dict]:
    """Aplica `decidir` a eventos classificados, em ordem cronológica.

    Cada evento precisa de "classificacao" e da origem (timestamp e tipo_fonte).
    Devolve só os sinais de compra/venda.
    """
    ordenados = sorted(eventos, key=lambda e: instante_do_evento(e) or "")
    sinais = []
    for i, evento in enumerate(ordenados):
        decisao = decidir(evento, evento.get("classificacao"), historico=ordenados[:i])
        if decisao.decisao in (COMPRA, VENDA):
            sinais.append({
                "ticker": decisao.ticker,
                "decisao": decisao.decisao,
                "fracao_alvo": decisao.fracao_alvo,
                "instante": instante_do_evento(evento),
                "tipo_fonte": tipo_fonte_do_evento(evento),
                "motivo": decisao.motivo,
            })
    return sinais


def sinais_para_ordens(sinais: list[dict], pregoes: pd.DatetimeIndex) -> list[dict]:
    """Converte sinais (com instante de publicação) em ordens datadas por pregão."""
    ordens = []
    for sinal in sinais:
        if not sinal.get("tipo_fonte"):
            raise ValueError("sinal sem tipo_fonte: a origem de cada evento precisa ser registrada")
        if not sinal.get("instante"):
            logger.warning("Sinal sem instante de publicação ignorado: %r", sinal)
            continue
        execucao = proximo_pregao(sinal["instante"], pregoes)
        if execucao is None:
            continue  # publicado depois do último pregão disponível
        ordens.append({**sinal, "data_execucao": execucao})
    return ordens


# ---------------------------------------------------------------------------
# Simulação
# ---------------------------------------------------------------------------

@dataclass
class Simulacao:
    patrimonio: pd.Series
    operacoes: list[dict] = field(default_factory=list)   # idas e voltas
    ignoradas: list[dict] = field(default_factory=list)


def simular(
    ordens: list[dict],
    precos: pd.DataFrame,
    capital: float | None = None,
    custo: float | None = None,
) -> Simulacao:
    """Executa as ordens no fechamento de `data_execucao` e marca a carteira a mercado.

    Posições abertas no último pregão são liquidadas teoricamente no último
    fechamento (com custo) para o cálculo do retorno por operação.
    """
    capital = config.CAPITAL_INICIAL if capital is None else capital
    custo = custo_total() if custo is None else custo
    pregoes = precos.index

    por_dia: dict[pd.Timestamp, list[dict]] = {}
    for ordem in ordens:
        por_dia.setdefault(pd.Timestamp(ordem["data_execucao"]), []).append(ordem)

    caixa = capital
    posicoes: dict[str, dict] = {}
    operacoes, ignoradas, patrimonio = [], [], []

    def valor_carteira(dia) -> float:
        return caixa + sum(p["quantidade"] * precos.at[dia, t] for t, p in posicoes.items())

    for dia in pregoes:
        # Vendas antes das compras; ordem alfabética para ser determinístico.
        do_dia = sorted(por_dia.get(dia, []), key=lambda o: (o["decisao"] != VENDA, o["ticker"]))
        for ordem in do_dia:
            ticker = ordem["ticker"]
            preco = precos.at[dia, ticker] if ticker in precos.columns else float("nan")
            if pd.isna(preco):
                ignoradas.append({**ordem, "razao": "sem preço no pregão"})
                continue
            if ordem["decisao"] == VENDA:
                if ticker not in posicoes:
                    ignoradas.append({**ordem, "razao": "sem posição para vender"})
                    continue
                pos = posicoes.pop(ticker)
                recebido = pos["quantidade"] * preco * (1 - custo)
                caixa += recebido
                operacoes.append({"ticker": ticker, "entrada": pos["entrada"], "saida": dia,
                                  "investido": pos["investido"], "recebido": recebido,
                                  "retorno": recebido / pos["investido"] - 1, "aberta": False})
            else:
                if ticker in posicoes:
                    ignoradas.append({**ordem, "razao": "já posicionado"})
                    continue
                valor = min(ordem["fracao_alvo"] * valor_carteira(dia), caixa)
                if valor <= 0:
                    ignoradas.append({**ordem, "razao": "sem caixa"})
                    continue
                caixa -= valor
                posicoes[ticker] = {"quantidade": valor * (1 - custo) / preco,
                                    "entrada": dia, "investido": valor}
        patrimonio.append(valor_carteira(dia))

    if len(pregoes):
        ultimo = pregoes[-1]
        for ticker, pos in posicoes.items():
            recebido = pos["quantidade"] * precos.at[ultimo, ticker] * (1 - custo)
            operacoes.append({"ticker": ticker, "entrada": pos["entrada"], "saida": ultimo,
                              "investido": pos["investido"], "recebido": recebido,
                              "retorno": recebido / pos["investido"] - 1, "aberta": True})

    return Simulacao(pd.Series(patrimonio, index=pregoes, dtype=float), operacoes, ignoradas)


def comprar_e_segurar(serie: pd.Series, capital: float | None = None) -> pd.Series:
    """Patrimônio de comprar e segurar uma série (baseline 3: Ibovespa)."""
    capital = config.CAPITAL_INICIAL if capital is None else capital
    serie = serie.dropna()
    return capital * serie / serie.iloc[0]


# ---------------------------------------------------------------------------
# Períodos (travas)
# ---------------------------------------------------------------------------

class PeriodoPendente(RuntimeError):
    """Período ainda não aprovado pelo autor."""


class CongelamentoPendente(RuntimeError):
    """Período de teste não pode rodar antes do congelamento da regra."""


def validar_periodo(periodo: tuple[str, str] | None,
                    nome: str = "período") -> tuple[pd.Timestamp, pd.Timestamp]:
    """Converte e valida o período. Recusa `None` (pendente de aprovação)."""
    if periodo is None:
        raise PeriodoPendente(
            f"O {nome} está PENDENTE DE APROVAÇÃO (None em config.py). O backtest não roda "
            "sem período aprovado pelo autor, para evitar escolher datas olhando resultados."
        )
    inicio, fim = (pd.Timestamp(p) for p in periodo)
    if inicio > fim:
        raise ValueError(f"{nome}: início {inicio.date()} posterior ao fim {fim.date()}")
    return inicio, fim


def periodo_do_config(nome: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    """Período 'treino', 'validacao' ou 'teste' de config.py, com as travas aplicáveis."""
    periodo = {"treino": config.PERIODO_TREINO, "validacao": config.PERIODO_VALIDACAO,
               "teste": config.PERIODO_TESTE}[nome]
    validado = validar_periodo(periodo, f"período de {nome}")
    if nome == "teste" and config.DATA_CONGELAMENTO is None:
        raise CongelamentoPendente(
            "O período de teste só pode ser executado depois que DATA_CONGELAMENTO for "
            "preenchida pelo autor em config.py (regra congelada)."
        )
    return validado


# ---------------------------------------------------------------------------
# Preços (yfinance com cache em data/precos/)
# ---------------------------------------------------------------------------

def simbolo_yfinance(ticker: str) -> str:
    return ticker if ticker.startswith("^") else ticker + config.SUFIXO_B3


def _baixar_yfinance(simbolo: str, inicio: str, fim: str) -> pd.Series:
    import yfinance  # import local: testes não precisam de rede

    # `end` do yfinance é exclusivo; soma um dia para incluir a data final.
    fim_exclusivo = (pd.Timestamp(fim) + pd.Timedelta(days=1)).date().isoformat()
    dados = yfinance.download(simbolo, start=inicio, end=fim_exclusivo,
                              auto_adjust=True, progress=False)
    fechamento = dados["Close"]
    if isinstance(fechamento, pd.DataFrame):  # colunas MultiIndex nas versões novas
        fechamento = fechamento.iloc[:, 0]
    return fechamento


def carregar_precos(
    inicio: str,
    fim: str,
    tickers: list[str] | None = None,
    pasta: Path | None = None,
    baixar: Callable[[str, str, str], pd.Series] | None = None,
) -> pd.DataFrame:
    """Fechamentos ajustados (proventos incluídos) da carteira e do benchmark.

    Cada série é salva em data/precos/<simbolo>_<inicio>_<fim>.csv, com a data
    do download registrada em data/precos/downloads.jsonl. Se o CSV existe,
    não baixa de novo. O calendário de pregões é o do benchmark.
    """
    tickers = (config.CARTEIRA + [config.BENCHMARK]) if tickers is None else tickers
    pasta = Path(pasta or config.DIR_PRECOS)
    pasta.mkdir(parents=True, exist_ok=True)
    baixar = baixar or _baixar_yfinance

    series = {}
    for ticker in tickers:
        simbolo = simbolo_yfinance(ticker)
        caminho = pasta / f"{simbolo}_{inicio}_{fim}.csv"
        if caminho.exists():
            serie = pd.read_csv(caminho, index_col=0, parse_dates=True).iloc[:, 0]
        else:
            serie = baixar(simbolo, inicio, fim)
            serie.index = pd.DatetimeIndex(serie.index).tz_localize(None).normalize()
            serie.rename(ticker).to_csv(caminho)
            with open(pasta / "downloads.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"simbolo": simbolo, "inicio": inicio, "fim": fim,
                                    "arquivo": caminho.name, "fonte": "yfinance (auto_adjust=True)",
                                    "data_download": datetime.now(FUSO).isoformat()}) + "\n")
        series[ticker] = serie

    precos = pd.DataFrame(series)
    if config.BENCHMARK in precos.columns:
        precos = precos[precos[config.BENCHMARK].notna()]
    return precos.sort_index()


# ---------------------------------------------------------------------------
# Métricas e critério de decisão
# ---------------------------------------------------------------------------

def calcular_metricas(patrimonio: pd.Series, operacoes: list[dict] | None = None) -> dict:
    """Retorno acumulado, volatilidade, drawdown e estatísticas por operação."""
    retornos_diarios = patrimonio.pct_change().dropna()
    pico = patrimonio.cummax()
    volatilidade = float(retornos_diarios.std(ddof=1)) if len(retornos_diarios) > 1 else 0.0
    metricas = {
        "retorno_acumulado": float(patrimonio.iloc[-1] / patrimonio.iloc[0] - 1),
        "volatilidade_diaria": volatilidade,
        "volatilidade_anualizada": volatilidade * 252 ** 0.5,
        "drawdown_maximo": float((patrimonio / pico - 1).min()),
    }
    if operacoes is not None:
        retornos = pd.Series([op["retorno"] for op in operacoes], dtype=float)
        n = len(retornos)
        metricas.update({
            "n_operacoes": n,
            "taxa_acerto": float((retornos > 0).mean()) if n else None,
            "retorno_medio_operacao": float(retornos.mean()) if n else None,
            # Erro padrão da média: desvio-padrão amostral / raiz(n).
            "erro_padrao_operacao": float(retornos.std(ddof=1) / n ** 0.5) if n > 1 else None,
        })
    return metricas


def avaliar_criterio(estrategia: dict, baseline_1: dict, ibovespa: dict) -> dict:
    """Critério do README: superar baseline 1 e Ibovespa por mais que o erro padrão."""
    erro_padrao = estrategia.get("erro_padrao_operacao")
    dif_b1 = estrategia["retorno_acumulado"] - baseline_1["retorno_acumulado"]
    dif_ibov = estrategia["retorno_acumulado"] - ibovespa["retorno_acumulado"]
    demonstrado = erro_padrao is not None and dif_b1 > erro_padrao and dif_ibov > erro_padrao
    return {
        "diferenca_vs_baseline_1": dif_b1,
        "diferenca_vs_ibovespa": dif_ibov,
        "erro_padrao": erro_padrao,
        "sinal_demonstrado": demonstrado,
        "conclusao": "sinal demonstrado" if demonstrado else "sinal não demonstrado",
    }


def rodar_backtest(
    eventos: list[dict],
    precos: pd.DataFrame,
    periodo: tuple[str, str] | None,
    tipo_fonte: str,
    nome_periodo: str = "período",
    capital: float | None = None,
    custo: float | None = None,
) -> dict:
    """Estratégia × baseline 1 × Ibovespa em um período, para UMA fonte.

    `eventos`: eventos classificados (todo o histórico disponível; o filtro de
    evento recente só usa eventos anteriores). Só entram ordens executadas
    dentro do período. Eventos de outra fonte levantam erro (regra 8).
    Para o período de teste, obtenha o período com periodo_do_config("teste"),
    que exige DATA_CONGELAMENTO.
    """
    from src.baselines import sinais_baseline_1  # import local evita ciclo

    inicio, fim = validar_periodo(periodo, nome_periodo)
    fontes = {tipo_fonte_do_evento(e) for e in eventos}
    if fontes - {tipo_fonte}:
        raise ValueError(f"eventos de fontes misturadas {sorted(map(str, fontes))}; "
                         f"este backtest é só de '{tipo_fonte}'")
    capital = config.CAPITAL_INICIAL if capital is None else capital
    precos_periodo = precos.loc[inicio:fim]
    if len(precos_periodo) < 2:
        raise ValueError(f"{nome_periodo}: menos de dois pregões com preço")

    resultado = {
        "periodo": [inicio.date().isoformat(), fim.date().isoformat()],
        "nome_periodo": nome_periodo,
        "tipo_fonte": tipo_fonte,
        "capital_inicial": capital,
        "custo_por_operacao": custo_total() if custo is None else custo,
    }
    simulacoes = {}
    for nome, sinais in (("estrategia", sinais_da_estrategia(eventos)),
                         ("baseline_1", sinais_baseline_1(eventos))):
        ordens = sinais_para_ordens(sinais, precos_periodo.index)
        simulacoes[nome] = simular(ordens, precos_periodo, capital, custo)
        resultado[nome] = calcular_metricas(simulacoes[nome].patrimonio, simulacoes[nome].operacoes)
    resultado["ibovespa"] = calcular_metricas(
        comprar_e_segurar(precos_periodo[config.BENCHMARK], capital))
    resultado["criterio"] = avaliar_criterio(resultado["estrategia"], resultado["baseline_1"],
                                             resultado["ibovespa"])
    resultado["operacoes_estrategia"] = simulacoes["estrategia"].operacoes
    return resultado
