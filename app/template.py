"""Monta o email (assunto, HTML e texto) personalizado por empresa/colaborador."""
from __future__ import annotations

import html
import re
from functools import lru_cache
from pathlib import Path

from . import textfmt
from .config import settings
from .links import apresentar_empresa, normalizar_imagem, slug

_TEMPLATE = Path(__file__).resolve().parent / "templates" / "campanha.html"

# Content-IDs usados quando o envio e por SMTP (imagem viaja dentro do email).
CID_POSTER = "poster@shild"
CID_LOGO_SHILD = "logoshild@shild"


@lru_cache(maxsize=1)
def _raw() -> str:
    return _TEMPLATE.read_text(encoding="utf-8")


# --------------------------------------------------------------------------- #
# blocos
# --------------------------------------------------------------------------- #
def _bloco_empresa(url: str, empresa: str) -> str:
    """Cabecalho com a marca da empresa do colaborador.

    Com logo: 'chip' branco (funciona com logo de qualquer cor sobre o azul) + nome abaixo.
    Sem logo: so o nome, em corpo maior — evita repetir o nome duas vezes.
    """
    seguro = html.escape(empresa)
    direto = normalizar_imagem(url, largura=400)
    if not direto:
        return ('<p style="margin:0;color:#ffffff;font-family:Arial,Helvetica,sans-serif;'
                f'font-size:24px;font-weight:800;line-height:1.3;">{seguro}</p>')
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center" '
        'style="margin:0 auto;background:#ffffff;border-radius:12px;">'
        '<tr><td style="padding:14px 24px;text-align:center;">'
        f'<img src="{html.escape(direto, quote=True)}" width="160" alt="{html.escape(empresa, quote=True)}" '
        'style="display:block;border:0;outline:none;width:160px;max-width:160px;height:auto;">'
        "</td></tr></table>"
        '<p style="margin:16px 0 0;color:#ffffff;font-family:Arial,Helvetica,sans-serif;'
        f'font-size:17px;font-weight:bold;line-height:1.3;">{seguro}</p>'
    )


def _logo_shild(srcs: dict) -> str:
    src = srcs.get("shild")
    if src is None:
        src = html.escape(normalizar_imagem(settings.email_logo_url, largura=320), quote=True)
    if not src:
        return ('<span style="color:#ffffff;font-family:Arial,Helvetica,sans-serif;font-size:24px;'
                'font-weight:800;letter-spacing:5px;">SHILD</span>')
    return (f'<img src="{src}" width="130" alt="SHILD" '
            'style="display:inline-block;border:0;outline:none;max-width:130px;height:auto;">')


def _poster(camp: dict, srcs: dict) -> str:
    src = srcs.get("poster")
    if src is None:
        src = html.escape(normalizar_imagem(camp.get("poster_url", ""), largura=1200), quote=True)
    if not src:
        return ""
    return (
        '<tr><td style="padding:0;font-size:0;line-height:0;background:#f2f2f2;">'
        f'<img src="{src}" width="600" alt="Poster da campanha" '
        'style="display:block;border:0;outline:none;width:100%;max-width:600px;height:auto;">'
        "</td></tr>"
    )


def _cta(texto: str, url: str) -> str:
    texto, url = (texto or "").strip(), (url or "").strip()
    if not (texto and url):
        return ""
    return (
        '<tr><td style="padding:16px 34px 6px;text-align:center;">'
        '<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center" style="margin:0 auto;"><tr>'
        '<td style="border-radius:10px;background:#c8905d;">'
        f'<a href="{html.escape(url, quote=True)}" target="_blank" '
        'style="display:inline-block;padding:16px 36px;font-family:Arial,Helvetica,sans-serif;font-size:16px;'
        'font-weight:bold;color:#002643;text-decoration:none;border-radius:10px;">'
        f"{html.escape(texto)} &rarr;</a></td></tr></table></td></tr>"
    )


def _links_rodape() -> str:
    partes = []
    if settings.shild_site_url:
        partes.append(f'<a href="{html.escape(settings.shild_site_url, quote=True)}" '
                      'style="color:#8b96a8;text-decoration:underline;">shild.click</a>')
    if settings.instagram_url:
        partes.append(f'<a href="{html.escape(settings.instagram_url, quote=True)}" '
                      'style="color:#8b96a8;text-decoration:underline;">@shildconsultoria</a>')
    return " &middot; ".join(partes)


def _unsub_html() -> str:
    if settings.mail_unsubscribe_email:
        link = (f"mailto:{settings.mail_unsubscribe_email}"
                "?subject=Descadastrar&body=Nao%20desejo%20receber%20novos%20comunicados")
        return f'Nao quer mais receber estes comunicados? <a href="{link}" style="color:#5a6472;">Clique aqui</a>.'
    return "Para nao receber novos comunicados, responda este email com o assunto SAIR."


def _unsub_texto() -> str:
    if settings.mail_unsubscribe_email:
        return f"Para nao receber novos comunicados, escreva para {settings.mail_unsubscribe_email}."
    return "Para nao receber novos comunicados, responda este email com o assunto SAIR."


# --------------------------------------------------------------------------- #
# montagem
# --------------------------------------------------------------------------- #
def _vars(camp: dict, empresa: str, nome: str) -> dict:
    primeiro = (nome or "").strip().split(" ")[0] if nome else ""
    return {
        "empresa": empresa,
        "EMPRESA": empresa.upper(),
        "nome": (nome or "").strip(),
        "primeiro_nome": primeiro,
    }


VAR_RE = re.compile(r"\{(\w+)\}")
CAMPOS_COM_VARIAVEL = ("eyebrow", "assunto", "titulo", "saudacao", "mensagem", "preheader", "cta_url")


def _aplicar(txt: str, v: dict) -> str:
    """Substitui {empresa}, {nome}, {primeiro_nome}, {virgula_nome}.

    Tolerante de proposito: `{Empresa}` e `{EMPRESA}` funcionam igual a `{empresa}`,
    e um nome de variavel que nao existe fica como esta em vez de quebrar o email.
    """
    if not txt:
        return ""
    # {virgula_nome} engole o espaco anterior: "Ola {virgula_nome}!" -> "Ola, Maria!"
    virgula = f", {v['primeiro_nome']}" if v.get("primeiro_nome") else ""
    txt = re.sub(r"[ \t]*\{virgula_nome\}", virgula, txt, flags=re.IGNORECASE)

    def rep(m: re.Match) -> str:
        chave = m.group(1)
        if chave in v:
            return str(v[chave])
        for k, valor in v.items():          # tenta de novo ignorando maiuscula/minuscula
            if k.lower() == chave.lower():
                return str(valor)
        return m.group(0)

    return VAR_RE.sub(rep, txt)


def variaveis_desconhecidas(camp: dict) -> list[str]:
    """Variaveis escritas na campanha que nao existem — sairiam literais no email."""
    conhecidas = {k.lower() for k in _vars({}, "x", "y")} | {"virgula_nome"}
    achadas = {m.group(1) for campo in CAMPOS_COM_VARIAVEL
               for m in VAR_RE.finditer(camp.get(campo) or "")}
    return sorted(x for x in achadas if x.lower() not in conhecidas)


def _saudacao(camp: dict, v: dict) -> str:
    padrao = "Ola{virgula_nome}! Este comunicado e para toda a equipe {empresa}."
    return _aplicar((camp.get("saudacao") or "").strip() or padrao, v)


def montar(camp: dict, empresa_bruta: str = "", nome: str = "", logo_url: str = "",
           srcs: dict | None = None) -> tuple[str, str, str]:
    """Retorna (assunto, html, texto) para um destinatario.

    `srcs` sobrescreve o endereco das imagens da SHILD: chaves "poster" e "shild".
    No envio por SMTP vem como `cid:...` (imagem embutida); na previa da tela vem
    como caminho local; ausente = comportamento padrao (URL publica ou wordmark).
    """
    srcs = srcs or {}
    empresa = apresentar_empresa(empresa_bruta) or "sua equipe"
    v = _vars(camp, empresa, nome)

    titulo = _aplicar(camp.get("titulo", "") or "Comunicado", v)
    saudacao = _saudacao(camp, v)
    mensagem = _aplicar(camp.get("mensagem", ""), v)
    preheader = (_aplicar(camp.get("preheader", ""), v).strip()
                 or re.sub(r"\s+", " ", textfmt.para_texto(mensagem))[:140])

    html_out = (
        _raw()
        .replace("[[PREHEADER]]", html.escape(preheader))
        .replace("[[EYEBROW]]", html.escape(_aplicar(camp.get("eyebrow", "") or "Comunicado interno", v)))
        .replace("[[BLOCO_EMPRESA]]", _bloco_empresa(logo_url, empresa))
        .replace("[[POSTER]]", _poster(camp, srcs))
        .replace("[[TITULO]]", html.escape(titulo))
        .replace("[[SAUDACAO]]", html.escape(saudacao))
        .replace("[[MENSAGEM]]", textfmt.para_html(mensagem))
        .replace("[[CTA]]", _cta(camp.get("cta_texto", ""), _aplicar(camp.get("cta_url", ""), v)))
        .replace("[[LOGO_SHILD]]", _logo_shild(srcs))
        .replace("[[LINKS]]", _links_rodape())
        .replace("[[UNSUB]]", _unsub_html())
        .replace("[[EMPRESA]]", html.escape(empresa))
    )

    assunto = _aplicar(camp.get("assunto", "") or titulo, v)
    texto = _texto(titulo, saudacao, mensagem, camp, v)
    return assunto, html_out, texto


def _texto(titulo: str, saudacao: str, mensagem: str, camp: dict, v: dict) -> str:
    corpo = [titulo.upper(), "", saudacao, "", textfmt.para_texto(mensagem)]
    cta_t, cta_u = (camp.get("cta_texto") or "").strip(), _aplicar(camp.get("cta_url", ""), v).strip()
    if cta_t and cta_u:
        corpo += ["", f"{cta_t}: {cta_u}"]
    corpo += ["", "--", "SHILD - Gestao inteligente, crescimento imbativel.", _unsub_texto()]
    return "\n".join(corpo)


# --------------------------------------------------------------------------- #
# remetente por empresa
# --------------------------------------------------------------------------- #
def remetente(camp: dict, empresa_bruta: str = "") -> dict:
    """Monta {email, name} do remetente, opcionalmente unico por empresa.

    O dominio precisa estar autenticado no Brevo (SPF/DKIM); com o dominio
    autenticado qualquer prefixo local e aceito sem verificacao individual.
    """
    empresa = apresentar_empresa(empresa_bruta)
    prefixo = (camp.get("from_prefix") or settings.mail_from_prefix or "comunicados").strip().lstrip("@")
    dominio = (camp.get("from_domain") or settings.mail_from_domain).strip().lstrip("@")

    por_empresa = camp.get("from_per_empresa")
    if por_empresa is None:
        por_empresa = settings.mail_from_per_empresa
    if por_empresa and empresa:
        s = slug(empresa)
        if s:
            prefixo = f"{prefixo}-{s}"

    nome_tpl = (camp.get("from_name") or settings.mail_from_name or "Comunicados {empresa}").strip()
    nome = _aplicar(nome_tpl, {"empresa": empresa or "SHILD", "EMPRESA": (empresa or "SHILD").upper()})
    return {"email": f"{prefixo}@{dominio}", "name": nome[:70]}
