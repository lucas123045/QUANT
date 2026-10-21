"""Gera a vitrine estática (somente leitura) para publicar o site no Vercel.

O site publicado não tem a API Python: ele lê arquivos JSON gerados aqui,
a partir dos dados locais, usando os mesmos endpoints da API (mesmos números).
Nada de data/ é alterado; a chave de API nunca é exportada (a API não a devolve).

Uso: python -m src.web.exportar   (ou npm run vitrine)
Depois: git add web/public/dados && git commit && git push  → o Vercel republica.
"""

import argparse
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from src import config
from src.web import api

# QUANT_VITRINE_DIR: na nuvem, a vitrine vai para o ramo "dados" (o site lê de lá).
DESTINO = Path(os.environ.get("QUANT_VITRINE_DIR") or config.RAIZ_PROJETO / "web" / "public" / "dados")
BASES = ("real", "teste")


def _gravar(caminho: Path, dados) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, default=str), encoding="utf-8")


class VitrineEncolheu(RuntimeError):
    """A vitrine nova tem menos notícias ou operações que a publicada."""


def _contagens_publicadas(destino: Path) -> dict:
    meta = destino / "meta.json"
    try:
        return json.loads(meta.read_text(encoding="utf-8")).get("bases", {}) if meta.exists() else {}
    except (ValueError, OSError):
        return {}


def _encolhimentos(antes: dict, depois: dict) -> list[str]:
    """O arquivo de notícias e o log de operações só crescem: se a contagem caiu,
    a pasta de dados usada está errada ou incompleta (ex.: outro computador).

    Só vale para a base real: a base de teste é descartável (notícias de exemplo),
    e um computador que nunca rodou o modo de teste a teria "encolhido" sempre,
    travando a vitrine todo dia.
    """
    problemas = []
    for base, novo in depois.items():
        if base != "real":
            continue
        velho = antes.get(base) or {}
        for campo in ("noticias", "operacoes"):
            if (velho.get(campo) or 0) > (novo.get(campo) or 0):
                problemas.append(f"{base}: {campo} {velho[campo]} → {novo.get(campo) or 0}")
    return problemas


def exportar(destino: Path | None = None, bases: tuple[str, ...] = BASES, forcar: bool = False) -> dict:
    """Regera a pasta da vitrine e devolve um resumo.

    Gera numa pasta temporária e só troca pela publicada no fim, de uma vez:
    uma falha no meio não deixa a vitrine pela metade. Recusa (VitrineEncolheu)
    se a nova tiver menos notícias ou operações que a publicada, a menos que
    `forcar` seja True.
    """
    destino = Path(destino or DESTINO)
    novo = destino.with_name(destino.name + ".novo")
    if novo.exists():
        shutil.rmtree(novo)  # sobra de uma geração interrompida
    cliente = TestClient(api.app)

    def obter(url: str):
        resposta = cliente.get(url)
        if resposta.status_code == 200:
            return resposta.json()
        detalhe = (resposta.json() or {}).get("detail", f"Erro {resposta.status_code}")
        return {"_erro": resposta.status_code, "detail": detalhe}

    try:
        resumo = {"gerado_em": datetime.now(ZoneInfo(config.FUSO_REFERENCIA)).isoformat(),
                  "bases": {}}
        _gravar(novo / "status.json", obter("/api/status"))
        _gravar(novo / "config.json", obter("/api/config"))
        for base in bases:
            _gravar(novo / f"funil-{base}.json", obter(f"/api/funil?base={base}"))
            noticias = obter(f"/api/noticias?base={base}&limite=5000")
            _gravar(novo / f"noticias-{base}.json", noticias)
            execucoes = obter(f"/api/execucoes?base={base}")
            _gravar(novo / f"execucoes-{base}.json", execucoes)
            execucoes = execucoes if isinstance(execucoes, list) else []
            for execucao in execucoes:
                _gravar(novo / f"execucoes-{base}" / f"{execucao['data']}.json",
                        obter(f"/api/execucoes/{execucao['data']}?base={base}"))
            operacoes = obter(f"/api/operacoes?base={base}")
            _gravar(novo / f"operacoes-{base}.json", operacoes)
            simulacao = obter(f"/api/simulacao?base={base}")
            _gravar(novo / f"simulacao-{base}.json", simulacao)
            resumo["bases"][base] = {
                "noticias": noticias.get("total", 0), "execucoes": len(execucoes),
                "operacoes": len(operacoes) if isinstance(operacoes, list) else 0,
                "simulacao": simulacao.get("estado") or f"erro: {simulacao.get('detail')}",
            }
        _gravar(novo / "meta.json", resumo)

        problemas = _encolhimentos(_contagens_publicadas(destino), resumo["bases"])
        if problemas and not forcar:
            raise VitrineEncolheu(
                "A vitrine nova tem menos dados que a publicada (" + "; ".join(problemas) + "). "
                "Confira se a pasta data/ deste computador é a certa. Para publicar mesmo assim, "
                "use --forcar.")
    except BaseException:
        shutil.rmtree(novo, ignore_errors=True)  # a publicada fica intacta
        raise

    # Troca: a antiga sai só depois que a nova está completa.
    antigo = destino.with_name(destino.name + ".antigo")
    if antigo.exists():
        shutil.rmtree(antigo)
    if destino.exists():
        destino.rename(antigo)
    novo.rename(destino)
    shutil.rmtree(antigo, ignore_errors=True)
    return resumo


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gera a vitrine estática (somente leitura).")
    parser.add_argument("--forcar", action="store_true",
                        help="publica mesmo se a vitrine nova tiver menos dados que a atual")
    args = parser.parse_args(argv)
    try:
        resumo = exportar(forcar=args.forcar)
    except VitrineEncolheu as erro:
        print(f"Vitrine NÃO atualizada: {erro}")
        return 1
    print(f"Vitrine gerada em {DESTINO} ({resumo['gerado_em']}).")
    for base, r in resumo["bases"].items():
        print(f"  {base}: {r['noticias']} notícias, {r['execucoes']} execuções, "
              f"{r['operacoes']} operações, simulação: {r['simulacao']}")
    print("Para publicar: git add web/public/dados && git commit -m \"Atualiza vitrine\" && git push")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
