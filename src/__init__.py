"""Pacote principal do projeto QUANT."""

import sys

# Terminais com codificação antiga (ex.: cmd do Windows com saída redirecionada)
# não têm "—", "ç" etc.: em vez de derrubar o comando com UnicodeEncodeError,
# o caractere impossível vira "?".
for _fluxo in (sys.stdout, sys.stderr):
    if _fluxo is not None and hasattr(_fluxo, "reconfigure"):
        try:
            _fluxo.reconfigure(errors="replace")
        except (ValueError, OSError):
            pass
