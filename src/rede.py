"""Acesso HTTP com a verificação de certificados do sistema operacional.

O Python, por conta própria, não completa cadeias de certificado incompletas;
o navegador e o Windows completam. O InfoMoney serve a cadeia incompleta, e por
isso a coleta falhava com CERTIFICATE_VERIFY_FAILED. Com `truststore`, a
verificação é a do sistema (continua recusando certificado inválido). Sem a
biblioteca instalada, usa a verificação padrão do Python.
"""

import ssl
import urllib.request
from functools import lru_cache


@lru_cache(maxsize=1)
def contexto_ssl() -> ssl.SSLContext:
    try:
        import truststore
    except ImportError:
        return ssl.create_default_context()
    return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)


def baixar(url: str, timeout: float, user_agent: str) -> bytes:
    """Conteúdo bruto da URL (levanta em erro de rede, HTTP ou certificado)."""
    pedido = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(pedido, timeout=timeout, context=contexto_ssl()) as resposta:
        return resposta.read()
