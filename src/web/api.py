"""API local da interface web.

Só leitura dos dados em data/ e disparo das ações já existentes no projeto
(coletar, pipeline de teste, pipeline real). Nenhum parâmetro congelável pode
ser alterado por aqui, e a chave de API nunca é devolvida.

Uso: python -m uvicorn src.web.api:app --host 127.0.0.1 --port 8000
(ou `npm run dev`, que sobe a API e o frontend juntos).
"""

import json
import logging
import os
import re
import threading
import traceback
import uuid
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel

from src import archive, auditoria, config, funil, llm, main, news
from src.matching import identificar_tickers

FUSO = ZoneInfo(config.FUSO_REFERENCIA)
DATA_VALIDA = re.compile(r"^\d{4}-\d{2}-\d{2}$")

app = FastAPI(title="QUANT", docs_url="/api/docs", openapi_url="/api/openapi.json")


def _dir(base: str) -> Path:
    if base not in ("real", "teste"):
        raise HTTPException(400, "base deve ser 'real' ou 'teste'")
    return config.DIR_DATA if base == "real" else config.DIR_DATA / "teste"


def _ler_json(caminho: Path, padrao):
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else padrao


# ---------------------------------------------------------------------------
# Leitura
# ---------------------------------------------------------------------------

@app.get("/api/status")
def status() -> dict:
    llm.carregar_env()
    provedor = os.environ.get("LLM_PROVEDOR", "").strip() or None
    periodos = {"treino": config.PERIODO_TREINO, "validacao": config.PERIODO_VALIDACAO,
                "teste": config.PERIODO_TESTE}
    pendencias = []
    if not os.environ.get("LLM_API_KEY"):
        pendencias.append("Configurar LLM_API_KEY no .env")
    if provedor == "openai" and not os.environ.get("LLM_MODELO"):
        pendencias.append("Definir LLM_MODELO no .env")
    if config.DATA_CORTE_CONHECIMENTO_MODELO is None:
        pendencias.append("Registrar DATA_CORTE_CONHECIMENTO_MODELO (documentação do modelo)")
    for nome, valor in periodos.items():
        if valor is None:
            pendencias.append(f"Aprovar o período de {nome}")
    if config.DATA_CONGELAMENTO is None:
        pendencias.append("Definir a data de congelamento da regra")
    pendencias += ["Verificar a cobertura da CVM (fatos relevantes)",
                   "Confirmar acesso à API do Jev",
                   "Aprovar JANELA_EVENTO_RECENTE_DIAS e ALFA_CRITERIO"]
    return {
        "provedor": provedor,
        "modelo": llm.modelo_atual() if provedor else None,
        "chave_configurada": bool(os.environ.get("LLM_API_KEY")),
        "periodos": periodos,
        "data_congelamento": config.DATA_CONGELAMENTO,
        "data_corte_modelo": config.DATA_CORTE_CONHECIMENTO_MODELO,
        "usar_jev": config.USAR_JEV,
        "carteira": [{"ticker": t, "empresa": config.NOMES_EMPRESAS[t]} for t in config.CARTEIRA],
        "pendencias": pendencias,
        "agora": datetime.now(FUSO).isoformat(),
    }


@app.get("/api/config")
def configuracao() -> dict:
    return {
        "regra": {
            "LIMIAR_PROBABILIDADE": config.LIMIAR_PROBABILIDADE,
            "MAX_POSICAO_PCT": config.MAX_POSICAO_PCT,
            "JANELA_EVENTO_RECENTE_DIAS": config.JANELA_EVENTO_RECENTE_DIAS,
            "CAPITAL_INICIAL": config.CAPITAL_INICIAL,
        },
        "criterio": {"versao": "CRITERIO_V2", "ALFA_CRITERIO": config.ALFA_CRITERIO},
        "custos": {"CORRETAGEM": config.CORRETAGEM, "EMOLUMENTOS": config.EMOLUMENTOS,
                   "SLIPPAGE": config.SLIPPAGE},
        "periodos": {"PERIODO_TREINO": config.PERIODO_TREINO,
                     "PERIODO_VALIDACAO": config.PERIODO_VALIDACAO,
                     "PERIODO_TESTE": config.PERIODO_TESTE,
                     "DATA_CONGELAMENTO": config.DATA_CONGELAMENTO},
        "outros": {"FUSO_REFERENCIA": config.FUSO_REFERENCIA, "BENCHMARK": config.BENCHMARK,
                   "SEMENTE_BASELINE_2": config.SEMENTE_BASELINE_2,
                   "N_SIMULACOES_BASELINE_2": config.N_SIMULACOES_BASELINE_2,
                   "JANELA_COLETA_HORAS": config.JANELA_COLETA_HORAS,
                   "USAR_JEV": config.USAR_JEV,
                   "DATA_CORTE_CONHECIMENTO_MODELO": config.DATA_CORTE_CONHECIMENTO_MODELO},
        "fontes_rss": config.FONTES_RSS,
        "aliases": config.ALIASES,
        "exclusoes": config.EXCLUSOES,
    }


@app.get("/api/funil")
def obter_funil(base: str = "real") -> dict:
    return funil.medir_funil(_dir(base))


@app.get("/api/noticias")
def noticias(base: str = "real", ticker: str | None = None, q: str | None = None,
             so_carteira: bool = False, limite: int = Query(300, ge=1, le=5000)) -> dict:
    registros = archive.carregar_arquivo(_dir(base) / "arquivo")
    for r in registros:
        # Casamento com as regras atuais (o campo gravado reflete as da coleta).
        r["tickers_atuais"] = identificar_tickers(f"{r['titulo']}\n{r['texto']}")
    if so_carteira:
        registros = [r for r in registros if r["tickers_atuais"]]
    if ticker:
        registros = [r for r in registros if ticker in r["tickers_atuais"]]
    if q:
        termo = q.lower()
        registros = [r for r in registros if termo in (r["titulo"] + " " + r["texto"]).lower()]
    registros.sort(key=lambda r: r.get("timestamp_publicacao") or "", reverse=True)
    return {"total": len(registros), "itens": registros[:limite]}


@app.get("/api/execucoes")
def execucoes(base: str = "real") -> list[dict]:
    pasta = _dir(base) / "execucoes"
    dias = sorted((p for p in pasta.glob("*") if p.is_dir() and DATA_VALIDA.match(p.name)),
                  reverse=True) if pasta.exists() else []
    return [{"data": p.name, "resumo": _ler_json(p / "resumo.json", None)} for p in dias]


@app.get("/api/execucoes/{data}")
def execucao(data: str, base: str = "real") -> dict:
    if not DATA_VALIDA.match(data):
        raise HTTPException(400, "data inválida")
    pasta = _dir(base) / "execucoes" / data
    if not pasta.exists():
        raise HTTPException(404, "execução não encontrada")
    relatorio = pasta / "relatorio.txt"
    return {
        "data": data,
        "resumo": _ler_json(pasta / "resumo.json", None),
        "decisoes": _ler_json(pasta / "05_decisoes.json", []),
        "explicacoes": _ler_json(pasta / "06_explicacoes.json", {}),
        "relatorio": relatorio.read_text(encoding="utf-8") if relatorio.exists() else None,
    }


@app.get("/api/operacoes")
def operacoes(base: str = "real") -> list[dict]:
    return list(reversed(auditoria.ler_operacoes(_dir(base) / "operacoes.jsonl")))


# ---------------------------------------------------------------------------
# Ações (uma por vez, em segundo plano, com log capturado)
# ---------------------------------------------------------------------------

class PedidoTarefa(BaseModel):
    tipo: str  # "coletar" | "pipeline_teste" | "pipeline_real"


_tarefas: dict[str, dict] = {}
_trava = threading.Lock()
_em_execucao: str | None = None


class _CapturaLog(logging.Handler):
    def __init__(self, tarefa: dict, thread_id: int):
        super().__init__(logging.INFO)
        self.tarefa, self.thread_id = tarefa, thread_id
        self.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s",
                                            "%H:%M:%S"))

    def emit(self, registro: logging.LogRecord) -> None:
        if registro.thread == self.thread_id:
            self.tarefa["logs"].append(self.format(registro))


def _executar_tarefa(tarefa: dict) -> None:
    global _em_execucao
    raiz = logging.getLogger()
    nivel_anterior = raiz.level
    raiz.setLevel(logging.INFO)
    captura = _CapturaLog(tarefa, threading.get_ident())
    raiz.addHandler(captura)
    try:
        if tarefa["tipo"] == "coletar":
            novos = archive.arquivar(news.coletar_noticias())
            tarefa["resultado"] = {"novos_arquivados": len(novos),
                                   "mencionam_carteira": sum(bool(r["tickers"]) for r in novos)}
        else:
            tarefa["resultado"] = main.executar(teste=tarefa["tipo"] == "pipeline_teste")
        tarefa["estado"] = "concluida"
    except Exception as erro:  # a interface mostra o erro; nada derruba a API
        tarefa["estado"] = "erro"
        tarefa["erro"] = f"{type(erro).__name__}: {erro}"
        tarefa["logs"].append(traceback.format_exc())
    finally:
        raiz.removeHandler(captura)
        raiz.setLevel(nivel_anterior)
        tarefa["fim"] = datetime.now(FUSO).isoformat()
        with _trava:
            _em_execucao = None


@app.post("/api/tarefas", status_code=202)
def criar_tarefa(pedido: PedidoTarefa) -> dict:
    global _em_execucao
    if pedido.tipo not in ("coletar", "pipeline_teste", "pipeline_real"):
        raise HTTPException(400, "tipo de tarefa desconhecido")
    with _trava:
        if _em_execucao is not None:
            raise HTTPException(409, "já existe uma tarefa em execução")
        tarefa = {"id": uuid.uuid4().hex[:12], "tipo": pedido.tipo, "estado": "executando",
                  "inicio": datetime.now(FUSO).isoformat(), "fim": None, "logs": [],
                  "resultado": None, "erro": None}
        _tarefas[tarefa["id"]] = tarefa
        _em_execucao = tarefa["id"]
    threading.Thread(target=_executar_tarefa, args=(tarefa,), daemon=True).start()
    return tarefa


@app.get("/api/tarefas")
def listar_tarefas() -> list[dict]:
    return sorted(_tarefas.values(), key=lambda t: t["inicio"], reverse=True)[:20]


@app.get("/api/tarefas/{tarefa_id}")
def obter_tarefa(tarefa_id: str) -> dict:
    if tarefa_id not in _tarefas:
        raise HTTPException(404, "tarefa não encontrada")
    return _tarefas[tarefa_id]
