"""Traz para data/ o que a coleta automática na nuvem gravou (ramo "dados" no GitHub).

Com a coleta rodando na nuvem (.github/workflows/quant.yml), o computador não
precisa coletar: basta sincronizar para a interface local mostrar os mesmos dados.
Baixa o ZIP do ramo pelo GitHub (não precisa de git instalado).

- Arquivos que só crescem (arquivo de notícias, log de operações): junta as linhas,
  as da nuvem primeiro e depois as que só existem aqui. Nada local se perde.
- Os demais (execuções, caches): a versão da nuvem prevalece.
- O log e a trava locais nunca são tocados.

Uso: python -m src.sincronizar
"""

import io
import json
import logging
import zipfile
from pathlib import Path, PurePosixPath

from src import config, rede

logger = logging.getLogger(__name__)
URL_ZIP = "https://codeload.github.com/{repo}/zip/refs/heads/{ramo}"
IGNORADOS = {"agendamento.log", "agendamento.log.old", ".pipeline.lock"}


def _so_crescem(relativo: PurePosixPath) -> bool:
    return (relativo.parts[0] == "arquivo" and relativo.suffix == ".jsonl") or str(relativo) == "operacoes.jsonl"


def _unir_linhas(nuvem: bytes, local: bytes) -> bytes:
    linhas = [l for l in nuvem.decode("utf-8").splitlines() if l.strip()]
    vistas = set(linhas)
    linhas += [l for l in local.decode("utf-8").splitlines() if l.strip() and l not in vistas]
    return ("\n".join(linhas) + "\n").encode("utf-8")


def sincronizar(destino: Path | None = None, conteudo_zip: bytes | None = None,
                repo: str | None = None, ramo: str = "dados") -> dict:
    """Atualiza `destino` (padrão: data/) com o ramo da nuvem e devolve as contagens."""
    destino = Path(destino or config.DIR_DATA)
    repo = repo or config.REPOSITORIO_GITHUB
    if conteudo_zip is None:
        conteudo_zip = rede.baixar(URL_ZIP.format(repo=repo, ramo=ramo), 60, "quant-academico/1.0")
    novos = atualizados = unidos = 0
    with zipfile.ZipFile(io.BytesIO(conteudo_zip)) as z:
        for info in z.infolist():
            partes = PurePosixPath(info.filename).parts[1:]  # tira a pasta "QUANT-dados/"
            if info.is_dir() or not partes or partes[-1] in IGNORADOS or ".." in partes:
                continue
            relativo = PurePosixPath(*partes)
            alvo = destino.joinpath(*partes)
            nuvem = z.read(info)
            if not alvo.exists():
                alvo.parent.mkdir(parents=True, exist_ok=True)
                alvo.write_bytes(nuvem)
                novos += 1
                continue
            local = alvo.read_bytes()
            if local == nuvem:
                continue
            if _so_crescem(relativo):
                alvo.write_bytes(_unir_linhas(nuvem, local))
                unidos += 1
            else:
                alvo.write_bytes(nuvem)
                atualizados += 1
    resumo = {"novos": novos, "atualizados": atualizados, "unidos": unidos}
    logger.info("Sincronizado com %s (ramo %s): %s", repo, ramo, json.dumps(resumo))
    return resumo


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        r = sincronizar()
    except Exception as erro:  # sem internet, ou a coleta na nuvem ainda não foi ligada
        print(f"Não foi possível sincronizar com a nuvem: {erro}")
        return 1
    print(f"Dados da nuvem: {r['novos']} arquivos novos, {r['atualizados']} atualizados, {r['unidos']} unidos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
