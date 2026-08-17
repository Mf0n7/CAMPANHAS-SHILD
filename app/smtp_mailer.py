"""Envio pelo relay SMTP do Brevo.

Existe por um motivo unico e importante: a API v3 do Brevo **nao** suporta imagem
embutida (CID). Por ela, o poster so aparece dentro do email se estiver numa URL
publica; um arquivo enviado vira anexo, que o funcionario precisa baixar.

Pelo SMTP montamos um `multipart/related` de verdade: a imagem viaja junto do email
e aparece no corpo, em qualquer cliente, sem hospedagem nenhuma.
"""
from __future__ import annotations

import mimetypes
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path

from .config import settings


class SmtpError(Exception):
    pass


def configurado() -> bool:
    return settings.smtp_configurado()


def _tipo(caminho: Path) -> tuple[str, str]:
    tipo, _ = mimetypes.guess_type(caminho.name)
    if not tipo or "/" not in tipo:
        tipo = "application/octet-stream"
    principal, _, sub = tipo.partition("/")
    return principal, sub


def montar_mensagem(
    to_email: str,
    subject: str,
    html: str,
    texto: str,
    sender: dict,
    to_name: str = "",
    anexos: list[dict] | None = None,
    inline: dict[str, Path] | None = None,
    tag: str = "",
) -> EmailMessage:
    """`inline` = {cid: caminho}. O HTML deve referenciar como <img src="cid:CID">."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = formataddr((sender.get("name", ""), sender["email"]))
    msg["To"] = formataddr((to_name or "", to_email))
    msg["Message-ID"] = make_msgid(domain=sender["email"].split("@")[-1])
    if settings.mail_reply_to:
        msg["Reply-To"] = settings.mail_reply_to
    if settings.mail_unsubscribe_email:
        msg["List-Unsubscribe"] = f"<mailto:{settings.mail_unsubscribe_email}?subject=Descadastrar>"
        msg["List-Unsubscribe-Post"] = "List-Unsubscribe=One-Click"
    if tag:
        # header proprietario do Brevo: alimenta a tag em Transacional > Logs/Estatisticas
        msg["X-Mailin-Tag"] = tag

    msg.set_content(texto)
    msg.add_alternative(html, subtype="html")

    if inline:
        parte_html = msg.get_payload()[-1]     # a alternativa HTML
        for cid, caminho in inline.items():
            caminho = Path(caminho)
            if not caminho.exists():
                continue
            principal, sub = _tipo(caminho)
            # disposition="inline" e obrigatorio: sem isso o cabecalho sai como
            # "attachment" e o Gmail mostra a arte como anexo para baixar, mesmo
            # estando embutida no corpo. Por isso tambem nao mandamos filename.
            parte_html.add_related(caminho.read_bytes(), maintype=principal, subtype=sub,
                                   cid=f"<{cid}>", disposition="inline")

    for a in anexos or []:
        import base64
        principal, sub = _tipo(Path(a["name"]))
        msg.add_attachment(base64.b64decode(a["content"]), maintype=principal,
                           subtype=sub, filename=a["name"])
    return msg


class Sessao:
    """Mantem uma conexao SMTP aberta durante o lote (reconecta sozinha se cair)."""

    def __init__(self) -> None:
        if not configurado():
            raise SmtpError(
                "BREVO_SMTP_LOGIN/BREVO_SMTP_KEY nao definidos no .env. "
                "Pegue em Brevo > SMTP & API > aba SMTP (a chave comeca com xsmtpsib-)."
            )
        self._srv: smtplib.SMTP | None = None

    def _conectar(self) -> smtplib.SMTP:
        if self._srv is not None:
            try:
                self._srv.noop()
                return self._srv
            except (smtplib.SMTPException, OSError):
                self.fechar()
        try:
            srv = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=45)
            srv.ehlo()
            srv.starttls()
            srv.ehlo()
            srv.login(settings.smtp_login, settings.smtp_key)
        except smtplib.SMTPAuthenticationError as exc:
            raise SmtpError(
                f"Login SMTP recusado ({exc.smtp_code}). Confira BREVO_SMTP_LOGIN e "
                "BREVO_SMTP_KEY (a chave SMTP xsmtpsib-, nao a API key xkeysib-)."
            ) from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise SmtpError(f"Nao consegui conectar em {settings.smtp_host}:{settings.smtp_port}: {exc}") from exc
        self._srv = srv
        return srv

    def enviar(self, to_email: str, subject: str, html: str, texto: str, sender: dict,
               to_name: str = "", anexos: list[dict] | None = None,
               inline: dict[str, Path] | None = None, tag: str = "") -> str:
        msg = montar_mensagem(to_email, subject, html, texto, sender, to_name, anexos, inline, tag)
        srv = self._conectar()
        try:
            srv.send_message(msg)
        except smtplib.SMTPServerDisconnected:
            self.fechar()
            self._conectar().send_message(msg)
        except smtplib.SMTPRecipientsRefused as exc:
            raise SmtpError(f"Destinatario recusado: {exc.recipients}") from exc
        except smtplib.SMTPException as exc:
            raise SmtpError(str(exc)) from exc
        return msg["Message-ID"]

    def fechar(self) -> None:
        if self._srv is not None:
            try:
                self._srv.quit()
            except (smtplib.SMTPException, OSError):
                pass
            self._srv = None


def testar_conexao() -> str:
    s = Sessao()
    try:
        s._conectar()
        return f"Conectado em {settings.smtp_host}:{settings.smtp_port} como {settings.smtp_login}."
    finally:
        s.fechar()
