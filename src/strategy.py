"""Regra de decisão determinística: única fonte de compra e venda do sistema.

Nenhuma chamada a LLM ou a rede. Mesma entrada, mesma saída.

Regra (V1):
- COMPRA: evento confirmado, classificado como positivo com probabilidade
  estritamente acima de LIMIAR_PROBABILIDADE, e nenhum evento negativo do
  mesmo ticker nos JANELA_EVENTO_RECENTE_DIAS dias corridos anteriores.
- VENDA: espelho da compra (negativo, sem positivo recente). Sem venda a
  descoberto: no backtest, VENDA só zera posição existente.
- MANTER: todos os outros casos.
"""

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

from src import config

VERSAO_REGRA = "REGRA_V1"

COMPRA, VENDA, MANTER = "compra", "venda", "manter"


@dataclass(frozen=True)
class Decisao:
    ticker: str
    decisao: str
    motivo: str
    fracao_alvo: float  # fração do patrimônio a alocar na compra (0 nos demais)
    versao_regra: str = VERSAO_REGRA

    def como_dict(self) -> dict:
        return asdict(self)


def _instante(evento: dict) -> datetime | None:
    valor = (evento.get("origem") or {}).get("timestamp_publicacao") or evento.get("timestamp_publicacao")
    return datetime.fromisoformat(valor) if valor else None


def _oposto_recente(evento: dict, historico: list[dict], sentimento_oposto: str,
                    janela_dias: int) -> bool:
    """Há evento do mesmo ticker, com o sentimento oposto, na janela anterior ao evento?"""
    agora = _instante(evento)
    if agora is None:
        return False
    inicio = agora - timedelta(days=janela_dias)
    for anterior in historico:
        if anterior.get("ticker") != evento["ticker"]:
            continue
        classificacao = anterior.get("classificacao") or {}
        quando = _instante(anterior)
        if (classificacao.get("sentimento") == sentimento_oposto
                and quando is not None and inicio <= quando < agora):
            return True
    return False


def decidir(
    evento: dict,
    classificacao: dict | None,
    historico: list[dict] | None = None,
    limiar: float | None = None,
    max_posicao: float | None = None,
    janela_dias: int | None = None,
) -> Decisao:
    """Decide compra, venda ou manter para um evento classificado.

    `historico`: eventos anteriores já classificados (cada um com a chave
    "classificacao"), usados para o filtro de evento oposto recente.
    Parâmetros opcionais existem só para testes; o padrão vem de config.py.
    """
    limiar = config.LIMIAR_PROBABILIDADE if limiar is None else limiar
    max_posicao = config.MAX_POSICAO_PCT if max_posicao is None else max_posicao
    janela_dias = config.JANELA_EVENTO_RECENTE_DIAS if janela_dias is None else janela_dias
    historico = historico or []
    ticker = evento["ticker"]

    def manter(motivo: str) -> Decisao:
        return Decisao(ticker, MANTER, motivo, 0.0)

    if classificacao is None:
        return manter("evento sem classificação válida")
    if not evento.get("confirmado"):
        return manter("evento não confirmado (rumor ou expectativa)")
    sentimento = classificacao["sentimento"]
    probabilidade = classificacao["probabilidade"]
    if sentimento == "neutro":
        return manter("sentimento neutro")
    if probabilidade <= limiar:
        return manter(f"probabilidade {probabilidade:.2f} não supera o limiar {limiar:.2f}")

    if sentimento == "positivo":
        if _oposto_recente(evento, historico, "negativo", janela_dias):
            return manter(f"positivo, mas houve evento negativo de {ticker} nos últimos {janela_dias} dias")
        return Decisao(ticker, COMPRA,
                       f"evento positivo confirmado ({evento['tipo_evento']}) com probabilidade "
                       f"{probabilidade:.2f} > {limiar:.2f} e sem evento negativo recente",
                       max_posicao)

    if _oposto_recente(evento, historico, "positivo", janela_dias):
        return manter(f"negativo, mas houve evento positivo de {ticker} nos últimos {janela_dias} dias")
    return Decisao(ticker, VENDA,
                   f"evento negativo confirmado ({evento['tipo_evento']}) com probabilidade "
                   f"{probabilidade:.2f} > {limiar:.2f} e sem evento positivo recente",
                   0.0)
