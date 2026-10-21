"""Ponto de entrada das tarefas agendadas (Agendador de Tarefas do Windows).

Chamado pelo pythonw.exe (sem janela). Grava o log em data/agendamento.log, em
UTF-8, e o renomeia para .old ao passar de 5 MB. Antes, as tarefas passavam pelo
PowerShell 5.1, cujo redirecionamento gravava o log em UTF-16 misturado e
devolvia código de erro sempre que o Python escrevia no stderr (o log normal).

Uso: pythonw -m src.agendado pipeline | coleta | vitrine
"""

import argparse
import json
import logging
import os
import traceback

from src import config

LIMITE_LOG_BYTES = 5 * 1024 * 1024
logger = logging.getLogger("agendado")


def caminho_log():
    return config.DIR_DATA / "agendamento.log"


def _configurar_log() -> None:
    log = caminho_log()
    log.parent.mkdir(parents=True, exist_ok=True)
    if log.exists() and log.stat().st_size > LIMITE_LOG_BYTES:
        log.replace(log.with_name(log.name + ".old"))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.FileHandler(log, encoding="utf-8")], force=True)
    logging.captureWarnings(True)


def _pipeline() -> None:
    from src import llm, main
    llm.carregar_env()
    if llm.provedor_atual() != "falso" and not os.environ.get("LLM_API_KEY"):
        # Computador novo sem a chave no .env: as notícias continuam sendo coletadas;
        # quando a chave for configurada, a próxima execução analisa as que estiverem na coleta.
        logger.warning("LLM_API_KEY não configurada no .env: só coleta, sem análise da IA.")
        _coleta()
        return
    try:
        resumo = main.executar()
    except main.PipelineEmExecucao as aviso:  # botão da interface rodando: não é falha
        logger.info("%s", aviso)
        return
    campos = ("coletados", "novos_arquivados", "eventos_validos", "operacoes", "por_fonte", "backup")
    logger.info("resumo: %s", json.dumps({c: resumo.get(c) for c in campos}, ensure_ascii=False))


def _coleta() -> None:
    from src import archive, news
    novos = archive.arquivar(news.coletar_noticias())
    logger.info("coleta: %d novos (%d mencionam a carteira)", len(novos), sum(bool(r["tickers"]) for r in novos))


def _vitrine() -> None:
    from src.web import exportar
    resumo = exportar.exportar()  # VitrineEncolheu sobe e vira falha no log
    logger.info("vitrine: %s", json.dumps(resumo["bases"], ensure_ascii=False))


def _sincronizar() -> None:
    from src import sincronizar
    sincronizar.sincronizar()  # o resumo vai para o log


TAREFAS = {"pipeline": _pipeline, "coleta": _coleta, "vitrine": _vitrine, "sincronizar": _sincronizar}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Tarefas agendadas do QUANT.")
    parser.add_argument("tarefa", choices=sorted(TAREFAS))
    args = parser.parse_args(argv)
    _configurar_log()
    logger.info("==== início: %s", args.tarefa)
    try:
        TAREFAS[args.tarefa]()
    except Exception:  # registra tudo no log: ninguém vê a tela de uma tarefa agendada
        logger.error("==== fim: %s (FALHOU)\n%s", args.tarefa, traceback.format_exc())
        return 1
    logger.info("==== fim: %s (ok)", args.tarefa)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
