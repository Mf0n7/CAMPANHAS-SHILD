"""Converte a mensagem escrita em texto simples no HTML do corpo do email.

Regras (propositalmente poucas, para o uso ser intuitivo):
  linha em branco   -> novo paragrafo
  linha "## Titulo" -> subtitulo
  linhas "- item"   -> lista com marcadores
  **negrito**       -> <b>negrito</b>
  quebra simples    -> <br>
"""
from __future__ import annotations

import html
import re

P = ('<p style="margin:0 0 16px;color:#33404f;font-size:16px;line-height:1.65;'
     'font-family:Arial,Helvetica,sans-serif;">{}</p>')
H = ('<p style="margin:26px 0 10px;color:#002643;font-size:18px;line-height:1.35;'
     'font-weight:bold;font-family:Arial,Helvetica,sans-serif;">{}</p>')
LI = ('<tr><td valign="top" style="padding:0 10px 8px 0;color:#c8905d;font-size:16px;'
      'line-height:1.6;font-family:Arial,Helvetica,sans-serif;">&#9679;</td>'
      '<td style="padding:0 0 8px;color:#33404f;font-size:16px;line-height:1.6;'
      'font-family:Arial,Helvetica,sans-serif;">{}</td></tr>')


def _inline(texto: str) -> str:
    esc = html.escape(texto, quote=False)
    esc = re.sub(r"\*\*(.+?)\*\*", r'<b style="color:#002643;">\1</b>', esc)
    esc = re.sub(
        r"(https?://[^\s<]+)",
        r'<a href="\1" style="color:#01245f;text-decoration:underline;">\1</a>',
        esc,
    )
    return esc.replace("\n", "<br>")


def _tipo(linha: str) -> str:
    nu = linha.lstrip()
    if nu.startswith(("- ", "* ", "• ")):
        return "item"
    if nu.startswith(("## ", "# ")):
        return "titulo"
    return "texto"


def _render(tipo: str, linhas: list[str]) -> str:
    if tipo == "item":
        itens = "".join(LI.format(_inline(ln.lstrip()[2:].strip())) for ln in linhas)
        return ('<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
                f'style="margin:0 0 16px;">{itens}</table>')
    if tipo == "titulo":
        return "\n".join(H.format(_inline(ln.lstrip().lstrip("#").strip())) for ln in linhas)
    return P.format(_inline("\n".join(linhas)))


def para_html(mensagem: str) -> str:
    """Um bloco pode misturar subtitulo, lista e texto; agrupamos linhas do mesmo tipo."""
    saida: list[str] = []
    for bloco in re.split(r"\n\s*\n", (mensagem or "").strip()):
        linhas = [ln.rstrip() for ln in bloco.split("\n") if ln.strip()]
        grupo: list[str] = []
        atual = ""
        for ln in linhas:
            t = _tipo(ln)
            if t != atual and grupo:
                saida.append(_render(atual, grupo))
                grupo = []
            atual = t
            grupo.append(ln)
        if grupo:
            saida.append(_render(atual, grupo))
    return "\n".join(saida)


def para_texto(mensagem: str) -> str:
    """Versao texto puro (fallback para clientes sem HTML)."""
    limpo = re.sub(r"\*\*(.+?)\*\*", r"\1", mensagem or "")
    return re.sub(r"^#{1,2} ", "", limpo, flags=re.MULTILINE).strip()


def para_whatsapp(mensagem: str) -> str:
    """Converte a mesma mensagem para a formatacao do WhatsApp.

    `**negrito**` -> `*negrito*` · `## Titulo` -> `*Titulo*` · `- item` -> `• item`

    Maiuscula/minuscula do que voce escreveu nunca e alterada: se quiser CAIXA ALTA,
    digite em caixa alta.
    """
    linhas = []
    for ln in (mensagem or "").split("\n"):
        nu = ln.strip()
        if nu.startswith(("## ", "# ")):
            linhas.append("*" + nu.lstrip("#").strip() + "*")
        elif nu.startswith(("- ", "* ", "• ")):
            linhas.append("• " + nu[2:].strip())
        else:
            linhas.append(ln)
    texto = "\n".join(linhas)
    texto = re.sub(r"\*\*(.+?)\*\*", r"*\1*", texto)      # negrito do markdown
    texto = re.sub(r"\n{3,}", "\n\n", texto)              # nao acumula linha vazia
    return texto.strip()


def dividir_para_whatsapp(texto: str, limite: int) -> tuple[str, str]:
    """Separa em (legenda da imagem, mensagem seguinte). Corta em paragrafo inteiro."""
    if len(texto) <= limite:
        return texto, ""
    corte = texto.rfind("\n\n", 0, limite)
    if corte < limite * 0.4:                              # sem paragrafo util: corta na linha
        corte = texto.rfind("\n", 0, limite)
    if corte < limite * 0.3:
        corte = texto.rfind(" ", 0, limite)
    if corte <= 0:
        corte = limite
    return texto[:corte].rstrip(), texto[corte:].lstrip()
