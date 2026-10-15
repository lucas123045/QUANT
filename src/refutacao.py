"""Testes que tentam REFUTAR o sinal (em vez de só confirmá-lo).

1. Placebo: embaralha a classificação (sentimento + probabilidade) entre os
   eventos e roda a mesma regra muitas vezes. Se a regra real não for melhor
   que a maioria dos placebos, o "sinal" era só exposição ao mercado.
2. Defasagem: executa as mesmas ordens 0, 1, 2, 5 e 10 pregões mais tarde.
   Se a notícia move o preço, o ganho deve CAIR com o atraso; se não cai,
   não era a notícia.
3. Calibração: compara a probabilidade declarada pela IA com o acerto
   direcional observado, por faixa (e escore de Brier).

Todos exigem período aprovado (mesma trava do backtest). Use em treino ou
validação; no período de teste, só depois do congelamento.
"""

import random

import pandas as pd

from src import config
from src.backtest import (acerto_direcional, anotar_excesso, sinais_da_estrategia,
                          sinais_para_ordens, simular, tipo_fonte_do_evento,
                          validar_periodo, data_local)
from src.estatistica import tabela_calibracao

SEMENTE_PLACEBO = 20261016


def _precos_do_periodo(precos: pd.DataFrame, periodo, nome: str) -> pd.DataFrame:
    inicio, fim = validar_periodo(periodo, nome)
    recorte = precos.loc[inicio:fim]
    if len(recorte) < 2:
        raise ValueError(f"{nome}: menos de dois pregões com preço")
    return recorte


def _so_uma_fonte(eventos: list[dict], tipo_fonte: str) -> None:
    if {tipo_fonte_do_evento(e) for e in eventos} - {tipo_fonte}:
        raise ValueError(f"eventos de fontes misturadas; este teste é só de '{tipo_fonte}'")


def _retorno(eventos: list[dict], precos: pd.DataFrame, capital: float, custo: float | None) -> float:
    ordens = sinais_para_ordens(sinais_da_estrategia(eventos), precos.index)
    patrimonio = simular(ordens, precos, capital, custo).patrimonio
    return float(patrimonio.iloc[-1] / patrimonio.iloc[0] - 1)


def placebo(eventos: list[dict], precos: pd.DataFrame, periodo, tipo_fonte: str,
            n: int = 500, semente: int = SEMENTE_PLACEBO, capital: float | None = None,
            custo: float | None = None) -> dict:
    """Distribuição do retorno com classificações embaralhadas entre os eventos."""
    _so_uma_fonte(eventos, tipo_fonte)
    if n < 1:
        raise ValueError("n precisa ser maior que zero")
    recorte = _precos_do_periodo(precos, periodo, "período do placebo")
    capital = config.CAPITAL_INICIAL if capital is None else capital
    real = _retorno(eventos, recorte, capital, custo)
    classificacoes = [e.get("classificacao") for e in eventos]
    gerador = random.Random(semente)
    retornos = []
    for _ in range(n):
        embaralhadas = classificacoes[:]
        gerador.shuffle(embaralhadas)
        retornos.append(_retorno([{**e, "classificacao": c} for e, c in zip(eventos, embaralhadas)],
                                 recorte, capital, custo))
    melhores_ou_iguais = sum(r >= real for r in retornos)
    return {
        "retorno_real": real,
        "placebos": retornos,
        "media_placebo": sum(retornos) / n,
        # p-valor empírico com correção de +1 (nunca exatamente zero).
        "p_valor": (melhores_ou_iguais + 1) / (n + 1),
        "n": n,
        "semente": semente,
    }


def defasagem(eventos: list[dict], precos: pd.DataFrame, periodo, tipo_fonte: str,
              atrasos: tuple[int, ...] = (0, 1, 2, 5, 10), capital: float | None = None,
              custo: float | None = None) -> list[dict]:
    """Resultado da estratégia executando cada ordem k pregões mais tarde."""
    _so_uma_fonte(eventos, tipo_fonte)
    if not atrasos or any(not isinstance(k, int) or k < 0 for k in atrasos):
        raise ValueError("atrasos precisam ser inteiros não negativos")
    recorte = _precos_do_periodo(precos, periodo, "período da defasagem")
    capital = config.CAPITAL_INICIAL if capital is None else capital
    ordens = sinais_para_ordens(sinais_da_estrategia(eventos), recorte.index)
    pregoes = list(recorte.index)
    resultado = []
    for k in atrasos:
        atrasadas = []
        for o in ordens:
            posicao = pregoes.index(pd.Timestamp(o["data_execucao"])) + k
            if posicao < len(pregoes):
                atrasadas.append({**o, "data_execucao": pregoes[posicao]})
        sim = simular(atrasadas, recorte, capital, custo)
        anotar_excesso(sim.operacoes, recorte[config.BENCHMARK])
        excessos = [op["excesso"] for op in sim.operacoes]
        resultado.append({
            "atraso_pregoes": k,
            "retorno_acumulado": float(sim.patrimonio.iloc[-1] / sim.patrimonio.iloc[0] - 1),
            "excesso_medio_por_operacao": sum(excessos) / len(excessos) if excessos else None,
            "n_operacoes": len(sim.operacoes),
        })
    return resultado


def calibracao(eventos: list[dict], precos: pd.DataFrame, periodo,
               tipo_fonte: str, n_faixas: int = 5) -> dict:
    """A confiança da IA corresponde ao acerto direcional no período aprovado?

    Só conta eventos publicados dentro do período e cujo pregão de desfecho
    também está dentro dele. Assim a calibração não usa preços externos ao
    recorte nem mistura notícias e fatos relevantes.
    """
    _so_uma_fonte(eventos, tipo_fonte)
    inicio, fim = validar_periodo(periodo, "período da calibração")
    recorte = precos.loc[inicio:fim]
    if len(recorte) < 2:
        raise ValueError("período da calibração: menos de dois pregões com preço")
    pares = []
    sem_desfecho = 0
    for evento in eventos:
        instante = evento.get("origem", {}).get("timestamp_publicacao") or evento.get("timestamp_publicacao")
        if not instante:
            sem_desfecho += 1
            continue
        dia = data_local(instante)
        if dia < inicio or dia > fim:
            continue
        acerto = acerto_direcional(evento, recorte)
        if acerto is not None:
            pares.append((evento["classificacao"]["probabilidade"], acerto))
        else:
            sem_desfecho += 1
    tabela = tabela_calibracao([p for p, _ in pares], [a for _, a in pares], n_faixas)
    tabela["n_sem_desfecho"] = sem_desfecho
    tabela["periodo"] = [inicio.date().isoformat(), fim.date().isoformat()]
    tabela["tipo_fonte"] = tipo_fonte
    return tabela


def executar(eventos: list[dict], precos: pd.DataFrame, periodo,
             tipo_fonte: str, n_placebos: int = 500,
             semente: int = SEMENTE_PLACEBO, capital: float | None = None,
             custo: float | None = None, n_faixas: int = 5) -> dict:
    """Executa placebo, defasagem padrão e calibração sob o mesmo recorte."""
    inicio, fim = validar_periodo(periodo, "período dos testes de refutação")
    recorte = precos.loc[inicio:fim]
    if len(recorte) < 2:
        raise ValueError("período dos testes de refutação: menos de dois pregões com preço")
    return {
        "periodo": [inicio.date().isoformat(), fim.date().isoformat()],
        "tipo_fonte": tipo_fonte,
        "placebo": placebo(eventos, recorte, periodo, tipo_fonte, n_placebos,
                            semente, capital, custo),
        "defasagem": defasagem(eventos, recorte, periodo, tipo_fonte,
                               capital=capital, custo=custo),
        "calibracao": calibracao(eventos, recorte, periodo, tipo_fonte, n_faixas),
    }
