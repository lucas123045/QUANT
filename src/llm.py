"""Adaptador único para o LLM generativo.

- A chave vem da variável de ambiente LLM_API_KEY (ou de um arquivo .env local),
  nunca do código.
- O provedor é um ponto de configuração (LLM_PROVEDOR). Provedor real
  disponíveis: "anthropic" e "openai" (src/provedores.py). Outros podem ser registrados
  com `registrar_provedor`.
- Cada saída registra o modelo que de fato respondeu e a temperatura
  efetivamente aplicada (None quando o modelo não aceita o parâmetro).
- Modo de teste (QUANT_MODO_TESTE=1 ou LLM_PROVEDOR=falso): resposta falsa
  determinística, sem rede.
"""

import json
import logging
import os
import re
from collections.abc import Callable

from src import config

logger = logging.getLogger(__name__)

# Assinatura de um provedor: (prompt, temperatura, chave, modelo) -> texto
Provedor = Callable[[str, float, str | None, str], str]

_PROVEDORES: dict[str, Provedor] = {}
_ACEITA_TEMPERATURA: dict[str, bool] = {"falso": True}
_ultimo_modelo_servido: str | None = None
_NAO_INFORMADA = object()
_temperatura_informada: object = _NAO_INFORMADA


def carregar_env(caminho=None) -> None:
    """Carrega variáveis de um arquivo .env sem sobrescrever as já definidas."""
    caminho = caminho or (config.RAIZ_PROJETO / ".env")
    try:
        # utf-8-sig: aceita o .env com BOM (o Bloco de Notas e o PowerShell 5.1 às vezes gravam).
        linhas = open(caminho, encoding="utf-8-sig").read().splitlines()
    except FileNotFoundError:
        return
    for linha in linhas:
        linha = linha.strip()
        if not linha or linha.startswith("#") or "=" not in linha:
            continue
        nome, valor = linha.split("=", 1)
        os.environ.setdefault(nome.strip(), valor.strip().strip('"').strip("'"))


def modo_teste() -> bool:
    return os.environ.get("QUANT_MODO_TESTE", "") == "1"


def provedor_atual() -> str:
    if modo_teste():
        return "falso"
    return os.environ.get("LLM_PROVEDOR", "").strip() or "nao_definido"


def _modelo_configurado() -> str:
    modelo = os.environ.get("LLM_MODELO", "").strip()
    if not modelo and provedor_atual() == "anthropic":
        from src.provedores import MODELO_PADRAO_ANTHROPIC
        return MODELO_PADRAO_ANTHROPIC
    return modelo or "nao_definido"


def modelo_atual() -> str:
    """Modelo configurado (provedor:modelo)."""
    if provedor_atual() == "falso":
        return "falso:determinista-v1"
    return f"{provedor_atual()}:{_modelo_configurado()}"


def informar_modelo_servido(modelo: str) -> None:
    """Chamado pelo provedor quando sabe qual modelo respondeu (ex.: após fallback)."""
    global _ultimo_modelo_servido
    _ultimo_modelo_servido = modelo


def modelo_da_ultima_chamada() -> str:
    """Modelo que respondeu à última chamada de chamar_llm (ou o configurado)."""
    return _ultimo_modelo_servido or modelo_atual()


def informar_temperatura_aplicada(valor: float | None) -> None:
    """Chamado pelo provedor quando sabe a temperatura que de fato usou."""
    global _temperatura_informada
    _temperatura_informada = valor


def temperatura_efetiva(temperatura: float) -> float | None:
    """Temperatura realmente aplicada na última chamada (None se não suportada)."""
    if _temperatura_informada is not _NAO_INFORMADA:
        return _temperatura_informada
    return temperatura if _ACEITA_TEMPERATURA.get(provedor_atual(), True) else None


def registrar_provedor(nome: str, funcao: Provedor, aceita_temperatura: bool = True) -> None:
    """Registra um provedor real de LLM (ponto de extensão)."""
    _PROVEDORES[nome] = funcao
    _ACEITA_TEMPERATURA[nome] = aceita_temperatura


def _registrar_embutidos() -> None:
    if "anthropic" not in _PROVEDORES or "openai" not in _PROVEDORES:
        from src import provedores  # import local evita ciclo
        provedores.registrar_todos()


def chamar_llm(prompt: str, temperatura: float = 0.0) -> str:
    """Envia o prompt ao provedor configurado e devolve o texto da resposta."""
    global _ultimo_modelo_servido, _temperatura_informada
    _ultimo_modelo_servido = None
    _temperatura_informada = _NAO_INFORMADA
    carregar_env()
    _registrar_embutidos()
    nome = provedor_atual()
    if nome == "falso":
        return resposta_falsa(prompt)
    if nome not in _PROVEDORES:
        raise NotImplementedError(
            f"Provedor de LLM '{nome}' não implementado. Defina LLM_PROVEDOR e "
            "registre o provedor com registrar_provedor(), ou use QUANT_MODO_TESTE=1."
        )
    chave = os.environ.get("LLM_API_KEY") or None
    if not chave:
        raise RuntimeError("LLM_API_KEY não definida no ambiente (.env).")
    modelo = _modelo_configurado()
    logger.info("Chamando LLM %s (temperatura aplicada=%s)", modelo_atual(),
                temperatura_efetiva(temperatura))
    return _PROVEDORES[nome](prompt, temperatura, chave, modelo)


# ---------------------------------------------------------------------------
# Provedor falso (modo de teste): reconhece o prompt pelo identificador
# ---------------------------------------------------------------------------

def _secao(prompt: str, nome: str) -> str:
    m = re.search(rf"<<<{nome}>>>\n(.*?)\n<<<FIM_{nome}>>>", prompt, re.S)
    return m.group(1) if m else ""


_PALAVRAS_POSITIVAS = ("dividendo", "lucro", "alta", "recorde", "aprova")
_PALAVRAS_NEGATIVAS = ("queda", "prejuizo", "investigacao", "multa", "rebaixa")


def resposta_falsa(prompt: str) -> str:
    """Resposta determinística e plausível para cada tipo de prompt.

    Usa palavras-chave simples só para exercitar todos os caminhos do
    pipeline em modo de teste. Não tem valor como classificador.
    """
    from src.matching import identificar_tickers, normalizar  # import local evita ciclo

    if "PROMPT_EXTRACAO" in prompt:
        texto = _secao(prompt, "TEXTO")
        frase = re.split(r"(?<=[.!?])\s", texto.strip(), maxsplit=1)[0][:200]
        texto_norm = normalizar(texto)
        if any(p in texto_norm for p in _PALAVRAS_NEGATIVAS):
            impacto = "negativo"
        elif any(p in texto_norm for p in _PALAVRAS_POSITIVAS):
            impacto = "positivo"
        else:
            impacto = "neutro"
        eventos = [
            {
                "ticker": t,
                "tipo_evento": "outro",
                "resumo": "Evento simulado pelo provedor falso.",
                "impacto_declarado": impacto,
                "confirmado": impacto != "neutro",
                "trecho_fonte": frase,
            }
            for t in identificar_tickers(texto)
        ]
        return json.dumps({"eventos": eventos}, ensure_ascii=False)
    if "PROMPT_CLASSIFICACAO" in prompt:
        m = re.search(r"impacto declarado pelo texto: (\w+)", prompt)
        sentimento = m.group(1) if m and m.group(1) in ("positivo", "negativo") else "neutro"
        return json.dumps({"sentimento": sentimento,
                           "probabilidade": 0.8 if sentimento != "neutro" else 0.5,
                           "materialidade": "alta" if sentimento != "neutro" else "baixa",
                           "motivo_materialidade": "Materialidade simulada pelo provedor falso."})
    if "PROMPT_EXPLICACAO" in prompt or "PROMPT_RELATORIO" in prompt:
        return "Texto gerado pelo provedor falso (modo de teste)."
    return ""
