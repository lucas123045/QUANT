"""Testes estatísticos e calibração, sem dependências além da biblioteca padrão.

- Distribuição t de Student via função beta incompleta regularizada
  (fração continuada, Numerical Recipes 6.4).
- Teste t de uma amostra (H1: média > 0) e teste de Welch (H1: média A > média B).
- Tabela de calibração e escore de Brier para probabilidades declaradas.
- Média com intervalo de confiança (t de Student) e teste bilateral, para o
  estudo de evento (src/estudo_evento.py).
"""

import math


def _fracao_continuada_beta(a: float, b: float, x: float) -> float:
    maximo, eps, minimo = 300, 3e-14, 1e-300
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > minimo else minimo)
    h = d
    for m in range(1, maximo + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > minimo else minimo)
        c = 1.0 + aa / c
        c = c if abs(c) > minimo else minimo
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > minimo else minimo)
        c = 1.0 + aa / c
        c = c if abs(c) > minimo else minimo
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def beta_incompleta(a: float, b: float, x: float) -> float:
    """Função beta incompleta regularizada I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    log_bt = (math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
              + a * math.log(x) + b * math.log(1.0 - x))
    bt = math.exp(log_bt)
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _fracao_continuada_beta(a, b, x) / a
    return 1.0 - bt * _fracao_continuada_beta(b, a, 1.0 - x) / b


def p_valor_t_unilateral(t: float, graus_liberdade: float) -> float:
    """P(T > t) para T ~ t de Student com os graus de liberdade dados."""
    if math.isinf(t):
        return 0.0 if t > 0 else 1.0
    cauda = 0.5 * beta_incompleta(graus_liberdade / 2.0, 0.5,
                                  graus_liberdade / (graus_liberdade + t * t))
    return cauda if t > 0 else 1.0 - cauda


def _media_variancia(valores: list[float]) -> tuple[int, float, float]:
    n = len(valores)
    media = sum(valores) / n
    variancia = sum((v - media) ** 2 for v in valores) / (n - 1)
    return n, media, variancia


def teste_t_uma_amostra(valores: list[float]) -> dict:
    """Teste t unilateral de que a média é maior que zero.

    Devolve p_valor=None quando o teste é indefinido (n < 2 ou desvio zero).
    """
    valores = [float(v) for v in valores]
    if len(valores) < 2:
        return {"n": len(valores), "media": valores[0] if valores else None,
                "erro_padrao": None, "t": None, "graus_liberdade": None, "p_valor": None}
    n, media, variancia = _media_variancia(valores)
    erro_padrao = math.sqrt(variancia / n)
    if erro_padrao == 0.0:
        return {"n": n, "media": media, "erro_padrao": 0.0, "t": None,
                "graus_liberdade": n - 1, "p_valor": None}
    t = media / erro_padrao
    return {"n": n, "media": media, "erro_padrao": erro_padrao, "t": t,
            "graus_liberdade": n - 1, "p_valor": p_valor_t_unilateral(t, n - 1)}


def teste_welch(a: list[float], b: list[float]) -> dict:
    """Teste de Welch unilateral de que média(a) > média(b) (variâncias desiguais)."""
    a, b = [float(v) for v in a], [float(v) for v in b]
    if len(a) < 2 or len(b) < 2:
        return {"n_a": len(a), "n_b": len(b), "diferenca": None, "t": None,
                "graus_liberdade": None, "p_valor": None}
    na, ma, va = _media_variancia(a)
    nb, mb, vb = _media_variancia(b)
    erro_padrao = math.sqrt(va / na + vb / nb)
    if erro_padrao == 0.0:
        return {"n_a": na, "n_b": nb, "diferenca": ma - mb, "t": None,
                "graus_liberdade": None, "p_valor": None}
    t = (ma - mb) / erro_padrao
    gl = (va / na + vb / nb) ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    return {"n_a": na, "n_b": nb, "diferenca": ma - mb, "t": t,
            "graus_liberdade": gl, "p_valor": p_valor_t_unilateral(t, gl)}


def tabela_calibracao(probabilidades: list[float], acertos: list[bool],
                      n_faixas: int = 5) -> dict:
    """Compara a probabilidade declarada com a taxa de acerto observada.

    Faixas de largura igual em [0, 1]. Um classificador calibrado tem, em cada
    faixa, taxa de acerto próxima da probabilidade média.
    """
    if len(probabilidades) != len(acertos):
        raise ValueError("probabilidades e acertos com tamanhos diferentes")
    faixas = []
    for i in range(n_faixas):
        inicio, fim = i / n_faixas, (i + 1) / n_faixas
        dentro = [(p, a) for p, a in zip(probabilidades, acertos)
                  if inicio <= p < fim or (i == n_faixas - 1 and p == 1.0)]
        faixas.append({
            "faixa": [inicio, fim],
            "n": len(dentro),
            "probabilidade_media": sum(p for p, _ in dentro) / len(dentro) if dentro else None,
            "taxa_acerto": sum(bool(a) for _, a in dentro) / len(dentro) if dentro else None,
        })
    n = len(probabilidades)
    brier = sum((p - float(bool(a))) ** 2 for p, a in zip(probabilidades, acertos)) / n if n else None
    return {"n": n, "brier": brier, "faixas": faixas}


def quantil_t(probabilidade: float, graus_liberdade: float) -> float:
    """t tal que P(T <= t) = probabilidade (bisseção sobre a cauda; 0,5 < p < 1)."""
    if not 0.5 < probabilidade < 1.0:
        raise ValueError("probabilidade fora de (0,5; 1)")
    alvo = 1.0 - probabilidade
    baixo, alto = 0.0, 1.0
    while p_valor_t_unilateral(alto, graus_liberdade) > alvo:
        alto *= 2.0
    for _ in range(200):
        meio = (baixo + alto) / 2.0
        if p_valor_t_unilateral(meio, graus_liberdade) > alvo:
            baixo = meio
        else:
            alto = meio
    return (baixo + alto) / 2.0


def media_com_intervalo(valores: list[float], confianca: float = 0.95) -> dict:
    """Média, erro padrão, intervalo de confiança t e p-valor bilateral (H0: média = 0).

    Com menos de 2 valores (ou desvio zero), intervalo e p-valor ficam None:
    com amostra assim, não há o que concluir.
    """
    valores = [float(v) for v in valores]
    base = {"n": len(valores), "media": sum(valores) / len(valores) if valores else None,
            "erro_padrao": None, "intervalo": None, "t": None, "p_valor_bilateral": None}
    if len(valores) < 2:
        return base
    n, media, variancia = _media_variancia(valores)
    erro_padrao = math.sqrt(variancia / n)
    if erro_padrao == 0.0:
        return {**base, "erro_padrao": 0.0}
    t = media / erro_padrao
    margem = quantil_t(0.5 + confianca / 2.0, n - 1) * erro_padrao
    return {**base, "erro_padrao": erro_padrao, "intervalo": [media - margem, media + margem],
            "t": t, "p_valor_bilateral": min(1.0, 2.0 * p_valor_t_unilateral(abs(t), n - 1))}
