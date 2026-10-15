"""Provedores reais de LLM, registrados em src/llm.py.

Disponíveis: "anthropic" e "openai" (escolha com LLM_PROVEDOR no .env).

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


def provedor_openai(prompt: str, temperatura: float, chave: str | None, modelo: str) -> str:
    """OpenAI (Chat Completions), pelo SDK oficial `openai`.

    LLM_MODELO é obrigatório: o modelo depende do que a conta tem acesso.
    Pede a temperatura solicitada (0 na extração). Se o modelo recusar o
    parâmetro (alguns modelos de raciocínio só aceitam o padrão), repete a
    chamada sem ele e registra a temperatura aplicada como None.
    """
    import openai  # import local: só é necessário com este provedor

    if not modelo or modelo == "nao_definido":
        raise RuntimeError("Com LLM_PROVEDOR=openai, defina LLM_MODELO no .env com um modelo "
                           "da OpenAI ao qual sua conta tem acesso.")
    cliente = openai.OpenAI(api_key=chave)
    mensagens = [{"role": "user", "content": prompt}]
    try:
        resposta = cliente.chat.completions.create(model=modelo, messages=mensagens,
                                                   temperature=temperatura)
        aplicada = temperatura
    except openai.BadRequestError as erro:
        if "temperature" not in str(erro).lower():
            raise
        logger.warning("Modelo %s não aceita temperature=%s; repetindo sem o parâmetro",
                       modelo, temperatura)
        resposta = cliente.chat.completions.create(model=modelo, messages=mensagens)
        aplicada = None
    llm.informar_temperatura_aplicada(aplicada)

    escolha = resposta.choices[0]
    recusa = getattr(escolha.message, "refusal", None)
    if recusa or escolha.finish_reason == "content_filter":
        raise RecusaDoModelo(f"o modelo recusou a requisição: {recusa or 'content_filter'}")
    if escolha.finish_reason == "length":
        logger.warning("Resposta truncada pelo limite de tokens do modelo")
    llm.informar_modelo_servido(f"openai:{resposta.model}")
    return escolha.message.content or ""


def registrar_todos() -> None:
    llm.registrar_provedor("anthropic", provedor_anthropic, aceita_temperatura=False)
    llm.registrar_provedor("openai", provedor_openai, aceita_temperatura=True)
