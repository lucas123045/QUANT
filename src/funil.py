"""Funil do pipeline: notícias → menções → eventos → operações.

Mede, com os dados já gravados em data/, quantos itens sobrevivem a cada
filtro e projeta o número de operações por semestre. Serve para estimar o
poder estatístico ANTES de usar o período de teste.

Uso: python -m src.funil [--data-dir data/teste]
"""

import argparse
import json
from collections import Counter
from pathlib import Path

from src import archive, config
from src.matching import identificar_tickers

PREGOES_POR_SEMESTRE = 126


def _ler(caminho: Path, padrao):
    return json.loads(caminho.read_text(encoding="utf-8")) if caminho.exists() else padrao


def medir_funil(dir_data: Path | None = None) -> dict:
    dir_data = Path(dir_data or config.DIR_DATA)
    registros = archive.carregar_arquivo(dir_data / "arquivo")
    # Casamento recalculado com as regras atuais (o campo gravado reflete as da coleta).
    mencoes = [r for r in registros if identificar_tickers(f"{r['titulo']}\n{r['texto']}")]
    dias_coleta = sorted({r["timestamp_coleta"][:10] for r in registros})

    eventos, classificacoes, decisoes = [], {}, []
    for pasta in sorted(p for p in (dir_data / "execucoes").glob("*") if p.is_dir()):
        for lista in _ler(pasta / "03_extracao.json", {}).values():
            eventos.extend(lista)
        classificacoes.update(_ler(pasta / "04_classificacao.json", {}))
        decisoes.extend(_ler(pasta / "05_decisoes.json", []))

    classificados = [classificacoes.get(e["id"]) for e in eventos]
    classificados = [c for c in classificados if c]
    confirmados = [e for e in eventos if e.get("confirmado")]
    acima_limiar = [c for c in classificados if c["sentimento"] != "neutro"
                    and c["probabilidade"] > config.LIMIAR_PROBABILIDADE]
    operacoes = [d for d in decisoes if d["decisao"]["decisao"] != "manter"]

    n_dias = len(dias_coleta)
    por_dia = len(operacoes) / n_dias if n_dias else None
    return {
        "dias_de_coleta": n_dias,
        "noticias_arquivadas": len(registros),
        "noticias_com_mencao": len(mencoes),
        "mencoes_por_ticker": dict(Counter(t for r in mencoes
                                           for t in identificar_tickers(f"{r['titulo']}\n{r['texto']}"))),
        "eventos_extraidos": len(eventos),
        "eventos_classificados": len(classificados),
        "eventos_confirmados": len(confirmados),
        "sentimentos": dict(Counter(c["sentimento"] for c in classificados)),
        "eventos_acima_do_limiar": len(acima_limiar),
        "operacoes": len(operacoes),
        "operacoes_por_dia_de_coleta": por_dia,
        # Projeção grosseira: supõe que cada dia de coleta equivale a um pregão.
        "projecao_operacoes_por_semestre": por_dia * PREGOES_POR_SEMESTRE if por_dia is not None else None,
        "aviso": ("Projeção com poucos dias de coleta é muito incerta. Sem provedor de LLM "
                  "configurado, as etapas a partir da extração ficam em zero."),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mede o funil do pipeline.")
    parser.add_argument("--data-dir", default=None, help="pasta de dados (padrão: data/)")
    args = parser.parse_args(argv)
    print(json.dumps(medir_funil(args.data_dir), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
