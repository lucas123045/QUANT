"""Estudo histórico com os fatos relevantes da CVM: amostra sem esperar meses.

A pergunta central do QUANT ("o preço reage à notícia a tempo de aproveitar?")
precisa de dezenas de eventos. Ao vivo, isso leva meses. Mas os fatos
relevantes entregues à CVM estão todos nos dados abertos, e os entregues depois
do corte de conhecimento do modelo não podem ter o desfecho conhecido pela IA.

Como evita olhar o futuro:
- só fatos com entrega a partir de `desde`, que deve ser posterior ao corte do
  modelo (gpt-4.1: 01/06/2024, documentação da OpenAI); antes disso, recusa;
- cada fato entra como se o QUANT o tivesse coletado no dia da entrega
  (timestamp_coleta = entrega, 23h59: execução no fechamento do pregão seguinte);
- dia a dia, em ordem: a extração, a classificação e a regra vigente usam só o
  histórico anterior, exatamente como no pipeline ao vivo;
- base separada (config.DIR_HISTORICO, versionada no repositório): não se
  mistura à carteira nem às decisões ao vivo.

Custo: uma extração e uma classificação por fato (sem explicação em texto).
`--estimar` mostra quantos fatos e o custo aproximado antes de chamar a IA.
Rodar de novo não paga de novo: extrações e classificações ficam gravadas.

Uso:
    python -m src.historico --desde 2025-01-01 --estimar
    python -m src.historico --desde 2025-01-01
"""

import argparse
import json
import logging
from collections import defaultdict
from datetime import date, datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

from src import archive, config, cvm, extract, llm, main
from src.strategy import VERSAO_REGRA

logger = logging.getLogger(__name__)
FUSO = ZoneInfo(config.FUSO_REFERENCIA)
# Corte de conhecimento documentado do modelo do projeto, se config.py ainda não o registra.
CORTE_DOCUMENTADO = {"gpt-4.1-2025-04-14": "2024-06-01"}
# Preço de referência do gpt-4.1 (US$ por milhão de tokens), só para a estimativa.
PRECO_ENTRADA, PRECO_SAIDA = 2.00, 8.00
CARACTERES_POR_TOKEN = 3.5


def pasta_historico() -> Path:
    return config.DIR_HISTORICO


def corte_do_modelo() -> date | None:
    valor = config.DATA_CORTE_CONHECIMENTO_MODELO or CORTE_DOCUMENTADO.get(llm.modelo_atual().split(":")[-1])
    return date.fromisoformat(valor) if valor else None


def universo() -> tuple[dict[str, str], dict[str, str]]:
    """(CNPJ -> ticker, ticker -> nome): a carteira mais o universo ampliado do estudo."""
    cnpjs = dict(config.CNPJ_CARTEIRA)
    nomes = dict(config.NOMES_EMPRESAS)
    for cnpj, (ticker, nome) in config.UNIVERSO_ESTUDO.items():
        cnpjs[cnpj], nomes[ticker] = ticker, nome
    return cnpjs, nomes


def fatos(desde: date, ate: date, pasta_cache: Path, baixar=None) -> list[dict]:
    linhas = []
    for ano in range(desde.year, ate.year + 1):
        linhas += cvm.linhas_do_arquivo(cvm.baixar_arquivo_anual(ano, pasta_cache, baixar))
    return [f for f in cvm.fatos_da_carteira(linhas, desde, universo()[0]) if f["entrega"] <= ate]


def itens(fatos_cvm: list[dict], conhecidas: set[str], baixar_documento=None) -> list[dict]:
    """Itens no formato da coleta, coletados "no dia da entrega"."""
    baixar_documento = baixar_documento or (lambda url: cvm.rede.baixar(url, 60, cvm.USER_AGENT))
    lista = []
    for fato in fatos_cvm:
        url = fato["Link_Download"].strip()
        if url in conhecidas:
            continue
        assunto = (fato.get("Assunto") or "").strip()
        texto = assunto
        try:
            lido = cvm.texto_do_pdf(baixar_documento(url))
            texto = lido if lido.strip() else assunto
        except Exception as erro:  # noqa: BLE001
            logger.warning("Histórico: PDF ilegível (%s, %s): %s", fato["ticker"], assunto, erro)
        instante = datetime.combine(fato["entrega"], time(23, 59), FUSO).isoformat()
        lista.append({"tipo_fonte": "fato_relevante", "fonte": "CVM (fato relevante)", "url": url,
                      "titulo": f"{universo()[1][fato['ticker']]}: {assunto}", "texto": texto,
                      "timestamp_publicacao": instante, "timestamp_coleta": instante,
                      "tickers": [fato["ticker"]]})
    return lista


def estimativa(registros: list[dict]) -> dict:
    caracteres = sum(min(len(r["texto"]), extract.MAX_CARACTERES_TEXTO) + len(r["titulo"]) for r in registros)
    # Extração: prompt (~1.500 tokens) + texto; classificação: ~700 tokens por fato.
    entrada = len(registros) * 2200 + caracteres / CARACTERES_POR_TOKEN
    saida = len(registros) * 450
    return {"fatos": len(registros), "tokens_entrada": int(entrada), "tokens_saida": int(saida),
            "custo_estimado_usd": round(entrada / 1e6 * PRECO_ENTRADA + saida / 1e6 * PRECO_SAIDA, 2)}


def executar(desde: date, ate: date | None = None, estimar: bool = False, dir_data: Path | None = None,
             baixar=None, baixar_documento=None) -> dict:
    dir_data = Path(dir_data or pasta_historico())
    ate = ate or datetime.now(FUSO).date()
    corte = corte_do_modelo()
    if corte is None or desde <= corte:
        raise ValueError(f"O início ({desde}) precisa ser posterior ao corte de conhecimento do modelo "
                         f"({corte or 'não registrado'}): antes disso, a IA pode conhecer o desfecho.")
    fatos_cvm = fatos(desde, ate, config.DIR_DATA / "cvm", baixar)
    if estimar:
        # Sem baixar os PDFs: tamanho típico de um fato relevante (~2.500 caracteres).
        registros = [{"texto": "x" * 2500, "titulo": f.get("Assunto", "")} for f in fatos_cvm]
        return {"estimativa": estimativa(registros), "desde": desde.isoformat(), "ate": ate.isoformat(),
                "por_ticker": _por_ticker(fatos_cvm), "corte_do_modelo": corte.isoformat()}

    conhecidas = {r["url"] for r in archive.carregar_arquivo(dir_data / "arquivo")}
    novos_itens = itens(fatos_cvm, conhecidas, baixar_documento)
    # Arquiva cada fato no dia da sua entrega (como se a coleta tivesse sido naquele dia).
    for item in novos_itens:
        archive.arquivar([item], pasta=dir_data / "arquivo", agora=datetime.fromisoformat(item["timestamp_coleta"]))
    urls = {f["Link_Download"].strip() for f in fatos_cvm}
    por_dia: dict[str, list[dict]] = defaultdict(list)
    for registro in archive.carregar_arquivo(dir_data / "arquivo"):
        if registro["url"] in urls and registro["tickers"]:
            por_dia[registro["timestamp_publicacao"][:10]].append(registro)

    decisoes_totais = 0
    for dia in sorted(por_dia):
        pasta = dir_data / "execucoes" / dia
        pasta.mkdir(parents=True, exist_ok=True)
        extraidos = main.etapa_extrair(pasta, por_dia[dia], tickers_do_registro=True)
        eventos = [e for lista in extraidos.values() for e in lista if main.do_prompt_vigente(e)]
        classificacoes = main.etapa_classificar(pasta, eventos)
        for evento in eventos:
            evento["classificacao"] = classificacoes.get(evento["id"])
        decisoes = main.etapa_decidir(pasta, eventos, main.carregar_historico(dir_data / "execucoes", dia))
        registrados = main.etapa_registrar(pasta, decisoes, {}, dir_data / "operacoes.jsonl", dia)
        decisoes_totais += sum(d["decisao"]["decisao"] != "manter" for d in decisoes)
        main._gravar(pasta / "resumo.json", {"data": dia, "versao_regra": VERSAO_REGRA,
                                             "versao_prompt": extract.VERSAO_PROMPT_EXTRACAO,
                                             "historico_cvm": True, "eventos_validos": len(eventos),
                                             "registrados_no_log": len(registrados)})
    resumo = {"desde": desde.isoformat(), "ate": ate.isoformat(), "fatos": len(fatos_cvm),
              "novos_neste_processamento": len(novos_itens), "dias": len(por_dia),
              "decisoes": decisoes_totais, "por_ticker": _por_ticker(fatos_cvm),
              "corte_do_modelo": corte.isoformat(), "versao_regra": VERSAO_REGRA}
    (dir_data / "resumo_historico.json").write_text(json.dumps(resumo, ensure_ascii=False, indent=2), encoding="utf-8")
    return resumo


def _por_ticker(fatos_cvm: list[dict]) -> dict:
    contagem = defaultdict(int)
    for f in fatos_cvm:
        contagem[f["ticker"]] += 1
    return dict(sorted(contagem.items()))


def main_cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Estudo histórico com fatos relevantes da CVM.")
    parser.add_argument("--desde", required=True, type=date.fromisoformat)
    parser.add_argument("--ate", type=date.fromisoformat)
    parser.add_argument("--estimar", action="store_true", help="só conta os fatos e estima o custo")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    llm.carregar_env()
    print(json.dumps(executar(args.desde, args.ate, args.estimar), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main_cli())
