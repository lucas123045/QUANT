"""Casamento de textos com as empresas da carteira.

Regras:
- ticker com fronteira de palavra (ex.: "PETR4"; aceita sufixo "F" do fracionário);
- nome completo ou alias de config.ALIASES, sem distinção de maiúsculas/acentos,
  com fronteira de palavra (nunca substring);
- padrões de contexto de config.PADROES_CONTEXTO, sensíveis a maiúsculas;
- a palavra "vale" isolada nunca indica VALE3;
- expressões de config.EXCLUSOES (ex.: "Itaú BBA") são ignoradas antes do casamento.
"""

import re
import unicodedata
from functools import lru_cache

from src import config

# Fronteira de palavra que considera letras acentuadas, dígitos e "_" como parte da palavra.
_ANTES = r"(?<![\w])"
_DEPOIS = r"(?![\w])"


def normalizar(texto: str) -> str:
    """Remove acentos, passa para minúsculas e colapsa espaços."""
    decomposto = unicodedata.normalize("NFKD", texto)
    sem_acento = "".join(c for c in decomposto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sem_acento).strip().lower()


def _exclusao(ticker: str) -> re.Pattern | None:
    termos = [re.escape(normalizar(t)).replace(r"\ ", r"\s+") for t in config.EXCLUSOES.get(ticker, [])]
    return re.compile(_ANTES + "(?:" + "|".join(termos) + ")" + _DEPOIS) if termos else None


@lru_cache(maxsize=None)
def _padroes(ticker: str) -> tuple[list[re.Pattern], list[re.Pattern]]:
    """Devolve (padrões sobre texto normalizado, padrões sobre texto original)."""
    normalizados = [re.compile(_ANTES + re.escape(ticker.lower()) + r"f?" + _DEPOIS)]
    for alias in config.ALIASES.get(ticker, []):
        alias_norm = re.escape(normalizar(alias)).replace(r"\ ", r"\s+")
        normalizados.append(re.compile(_ANTES + alias_norm + _DEPOIS))
    originais = [re.compile(p) for p in config.PADROES_CONTEXTO.get(ticker, [])]
    return normalizados, originais


def menciona(texto: str, ticker: str) -> bool:
    """Indica se o texto menciona a empresa do ticker segundo as regras acima."""
    if not texto:
        return False
    normalizados, originais = _padroes(ticker)
    texto_norm = normalizar(texto)
    exclusao = _exclusao(ticker)
    if exclusao is not None:
        texto_norm = exclusao.sub(" ", texto_norm)
    if any(p.search(texto_norm) for p in normalizados):
        return True
    return any(p.search(texto) for p in originais)


def identificar_tickers(texto: str, carteira: list[str] | None = None) -> list[str]:
    """Lista os tickers da carteira mencionados no texto, na ordem da carteira."""
    carteira = config.CARTEIRA if carteira is None else carteira
    return list(_identificar(texto, tuple(carteira)))


# A interface recalcula o casamento de todo o arquivo a cada pedido (Notícias,
# funil): com alguns meses de coleta, seriam segundos por pedido. As regras não
# mudam com o processo rodando (os padrões já ficam em cache acima), então o
# resultado por texto também pode ficar.
@lru_cache(maxsize=20_000)
def _identificar(texto: str, carteira: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(t for t in carteira if menciona(texto, t))
