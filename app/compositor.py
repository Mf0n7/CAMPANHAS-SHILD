"""Monta a imagem unica enviada no WhatsApp: cabecalho de marcas + poster.

    +--------------------------------------------------+
    |   [logo SHILD]      |      [logo da empresa]      |  faixa branca
    +--------------------------------------------------+
    |################ barra dourada ###################|
    +--------------------------------------------------+
    |                                                  |
    |                  poster da campanha              |
    |                                                  |

O cabecalho e branco de proposito: logo de empresa vem em qualquer cor e quase
sempre e desenhada para fundo claro. Sobre o azul da SHILD, metade delas sumiria.

O resultado e cacheado por empresa — o mesmo arquivo serve para todos os
funcionarios dela, entao a composicao roda uma vez, nao uma vez por pessoa.
"""
from __future__ import annotations

import hashlib
import io
from pathlib import Path

import httpx

from .config import settings
from .links import normalizar_imagem

LARGURA = 1080
ALTURA_CABECALHO = 210
ALTURA_BARRA = 9
MARGEM = 48
NAVY = (0, 38, 67)
OURO = (200, 144, 93)
BRANCO = (255, 255, 255)
CINZA_LINHA = (216, 221, 227)

FONTES = ("arialbd.ttf", "Arial Bold.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf")


class CompositorError(Exception):
    pass


def _dir_cache() -> Path:
    d = settings.output_dir / "compostas"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _fonte(tamanho: int):
    from PIL import ImageFont

    for nome in FONTES:
        try:
            return ImageFont.truetype(nome, tamanho)
        except OSError:
            continue
    return ImageFont.load_default()


def baixar_logo(url: str) -> bytes | None:
    """Baixa a logo da empresa. Devolve None se nao der (link privado, 404, etc)."""
    direto = normalizar_imagem(url, largura=600)
    if not direto or not direto.startswith("http"):
        return None
    try:
        with httpx.Client(timeout=25, follow_redirects=True) as c:
            r = c.get(direto, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200 or not r.content:
            return None
        if "image" not in r.headers.get("content-type", "") and not r.content.startswith(
                (b"\x89PNG", b"\xff\xd8", b"GIF8", b"RIFF")):
            return None            # veio pagina HTML: link nao esta publico
        return r.content
    except httpx.HTTPError:
        return None


def _encaixar(img, caixa_w: int, caixa_h: int):
    """Redimensiona mantendo proporcao para caber na caixa, sem cortar nem esticar."""
    from PIL import Image

    escala = min(caixa_w / img.width, caixa_h / img.height)
    if escala < 1 or escala > 1:
        img = img.resize((max(1, round(img.width * escala)), max(1, round(img.height * escala))),
                         Image.LANCZOS)
    return img


def _colar_centralizado(fundo, img, cx: int, cy: int) -> None:
    x, y = cx - img.width // 2, cy - img.height // 2
    fundo.paste(img, (x, y), img if img.mode in ("RGBA", "LA") else None)


def _quebrar(draw, texto: str, fonte, largura_max: int) -> list[str]:
    linhas, atual = [], ""
    for p in texto.split():
        teste = (atual + " " + p).strip()
        if not atual or draw.textlength(teste, font=fonte) <= largura_max:
            atual = teste
        else:
            linhas.append(atual)
            atual = p
    if atual:
        linhas.append(atual)
    return linhas


def _texto_centralizado(draw, texto: str, cx: int, cy: int, largura_max: int) -> None:
    """Nome da empresa quando nao ha logo.

    Prefere quebrar em duas linhas a encolher a fonte: nome comprido em corpo 24
    ao lado da logo da SHILD fica desequilibrado.
    """
    tam, linhas = 24, [texto]
    for t in range(46, 23, -3):
        f = _fonte(t)
        candidatas = _quebrar(draw, texto, f, largura_max)
        if len(candidatas) <= 2:
            tam, linhas = t, candidatas
            break
    else:
        linhas = _quebrar(draw, texto, _fonte(24), largura_max)[:2]

    f = _fonte(tam)
    altura = tam * 1.25
    y = cy - (len(linhas) - 1) * altura / 2
    for ln in linhas:
        draw.text((cx, y), ln, font=f, fill=NAVY, anchor="mm")
        y += altura


def compor(poster: Path, empresa: str, logo_bytes: bytes | None) -> bytes:
    """Devolve o JPEG final (cabecalho + poster) em bytes."""
    from PIL import Image, ImageDraw

    try:
        arte = Image.open(poster)
        arte.load()
    except OSError as exc:
        raise CompositorError(f"Nao consegui abrir o poster: {exc}") from exc
    arte = arte.convert("RGB")
    altura_arte = round(arte.height * LARGURA / arte.width)
    arte = arte.resize((LARGURA, altura_arte), Image.LANCZOS)

    total = ALTURA_CABECALHO + ALTURA_BARRA + altura_arte
    tela = Image.new("RGB", (LARGURA, total), BRANCO)
    draw = ImageDraw.Draw(tela)

    meio = LARGURA // 2
    caixa_w = meio - MARGEM - 30
    caixa_h = ALTURA_CABECALHO - 2 * MARGEM

    # --- lado esquerdo: SHILD ---
    shild = settings.brand_dir / "shild-navy.png"
    if shild.exists():
        _colar_centralizado(tela, _encaixar(Image.open(shild).convert("RGBA"), caixa_w, caixa_h),
                            meio // 2, ALTURA_CABECALHO // 2)
    else:
        draw.text((meio // 2, ALTURA_CABECALHO // 2), "SHILD", font=_fonte(52), fill=NAVY, anchor="mm")

    # --- divisoria ---
    draw.line([(meio, MARGEM - 6), (meio, ALTURA_CABECALHO - MARGEM + 6)], fill=CINZA_LINHA, width=2)

    # --- lado direito: empresa ---
    logo = None
    if logo_bytes:
        try:
            logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
        except OSError:
            logo = None
    if logo is not None:
        fundo = Image.new("RGBA", logo.size, (255, 255, 255, 255))
        fundo.alpha_composite(logo)          # achata transparencia sobre branco
        _colar_centralizado(tela, _encaixar(fundo.convert("RGB"), caixa_w, caixa_h),
                            meio + meio // 2, ALTURA_CABECALHO // 2)
    else:
        _texto_centralizado(draw, empresa or "", meio + meio // 2, ALTURA_CABECALHO // 2, caixa_w)

    # --- barra dourada e poster ---
    draw.rectangle([0, ALTURA_CABECALHO, LARGURA, ALTURA_CABECALHO + ALTURA_BARRA - 1], fill=OURO)
    tela.paste(arte, (0, ALTURA_CABECALHO + ALTURA_BARRA))

    saida = io.BytesIO()
    tela.save(saida, format="JPEG", quality=88, optimize=True, progressive=True)
    return saida.getvalue()


def _chave(poster: Path, empresa: str, logo_url: str) -> str:
    bruto = f"{poster.name}|{poster.stat().st_mtime_ns}|{empresa}|{logo_url}"
    return hashlib.sha1(bruto.encode("utf-8")).hexdigest()[:16]


def para_empresa(poster: Path, empresa: str, logo_url: str, usar_cache: bool = True) -> dict:
    """Compoe (ou reaproveita do cache) a imagem daquela empresa."""
    destino = _dir_cache() / f"{_chave(poster, empresa, logo_url)}.jpg"
    if usar_cache and destino.exists():
        return {"arquivo": destino, "kb": round(destino.stat().st_size / 1024, 1),
                "logo_ok": None, "cache": True}

    bytes_logo = baixar_logo(logo_url) if logo_url else None
    dados = compor(poster, empresa, bytes_logo)
    destino.write_bytes(dados)
    return {"arquivo": destino, "kb": round(len(dados) / 1024, 1),
            "logo_ok": bool(bytes_logo), "cache": False}


def limpar_cache() -> int:
    n = 0
    for f in _dir_cache().glob("*.jpg"):
        f.unlink(missing_ok=True)
        n += 1
    return n
