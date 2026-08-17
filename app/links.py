"""Normaliza links de imagem para que funcionem dentro de <img> no email.

Links de compartilhamento do Google Drive (.../file/d/ID/view) NAO renderizam em
email: devolvem uma pagina HTML, nao a imagem. Aqui convertemos para o endpoint
de conteudo (lh3.googleusercontent.com/d/ID), que serve o PNG direto.
"""
from __future__ import annotations

import re
import unicodedata

_DRIVE_PATTERNS = (
    re.compile(r"drive\.google\.com/file/d/([A-Za-z0-9_-]{10,})"),
    re.compile(r"drive\.google\.com/open\?id=([A-Za-z0-9_-]{10,})"),
    re.compile(r"drive\.(?:google|usercontent\.google)\.com/uc\?(?:[^\"]*&)?id=([A-Za-z0-9_-]{10,})"),
    re.compile(r"drive\.google\.com/thumbnail\?(?:[^\"]*&)?id=([A-Za-z0-9_-]{10,})"),
    re.compile(r"docs\.google\.com/uc\?(?:[^\"]*&)?id=([A-Za-z0-9_-]{10,})"),
    re.compile(r"lh3\.googleusercontent\.com/d/([A-Za-z0-9_-]{10,})"),
)


def normalizar_imagem(url: str, largura: int = 0) -> str:
    """Devolve uma URL que o cliente de email consegue carregar como imagem."""
    url = (url or "").strip()
    if not url:
        return ""
    if url.startswith("//"):
        url = "https:" + url
    for pat in _DRIVE_PATTERNS:
        m = pat.search(url)
        if m:
            direto = f"https://lh3.googleusercontent.com/d/{m.group(1)}"
            return f"{direto}=w{largura}" if largura else direto
    return url


def slug(texto: str) -> str:
    """`Padaria São João Ltda` -> `padaria-sao-joao-ltda` (para endereco de origem)."""
    t = unicodedata.normalize("NFKD", texto or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return re.sub(r"-{2,}", "-", t)[:40]


def apresentar_empresa(nome: str) -> str:
    """Devolve o nome da empresa exatamente como esta na planilha.

    Nao mexemos em maiuscula/minuscula de proposito: muita razao social e sigla
    ou iniciais de nome de pessoa (`MRC`, `J F COMERCIO`), e "arrumar" isso viraria
    `Mrc` e `J F Comercio`. Quem digita a planilha decide como o nome aparece.
    Aqui so tiramos espaco sobrando.
    """
    return " ".join((nome or "").split())
