"""Gera a vitrine estática (somente leitura) para publicar o site no Vercel.

O site publicado não tem a API Python: ele lê arquivos JSON gerados aqui,
a partir dos dados locais, usando os mesmos endpoints da API (mesmos números).
Nada de data/ é alterado; a chave de API nunca é exportada (a API não a devolve).

Uso: python -m src.web.exportar   (ou npm run vitrine)
Depois: git add web/public/dados && git commit && git push  → o Vercel republica.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from src import config
from src.web import api

DESTINO = config.RAIZ_PROJETO / "web" / "public" / "dados"
BASES = ("real", "teste")


def _gravar(caminho: Path, dados) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, default=str), encoding="utf-8")


def exportar(destino: Path | None = None, bases: tuple[str, ...] = BASES) -> dict:
    """Regrava a pasta da vitrine do zero e devolve um resumo."""
    destino = Path(destino or DESTINO)
    cliente = TestClient(api.app)

    def obter(url: str):
        resposta = cliente.get(url)
        if resposta.status_code == 200:
            return resposta.json()
        detalhe = (resposta.json() or {}).get("detail", f"Erro {resposta.status_code}")
        return {"_erro": resposta.status_code, "detail": detalhe}

    if destino.exists():
        shutil.rmtree(destino)  # só a pasta gerada da vitrine
    resumo = {"gerado_em": datetime.now(ZoneInfo(config.FUSO_REFERENCIA)).isoformat(),
              "bases": {}}
    _gravar(destino / "status.json", obter("/api/status"))
    _gravar(destino / "config.json", obter("/api/config"))
    for base in bases:
        _gravar(destino / f"funil-{base}.json", obter(f"/api/funil?base={base}"))
        noticias = obter(f"/api/noticias?base={base}&limite=5000")
        _gravar(destino / f"noticias-{base}.json", noticias)
        execucoes = obter(f"/api/execucoes?base={base}")
        _gravar(destino / f"execucoes-{base}.json", execucoes)
        for execucao in execucoes:
            _gravar(destino / f"execucoes-{base}" / f"{execucao['data']}.json",
                    obter(f"/api/execucoes/{execucao['data']}?base={base}"))
        operacoes = obter(f"/api/operacoes?base={base}")
        _gravar(destino / f"operacoes-{base}.json", operacoes)
        simulacao = obter(f"/api/simulacao?base={base}")
        _gravar(destino / f"simulacao-{base}.json", simulacao)
        resumo["bases"][base] = {
            "noticias": noticias.get("total", 0), "execucoes": len(execucoes),
            "operacoes": len(operacoes),
            "simulacao": simulacao.get("estado") or f"erro: {simulacao.get('detail')}",
        }
    _gravar(destino / "meta.json", resumo)
    return resumo


def main() -> int:
    resumo = exportar()
    print(f"Vitrine gerada em {DESTINO} ({resumo['gerado_em']}).")
    for base, r in resumo["bases"].items():
        print(f"  {base}: {r['noticias']} notícias, {r['execucoes']} execuções, "
              f"{r['operacoes']} operações, simulação: {r['simulacao']}")
    print("Para publicar: git add web/public/dados && git commit -m \"Atualiza vitrine\" && git push")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
