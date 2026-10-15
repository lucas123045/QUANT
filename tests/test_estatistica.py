import pytest

from src import estatistica as est
from src.estatistica import beta_incompleta, p_valor_t_unilateral, tabela_calibracao


@pytest.mark.parametrize("t,gl,esperado", [
    (0.0, 10, 0.5),
    (1.812461, 10, 0.05),     # valores críticos de tabela
    (2.228139, 10, 0.025),
    (1.644854, 1e7, 0.05),    # gl grande -> normal
    (-1.812461, 10, 0.95),
    (12.706205, 1, 0.025),
])
def test_p_valor_t_contra_tabela(t, gl, esperado):
    assert p_valor_t_unilateral(t, gl) == pytest.approx(esperado, abs=1e-5)


def test_beta_incompleta_casos_simples():
    assert beta_incompleta(1, 1, 0.3) == pytest.approx(0.3)      # uniforme
    assert beta_incompleta(2, 2, 0.5) == pytest.approx(0.5)      # simétrica
    assert beta_incompleta(2, 3, 0.0) == 0.0 and beta_incompleta(2, 3, 1.0) == 1.0


def test_teste_t_uma_amostra_resultado_conhecido():
    # média 2, desvio amostral 1,5811, n 5 -> t = 2 / (1,5811/√5) = 2,8284
    r = est.teste_t_uma_amostra([0, 1, 2, 3, 4])
    assert r["t"] == pytest.approx(2.828427, rel=1e-6)
    assert r["graus_liberdade"] == 4
    assert r["p_valor"] == pytest.approx(0.02371, abs=1e-4)


def test_teste_t_indefinido():
    assert est.teste_t_uma_amostra([0.1])["p_valor"] is None
    assert est.teste_t_uma_amostra([])["p_valor"] is None
    assert est.teste_t_uma_amostra([0.1, 0.1])["p_valor"] is None


def test_teste_welch_resultado_conhecido():
    a, b = [5.0, 6.0, 7.0, 8.0], [1.0, 2.0, 3.0]
    r = est.teste_welch(a, b)
    # var a = 1,6667 (n 4); var b = 1 (n 3); EP = √(0,41667+0,33333) = 0,866
    assert r["diferenca"] == pytest.approx(4.5)
    assert r["t"] == pytest.approx(4.5 / 0.8660254, rel=1e-6)
    assert r["graus_liberdade"] == pytest.approx(4.959184, abs=1e-5)
    assert r["p_valor"] < 0.01
    assert est.teste_welch(b, a)["p_valor"] > 0.99
    assert est.teste_welch([1.0], a)["p_valor"] is None


def test_calibracao():
    probs = [0.95, 0.9, 0.85, 0.8, 0.75, 0.72]
    acertos = [True, False, True, False, False, True]
    r = tabela_calibracao(probs, acertos, n_faixas=5)
    alta = r["faixas"][4]   # [0,8; 1,0]
    assert alta["n"] == 4 and alta["taxa_acerto"] == 0.5
    assert r["faixas"][3]["n"] == 2
    assert r["brier"] == pytest.approx(sum((p - a) ** 2 for p, a in zip(probs, acertos)) / 6)
    with pytest.raises(ValueError):
        tabela_calibracao([0.5], [])
