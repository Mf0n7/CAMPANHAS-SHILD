"""O poster vive no banco; algumas bibliotecas precisam dele como arquivo.

Pillow e o anexo do email trabalham com caminho/bytes, entao materializamos o blob
num cache em disco. O cache e descartavel: se sumir (container reiniciou), e
reescrito do banco na proxima vez. Nada aqui precisa de volume.
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from . import db
from .config import settings

POSTER = "poster"          # chave unica do poster da campanha atual


def cache_dir() -> Path:
    d = settings.output_dir / "cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def guardar_poster(nome: str, conteudo: bytes) -> None:
    mime, _ = mimetypes.guess_type(nome)
    db.gravar_arquivo(POSTER, conteudo, mime or "image/jpeg")
    db.gravar_config("poster_nome", nome)
    for velho in cache_dir().glob("poster.*"):
        velho.unlink(missing_ok=True)


def nome_poster() -> str:
    return db.ler_config("poster_nome", "") or ""


def info_poster() -> dict | None:
    info = db.info_arquivo(POSTER)
    if info:
        info["nome"] = nome_poster() or info["nome"]
    return info


def caminho_poster() -> Path | None:
    """Materializa o poster no cache e devolve o caminho. None se nao houver poster."""
    nome = nome_poster()
    if not nome:
        return None
    destino = cache_dir() / ("poster" + Path(nome).suffix.lower())
    info = db.info_arquivo(POSTER)
    if info is None:
        return None
    if destino.exists() and destino.stat().st_size == info["bytes"]:
        return destino
    lido = db.ler_arquivo(POSTER)
    if lido is None:
        return None
    destino.write_bytes(lido[0])
    return destino


def bytes_poster() -> bytes | None:
    lido = db.ler_arquivo(POSTER)
    return lido[0] if lido else None
