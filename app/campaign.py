"""Campanha por email: configuracao, plano de envio, disparo e sync de eventos.

Os destinatarios vem da planilha importada (ver `dados.py`); aqui so cuidamos do
conteudo, de como o email sai e do laco de envio.
"""
from __future__ import annotations

import base64
import time
from pathlib import Path

from . import arquivos, dados, db, mailer, smtp_mailer, template
from .config import settings

CHAVE = "campanha"

SEND_PROG: dict = {"status": "ocioso"}

OPEN_EVENTS = {"opened", "uniqueopened", "loadedbyproxy"}
CLICK_EVENTS = {"click", "clicks"}
PROBLEM_EVENTS = {"hardbounce", "softbounce", "blocked", "spam", "invalid", "error"}

CAMPANHA_PADRAO = {
    "eyebrow": "Comunicado interno",
    "assunto": "",
    "titulo": "",
    "saudacao": "Ola{virgula_nome}! Este comunicado e para toda a equipe {empresa}.",
    "mensagem": "",
    "preheader": "",
    "poster_url": "",
    "anexar_poster": True,
    "cta_texto": "",
    "cta_url": "",
    "from_prefix": settings.mail_from_prefix,
    "from_domain": settings.mail_from_domain,
    "from_name": settings.mail_from_name,
    "from_per_empresa": settings.mail_from_per_empresa,
    "tag": settings.campaign_tag,
    "whatsapp_texto": "",
    "whatsapp_assinatura": "SHILD · Gestão inteligente, crescimento imbatível.",
}


# --------------------------------------------------------------------------- #
# configuracao da campanha
# --------------------------------------------------------------------------- #
def carregar_campanha() -> dict:
    dados_ = dict(CAMPANHA_PADRAO)
    dados_.update(db.ler_config(CHAVE, {}) or {})
    dados_["poster_arquivo"] = arquivos.nome_poster()
    return dados_


def salvar_campanha(parcial: dict) -> dict:
    atual = {k: v for k, v in carregar_campanha().items() if k in CAMPANHA_PADRAO}
    for k in CAMPANHA_PADRAO:
        if k in (parcial or {}):
            atual[k] = parcial[k]
    db.gravar_config(CHAVE, atual)
    return carregar_campanha()


def tag_atual() -> str:
    return (carregar_campanha().get("tag") or settings.campaign_tag).strip()


# --------------------------------------------------------------------------- #
# como o email sai
# --------------------------------------------------------------------------- #
def poster_path(_camp: dict | None = None) -> Path | None:
    return arquivos.caminho_poster()


def _base64_poster() -> list[dict]:
    caminho = arquivos.caminho_poster()
    conteudo = arquivos.bytes_poster()
    if caminho is None or conteudo is None:
        return []
    return [{"content": base64.b64encode(conteudo).decode("ascii"), "name": caminho.name}]


def plano_envio(camp: dict) -> dict:
    """Decide COMO o email sai — e, em especial, se o poster aparece no corpo.

    A API v3 do Brevo nao embute imagem: por ela o poster so aparece se estiver numa
    URL publica; um upload vira anexo. Pelo relay SMTP o arquivo viaja dentro do email
    (multipart/related) e aparece no corpo sem hospedagem nenhuma.
    """
    modo = settings.transporte
    if modo not in ("api", "smtp"):
        modo = "smtp" if smtp_mailer.configurado() else "api"

    avisos: list[str] = []
    if modo == "smtp" and not smtp_mailer.configurado():
        modo = "api"
        avisos.append("TRANSPORTE=smtp mas falta BREVO_SMTP_LOGIN/BREVO_SMTP_KEY. Usando a API.")

    arquivo = arquivos.caminho_poster()
    url = (camp.get("poster_url") or "").strip()
    srcs: dict[str, str] = {}
    recursos: dict[str, Path] = {}
    previa: dict[str, str] = {}
    anexos: list[dict] = []

    if modo == "smtp":
        logo = settings.brand_dir / "shild-branca.png"
        if not settings.email_logo_url and logo.exists():
            srcs["shild"] = f"cid:{template.CID_LOGO_SHILD}"
            recursos[template.CID_LOGO_SHILD] = logo
            previa["shild"] = "/static/brand/shild-branca.png"

    if modo == "smtp" and arquivo:
        srcs["poster"] = f"cid:{template.CID_POSTER}"
        recursos[template.CID_POSTER] = arquivo
        previa["poster"] = "/api/poster/arquivo"
        poster_como = "embutido"
    elif url:
        poster_como = "url"
        if arquivo and camp.get("anexar_poster"):
            anexos.extend(_base64_poster())
    elif arquivo and camp.get("anexar_poster"):
        poster_como = "anexo"
        anexos.extend(_base64_poster())
        avisos.append(
            "O poster vai como ANEXO: o funcionario precisa baixar para ver. "
            "Para ele aparecer no corpo do email, configure o SMTP no .env "
            "(BREVO_SMTP_LOGIN/BREVO_SMTP_KEY) ou cole a URL publica do poster.")
    elif arquivo:
        poster_como = "ausente"
        avisos.append("Ha um poster enviado, mas ele nao vai sair: o anexo esta desmarcado "
                      "e nao ha SMTP configurado nem URL publica.")
    else:
        poster_como = "ausente"

    return {"transporte": modo, "srcs": srcs, "srcs_previa": {**srcs, **previa},
            "recursos": recursos, "anexos": anexos, "poster_como": poster_como,
            "poster_no_corpo": poster_como in ("embutido", "url"), "avisos": avisos,
            "tag": (camp.get("tag") or settings.campaign_tag).strip()}


class _TransporteApi:
    """Adapta a API v3 a mesma interface do relay SMTP."""

    def enviar(self, to_email, subject, html, texto, sender, to_name="",
               anexos=None, inline=None, tag=""):
        return mailer.enviar(to_email, subject, html, texto, sender=sender,
                             to_name=to_name, anexos=anexos, tag=tag)

    def fechar(self) -> None:
        pass


def abrir_transporte(plano: dict):
    return smtp_mailer.Sessao() if plano["transporte"] == "smtp" else _TransporteApi()


# --------------------------------------------------------------------------- #
# disparo
# --------------------------------------------------------------------------- #
def _validar(camp: dict) -> None:
    if not (camp.get("titulo") or "").strip():
        raise ValueError("Defina o titulo da campanha.")
    if not (camp.get("mensagem") or "").strip():
        raise ValueError("Escreva a mensagem da campanha.")


def enviar_campanha(params: dict, progress: dict) -> None:
    modo = params.get("modo", "pendentes")
    max_envios = int(params.get("max_envios", 0) or 0)
    empresa_filtro = (params.get("empresa") or "").strip()
    apenas_teste = bool(params.get("apenas_teste"))

    progress.update({"status": "rodando", "etapa": "Preparando", "enviados": 0, "erros": 0,
                     "total": 0, "atual": "", "cancelar": False, "erro": None, "ultimos": []})
    transporte = None
    try:
        camp = carregar_campanha()
        _validar(camp)
        plano = plano_envio(camp)
        anexos, srcs, recursos, tag = (plano["anexos"], plano["srcs"],
                                       plano["recursos"], plano["tag"])
        progress.update({"transporte": plano["transporte"], "poster_como": plano["poster_como"],
                         "avisos": plano["avisos"]})
        transporte = abrir_transporte(plano)

        if apenas_teste:
            destino = (params.get("test_to") or settings.mail_test_to).strip()
            if not destino:
                raise ValueError("Informe um email de teste (campo na tela ou MAIL_TEST_TO no .env).")
            empresa = (params.get("test_empresa") or "Empresa Exemplo Ltda").strip()
            assunto, html, texto = template.montar(camp, empresa, params.get("test_nome", ""),
                                                   (params.get("test_logo") or "").strip(), srcs=srcs)
            progress.update({"total": 1, "etapa": f"Enviando teste para {destino}"})
            transporte.enviar(destino, "[TESTE] " + assunto, html, texto,
                              sender=template.remetente(camp, empresa),
                              to_name=params.get("test_nome", ""), anexos=anexos,
                              inline=recursos, tag=tag)
            progress.update({"enviados": 1, "status": "concluido", "etapa": "Teste enviado"})
            return

        alvos = dados.alvos("email", tag, modo=modo, empresa=empresa_filtro, limite=max_envios)
        progress["total"] = len(alvos)
        if not alvos:
            progress.update({"status": "concluido", "etapa": "Nada a enviar (0 destinatarios)"})
            return

        for p in alvos:
            if progress.get("cancelar"):
                progress.update({"status": "parado", "etapa": "Cancelado pelo usuario"})
                return
            progress["atual"] = p["email"]
            assunto, html, texto = template.montar(
                camp, p["empresa"] or "", p["nome"] or "", p["logo_url"] or "", srcs=srcs)
            try:
                mid = transporte.enviar(
                    p["email"], assunto, html, texto,
                    sender=template.remetente(camp, p["empresa"] or ""),
                    to_name=p["nome"] or "", anexos=anexos, inline=recursos, tag=tag)
                dados.marcar_enviado(p["id"], "email", tag, mid)
                progress["enviados"] += 1
            except Exception as exc:  # noqa: BLE001
                dados.marcar_erro(p["id"], "email", tag, str(exc))
                progress["erros"] += 1
                progress["ultimos"] = ([f"{p['email']}: {str(exc)[:120]}"]
                                       + progress.get("ultimos", []))[:8]
            feitos = progress["enviados"] + progress["erros"]
            progress["etapa"] = f"Enviando {feitos}/{progress['total']}"
            time.sleep(settings.send_delay_seconds)

        progress.update({"status": "concluido", "etapa": "Envio concluido"})
    except Exception as exc:  # noqa: BLE001
        progress.update({"status": "erro", "erro": f"{type(exc).__name__}: {exc}", "etapa": "Erro"})
    finally:
        if transporte is not None:
            transporte.fechar()


# --------------------------------------------------------------------------- #
# sync de eventos (abertura / clique)
# --------------------------------------------------------------------------- #
def agregar_eventos(eventos: list[dict]) -> dict[str, dict]:
    agg: dict[str, dict] = {}
    for ev in eventos:
        email = (ev.get("email") or "").strip().lower()
        if not email:
            continue
        tipo = (ev.get("event") or "").strip().lower().replace(" ", "")
        a = agg.setdefault(email, {"delivered": 0, "opened": 0, "opened_count": 0,
                                   "clicked": 0, "clicked_count": 0, "bounced": 0,
                                   "last_link": None, "last_event_at": None})
        data = ev.get("date")
        if data and (a["last_event_at"] is None or data > a["last_event_at"]):
            a["last_event_at"] = data
        if tipo == "delivered":
            a["delivered"] = 1
        elif tipo in OPEN_EVENTS:
            a["opened"] = 1; a["opened_count"] += 1
        elif tipo in CLICK_EVENTS:
            a["clicked"] = 1; a["clicked_count"] += 1
            if ev.get("link"):
                a["last_link"] = ev["link"]
        elif tipo in PROBLEM_EVENTS:
            a["bounced"] = 1
    return agg


def sincronizar_eventos() -> dict:
    tag = tag_atual()
    evs = mailer.eventos(tag=tag)
    origem = f"tag '{tag}'"
    if not evs:
        # O relay SMTP nem sempre propaga o X-Mailin-Tag para a busca por tag.
        # Sem tag, puxamos tudo — so casamos com quem esta na nossa base.
        evs = mailer.eventos(tag=None)
        origem = "todos os eventos recentes (a tag nao retornou nada)"
    atualizados = dados.aplicar_eventos(agregar_eventos(evs), "email", tag)
    return {"eventos_lidos": len(evs), "contatos_atualizados": atualizados,
            "origem": origem, "resumo": dados.resumo("email", tag)}
