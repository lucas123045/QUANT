"""Alerta no celular quando a regra registra uma compra ou venda.

O QUANT como apoio à decisão: ele avisa, com o motivo, e a pessoa decide.

Dois canais, ambos opcionais (variáveis de ambiente no .env ou nos segredos do
GitHub; sem nenhuma, nada é enviado):
- ntfy (https://ntfy.sh): sem cadastro. Instale o app ntfy, assine um tópico
  com nome difícil de adivinhar (quem souber o nome lê os alertas) e ponha o
  mesmo nome em QUANT_NTFY_TOPICO. QUANT_NTFY_SERVIDOR troca o servidor.
- Telegram: crie um bot com o @BotFather e defina QUANT_TELEGRAM_TOKEN e
  QUANT_TELEGRAM_CHAT (o id da sua conversa com o bot).

QUANT_ALERTAS_TICKERS (opcional, ex.: "PETR4,ITUB4"): só avisa dessas ações, as
que a pessoa tem (a página Minhas ações gera a lista). Só os códigos, sem
quantidade nem valor: as posições continuam só no navegador.

Falha no envio vira aviso no log: nunca derruba o pipeline. Não manda a chave
do LLM nem nada além da decisão e do motivo.
"""

import json
import logging
import os
import urllib.request

from src import config, rede

logger = logging.getLogger(__name__)
TIMEOUT = 15


def canais() -> list[str]:
    lista = []
    if os.environ.get("QUANT_NTFY_TOPICO", "").strip():
        lista.append("ntfy")
    if os.environ.get("QUANT_TELEGRAM_TOKEN", "").strip() and os.environ.get("QUANT_TELEGRAM_CHAT", "").strip():
        lista.append("telegram")
    return lista


def tickers_filtrados() -> set[str] | None:
    """Ações que a pessoa quer acompanhar no celular (None: todas)."""
    tickers = {t.strip().upper() for t in os.environ.get("QUANT_ALERTAS_TICKERS", "").split(",") if t.strip()}
    return tickers or None


def mensagem(registro: dict) -> tuple[str, str]:
    """(título, texto) de uma decisão registrada no log de auditoria."""
    decisao = registro["decisao"].upper()
    ticker = registro["ticker"]
    evento = registro.get("evento") or {}
    origem = evento.get("origem") or {}
    titulo = f"QUANT: {decisao} {ticker} ({config.NOMES_EMPRESAS.get(ticker, ticker)})"
    linhas = [evento.get("resumo") or "", "", f"Motivo da regra: {registro.get('motivo', '')}"]
    criterios = registro.get("criterios") or []
    if criterios:
        linhas.append("")
        linhas += [f"{'✓' if c.get('ok') else '✗' if c.get('ok') is False else '–'} {c.get('criterio')}"
                   for c in criterios]
    linhas += ["", "Execução simulada no fechamento do próximo pregão. Simulação com dinheiro fictício: "
               "não é recomendação de investimento."]
    if origem.get("url"):
        linhas += ["", f"Fonte: {origem.get('fonte', '')} - {origem['url']}"]
    return titulo, "\n".join(linhas).strip()


def _postar(url: str, corpo: bytes, cabecalhos: dict) -> None:
    pedido = urllib.request.Request(url, data=corpo, method="POST", headers=cabecalhos)
    with urllib.request.urlopen(pedido, timeout=TIMEOUT, context=rede.contexto_ssl()) as resposta:
        resposta.read()


def _ntfy(titulo: str, texto: str, clique: str | None) -> None:
    # Publicação em JSON (na raiz do servidor): título com acento não cabe em cabeçalho HTTP.
    servidor = os.environ.get("QUANT_NTFY_SERVIDOR", "https://ntfy.sh").rstrip("/")
    corpo = {"topic": os.environ["QUANT_NTFY_TOPICO"].strip(), "title": titulo, "message": texto,
             "tags": ["chart_with_upwards_trend"]}
    if clique:
        corpo["click"] = clique
    _postar(servidor, json.dumps(corpo).encode("utf-8"), {"Content-Type": "application/json"})


def _telegram(titulo: str, texto: str) -> None:
    token = os.environ["QUANT_TELEGRAM_TOKEN"].strip()
    corpo = json.dumps({"chat_id": os.environ["QUANT_TELEGRAM_CHAT"].strip(), "text": f"{titulo}\n\n{texto}",
                        "disable_web_page_preview": True}).encode("utf-8")
    _postar(f"https://api.telegram.org/bot{token}/sendMessage", corpo, {"Content-Type": "application/json"})


def enviar(registros: list[dict]) -> dict:
    """Envia um alerta por decisão registrada. Devolve {"enviados", "falhas", "canais"}."""
    lista = canais()
    enviados = falhas = 0
    filtro = tickers_filtrados()
    if filtro is not None:
        registros = [r for r in registros if r.get("ticker") in filtro]
    if not lista or not registros:
        return {"enviados": 0, "falhas": 0, "canais": lista}
    for registro in registros:
        titulo, texto = mensagem(registro)
        if filtro is not None:
            titulo += " · você tem esta ação"
        clique = ((registro.get("evento") or {}).get("origem") or {}).get("url")
        for canal in lista:
            try:
                _ntfy(titulo, texto, clique) if canal == "ntfy" else _telegram(titulo, texto)
                enviados += 1
            except Exception as erro:  # noqa: BLE001 - alerta é opcional
                falhas += 1
                # Sem a URL: no Telegram ela contém o token do bot.
                logger.warning("Alerta por %s falhou: %s", canal, type(erro).__name__)
    return {"enviados": enviados, "falhas": falhas, "canais": lista}
