"""Backup dos dados locais (o ativo mais caro do projeto: o histórico).

Cria um .zip com data/arquivo, data/execucoes, data/operacoes.jsonl e os
preços, fora da pasta do projeto. Nada é apagado: cada backup é um arquivo
novo. O pipeline real chama isto ao final de cada execução.

Destino: variável QUANT_BACKUP_DIR (ex.: uma pasta do OneDrive/Google Drive)
ou, por padrão, ../quant-backups ao lado do projeto.

Uso: python -m src.backup
"""

import os
import logging
import zipfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from src import config

ITENS = ("arquivo", "execucoes", "operacoes.jsonl", "precos", "simulacao")
logger = logging.getLogger(__name__)


def raizes_sincronizadas() -> list[Path]:
    raizes = []
    for variavel in ("OneDrive", "OneDriveCommercial", "OneDriveConsumer"):
        valor = os.environ.get(variavel)
        if valor and Path(valor).is_dir():
            raizes.append(Path(valor).expanduser().resolve())
    onedrive_padrao = Path.home() / "OneDrive"
    if onedrive_padrao.is_dir():
        raiz = onedrive_padrao.resolve()
        if raiz not in raizes:
            raizes.append(raiz)
    return raizes


def dentro_de(arquivo: Path, diretorios: list[Path]) -> bool:
    arquivo = arquivo.resolve()
    for diretorio in diretorios:
        try:
            arquivo.relative_to(diretorio)
            return True
        except ValueError:
            continue
    return False


def pasta_destino() -> Path:
    configurado = os.environ.get("QUANT_BACKUP_DIR")
    if configurado:
        return Path(configurado).expanduser()
    # OneDrive oferece uma cópia sincronizada fora do computador sem exigir
    # configuração manual. Se não estiver disponível, usa o destino local e
    # avisa que é preciso escolher outro volume para proteção contra falha.
    raizes = raizes_sincronizadas()
    if raizes:
        return raizes[0] / "QUANT-backups"
    return config.RAIZ_PROJETO.parent / "quant-backups"


def aviso_destino(dir_data: Path | None = None, destino: Path | None = None) -> str | None:
    """Informa quando o destino fica no mesmo volume dos dados originais."""
    origem = Path(dir_data or config.DIR_DATA).resolve()
    destino = Path(destino or pasta_destino()).expanduser().resolve()
    if dentro_de(destino, raizes_sincronizadas()):
        return None
    if origem.anchor.casefold() == destino.anchor.casefold():
        return (f"O backup está em {destino}, no mesmo volume dos dados ({origem.anchor}). "
                "Uma falha desse disco pode atingir os dois; configure QUANT_BACKUP_DIR "
                "para uma pasta sincronizada ou outro disco.")
    return None


def fazer_backup(dir_data: Path | None = None, destino: Path | None = None,
                 agora: datetime | None = None) -> Path | None:
    """Compacta os dados e devolve o caminho do .zip (None se não houver dados)."""
    dir_data = Path(dir_data or config.DIR_DATA)
    destino = Path(destino or pasta_destino())
    agora = agora or datetime.now(ZoneInfo(config.FUSO_REFERENCIA))
    arquivos = []
    for item in ITENS:
        caminho = dir_data / item
        if caminho.is_file():
            arquivos.append(caminho)
        elif caminho.is_dir():
            arquivos.extend(p for p in sorted(caminho.rglob("*")) if p.is_file())
    if not arquivos:
        return None
    alerta = aviso_destino(dir_data, destino)
    if alerta:
        logger.warning(alerta)
    destino.mkdir(parents=True, exist_ok=True)
    zip_final = destino / f"quant-dados-{agora:%Y-%m-%d_%H%M%S}.zip"
    temporario = zip_final.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporario, "w", zipfile.ZIP_DEFLATED) as z:
        for arquivo in arquivos:
            z.write(arquivo, arquivo.relative_to(dir_data).as_posix())
    temporario.replace(zip_final)  # só aparece completo
    return zip_final


def main() -> int:
    caminho = fazer_backup()
    print(f"Backup criado: {caminho}" if caminho else "Nada para copiar ainda.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
