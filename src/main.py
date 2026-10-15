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
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src import archive, auditoria, backup, classify, config, explain, extract, llm, news
from src.strategy import MANTER, Decisao, decidir

logger = logging.getLogger(__name__)

FUSO = ZoneInfo(config.FUSO_REFERENCIA)

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

def etapa_coletar(pasta: Path, agora: datetime, teste: bool) -> list[dict]:
    caminho = pasta / "01_coleta.json"
    if caminho.exists():
        logger.info("Coleta reaproveitada de %s", caminho)
        return _ler(caminho, [])
    if teste:
        itens = itens_de_exemplo(agora)
    else:
        itens = news.coletar_noticias(agora=agora)
        try:
            itens += news.coletar_fatos_relevantes()
        except NotImplementedError as erro:
            logger.warning("Fonte CVM indisponível (bloqueio documentado): %s", erro)
    _gravar(caminho, itens)
    return itens


def etapa_arquivar(pasta: Path, itens: list[dict], dir_arquivo: Path, agora: datetime) -> list[dict]:
    caminho = pasta / "02_arquivo.json"
    if caminho.exists():
        return _ler(caminho, [])
    novos = archive.arquivar(itens, pasta=dir_arquivo, agora=agora)
    _gravar(caminho, novos)
    return novos


def _metadados(registro: dict) -> dict:
    return {c: registro[c] for c in ("id", "tipo_fonte", "fonte", "url", "timestamp_publicacao")}


def etapa_extrair(pasta: Path, registros: list[dict]) -> dict[str, list[dict]]:
    """Extrai eventos só de registros que mencionam a carteira. Salva item a item."""
    caminho = pasta / "03_extracao.json"
    feitos = _ler(caminho, {})
    for registro in registros:
        if not registro["tickers"] or registro["id"] in feitos:
            continue
        try:
            eventos = extract.extrair_eventos(f"{registro['titulo']}\n{registro['texto']}",
                                              metadados=_metadados(registro))
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


def carregar_historico(dir_execucoes: Path, data_atual: str) -> list[dict]:
    """Eventos classificados de execuções ANTERIORES (para o filtro de evento recente)."""
    historico = []
    for pasta in sorted(p for p in dir_execucoes.glob("*") if p.is_dir() and p.name < data_atual):
        extraidos = _ler(pasta / "03_extracao.json", {})
        classificados = _ler(pasta / "04_classificacao.json", {})
        for eventos in extraidos.values():
            for evento in eventos:
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


def etapa_registrar(pasta: Path, decisoes: list[dict], explicacoes: dict[str, str],
                    arquivo_operacoes: Path, data: str) -> list[str]:
    """Registra compras e vendas no log de auditoria, uma única vez por evento."""
    caminho = pasta / "07_registro.json"
    registrados = _ler(caminho, [])
    for item in decisoes:
        evento, d = item["evento"], item["decisao"]
        if d["decisao"] == MANTER or evento["id"] in registrados:
            continue
        auditoria.registrar_operacao({
            "data": data,
            "ticker": d["ticker"],
            "evento": {k: v for k, v in evento.items() if k != "classificacao"},
            "classificacao": evento.get("classificacao"),
            "modelo": evento["modelo"],
            "versao_prompt": evento["versao_prompt"],
            "decisao": d["decisao"],
            "motivo": d["motivo"],
            "explicacao": explicacoes.get(evento["id"], ""),
        }, arquivo_operacoes)
        registrados.append(evento["id"])
        _gravar(caminho, registrados)
    return registrados


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

def executar(agora: datetime | None = None, teste: bool = False, dir_data: Path | None = None) -> dict:
    """Roda o pipeline do dia e devolve um resumo."""
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
    data = agora.date().isoformat()

    dir_data = Path(dir_data or (config.DIR_DATA / "teste" if teste else config.DIR_DATA))
    dir_execucoes = dir_data / "execucoes"
    pasta = dir_execucoes / data
    pasta.mkdir(parents=True, exist_ok=True)

    itens = etapa_coletar(pasta, agora, teste)
    novos = etapa_arquivar(pasta, itens, dir_data / "arquivo", agora)
    extraidos = etapa_extrair(pasta, novos)
    eventos = [e for lista in extraidos.values() for e in lista]
    classificacoes = etapa_classificar(pasta, eventos)
    for evento in eventos:
        evento["classificacao"] = classificacoes.get(evento["id"])
    decisoes = etapa_decidir(pasta, eventos, carregar_historico(dir_execucoes, data))
    explicacoes = etapa_explicar(pasta, decisoes)
    registrados = etapa_registrar(pasta, decisoes, explicacoes,
                                  dir_data / "operacoes.jsonl", data)

    relatorio = explain.gerar_relatorio_diario(decisoes, data)
    if teste:
        relatorio = f"{AVISO_MODO_TESTE}\n\n{relatorio}"
    (pasta / "relatorio.txt").write_text(relatorio, encoding="utf-8")

    resumo = {
        "data": data,
        "modo_teste": teste,
        "coletados": len(itens),
        "novos_arquivados": len(novos),
        "eventos_validos": len(eventos),
        "operacoes": sum(item["decisao"]["decisao"] != MANTER for item in decisoes),
        "registrados_no_log": len(registrados),
        "pasta": str(pasta),
        "backtest": "não executado: períodos PENDENTES DE APROVAÇÃO em config.py",
        "por_fonte": contar_por_fonte(itens, teste),
    }
    if not teste:
        resumo["aviso_backup"] = backup.aviso_destino(dir_data, backup.pasta_destino())
        try:
            caminho = backup.fazer_backup(dir_data)
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
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    resumo = executar(teste=args.teste)
    print(json.dumps(resumo, ensure_ascii=False, indent=2))
    print("\n" + Path(resumo["pasta"], "relatorio.txt").read_text(encoding="utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
