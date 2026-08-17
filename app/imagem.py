"""Prepara o poster para email: reduz largura e peso sem estragar a arte.

O email tem 600 px de largura. Um PNG de 3 MB vindo do Canva nao melhora nada na
tela do funcionario e custa caro: atrasa o envio, engorda a caixa de entrada de
todo mundo e piora a pontuacao de spam. Reduzimos para 1200 px (o dobro, para
telas retina) e escolhemos o formato que ficar menor.
"""
from __future__ import annotations

import io
from pathlib import Path

LARGURA_MAX = 1200
ALVO_BYTES = 900 * 1024


def disponivel() -> bool:
    try:
        import PIL  # noqa: F401
    except ImportError:
        return False
    return True


def otimizar(caminho: Path) -> dict:
    """Reescreve o arquivo otimizado. Devolve o que mudou, para mostrar na tela.

    A chave "erro" so vem preenchida quando o arquivo nao e uma imagem utilizavel —
    nesse caso quem chamou deve recusar o upload, porque a extensao mente.
    """
    antes = caminho.stat().st_size
    resultado = {"antes_kb": round(antes / 1024, 1), "depois_kb": round(antes / 1024, 1),
                 "largura": 0, "convertido_para": caminho.suffix.lstrip("."), "mudou": False,
                 "aviso": "", "erro": ""}
    if not disponivel():
        resultado["aviso"] = ("Pillow nao instalado — a imagem vai no tamanho original. "
                              "Instale com: pip install Pillow")
        return resultado

    from PIL import Image, UnidentifiedImageError

    try:
        img = Image.open(caminho)
        img.load()
    except (OSError, UnidentifiedImageError) as exc:
        resultado["erro"] = (f"O arquivo nao e uma imagem valida ({exc.__class__.__name__}). "
                             "A extensao pode estar certa mas o conteudo nao e uma imagem.")
        return resultado

    if img.width > LARGURA_MAX:
        altura = round(img.height * LARGURA_MAX / img.width)
        img = img.resize((LARGURA_MAX, altura), Image.LANCZOS)
    resultado["largura"] = img.width

    tem_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    candidatos: list[tuple[str, bytes]] = []

    png = io.BytesIO()
    (img if tem_alpha else img.convert("RGB")).save(png, format="PNG", optimize=True)
    candidatos.append(("png", png.getvalue()))

    if not tem_alpha:
        # sem transparencia, JPEG costuma ficar varias vezes menor sem diferenca visivel
        for q in (85, 78, 70):
            jpg = io.BytesIO()
            img.convert("RGB").save(jpg, format="JPEG", quality=q, optimize=True, progressive=True)
            candidatos.append(("jpg", jpg.getvalue()))
            if len(jpg.getvalue()) <= ALVO_BYTES:
                break

    ext, dados = min(candidatos, key=lambda c: len(c[1]))
    if len(dados) >= antes and img.width == Image.open(caminho).width:
        return resultado                      # ja estava bom, nao mexe

    destino = caminho.with_suffix("." + ext)
    destino.write_bytes(dados)
    if destino != caminho:
        caminho.unlink(missing_ok=True)

    resultado.update({"arquivo": destino.name, "depois_kb": round(len(dados) / 1024, 1),
                      "convertido_para": ext, "mudou": True})
    if len(dados) > ALVO_BYTES:
        resultado["aviso"] = (f"O poster ainda tem {resultado['depois_kb']} KB. "
                              "Acima de ~900 KB o envio fica lento e cai mais em spam.")
    return resultado
