"""Medição da qualidade do casamento de tickers e da extração, com rótulos manuais.

Fluxo:
1. `python -m src.avaliacao exportar-matching --n 100` gera um CSV com uma
   amostra sorteada (semente fixa) das notícias arquivadas, com a coluna
   "tickers_corretos" em branco.
2. Uma pessoa preenche "tickers_corretos" (tickers separados por espaço;
   vazio = nenhuma empresa da carteira é assunto da notícia).
3. `python -m src.avaliacao medir-matching arquivo.csv` calcula precisão e
   revocação por ticker e no total.

Para a extração: `exportar-eventos` gera um CSV com os eventos extraídos e a
coluna "evento_correto" (sim/nao); `medir-extracao` calcula a precisão.

Use apenas dados de treino/validação, nunca do período de teste.
"""

import argparse
import csv
import json
import random
from pathlib import Path

from src import archive, config
from src.matching import identificar_tickers

SEMENTE_AMOSTRA = 20261015


def exportar_amostra_matching(caminho: Path, n: int = 100, dir_arquivo: Path | None = None,
                              semente: int = SEMENTE_AMOSTRA) -> int:
    registros = archive.carregar_arquivo(dir_arquivo)
    amostra = random.Random(semente).sample(registros, min(n, len(registros)))
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(["id", "titulo", "texto", "tickers_previstos", "tickers_corretos"])
        for r in amostra:
            previstos = identificar_tickers(f"{r['titulo']}\n{r['texto']}")
            escritor.writerow([r["id"], r["titulo"], r["texto"], " ".join(previstos), ""])
    return len(amostra)


def medir_matching(caminho: Path, carteira: list[str] | None = None) -> dict:
    """Precisão e revocação por ticker a partir do CSV rotulado."""
    carteira = config.CARTEIRA if carteira is None else carteira
    contagem = {t: {"vp": 0, "fp": 0, "fn": 0} for t in carteira}
    with open(caminho, encoding="utf-8", newline="") as f:
        linhas = list(csv.DictReader(f))
    for linha in linhas:
        previstos = set(linha["tickers_previstos"].split())
        corretos = set(linha["tickers_corretos"].split())
        for t in carteira:
            if t in previstos and t in corretos:
                contagem[t]["vp"] += 1
            elif t in previstos:
                contagem[t]["fp"] += 1
            elif t in corretos:
                contagem[t]["fn"] += 1

    def metricas(c: dict) -> dict:
        vp, fp, fn = c["vp"], c["fp"], c["fn"]
        return {**c, "precisao": vp / (vp + fp) if vp + fp else None,
                "revocacao": vp / (vp + fn) if vp + fn else None}

    total = {k: sum(c[k] for c in contagem.values()) for k in ("vp", "fp", "fn")}
    return {"n_noticias": len(linhas), "total": metricas(total),
            "por_ticker": {t: metricas(c) for t, c in contagem.items()}}


def exportar_eventos(caminho: Path, dir_execucoes: Path | None = None) -> int:
    dir_execucoes = Path(dir_execucoes or config.DIR_EXECUCOES)
    eventos = []
    for arquivo in sorted(dir_execucoes.glob("*/03_extracao.json")):
        for lista in json.loads(arquivo.read_text(encoding="utf-8")).values():
            eventos.extend(lista)
    with open(caminho, "w", encoding="utf-8", newline="") as f:
        escritor = csv.writer(f)
        escritor.writerow(["id", "ticker", "tipo_evento", "impacto_declarado", "confirmado",
                           "resumo", "trecho_fonte", "url", "evento_correto"])
        for e in eventos:
            escritor.writerow([e["id"], e["ticker"], e["tipo_evento"], e["impacto_declarado"],
                               e["confirmado"], e["resumo"], e["trecho_fonte"],
                               (e.get("origem") or {}).get("url", ""), ""])
    return len(eventos)


def medir_extracao(caminho: Path) -> dict:
    """Precisão da extração: fração dos eventos rotulados como corretos."""
    with open(caminho, encoding="utf-8", newline="") as f:
        rotulos = [l["evento_correto"].strip().lower() for l in csv.DictReader(f)]
    validos = [r for r in rotulos if r in ("sim", "nao", "não")]
    corretos = sum(r == "sim" for r in validos)
    return {"n_rotulados": len(validos), "n_sem_rotulo": len(rotulos) - len(validos),
            "precisao": corretos / len(validos) if validos else None}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Avaliação com rótulos manuais.")
    sub = parser.add_subparsers(dest="comando", required=True)
    p = sub.add_parser("exportar-matching")
    p.add_argument("--saida", default="amostra_matching.csv")
    p.add_argument("--n", type=int, default=100)
    sub.add_parser("medir-matching").add_argument("arquivo")
    sub.add_parser("exportar-eventos").add_argument("--saida", default="amostra_eventos.csv")
    sub.add_parser("medir-extracao").add_argument("arquivo")
    args = parser.parse_args(argv)

    if args.comando == "exportar-matching":
        print(f"{exportar_amostra_matching(Path(args.saida), args.n)} notícias em {args.saida}")
    elif args.comando == "medir-matching":
        print(json.dumps(medir_matching(Path(args.arquivo)), ensure_ascii=False, indent=2))
    elif args.comando == "exportar-eventos":
        print(f"{exportar_eventos(Path(args.saida))} eventos em {args.saida}")
    else:
        print(json.dumps(medir_extracao(Path(args.arquivo)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
