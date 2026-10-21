"""Surpresa em relação à expectativa, lida no texto da notícia (sem LLM).

O que move o preço é a notícia comparada ao que o mercado esperava: "lucro
recorde" abaixo do consenso derruba a ação. A IA classifica se o fato é bom ou
ruim; este módulo procura no trecho citado pela IA (e no resumo dela) se o
próprio texto compara o número com a expectativa: "acima do consenso",
"superou as estimativas", "frustrou", "abaixo do esperado", "em linha com".

Por que não pedir isso à IA: mudar o prompt de extração cria uma nova versão e
deixa de fora da regra todos os eventos já extraídos (src/main.py,
do_prompt_vigente). Palavras-chave são transparentes, determinísticas e não
custam nada. Limite: só vê a surpresa quando o texto a explicita.
"""

import re
import unicodedata

_REFERENCIA = (r"(?:o |a |os |as )?(?:consenso|esperad[oa]s?|expectativas?|estimativas?|estimad[oa]s?|"
               r"projec(?:ao|oes)|projetad[oa]s?|previst[oa]s?|previs(?:ao|oes)|mercado|analistas)")

# Com um número ou trecho curto no meio, na mesma frase ("acima dos 2,77 milhões
# de barris por dia considerados pelo consenso"): só referências fortes, para
# "acima de R$ 50, segundo analistas" não virar surpresa.
_REFERENCIA_FORTE = (r"(?:consenso|esperad[oa]s?|expectativas?|estimativas?|estimad[oa]s?|"
                     r"projec(?:ao|oes)|projetad[oa]s?|previst[oa]s?)")
_NO_MEIO = r"[^.;!?]{0,80}?"

PADROES = {
    "acima": [
        rf"\b(?:acima|alem)\s+d[oa]s?\s+{_REFERENCIA}",
        rf"\bacima\s+d[oa]s?\s{_NO_MEIO}\b{_REFERENCIA_FORTE}",
        rf"\b(?:superou|superaram|supera|superam|superando|bateu|bateram|batendo)\s+{_REFERENCIA}",
        r"\bsurpreend\w*\s+positivamente\b",
        rf"\bmelhor(?:es)?\s+(?:do\s+)?que\s+{_REFERENCIA}",
    ],
    "abaixo": [
        rf"\babaixo\s+d[oa]s?\s+{_REFERENCIA}",
        rf"\babaixo\s+d[oa]s?\s{_NO_MEIO}\b{_REFERENCIA_FORTE}",
        rf"\baquem\s+d[oa]s?\s+{_REFERENCIA}",
        r"\b(?:frustrou|frustraram|frustrando|decepcionou|decepcionaram|decepcionando)\b",
        r"\bsurpreend\w*\s+negativamente\b",
        rf"\bpior(?:es)?\s+(?:do\s+)?que\s+{_REFERENCIA}",
    ],
    "em_linha": [rf"\bem\s+linha\s+com\s+{_REFERENCIA}"],
}


def _normalizar(texto: str) -> str:
    sem_acento = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", sem_acento.lower())


def detectar(*textos: str) -> dict:
    """{"surpresa": "acima" | "abaixo" | "em_linha" | "mista" | None, "trecho": str | None}."""
    texto = _normalizar(" ".join(t for t in textos if t))
    achados = {}
    for tipo, padroes in PADROES.items():
        for padrao in padroes:
            encontrado = re.search(padrao, texto)
            if encontrado:
                achados[tipo] = encontrado.group(0)
                break
    if "acima" in achados and "abaixo" in achados:
        return {"surpresa": "mista", "trecho": f"{achados['acima']} / {achados['abaixo']}"}
    for tipo in ("acima", "abaixo", "em_linha"):
        if tipo in achados:
            return {"surpresa": tipo, "trecho": achados[tipo]}
    return {"surpresa": None, "trecho": None}


def contradiz(surpresa: str | None, sentimento: str) -> bool:
    """O texto diz o contrário da classificação? (positivo, mas abaixo do esperado; e vice-versa)"""
    return (sentimento == "positivo" and surpresa == "abaixo") or (sentimento == "negativo" and surpresa == "acima")
