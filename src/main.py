"""Pipeline diário em lote.

coletar → arquivar → extrair (com validação do trecho) → classificar →
decidir → explicar → registrar → relatório.

A explicação vem antes do registro porque o log de auditoria exige o campo
`explicacao`. Cada etapa grava seu resultado em data/execucoes/AAAA-MM-DD/;
ao rodar de novo no mesmo dia, as etapas e itens já gravados são reaproveitados
sem novas chamadas ao LLM.

Uso:
    python -m src.main            # execução real (rede e LLM configurado)
    python -m src.main --teste    # sem rede e sem LLM real, em data/teste/
    QUANT_MODO_TESTE=1 python -m src.main   # equivalente a --teste
"""

import argparse
import json
import logging
import os
import time
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src import alertas, archive, auditoria, backup, classify, config, explain, extract, llm, news
from src.strategy import MANTER, VERSAO_REGRA, Decisao, decidir

logger = logging.getLogger(__name__)

FUSO = ZoneInfo(config.FUSO_REFERENCIA)
# Rodando a cada hora: no máximo um backup a cada tantas horas.
INTERVALO_BACKUP_HORAS = 6
# Trava de uma execução que morreu sem apagá-la deixa de valer depois disso.
VALIDADE_TRAVA_HORAS = 2

AVISO_MODO_TESTE = ("*** MODO DE TESTE: notícias de exemplo e LLM falso por palavras-chave. "
                    "NÃO USAR ESTE RELATÓRIO EM NENHUMA CONCLUSÃO DO TRABALHO. ***")


# ---------------------------------------------------------------------------
# Persistência das etapas
# ---------------------------------------------------------------------------

def _ler(caminho: Path, padrao):
    if caminho.exists():
        return json.loads(caminho.read_text(encoding="utf-8"))
    return padrao


def _gravar(caminho: Path, dados) -> None:
    """Grava de forma atômica (arquivo temporário + renomear)."""
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(json.dumps(dados, ensure_ascii=False, indent=2, default=str),
                          encoding="utf-8")
    temporario.replace(caminho)


# ---------------------------------------------------------------------------
# Dados de exemplo para o modo de teste (sem rede)
# ---------------------------------------------------------------------------

def itens_de_exemplo(agora: datetime) -> list[dict]:
    publicado = (agora - timedelta(hours=2)).isoformat()
    base = {"tipo_fonte": "noticia", "fonte": "Exemplo (modo de teste)",
            "timestamp_publicacao": publicado, "timestamp_coleta": agora.isoformat()}
    return [
        {**base, "url": "https://exemplo.teste/petrobras-dividendos",
         "titulo": "Petrobras aprova dividendos extraordinários",
         "texto": "A Petrobras aprovou o pagamento de dividendos extraordinários. "
                  "O valor será pago em dezembro."},
        {**base, "url": "https://exemplo.teste/vale-investigacao",
         "titulo": "Lucro da Vale é alvo de investigação",
         "texto": "A Vale informou que é alvo de investigação sobre barragens. "
                  "A empresa diz colaborar com as autoridades."},
        {**base, "url": "https://exemplo.teste/cdb",
         "titulo": "Vale a pena investir em CDB?",
         "texto": "Especialistas comparam renda fixa e poupança."},
    ]


# ---------------------------------------------------------------------------
# Etapas
# ---------------------------------------------------------------------------

def _unir_por_url(antigos: list[dict], novos: list[dict]) -> list[dict]:
    """Acrescenta os itens de URL ainda não vista (nem entre os novos), preservando os antigos."""
    vistas = {i.get("url") for i in antigos}
    unidos = list(antigos)
    for item in novos:
        if item.get("url") not in vistas:
            vistas.add(item.get("url"))
            unidos.append(item)
    return unidos


def etapa_coletar(pasta: Path, agora: datetime, teste: bool) -> list[dict]:
    """Coleta e acumula no arquivo do dia.

    O pipeline pode rodar várias vezes por dia (ex.: a cada hora): cada execução
    coleta de novo e soma ao que já foi coletado no dia. Coletar não usa o LLM,
    então repetir não tem custo; as etapas seguintes só tratam o que é novo.
    """
    caminho = pasta / "01_coleta.json"
    anteriores = _ler(caminho, [])
    if teste:
        itens = itens_de_exemplo(agora)
    else:
        itens = news.coletar_noticias(agora=agora)
        try:
            itens += news.coletar_fatos_relevantes(agora=agora, dir_data=pasta.parent.parent)
        except Exception as erro:  # noqa: BLE001 - CVM fora do ar não pode parar a coleta de notícias
            logger.warning("Fatos relevantes da CVM indisponíveis nesta coleta: %s", erro)
    todos = _unir_por_url(anteriores, itens)
    if anteriores:
        logger.info("Coleta: %d itens novos nesta execução (%d no dia)", len(todos) - len(anteriores), len(todos))
    _gravar(caminho, todos)
    return todos


def etapa_arquivar(pasta: Path, itens: list[dict], dir_arquivo: Path, agora: datetime) -> list[dict]:
    """Arquiva o que é novo e devolve tudo o que esta pasta do dia já arquivou."""
    caminho = pasta / "02_arquivo.json"
    novos = archive.arquivar(itens, pasta=dir_arquivo, agora=agora)
    do_dia = _unir_por_url(_ler(caminho, []), novos)
    _gravar(caminho, do_dia)
    return do_dia


def registros_para_extrair(itens: list[dict], novos: list[dict], dir_arquivo: Path,
                           dir_execucoes: Path, data_atual: str) -> list[dict]:
    """Registros desta coleta que ainda não passaram pela extração.

    Além dos arquivados agora, inclui os que já estavam no arquivo sem ter sido
    extraídos em nenhuma execução anterior: por exemplo, notícias coletadas antes
    no mesmo dia por `archive --coletar` (ou pelo botão da interface). Sem isso,
    elas seriam tratadas como "já vistas" e nunca chegariam ao LLM.
    """
    urls = {i["url"] for i in itens if i.get("url")}
    ja_extraidos: set[str] = set()
    for pasta in dir_execucoes.glob("*"):
        if pasta.is_dir() and pasta.name != data_atual:
            ja_extraidos.update(_ler(pasta / "03_extracao.json", {}))
    ids_novos = {r["id"] for r in novos}
    antigos = [r for r in archive.carregar_arquivo(dir_arquivo)
               if r["tickers"] and r["url"] in urls
               and r["id"] not in ids_novos and r["id"] not in ja_extraidos]
    return novos + antigos


def _metadados(registro: dict) -> dict:
    # timestamp_coleta: quando o QUANT soube do fato (critério "fato novo" da REGRA_V3).
    return {c: registro[c] for c in ("id", "tipo_fonte", "fonte", "url", "timestamp_publicacao", "timestamp_coleta")
            if c in registro}


def etapa_extrair(pasta: Path, registros: list[dict], tickers_do_registro: bool = False) -> dict[str, list[dict]]:
    """Extrai eventos só de registros que mencionam a carteira. Salva item a item.

    `tickers_do_registro`: pede ao LLM só as empresas do próprio registro (estudo
    histórico com o universo ampliado). Ao vivo, a lista é a da carteira.
    """
    caminho = pasta / "03_extracao.json"
    feitos = _ler(caminho, {})
    for registro in registros:
        if not registro["tickers"] or registro["id"] in feitos:
            continue
        try:
            eventos = extract.extrair_eventos(f"{registro['titulo']}\n{registro['texto']}",
                                              metadados=_metadados(registro),
                                              tickers=registro["tickers"] if tickers_do_registro else None)
        except Exception as erro:  # LLM fora do ar: segue e tenta de novo na próxima execução
            logger.error("Extração falhou para %s: %s", registro["url"], erro)
            continue
        for i, evento in enumerate(eventos):
            evento["id"] = f"{registro['id']}-{i}"
        feitos[registro["id"]] = eventos
        _gravar(caminho, feitos)
    return feitos


def etapa_classificar(pasta: Path, eventos: list[dict]) -> dict[str, dict | None]:
    caminho = pasta / "04_classificacao.json"
    feitos = _ler(caminho, {})
    for evento in eventos:
        if evento["id"] in feitos:
            continue
        try:
            feitos[evento["id"]] = classify.classificar(evento)
        except Exception as erro:
            logger.error("Classificação falhou para %s: %s", evento["id"], erro)
            continue
        _gravar(caminho, feitos)
    return feitos


def do_prompt_vigente(evento: dict) -> bool:
    """Evento extraído com o prompt atual? Os de prompts anteriores ficam gravados para
    auditoria, mas a regra vigente não decide sobre eles nem os usa como histórico:
    com o PROMPT_EXTRACAO_V1, resumos de cotação saíam como "outro" e a REGRA_V2
    os trataria como fatos."""
    return evento.get("versao_prompt") == extract.VERSAO_PROMPT_EXTRACAO


def carregar_historico(dir_execucoes: Path, data_atual: str) -> list[dict]:
    """Eventos classificados de execuções ANTERIORES, do prompt vigente (filtro de evento recente)."""
    historico = []
    for pasta in sorted(p for p in dir_execucoes.glob("*") if p.is_dir() and p.name < data_atual):
        extraidos = _ler(pasta / "03_extracao.json", {})
        classificados = _ler(pasta / "04_classificacao.json", {})
        for eventos in extraidos.values():
            for evento in eventos:
                if do_prompt_vigente(evento):
                    historico.append({**evento, "classificacao": classificados.get(evento["id"])})
    return historico


def etapa_decidir(pasta: Path, eventos: list[dict], historico: list[dict]) -> list[dict]:
    """Decisão determinística (sem LLM). Barata: recalculada a cada execução."""
    ordenados = sorted(eventos, key=lambda e: e["origem"]["timestamp_publicacao"])
    decisoes = []
    for i, evento in enumerate(ordenados):
        anteriores = historico + ordenados[:i]
        decisao = decidir(evento, evento.get("classificacao"), anteriores)
        decisoes.append({"evento": evento, "decisao": decisao.como_dict()})
    _gravar(pasta / "05_decisoes.json", decisoes)
    return decisoes


def etapa_explicar(pasta: Path, decisoes: list[dict]) -> dict[str, str]:
    caminho = pasta / "06_explicacoes.json"
    feitos = _ler(caminho, {})
    for item in decisoes:
        evento, d = item["evento"], item["decisao"]
        if d["decisao"] == MANTER or evento["id"] in feitos:
            continue
        feitos[evento["id"]] = explain.gerar_justificativa(
            Decisao(**d), evento, evento.get("classificacao"))
        _gravar(caminho, feitos)
    return feitos


def etapa_relatorio(pasta: Path, decisoes: list[dict], data: str, teste: bool) -> str:
    """Relatório do dia, refeito só quando as decisões mudam.

    O resumo do relatório é escrito pelo LLM: com o pipeline rodando a cada 30
    minutos, refazê-lo sem decisões novas seria uma chamada paga à toa a cada vez.
    """
    caminho, marca = pasta / "relatorio.txt", pasta / "08_relatorio.json"
    assinatura = json.dumps([[d["evento"]["id"], d["decisao"]["decisao"], d["decisao"]["motivo"]]
                             for d in decisoes], ensure_ascii=False)
    if caminho.exists() and _ler(marca, {}).get("decisoes") == assinatura:
        return caminho.read_text(encoding="utf-8")
    relatorio = explain.gerar_relatorio_diario(decisoes, data)
    if teste:
        relatorio = f"{AVISO_MODO_TESTE}\n\n{relatorio}"
    caminho.write_text(relatorio, encoding="utf-8")
    _gravar(marca, {"decisoes": assinatura})
    return relatorio


def etapa_registrar(pasta: Path, decisoes: list[dict], explicacoes: dict[str, str],
                    arquivo_operacoes: Path, data: str, novos: list[dict] | None = None) -> list[str]:
    """Registra compras e vendas no log de auditoria, uma única vez por evento.

    `novos` (opcional) recebe os registros gravados nesta chamada, para os alertas.
    """
    caminho = pasta / "07_registro.json"
    registrados = _ler(caminho, [])
    for item in decisoes:
        evento, d = item["evento"], item["decisao"]
        if d["decisao"] == MANTER or evento["id"] in registrados:
            continue
        registro = auditoria.registrar_operacao({
            "data": data,
            "ticker": d["ticker"],
            "evento": {k: v for k, v in evento.items() if k != "classificacao"},
            "classificacao": evento.get("classificacao"),
            "modelo": evento["modelo"],
            "versao_prompt": evento["versao_prompt"],
            "decisao": d["decisao"],
            "motivo": d["motivo"],
            "explicacao": explicacoes.get(evento["id"], ""),
            "versao_regra": d["versao_regra"],
            "criterios": d.get("criterios", []),
        }, arquivo_operacoes)
        if novos is not None:
            novos.append(registro)
        registrados.append(evento["id"])
        _gravar(caminho, registrados)
    return registrados


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

class PipelineEmExecucao(RuntimeError):
    """Já há outra execução do pipeline em andamento nesta pasta de dados."""


@contextmanager
def _trava(dir_data: Path):
    """Uma execução por vez por pasta de dados (agendamento + botão da interface).

    Trava esquecida por uma execução que morreu expira depois de VALIDADE_TRAVA_HORAS.
    """
    dir_data.mkdir(parents=True, exist_ok=True)
    caminho = dir_data / ".pipeline.lock"
    if caminho.exists() and time.time() - caminho.stat().st_mtime > VALIDADE_TRAVA_HORAS * 3600:
        logger.warning("Trava antiga removida (%s): a execução anterior não terminou", caminho)
        caminho.unlink(missing_ok=True)
    try:
        descritor = os.open(caminho, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise PipelineEmExecucao("Outra execução do pipeline está em andamento; esta foi pulada.") from None
    os.write(descritor, str(os.getpid()).encode())
    os.close(descritor)
    try:
        yield
    finally:
        caminho.unlink(missing_ok=True)


def executar(agora: datetime | None = None, teste: bool = False, dir_data: Path | None = None) -> dict:
    """Roda o pipeline (pode ser várias vezes por dia) e devolve um resumo."""
    if not teste or llm.modo_teste():
        return _executar(agora, teste or llm.modo_teste(), dir_data)
    # --teste: liga o provedor falso só durante esta execução.
    os.environ["QUANT_MODO_TESTE"] = "1"
    try:
        return _executar(agora, True, dir_data)
    finally:
        del os.environ["QUANT_MODO_TESTE"]


def _executar(agora: datetime | None, teste: bool, dir_data: Path | None) -> dict:
    agora = (agora or datetime.now(FUSO)).astimezone(FUSO)
    dir_data = Path(dir_data or (config.DIR_DATA / "teste" if teste else config.DIR_DATA))
    with _trava(dir_data):
        return _rodar(agora, teste, dir_data)


def _rodar(agora: datetime, teste: bool, dir_data: Path) -> dict:
    from src import congelamento  # import local: congelamento importa strategy e os prompts
    verificacao = congelamento.verificar()
    if verificacao["estado"] in ("alterada", "sem_registro"):
        logger.error("A regra não é mais a congelada: %s. As decisões seguem registradas, mas não valem "
                     "como teste.", "; ".join(verificacao["problemas"]))
    data = agora.date().isoformat()
    dir_execucoes = dir_data / "execucoes"
    pasta = dir_execucoes / data
    pasta.mkdir(parents=True, exist_ok=True)

    itens = etapa_coletar(pasta, agora, teste)
    novos = etapa_arquivar(pasta, itens, dir_data / "arquivo", agora)
    a_extrair = registros_para_extrair(itens, novos, dir_data / "arquivo", dir_execucoes, data)
    extraidos = etapa_extrair(pasta, a_extrair)
    # Só os eventos do prompt vigente seguem para a classificação e a regra.
    eventos = [e for lista in extraidos.values() for e in lista if do_prompt_vigente(e)]
    classificacoes = etapa_classificar(pasta, eventos)
    for evento in eventos:
        evento["classificacao"] = classificacoes.get(evento["id"])
    decisoes = etapa_decidir(pasta, eventos, carregar_historico(dir_execucoes, data))
    explicacoes = etapa_explicar(pasta, decisoes)
    novos_no_log: list[dict] = []
    registrados = etapa_registrar(pasta, decisoes, explicacoes,
                                  dir_data / "operacoes.jsonl", data, novos_no_log)
    # Alerta no celular (se configurado): só decisões novas e só na base real.
    avisos_enviados = None if teste else alertas.enviar(novos_no_log)

    etapa_relatorio(pasta, decisoes, data, teste)

    resumo = {
        "data": data,
        "versao_regra": VERSAO_REGRA,
        "versao_prompt": extract.VERSAO_PROMPT_EXTRACAO,
        "modo_teste": teste,
        "coletados": len(itens),
        "novos_arquivados": len(novos),
        "ja_arquivados_sem_extracao": len(a_extrair) - len(novos),
        "eventos_validos": len(eventos),
        "operacoes": sum(item["decisao"]["decisao"] != MANTER for item in decisoes),
        "registrados_no_log": len(registrados),
        "pasta": str(pasta),
        "backtest": "não executado: períodos PENDENTES DE APROVAÇÃO em config.py",
        "por_fonte": contar_por_fonte(itens, teste),
        "alertas": avisos_enviados,
    }
    if not teste:
        destino = backup.pasta_destino()
        resumo["aviso_backup"] = backup.aviso_destino(dir_data, destino)
        ultimo = backup.ultimo_backup(destino)
        try:
            if ultimo and agora.replace(tzinfo=None) - ultimo < timedelta(hours=INTERVALO_BACKUP_HORAS):
                # Rodando a cada hora, seriam 24 ZIPs por dia: um a cada poucas horas basta.
                resumo["backup"] = f"mantido o de {ultimo:%d/%m %H:%M} (um a cada {INTERVALO_BACKUP_HORAS} h)"
            else:
                caminho = backup.fazer_backup(dir_data, destino, agora)
                resumo["backup"] = str(caminho) if caminho else None
        except Exception as erro:  # backup falhar não pode derrubar o pipeline
            logger.error("Backup falhou: %s", erro)
            resumo["backup"] = f"falhou: {erro}"
    _gravar(pasta / "resumo.json", resumo)
    return resumo


def contar_por_fonte(itens: list[dict], teste: bool) -> dict[str, int]:
    """Itens coletados por fonte; fontes configuradas sem itens aparecem com 0."""
    contagem = {} if teste else {f["nome"]: 0 for f in config.FONTES_RSS}
    for item in itens:
        contagem[item["fonte"]] = contagem.get(item["fonte"], 0) + 1
    return contagem


def fontes_mudas(dir_execucoes: Path, seguidas: int = 2) -> list[str]:
    """Fontes com 0 itens nas últimas `seguidas` execuções (portal mudou ou caiu?)."""
    resumos = []
    for pasta in sorted((p for p in dir_execucoes.glob("*") if p.is_dir()), reverse=True):
        resumo = _ler(pasta / "resumo.json", None)
        if resumo and resumo.get("por_fonte") and not resumo.get("modo_teste"):
            resumos.append(resumo["por_fonte"])
        if len(resumos) == seguidas:
            break
    if len(resumos) < seguidas:
        return []
    return sorted(nome for nome in resumos[0] if all(r.get(nome, 0) == 0 for r in resumos))


# Coleta com buraco maior que isto nas últimas 24 h: a notícia chega atrasada.
INTERVALO_MAXIMO_COLETA = timedelta(minutes=90)


def alertas_agenda(dir_arquivo: Path, agora: datetime | None = None) -> list[str]:
    """A coleta está rodando na frequência prevista (a cada 30 minutos)?

    Cada hora sem coleta é uma hora de atraso a mais entre a notícia e a decisão.
    Na nuvem, o agendador do GitHub atrasa ou pula execuções; um agendador
    externo (cron-job.org chamando /api/nuvem?agendar=...) resolve.
    """
    agora = (agora or datetime.now(FUSO)).astimezone(FUSO)
    instantes = [i.astimezone(FUSO) for i in archive.coletas(dir_arquivo)]
    if not instantes:
        return []
    inicio = agora - timedelta(hours=24)
    janela = [i for i in instantes if i >= inicio]
    pontos = ([max([i for i in instantes if i < inicio], default=inicio)] if instantes[0] < inicio else []) \
        + janela + [agora]
    maior, de, ate = timedelta(0), None, None
    for a, b in zip(pontos, pontos[1:]):
        if b - a > maior:
            maior, de, ate = b - a, a, b
    if maior <= INTERVALO_MAXIMO_COLETA:
        return []
    horas = f"{maior.total_seconds() / 3600:.1f}".replace(".", ",")
    trecho = f"de {de:%d/%m %H:%M} a {ate:%d/%m %H:%M}" if ate != agora else f"desde {de:%d/%m %H:%M}"
    feitas = f"{len(janela)} coleta" + ("" if len(janela) == 1 else "s")
    return [f"A coleta ficou {horas} h sem rodar ({trecho}); nas últimas 24 h foram {feitas}, e o previsto "
            "é uma a cada 30 minutos. Cada hora sem coleta atrasa as decisões. Na nuvem, configure o "
            "agendador externo (README, seção Tempo real na nuvem)."]


def alertas_backup(dir_execucoes: Path) -> list[str]:
    """Avisos de localidade ou falha do último backup real."""
    for pasta in sorted((p for p in dir_execucoes.glob("*") if p.is_dir()), reverse=True):
        resumo = _ler(pasta / "resumo.json", None)
        if not resumo or resumo.get("modo_teste"):
            continue
        alertas = []
        if resumo.get("aviso_backup"):
            alertas.append(resumo["aviso_backup"])
        if isinstance(resumo.get("backup"), str) and resumo["backup"].startswith("falhou:"):
            alertas.append(f"O último backup automático falhou: {resumo['backup'][8:]}")
        return alertas
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Pipeline diário QUANT.")
    parser.add_argument("--teste", action="store_true",
                        help="modo de teste: sem rede e sem LLM real; grava em data/teste/")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        resumo = executar(teste=args.teste)
    except PipelineEmExecucao as erro:  # agendamento e botão ao mesmo tempo: não é falha
        print(erro)
        return 0
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    print("\n" + Path(resumo["pasta"], "relatorio.txt").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
