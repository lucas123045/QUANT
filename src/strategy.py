"""Regra de decisão determinística: única fonte de compra e venda do sistema.

Nenhuma chamada a LLM ou a rede. Mesma entrada, mesma saída.

Regra (V3):
- COMPRA: evento que é um fato sobre a empresa (não só a variação da cotação),
  confirmado, com materialidade de pelo menos MATERIALIDADE_MINIMA, que o
  mercado ainda não negociou por um pregão inteiro, classificado como positivo
  com probabilidade estritamente acima de LIMIAR_PROBABILIDADE, que não seja a
  repetição de um fato que já gerou sinal nas JANELA_REPETICAO_HORAS anteriores,
  e sem evento negativo do mesmo ticker nos JANELA_EVENTO_RECENTE_DIAS dias
  corridos anteriores.
- VENDA: espelho da compra (negativo, sem positivo recente). Sem venda a
  descoberto: no backtest, VENDA só zera posição existente.
- MANTER: todos os outros casos.

V1 → V2 (antes do congelamento): com a V1, todas as operações reais dos primeiros
dias vieram de resumos de fechamento ("ações da Petrobras sobem 3%"). Comprar
porque a ação já subiu é seguir o preço, não reagir à notícia, e esvazia a
hipótese do trabalho. A V2 não opera evento do tipo "cotacao".

V2 → V3 (21/10/2026, antes do congelamento): no primeiro dia na nuvem, a V2
registrou 5 compras de PETR4. Quatro eram a MESMA notícia em dois portais ("a ANP
adiou uma audiência pública"), um fato confirmado e positivo, mas sem efeito
financeiro mensurável; a quinta era um fato relevante entregue à CVM 8 dias
antes. A V3 acrescenta três critérios: materialidade (o fato muda resultado,
caixa ou valor da empresa?), fato novo (o mercado já negociou um pregão inteiro
com ele?) e repetição (o mesmo fato já gerou sinal?).

Cada decisão traz também a lista de critérios conferidos (`criterios`), com o
resultado e o valor de cada um: é a justificativa passo a passo da decisão.
"""

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from src import config

VERSAO_REGRA = "REGRA_V3"
# Regras anteriores: decisões delas continuam no log, mas não guiam a carteira.
VERSOES_ANTERIORES = ("REGRA_V1", "REGRA_V2")
NIVEIS_MATERIALIDADE = {"baixa": 0, "media": 1, "alta": 2}
NOMES_MATERIALIDADE = {"baixa": "baixa", "media": "média", "alta": "alta"}
FUSO = ZoneInfo(config.FUSO_REFERENCIA)

COMPRA, VENDA, MANTER = "compra", "venda", "manter"
# Tipo de evento da notícia que só relata a variação do preço da ação.
TIPO_COTACAO = "cotacao"


@dataclass(frozen=True)
class Decisao:
    ticker: str
    decisao: str
    motivo: str
    fracao_alvo: float  # fração do patrimônio a alocar na compra (0 nos demais)
    versao_regra: str = VERSAO_REGRA
    criterios: tuple = ()  # [{criterio, ok, detalhe}]: a justificativa passo a passo

    def como_dict(self) -> dict:
        d = asdict(self)
        d["criterios"] = list(d["criterios"])
        return d


def _instante(evento: dict) -> datetime | None:
    valor = (evento.get("origem") or {}).get("timestamp_publicacao") or evento.get("timestamp_publicacao")
    return datetime.fromisoformat(valor) if valor else None


def _conhecido(evento: dict) -> datetime | None:
    """Quando o QUANT ficou sabendo do fato (hora da coleta). Eventos antigos não a guardavam."""
    valor = (evento.get("origem") or {}).get("timestamp_coleta") or evento.get("timestamp_coleta")
    return datetime.fromisoformat(valor) if valor else None


def _proximo_dia_util(dia: date) -> date:
    seguinte = dia + timedelta(days=1)
    while seguinte.weekday() >= 5:
        seguinte += timedelta(days=1)
    return seguinte


def ja_negociado(evento: dict) -> tuple[bool, datetime | None]:
    """O mercado já negociou um pregão inteiro com o fato quando o QUANT soube dele?

    Pela convenção de execução, um fato do dia D é executado no fechamento do
    primeiro pregão depois de D. Se o QUANT só soube do fato depois do início do
    leilão de fechamento desse pregão (HORA_LIMITE_EXECUCAO), a execução cairia no
    passado e o preço já reflete o fato. Feriados contam como dia útil: o erro
    possível é conservador (deixa de operar, nunca opera com informação velha).
    Devolve (já negociado?, instante limite).
    """
    publicado, conhecido = _instante(evento), _conhecido(evento)
    if publicado is None or conhecido is None:
        return False, None
    dia = publicado.astimezone(FUSO).date()
    limite = datetime.combine(_proximo_dia_util(dia), time(*config.HORA_LIMITE_EXECUCAO), FUSO)
    return conhecido.astimezone(FUSO) >= limite, limite


def materialidade_suficiente(classificacao: dict | None, minimo: str | None = None) -> bool | None:
    """Materialidade da classificação no mínimo exigido? None se não foi avaliada."""
    minimo = config.MATERIALIDADE_MINIMA if minimo is None else minimo
    valor = (classificacao or {}).get("materialidade")
    if valor not in NIVEIS_MATERIALIDADE:
        return None
    return NIVEIS_MATERIALIDADE[valor] >= NIVEIS_MATERIALIDADE[minimo]


def _gera_sinal(evento: dict, classificacao: dict | None, limiar: float, minimo: str) -> bool:
    """O evento passa por todos os critérios próprios (sem olhar o histórico)?"""
    if not classificacao or evento.get("tipo_evento") == TIPO_COTACAO or not evento.get("confirmado"):
        return False
    return (classificacao.get("sentimento") in ("positivo", "negativo")
            and classificacao.get("probabilidade", 0) > limiar
            and materialidade_suficiente(classificacao, minimo) is True
            and not ja_negociado(evento)[0])


def repeticao(evento: dict, historico: list[dict], sentimento: str, janela_horas: float,
              limiar: float, minimo: str) -> dict | None:
    """Fato anterior da mesma ação, no mesmo sentido, que já gerou sinal na janela?

    É como o QUANT reconhece o mesmo fato publicado por vários portais (ou duas
    vezes no mesmo portal): a primeira notícia decide, as outras repetem.
    """
    agora = _instante(evento)
    if agora is None:
        return None
    inicio = agora - timedelta(hours=janela_horas)
    for anterior in historico:
        classificacao = anterior.get("classificacao") or {}
        quando = _instante(anterior)
        if (anterior.get("ticker") == evento["ticker"] and classificacao.get("sentimento") == sentimento
                and quando is not None and inicio <= quando <= agora
                and _gera_sinal(anterior, classificacao, limiar, minimo)):
            return anterior
    return None


def _oposto_recente(evento: dict, historico: list[dict], sentimento_oposto: str,
                    janela_dias: int) -> bool:
    """Há fato do mesmo ticker, com o sentimento oposto, na janela anterior ao evento?

    Só conta o que a própria regra levaria em conta: evento confirmado e que não
    seja só a variação da cotação. Na V1, uma prévia de analista ("deve lucrar
    mais") ou um resumo de pregão bloqueava a reação a um fato confirmado.
    """
    agora = _instante(evento)
    if agora is None:
        return False
    inicio = agora - timedelta(days=janela_dias)
    for anterior in historico:
        if anterior.get("ticker") != evento["ticker"]:
            continue
        if not anterior.get("confirmado") or anterior.get("tipo_evento") == TIPO_COTACAO:
            continue
        classificacao = anterior.get("classificacao") or {}
        # V3: fato sem materialidade não muda o resultado da empresa, então também não
        # barra outro fato. Sem avaliação (classificação antiga), continua contando.
        if materialidade_suficiente(classificacao) is False:
            continue
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
    materialidade_minima: str | None = None,
    janela_repeticao_horas: float | None = None,
) -> Decisao:
    """Decide compra, venda ou manter para um evento classificado.

    `historico`: eventos anteriores já classificados (cada um com a chave
    "classificacao"), usados para o filtro de evento oposto recente.
    Parâmetros opcionais existem só para testes; o padrão vem de config.py.
    """
    limiar = config.LIMIAR_PROBABILIDADE if limiar is None else limiar
    max_posicao = config.MAX_POSICAO_PCT if max_posicao is None else max_posicao
    janela_dias = config.JANELA_EVENTO_RECENTE_DIAS if janela_dias is None else janela_dias
    minimo = config.MATERIALIDADE_MINIMA if materialidade_minima is None else materialidade_minima
    janela_rep = config.JANELA_REPETICAO_HORAS if janela_repeticao_horas is None else janela_repeticao_horas
    historico = historico or []
    ticker = evento["ticker"]
    lista = tuple(criterios(evento, classificacao, historico, limiar, janela_dias, minimo, janela_rep))

    def manter(motivo: str) -> Decisao:
        return Decisao(ticker, MANTER, motivo, 0.0, criterios=lista)

    if classificacao is None:
        return manter("evento sem classificação válida")
    if evento.get("tipo_evento") == TIPO_COTACAO:
        return manter("a notícia só descreve a variação da cotação: não é um fato novo sobre a empresa")
    if not evento.get("confirmado"):
        return manter("evento não confirmado (rumor ou expectativa)")
    suficiente = materialidade_suficiente(classificacao, minimo)
    if suficiente is None:
        return manter("classificação sem avaliação de materialidade (feita com um prompt anterior à REGRA_V3)")
    if not suficiente:
        return manter(f"materialidade {NOMES_MATERIALIDADE[classificacao['materialidade']]}: o fato não muda "
                      "o resultado, o caixa ou o valor da empresa de forma mensurável")
    velho, limite = ja_negociado(evento)
    if velho:
        return manter(f"fato velho: o QUANT só soube dele depois de {limite:%d/%m %H:%M}, quando o mercado "
                      "já tinha negociado um pregão inteiro com ele")
    sentimento = classificacao["sentimento"]
    probabilidade = classificacao["probabilidade"]
    if sentimento == "neutro":
        return manter("sentimento neutro")
    if probabilidade <= limiar:
        return manter(f"probabilidade {probabilidade:.2f} não supera o limiar {limiar:.2f}")
    anterior = repeticao(evento, historico, sentimento, janela_rep, limiar, minimo)
    if anterior is not None:
        fonte = (anterior.get("origem") or {}).get("fonte") or "outra fonte"
        return manter(f"repetição: o mesmo fato já gerou sinal nas {janela_rep:.0f} h anteriores ({fonte})")

    if sentimento == "positivo":
        if _oposto_recente(evento, historico, "negativo", janela_dias):
            return manter(f"positivo, mas houve evento negativo de {ticker} nos últimos {janela_dias} dias")
        return Decisao(ticker, COMPRA,
                       f"evento positivo confirmado ({evento['tipo_evento']}, materialidade "
                       f"{NOMES_MATERIALIDADE[classificacao['materialidade']]}) com probabilidade "
                       f"{probabilidade:.2f} > {limiar:.2f}, fato novo e sem evento negativo recente",
                       max_posicao, criterios=lista)

    if _oposto_recente(evento, historico, "positivo", janela_dias):
        return manter(f"negativo, mas houve evento positivo de {ticker} nos últimos {janela_dias} dias")
    return Decisao(ticker, VENDA,
                   f"evento negativo confirmado ({evento['tipo_evento']}, materialidade "
                   f"{NOMES_MATERIALIDADE[classificacao['materialidade']]}) com probabilidade "
                   f"{probabilidade:.2f} > {limiar:.2f}, fato novo e sem evento positivo recente",
                   0.0, criterios=lista)


def criterios(evento: dict, classificacao: dict | None, historico: list[dict],
              limiar: float, janela_dias: int, minimo: str | None = None,
              janela_repeticao_horas: float | None = None) -> list[dict]:
    """Cada condição da regra, conferida, com o valor que decidiu: a justificativa.

    `ok` é True (cumprida), False (barrou a operação) ou None (não se aplica).
    Todas são avaliadas, mesmo depois da primeira que falha, para a justificativa
    mostrar o quadro completo.
    """
    minimo = config.MATERIALIDADE_MINIMA if minimo is None else minimo
    janela_rep = config.JANELA_REPETICAO_HORAS if janela_repeticao_horas is None else janela_repeticao_horas
    lista = []

    def item(criterio: str, ok: bool | None, detalhe: str) -> None:
        lista.append({"criterio": criterio, "ok": ok, "detalhe": detalhe})

    item("A IA classificou o evento", classificacao is not None,
         "classificação recebida" if classificacao else "sem classificação válida")
    tipo = evento.get("tipo_evento")
    item("É um fato sobre a empresa, não só a variação da cotação", tipo != TIPO_COTACAO,
         f"tipo de evento: {tipo}")
    item("O evento está confirmado (não é rumor)", bool(evento.get("confirmado")),
         "o texto afirma que aconteceu" if evento.get("confirmado") else "rumor, expectativa ou especulação")
    velho, limite = ja_negociado(evento)
    item("Fato novo: o mercado ainda não negociou um pregão inteiro com ele", not velho,
         (f"o QUANT soube depois de {limite:%d/%m %H:%M}" if velho else
          f"o QUANT soube a tempo do pregão seguinte (antes de {limite:%d/%m %H:%M})" if limite else
          "hora da coleta não registrada"))
    if classificacao is None:
        return lista
    suficiente = materialidade_suficiente(classificacao, minimo)
    valor = classificacao.get("materialidade")
    motivo = classificacao.get("motivo_materialidade")
    item(f"Relevante para o resultado da empresa (materialidade {NOMES_MATERIALIDADE[minimo]} ou mais)",
         suficiente,
         (f"materialidade {NOMES_MATERIALIDADE[valor]}" + (f": {motivo}" if motivo else "")) if valor
         else "não avaliada (classificação anterior à REGRA_V3)")
    sentimento, probabilidade = classificacao["sentimento"], classificacao["probabilidade"]
    item("A IA vê efeito positivo ou negativo (não neutro)", sentimento != "neutro", f"sentimento: {sentimento}")
    item(f"Confiança da IA acima de {limiar:.2f}".replace(".", ","), probabilidade > limiar,
         f"confiança: {probabilidade:.2f}".replace(".", ","))
    if sentimento in ("positivo", "negativo"):
        anterior = repeticao(evento, historico, sentimento, janela_rep, limiar, minimo)
        item(f"Primeira notícia deste fato nas últimas {janela_rep:.0f} h", anterior is None,
             f"repete um fato que já gerou sinal ({(anterior.get('origem') or {}).get('fonte') or 'outra fonte'})"
             if anterior else "nenhum sinal igual nas horas anteriores")
        oposto = "negativo" if sentimento == "positivo" else "positivo"
        houve = _oposto_recente(evento, historico, oposto, janela_dias)
        item(f"Sem fato {oposto} confirmado da empresa nos {janela_dias} dias anteriores", not houve,
             f"houve fato {oposto} confirmado recente" if houve else f"nenhum fato {oposto} confirmado recente")
    else:
        item(f"Sem notícia de sentido oposto nos {janela_dias} dias anteriores", None,
             "não se aplica a sentimento neutro")
    return lista
