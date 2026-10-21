"""Fatos relevantes da CVM: a fonte primária, direto dos dados abertos.

Fato relevante é o comunicado obrigatório da empresa sobre qualquer fato que
possa mexer no preço da ação (Resolução CVM 44/2021). É a origem de boa parte
das notícias dos portais. Fonte: arquivo anual de documentos eventuais (IPE) do
Portal de Dados Abertos da CVM, uma linha por documento entregue, com CNPJ,
categoria, assunto, data de entrega e link para o PDF.

Decisões (verificadas no arquivo de 2026 em 21/10/2026):
- filtro por CNPJ (config.CNPJ_CARTEIRA), não por nome: o nome varia
  ("ITAÚ UNIBANCO HOLDING S.A.", "BANCO BRADESCO S.A.");
- só a primeira versão de cada documento: uma reapresentação corrige o mesmo
  fato e contaria duas vezes;
- a data de entrega vem SEM hora. O instante registrado é 23h59 do dia de
  entrega: pela convenção do backtest, a execução fica para o pregão seguinte de
  qualquer jeito, e o horário mais tardio evita usar o fato antes da hora;
- o arquivo é atualizado com alguns dias de atraso (em 21/10, o último registro
  era de 17/10). É confirmação de fonte primária, não furo de reportagem;
- o texto é o do PDF (pypdf); se não der para ler, fica só o assunto.

Os itens saem com tipo_fonte="fato_relevante": a regra decide sobre eles, mas a
carteira (que é de notícias de portal) não mistura as duas fontes.
"""

import csv
import io
import logging
import time as relogio
import zipfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from src import archive, config, rede

logger = logging.getLogger(__name__)
FUSO = ZoneInfo(config.FUSO_REFERENCIA)
USER_AGENT = "quant-academico/1.0 (+dados abertos CVM)"
VALIDADE_CACHE_HORAS = 3      # o arquivo da CVM muda no máximo algumas vezes por dia
MAX_CARACTERES = 20_000       # a extração usa os primeiros 8.000 (extract.MAX_CARACTERES_TEXTO)
CATEGORIA = "Fato Relevante"


def baixar_arquivo_anual(ano: int, pasta_cache: Path, baixar=None) -> bytes:
    """ZIP do IPE do ano, com cache de algumas horas (cerca de 2 MB)."""
    pasta_cache.mkdir(parents=True, exist_ok=True)
    caminho = pasta_cache / f"ipe_cia_aberta_{ano}.zip"
    if caminho.exists() and relogio.time() - caminho.stat().st_mtime < VALIDADE_CACHE_HORAS * 3600:
        return caminho.read_bytes()
    conteudo = (baixar or (lambda url: rede.baixar(url, 60, USER_AGENT)))(config.URL_CVM_IPE.format(ano=ano))
    caminho.write_bytes(conteudo)
    return conteudo


def linhas_do_arquivo(conteudo_zip: bytes) -> list[dict]:
    with zipfile.ZipFile(io.BytesIO(conteudo_zip)) as z:
        nome = next(n for n in z.namelist() if n.endswith(".csv"))
        texto = z.read(nome).decode("latin-1")  # o CSV da CVM é ISO-8859-1
    return list(csv.DictReader(io.StringIO(texto), delimiter=";"))


def fatos_da_carteira(linhas: list[dict], desde: date) -> list[dict]:
    """Fatos relevantes (1ª versão) das empresas da carteira entregues desde `desde`."""
    fatos = []
    for l in linhas:
        ticker = config.CNPJ_CARTEIRA.get(l.get("CNPJ_Companhia", "").strip())
        if not ticker or l.get("Categoria") != CATEGORIA or l.get("Versao", "").strip() != "1":
            continue
        try:
            entrega = date.fromisoformat(l["Data_Entrega"].strip())
        except (KeyError, ValueError):
            continue
        if entrega >= desde and l.get("Link_Download"):
            fatos.append({**l, "ticker": ticker, "entrega": entrega})
    return sorted(fatos, key=lambda f: f["entrega"])


def texto_do_pdf(conteudo: bytes) -> str:
    from pypdf import PdfReader  # import local: só quem coleta da CVM precisa

    leitor = PdfReader(io.BytesIO(conteudo))
    partes, tamanho = [], 0
    for pagina in leitor.pages:
        trecho = pagina.extract_text() or ""
        partes.append(trecho)
        tamanho += len(trecho)
        if tamanho >= MAX_CARACTERES:
            break
    return " ".join(" ".join(partes).split())[:MAX_CARACTERES]


def coletar(agora: datetime | None = None, dir_data: Path | None = None, baixar=None,
            baixar_documento=None) -> list[dict]:
    """Itens para o arquivo (mesmo formato da coleta de RSS), só dos fatos ainda não arquivados."""
    agora = (agora or datetime.now(FUSO)).astimezone(FUSO)
    dir_data = Path(dir_data or config.DIR_DATA)
    desde = agora.date() - timedelta(days=config.JANELA_CVM_DIAS)
    linhas = []
    for ano in sorted({desde.year, agora.year}):  # no começo de janeiro, a janela pega o ano anterior
        linhas += linhas_do_arquivo(baixar_arquivo_anual(ano, dir_data / "cvm", baixar))
    conhecidas = {r["url"] for r in archive.carregar_arquivo(dir_data / "arquivo")}
    baixar_documento = baixar_documento or (lambda url: rede.baixar(url, 60, USER_AGENT))
    itens = []
    for fato in fatos_da_carteira(linhas, desde):
        url = fato["Link_Download"].strip()
        if url in conhecidas:
            continue  # já arquivado: não baixa o PDF de novo
        assunto = (fato.get("Assunto") or "").strip()
        texto = assunto
        try:
            lido = texto_do_pdf(baixar_documento(url))
            if lido.strip():
                texto = lido
        except Exception as erro:  # noqa: BLE001 - PDF ilegível ou fora do ar: segue com o assunto
            logger.warning("CVM: não foi possível ler o PDF de %s (%s): %s", fato["ticker"], assunto, erro)
        empresa = config.NOMES_EMPRESAS[fato["ticker"]]
        itens.append({
            "tipo_fonte": "fato_relevante", "fonte": "CVM (fato relevante)", "url": url,
            # O nome da empresa no título garante o casamento com o ticker.
            "titulo": f"{empresa}: {assunto}" if assunto else f"Fato relevante - {empresa}",
            "texto": texto,
            "timestamp_publicacao": datetime.combine(fato["entrega"], time(23, 59), FUSO).isoformat(),
            "timestamp_coleta": agora.isoformat(),
        })
    logger.info("CVM: %d fato(s) relevante(s) novo(s) da carteira desde %s", len(itens), desde.isoformat())
    return itens
