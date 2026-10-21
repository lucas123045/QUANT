import json

import pytest

from src import classify

EVENTO = {"ticker": "PETR4", "tipo_evento": "dividendo", "resumo": "Petrobras paga dividendos.",
          "impacto_declarado": "positivo", "confirmado": True,
          "trecho_fonte": "pagamento de dividendos"}

CHAVES = {"sentimento", "probabilidade", "materialidade", "motivo_materialidade", "classificador", "modelo",
          "versao_prompt"}


def llm_falso(*respostas):
    fila = list(respostas)
    chamadas = []

    def chamar(prompt, temperatura=0.0):
        chamadas.append(prompt)
        return fila.pop(0)
    chamar.chamadas = chamadas
    return chamar


def test_caminho_llm_formato_padrao():
    chamar = llm_falso(json.dumps({"sentimento": "positivo", "probabilidade": 0.82, "materialidade": "alta",
                                   "motivo_materialidade": "muda o lucro"}))
    r = classify.classificar(EVENTO, usar_jev=False, chamar=chamar)
    assert set(r) == CHAVES
    assert r["sentimento"] == "positivo" and r["probabilidade"] == 0.82
    assert r["classificador"] == "llm"
    assert r["versao_prompt"] == "PROMPT_CLASSIFICACAO_V2" and r["materialidade"] == "alta"
    assert "[PROMPT_CLASSIFICACAO_V2]" in chamar.chamadas[0] and "materialidade" in chamar.chamadas[0]


def test_caminho_jev_mesmo_formato():
    jev = lambda evento: {"sentimento": "negativo", "probabilidade": 0.75}
    r = classify.classificar(EVENTO, usar_jev=True, jev=jev)
    assert set(r) == CHAVES
    assert r["classificador"] == "jev"


def test_adaptador_jev_bloqueado():
    with pytest.raises(NotImplementedError, match="API do Jev não especificada no repositório"):
        classify.classificar_jev(EVENTO)


def test_jev_indisponivel_usa_llm_como_fluxo_normal():
    chamar = llm_falso(json.dumps({"sentimento": "neutro", "probabilidade": 0.6, "materialidade": "baixa"}))
    r = classify.classificar(EVENTO, usar_jev=True, chamar=chamar)
    assert r["classificador"] == "llm"


def test_jev_saida_invalida_usa_llm():
    chamar = llm_falso(json.dumps({"sentimento": "neutro", "probabilidade": 0.6, "materialidade": "baixa"}))
    r = classify.classificar(EVENTO, usar_jev=True, jev=lambda e: {"x": 1}, chamar=chamar)
    assert r["classificador"] == "llm"


def test_llm_retry_uma_vez():
    chamar = llm_falso("lixo", json.dumps({"sentimento": "positivo", "probabilidade": 0.9, "materialidade": "media"}))
    assert classify.classificar(EVENTO, usar_jev=False, chamar=chamar)["sentimento"] == "positivo"
    assert len(chamar.chamadas) == 2


@pytest.mark.parametrize("respostas", [
    ("lixo", "lixo"),
    ('{"sentimento": "otimista", "probabilidade": 0.9}',) * 2,
    ('{"sentimento": "positivo", "probabilidade": 1.5}',) * 2,
    ('{"sentimento": "positivo", "probabilidade": "alta"}',) * 2,
    ('{"sentimento": "positivo", "probabilidade": 0.9}',) * 2,                          # sem materialidade
    ('{"sentimento": "positivo", "probabilidade": 0.9, "materialidade": "enorme"}',) * 2,
])
def test_llm_saida_invalida_devolve_none(respostas):
    chamar = llm_falso(*respostas)
    assert classify.classificar(EVENTO, usar_jev=False, chamar=chamar) is None
    assert len(chamar.chamadas) == 2


def test_llm_resposta_em_bloco_de_codigo_markdown():
    """Modelos costumam cercar o JSON com ```json; a extração já tolerava, a classificação também."""
    resposta = '```json\n{"sentimento": "negativo", "probabilidade": 0.77, "materialidade": "alta"}\n```'
    chamar = llm_falso(resposta)
    r = classify.classificar(EVENTO, usar_jev=False, chamar=chamar)
    assert r["sentimento"] == "negativo" and r["probabilidade"] == 0.77
    assert len(chamar.chamadas) == 1
