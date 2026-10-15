"""Provedores reais de LLM, registrados em src/llm.py.

Anthropic (Claude), pelo SDK oficial `anthropic`:
- LLM_PROVEDOR=anthropic, LLM_API_KEY=<chave>, LLM_MODELO opcional
  (padrão: claude-opus-5-5).
- Os modelos atuais não aceitam parâmetros de amostragem (temperature):
  a temperatura pedida não é enviada e fica registrada como None nas saídas.
  A reprodutibilidade vem do pipeline, que grava cada resposta e não a pede de novo.
- Esforço de raciocínio fixado em "medium" (o padrão do modelo, explícito
  para ficar registrado e congelável).
- Recusa por classificador de segurança: com o fallback do servidor
  ("default"), a API reexecuta em outro modelo. O modelo que de fato
  respondeu é informado ao llm.py e gravado em cada evento.
"""

import logging

from src import llm

logger = logging.getLogger(__name__)

MODELO_PADRAO_ANTHROPIC = "claude-opus-5-5"
ESFORCO = "medium"
MAX_TOKENS = 16000
BETA_FALLBACK = "server-side-fallback-2026-07-01"


class RecusaDoModelo(RuntimeError):
    """O modelo (e o fallback) recusou a requisição."""


def provedor_anthropic(prompt: str, temperatura: float, chave: str | None, modelo: str) -> str:
    import anthropic  # import local: só é necessário com este provedor

    modelo = modelo or MODELO_PADRAO_ANTHROPIC
    cliente = anthropic.Anthropic(api_key=chave)
    resposta = cliente.beta.messages.create(
        model=modelo,
        max_tokens=MAX_TOKENS,
        output_config={"effort": ESFORCO},
        betas=[BETA_FALLBACK],
        fallbacks="default",
        messages=[{"role": "user", "content": prompt}],
    )
    if resposta.stop_reason == "refusal":
        categoria = getattr(resposta.stop_details, "category", None) if resposta.stop_details else None
        raise RecusaDoModelo(f"o modelo recusou a requisição (categoria: {categoria})")
    if resposta.model != modelo:
        logger.warning("Resposta servida por %s (fallback a partir de %s)", resposta.model, modelo)
    llm.informar_modelo_servido(f"anthropic:{resposta.model}")
    if resposta.stop_reason == "max_tokens":
        logger.warning("Resposta truncada em max_tokens=%d", MAX_TOKENS)
    return "".join(bloco.text for bloco in resposta.content if bloco.type == "text")


def registrar_todos() -> None:
    llm.registrar_provedor("anthropic", provedor_anthropic, aceita_temperatura=False)
