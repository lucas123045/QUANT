"""Carteira prática: as mesmas decisões da regra, operadas como um investidor operaria.

A carteira da pesquisa (src/simulacao.py) testa a hipótese do trabalho e por isso
é simples de propósito: custo zero, 20% por compra, sem saída além da notícia
negativa, caixa parado. Para decidir com dinheiro de verdade, faltam coisas que
mudam o resultado. Esta carteira usa os mesmos sinais (compras e vendas da regra
vigente no log de auditoria) e acrescenta, em ordem:

1. Confirmação pela reação do mercado: não compra se, antes da execução, a ação
   já reagiu com força CONTRA a notícia (o mercado leu como surpresa ruim), e
   o espelho na venda. Ver config.PRATICA_Z_REACAO.
2. Surpresa no texto: não compra se o próprio texto diz que o número veio
   abaixo do esperado (src/surpresa.py), e o espelho na venda.
3. Tamanho pelo risco: ações mais voláteis recebem menos que os 20% da regra.
4. Limite por setor (bancos).
5. Saídas por prazo (20 pregões) e por perda fora do comum (stop).
6. Custos reais da B3 e imposto de renda (src/tributacao.py).
7. Caixa rendendo 100% do CDI (como num Tesouro Selic), antes do IR da renda
   fixa, igual à referência de renda fixa da simulação.

Tudo é decidido só com informação disponível antes de cada execução. Não altera
a regra congelada nem o critério do trabalho. Não é recomendação de investimento.
"""

import logging
import math
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from src import backtest, cdi, config, estudo_evento, risco, simulacao, surpresa, tributacao
from src.estatistica import quantil_t
from src.strategy import COMPRA, VENDA

logger = logging.getLogger(__name__)
FUSO = ZoneInfo(config.FUSO_REFERENCIA)
# Histórico antes do início: volatilidade (60 pregões) e beta do estudo de evento (120).
DIAS_HISTORICO = 200
PESO_MINIMO = 0.01  # abaixo de 1% do patrimônio, não vale a operação


def custo_por_lado() -> float:
    return config.PRATICA_EMOLUMENTOS + config.PRATICA_CORRETAGEM + config.PRATICA_SLIPPAGE


def volatilidade_diaria(rets: pd.Series, ate: int, janela: int | None = None) -> float | None:
    """Desvio dos retornos diários nos `janela` pregões antes da posição `ate` (exclusive)."""
    janela = config.PRATICA_JANELA_VOL_PREGOES if janela is None else janela
    trecho = rets.iloc[max(0, ate - janela):ate].dropna()
    return float(trecho.std(ddof=1)) if len(trecho) >= 20 else None


def peso_pelo_risco(vol_diaria: float | None) -> tuple[float, str]:
    """Fração do patrimônio e a explicação (até MAX_POSICAO_PCT, menos se a ação oscila mais)."""
    maximo = config.MAX_POSICAO_PCT
    if vol_diaria is None:
        return maximo, "volatilidade sem histórico suficiente: usado o tamanho da regra"
    anual = vol_diaria * math.sqrt(252)
    peso = maximo * min(1.0, config.PRATICA_VOL_REFERENCIA_ANUAL / anual)
    return peso, (f"oscila {anual * 100:.0f}% ao ano (referência {config.PRATICA_VOL_REFERENCIA_ANUAL * 100:.0f}%): "
                  f"{peso * 100:.1f}% do patrimônio").replace(".", ",")


def _item(criterio: str, ok: bool | None, detalhe: str) -> dict:
    return {"criterio": criterio, "ok": ok, "detalhe": detalhe}


def _pct(valor: float) -> str:
    return f"{valor * 100:.1f}%".replace(".", ",")


def _z(valor: float) -> str:
    return f"{valor:+.1f}".replace(".", ",")


def _reais(valor: float) -> str:
    return f"R$ {valor:.2f}".replace(".", ",")


def evidencia_ate(observacoes: list[dict], dia) -> dict:
    """O que os eventos já encerrados antes de `dia` dizem sobre o sinal (portão de evidência).

    Usa só eventos cuja janela de PRATICA_EVIDENCIA_HORIZONTE pregões depois da
    execução terminou ANTES de `dia`: nada do futuro entra na decisão.
    """
    h = config.PRATICA_EVIDENCIA_HORIZONTE
    limite_dia = pd.Timestamp(dia).date().isoformat()
    valores = [o[f"car_{h}"] for o in observacoes
               if o.get(f"car_{h}") is not None and o.get(f"fim_{h}") and o[f"fim_{h}"] < limite_dia]
    custo = 2 * custo_por_lado()
    base = {"n": len(valores), "minimo": config.PRATICA_EVIDENCIA_MINIMA, "custo_ida_e_volta": custo,
            "media": None, "limite_inferior": None, "aberto": False}
    if len(valores) < max(2, config.PRATICA_EVIDENCIA_MINIMA):
        return base
    media = sum(valores) / len(valores)
    desvio = (sum((v - media) ** 2 for v in valores) / (len(valores) - 1)) ** 0.5
    inferior = media - quantil_t(config.PRATICA_EVIDENCIA_CONFIANCA, len(valores) - 1) * desvio / len(valores) ** 0.5
    return {**base, "media": media, "limite_inferior": inferior, "aberto": inferior > custo}


def _texto_evidencia(e: dict) -> str:
    h = config.PRATICA_EVIDENCIA_HORIZONTE
    if e["n"] < e["minimo"]:
        return f"só {e['n']} evento(s) com {h} pregões encerrados; o mínimo é {e['minimo']}".replace("evento(s)", "evento" if e["n"] == 1 else "eventos")
    return (f"{e['n']} eventos: retorno médio de {_pct(e['media'])} em {h} pregões; "
            f"no pior caso plausível, {_pct(e['limite_inferior'])}, contra custo de {_pct(e['custo_ida_e_volta'])}")


def simular(sinais: list[dict], precos: pd.DataFrame, inicio, capital: float,
            taxas_cdi: pd.Series | None = None, evidencias: list[dict] | None = None) -> dict:
    """Simulação dia a dia. `precos` inclui histórico antes de `inicio` (para risco e reação).

    `evidencias`: observações do estudo de evento para o portão de evidência. None
    desliga o portão (testes da mecânica); a carteira prática de verdade sempre passa a lista.
    """
    inicio = pd.Timestamp(inicio)
    pregoes = precos.index[precos.index >= inicio]
    rets = estudo_evento.retornos(precos)
    custo = custo_por_lado()
    taxas_cdi = taxas_cdi if taxas_cdi is not None else pd.Series(dtype=float)
    ordens = backtest.sinais_para_ordens(sinais, pregoes)
    por_dia: dict[pd.Timestamp, list[dict]] = {}
    for ordem in ordens:
        por_dia.setdefault(pd.Timestamp(ordem["data_execucao"]), []).append(ordem)

    caixa = capital
    posicoes: dict[str, dict] = {}
    operacoes, descartados, vendas_ir = [], [], []
    custos_pagos = juros_caixa = 0.0
    bruto, exposicao = [], []

    def valor_posicoes(dia) -> float:
        return sum(p["quantidade"] * precos.at[dia, t] for t, p in posicoes.items() if not pd.isna(precos.at[dia, t]))

    def descartar(ordem, razao, detalhe, checagens=None):
        descartados.append({"ticker": ordem["ticker"], "decisao": ordem["decisao"],
                            "data": pd.Timestamp(ordem["data_execucao"]).date().isoformat(),
                            "razao": razao, "detalhe": detalhe, "checagens": checagens or [],
                            "origem": ordem.get("meta")})

    def vender(ticker, dia, motivo, detalhe, meta_saida=None):
        nonlocal caixa, custos_pagos
        pos = posicoes.pop(ticker)
        preco = float(precos.at[dia, ticker])
        bruto_venda = pos["quantidade"] * preco
        recebido = bruto_venda * (1 - custo)
        custos_pagos += bruto_venda * custo
        caixa += recebido
        resultado = recebido - pos["investido"]
        vendas_ir.append({"data": dia, "valor": bruto_venda, "lucro": resultado})
        operacoes.append({**pos["registro"], "saida": dia.date().isoformat(), "preco_saida": preco,
                          "valor": recebido, "resultado": resultado, "retorno": recebido / pos["investido"] - 1,
                          "pregoes": int(pregoes.get_loc(dia) - pos["i_entrada"]), "aberta": False,
                          "motivo_saida": motivo, "detalhe_saida": detalhe, "origem_saida": meta_saida})

    for i, dia in enumerate(pregoes):
        i_global = precos.index.get_loc(dia)
        if i > 0:
            taxa = float(taxas_cdi.get(pregoes[i - 1], 0.0) or 0.0)
            juros_caixa += caixa * taxa
            caixa *= 1 + taxa
        do_dia = por_dia.get(dia, [])

        # 1) Saídas, no fechamento: notícia negativa (regra), perda máxima, prazo.
        vendas_regra = {o["ticker"]: o for o in do_dia if o["decisao"] == VENDA}
        for ordem in sorted(vendas_regra.values(), key=lambda o: o["ticker"]):
            if ordem["ticker"] not in posicoes:
                continue  # nada a vender (a carteira da pesquisa também ignora): não é um filtro da prática
            reacao = estudo_evento.reacao_do_mercado(ordem["ticker"], ordem["instante"], precos, rets)
            if reacao and estudo_evento.leitura_reacao(reacao["z"], -1) == "contra":
                descartar(ordem, "mercado discordou",
                          f"notícia negativa, mas a ação subiu {_pct(reacao['car'])} além do Ibovespa antes da "
                          f"execução ({_z(reacao['z'])} desvios): o mercado não leu como ruim")
                continue
            texto = surpresa.detectar((ordem.get("meta") or {}).get("trecho_fonte"), (ordem.get("meta") or {}).get("resumo"))
            if surpresa.contradiz(texto["surpresa"], "negativo"):
                descartar(ordem, "texto contradiz", f"o texto diz que veio acima do esperado (\"{texto['trecho']}\")")
                continue
            vender(ordem["ticker"], dia, "notícia negativa", "a regra decidiu vender", ordem.get("meta"))
        for ticker in sorted(posicoes):
            preco = precos.at[dia, ticker]
            if pd.isna(preco):
                continue
            pos = posicoes[ticker]
            if preco <= pos["stop"]:
                vender(ticker, dia, "perda máxima",
                       f"fechou em {_reais(preco)}, abaixo do limite de perda de {_reais(pos['stop'])}")
            elif i - pos["i_entrada"] >= config.PRATICA_PRAZO_MAXIMO_PREGOES:
                vender(ticker, dia, "prazo", f"completou {config.PRATICA_PRAZO_MAXIMO_PREGOES} pregões")

        # 2) Entradas.
        for ordem in sorted((o for o in do_dia if o["decisao"] == COMPRA), key=lambda o: o["ticker"]):
            ticker = ordem["ticker"]
            preco = precos.at[dia, ticker] if ticker in precos.columns else float("nan")
            if pd.isna(preco):
                descartar(ordem, "sem preço", "sem preço no pregão de execução")
                continue
            if ticker in posicoes:
                descartar(ordem, "já posicionado", "a carteira prática já tem essa ação")
                continue
            meta = ordem.get("meta") or {}
            checagens = []
            if evidencias is not None:
                evidencia = evidencia_ate(evidencias, dia)
                checagens.append(_item("Há evidência de que o sinal paga o custo", evidencia["aberto"],
                                       _texto_evidencia(evidencia)))
                if not evidencia["aberto"]:
                    descartar(ordem, "sem evidência suficiente",
                              "o portão de evidência está fechado: " + _texto_evidencia(evidencia)
                              + ". O dinheiro segue no CDI", checagens)
                    continue
            reacao = estudo_evento.reacao_do_mercado(ticker, ordem["instante"], precos, rets)
            if reacao is None:
                checagens.append(_item("Reação do mercado antes da execução", None, "sem histórico de preços para medir"))
            else:
                leitura = estudo_evento.leitura_reacao(reacao["z"], 1)
                detalhe = (f"{_pct(reacao['car'])} além do Ibovespa em {reacao['n_pregoes']} pregão(ões), "
                           f"{_z(reacao['z'])} desvios"
                           if reacao["n_pregoes"] else "não houve pregão entre a notícia e a execução")
                checagens.append(_item("O mercado não reagiu com força contra a notícia", leitura != "contra",
                                       f"reação {leitura}: {detalhe}"))
            texto = surpresa.detectar(meta.get("trecho_fonte"), meta.get("resumo"))
            contradiz = surpresa.contradiz(texto["surpresa"], "positivo")
            checagens.append(_item("O texto não diz que veio abaixo do esperado", not contradiz,
                                   f"o texto compara com a expectativa: \"{texto['trecho']}\"" if texto["surpresa"]
                                   else "o texto não compara o número com a expectativa"))
            if any(c["ok"] is False for c in checagens):
                razao = next(("mercado discordou" if "reagiu" in c["criterio"] else "texto contradiz")
                             for c in checagens if c["ok"] is False)
                descartar(ordem, razao, next(c["detalhe"] for c in checagens if c["ok"] is False), checagens)
                continue

            patrimonio = caixa + valor_posicoes(dia)
            vol = volatilidade_diaria(rets[ticker], i_global)
            peso, detalhe_peso = peso_pelo_risco(vol)
            checagens.append(_item("Tamanho pelo risco", True, detalhe_peso))
            setor = config.SETORES.get(ticker)
            no_setor = sum(p["quantidade"] * precos.at[dia, t] for t, p in posicoes.items()
                           if config.SETORES.get(t) == setor and not pd.isna(precos.at[dia, t])) / patrimonio
            espaco = config.PRATICA_LIMITE_SETOR - no_setor
            if espaco < peso:
                peso = max(0.0, espaco)
                checagens.append(_item(f"Limite do setor ({setor}: até {_pct(config.PRATICA_LIMITE_SETOR)})",
                                       peso >= PESO_MINIMO, f"o setor já tem {_pct(no_setor)}: sobra {_pct(peso)}"))
            else:
                checagens.append(_item(f"Limite do setor ({setor}: até {_pct(config.PRATICA_LIMITE_SETOR)})", True,
                                       f"o setor tem {_pct(no_setor)}"))
            valor = min(peso * patrimonio, caixa)
            if valor < PESO_MINIMO * patrimonio:
                razao = "limite do setor" if peso < PESO_MINIMO else "sem caixa"
                descartar(ordem, razao, checagens[-1]["detalhe"] if razao == "limite do setor"
                          else "caixa insuficiente", checagens)
                continue
            vol_stop = vol if vol is not None else config.PRATICA_VOL_REFERENCIA_ANUAL / math.sqrt(252)
            queda_maxima = config.PRATICA_STOP_DESVIOS * vol_stop * math.sqrt(config.PRATICA_PRAZO_MAXIMO_PREGOES)
            stop = float(preco) * (1 - queda_maxima)
            checagens.append(_item("Saída planejada", True,
                                   f"vende se fechar abaixo de {_reais(stop)} (-{_pct(queda_maxima)}) ou em "
                                   f"{config.PRATICA_PRAZO_MAXIMO_PREGOES} pregões"))
            caixa -= valor
            custos_pagos += valor * custo
            posicoes[ticker] = {
                "quantidade": valor * (1 - custo) / float(preco), "investido": valor, "stop": stop,
                "i_entrada": i,
                "registro": {"ticker": ticker, "entrada": dia.date().isoformat(), "preco_entrada": float(preco),
                             "investido": valor, "peso": valor / patrimonio, "stop": stop,
                             "checagens": checagens, "origem": meta},
            }

        total = caixa + valor_posicoes(dia)
        bruto.append(total)
        exposicao.append((total - caixa) / total if total else 0.0)

    ultimo = pregoes[-1] if len(pregoes) else None
    abertas = []
    for ticker, pos in posicoes.items():
        preco = float(precos.at[ultimo, ticker])
        valor = pos["quantidade"] * preco * (1 - custo)
        abertas.append({**pos["registro"], "saida": None, "preco_atual": preco, "valor": valor,
                        "resultado": valor - pos["investido"], "retorno": valor / pos["investido"] - 1,
                        "pregoes": int(len(pregoes) - 1 - pos["i_entrada"]), "aberta": True,
                        "pregoes_restantes": max(0, config.PRATICA_PRAZO_MAXIMO_PREGOES - (len(pregoes) - 1 - pos["i_entrada"]))})

    serie_bruta = pd.Series(bruto, index=pregoes, dtype=float)
    provisao = tributacao.provisao_diaria(vendas_ir, pregoes)
    return {"bruto": serie_bruta, "liquido": serie_bruta - provisao, "provisao_ir": provisao,
            "exposicao": pd.Series(exposicao, index=pregoes, dtype=float),
            "operacoes": operacoes, "abertas": abertas, "descartados": descartados,
            "ir": tributacao.apurar(vendas_ir), "custos_pagos": custos_pagos, "juros_caixa": juros_caixa,
            "caixa": caixa}


def calcular(dir_data: Path | None = None, agora: datetime | None = None, baixar=None,
             baixar_cdi=None, capital: float | None = None) -> dict:
    """Carteira prática ao lado da carteira da pesquisa, do CDI e do Ibovespa."""
    dir_data = Path(dir_data or config.DIR_DATA)
    agora = (agora or datetime.now(FUSO)).astimezone(FUSO)
    capital = config.CAPITAL_INICIAL if capital is None else capital
    sinais = [s for s in simulacao.sinais_do_log(dir_data) if s["tipo_fonte"] == "noticia"]
    base = {"versao": config.VERSAO_PRATICA, "capital_inicial": capital, "parametros": parametros(),
            "aviso": ("Mesmas decisões da regra, operadas com custos, imposto e gestão de risco. "
                      "Simulação com dinheiro fictício; não é recomendação de investimento.")}
    inicio = simulacao._inicio(dir_data, sinais)
    if inicio is None:
        return {**base, "estado": "sem_dados", "mensagem": "Ainda não há execuções do pipeline."}

    hoje = agora.date()
    ultimo_dia = hoje if agora.time() >= simulacao.HORARIO_FECHAMENTO_CONFIAVEL else hoje - timedelta(days=1)
    precos = backtest.carregar_precos((inicio - timedelta(days=DIAS_HISTORICO)).isoformat(), ultimo_dia.isoformat(),
                                      pasta=dir_data / "pratica" / "precos", baixar=baixar)
    precos = simulacao._sem_preco_parcial(precos.dropna(how="all"), agora)
    pregoes = precos.index[precos.index >= pd.Timestamp(inicio)]
    if not len(pregoes):
        return {**base, "estado": "aguardando_pregao", "inicio": inicio.isoformat(),
                "mensagem": "Ainda não há fechamento de pregão desde o início da simulação."}

    taxas, aviso_cdi = pd.Series(dtype=float), None
    try:
        taxas = cdi.carregar_cdi(pregoes[0].date(), pregoes[-1].date(), dir_data / "simulacao" / "cdi", baixar=baixar_cdi)
    except Exception as erro:  # noqa: BLE001 - CDI fora do ar: o caixa fica parado e a página avisa
        logger.warning("CDI indisponível para a carteira prática: %s", erro)
    if taxas.empty and len(pregoes) > 1:
        aviso_cdi = "CDI indisponível agora: o caixa da carteira prática foi considerado parado (0%)."

    # Portão de evidência: todos os eventos classificados desta base (ao vivo), com
    # o retorno de cada um medido nos preços; cada compra só vê os já encerrados.
    eventos = simulacao.eventos_classificados(dir_data)
    obs = estudo_evento.observacoes(eventos, precos)
    pratica = simular(sinais, precos, inicio, capital, taxas, evidencias=obs)
    pesquisa = backtest.simular(backtest.sinais_para_ordens(sinais, pregoes), precos.loc[pregoes], capital, 0.0)
    ibov = backtest.comprar_e_segurar(precos.loc[pregoes, config.BENCHMARK], capital)
    if not taxas.empty:
        renda_fixa = cdi.patrimonio_cdi(pregoes, taxas, capital)
    else:  # um pregão só: nada rendeu ainda; mais que isso sem taxa, o CDI fica de fora
        renda_fixa = pd.Series(capital, index=pregoes, dtype=float) if len(pregoes) == 1 else None

    series = {"pratica": pratica["liquido"], "pratica_bruta": pratica["bruto"], "pesquisa": pesquisa.patrimonio,
              "ibovespa": ibov, "cdi": renda_fixa}
    metricas = {
        "pratica": risco.metricas(pratica["liquido"], taxas, ibov, pratica["operacoes"] + pratica["abertas"]),
        "pesquisa": risco.metricas(pesquisa.patrimonio, taxas, ibov,
                                   [{**o, "resultado": o["recebido"] - o["investido"]} for o in pesquisa.operacoes]),
        "ibovespa": risco.metricas(ibov, taxas, ibov),
    }
    if renda_fixa is not None:
        metricas["cdi"] = risco.metricas(renda_fixa, taxas, ibov)
    return {
        **base, "estado": "ok", "inicio": inicio.isoformat(), "ultimo_fechamento": pregoes[-1].date().isoformat(),
        "cdi_indisponivel": aviso_cdi,
        "serie": [{"data": d.date().isoformat(),
                   **{k: (float(s.at[d]) if s is not None and d in s.index else None) for k, s in series.items()}}
                  for d in pregoes],
        "metricas": metricas,
        "patrimonio": float(pratica["liquido"].iloc[-1]), "caixa": pratica["caixa"],
        "efeitos": {"custos_pagos": pratica["custos_pagos"], "imposto": pratica["ir"]["imposto_total"],
                    "juros_caixa": pratica["juros_caixa"],
                    "diferenca_para_pesquisa": float(pratica["liquido"].iloc[-1] - pesquisa.patrimonio.iloc[-1])},
        "posicoes_abertas": pratica["abertas"], "operacoes_encerradas": pratica["operacoes"],
        "descartados": pratica["descartados"], "imposto_de_renda": pratica["ir"],
        "exposicao_atual": float(pratica["exposicao"].iloc[-1]),
        "correlacoes": risco.correlacoes(precos, config.CARTEIRA),
        "portao_evidencia": {**evidencia_ate(obs, pregoes[-1] + pd.Timedelta(days=1)),
                             "texto": _texto_evidencia(evidencia_ate(obs, pregoes[-1] + pd.Timedelta(days=1)))},
    }


def parametros() -> dict:
    """Parâmetros da camada prática, com a explicação de cada um (para a página)."""
    return {
        "custo_por_lado": custo_por_lado(),
        "ir_aliquota": config.PRATICA_IR_ALIQUOTA,
        "ir_isencao_vendas_mes": config.PRATICA_IR_ISENCAO_VENDAS_MES,
        "vol_referencia_anual": config.PRATICA_VOL_REFERENCIA_ANUAL,
        "max_posicao": config.MAX_POSICAO_PCT,
        "limite_setor": config.PRATICA_LIMITE_SETOR,
        "setores": config.SETORES,
        "prazo_maximo_pregoes": config.PRATICA_PRAZO_MAXIMO_PREGOES,
        "stop_desvios": config.PRATICA_STOP_DESVIOS,
        "z_reacao": config.PRATICA_Z_REACAO,
        "evidencia_minima": config.PRATICA_EVIDENCIA_MINIMA,
        "evidencia_confianca": config.PRATICA_EVIDENCIA_CONFIANCA,
        "evidencia_horizonte": config.PRATICA_EVIDENCIA_HORIZONTE,
    }
