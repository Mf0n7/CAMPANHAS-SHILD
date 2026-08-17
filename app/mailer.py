"""Cliente da API Brevo: envio transacional + leitura de eventos (abertura/clique)."""
from __future__ import annotations

import httpx

from .config import settings

API = "https://api.brevo.com/v3"


class BrevoError(Exception):
    pass


def configurado() -> bool:
    return bool(settings.brevo_api_key)


def _headers() -> dict:
    if not configurado():
        raise BrevoError("BREVO_API_KEY nao definido no .env (crie uma API key xkeysib- no Brevo).")
    return {
        "api-key": settings.brevo_api_key,
        "accept": "application/json",
        "content-type": "application/json",
    }


def enviar(
    to_email: str,
    subject: str,
    html: str,
    texto: str,
    sender: dict,
    to_name: str = "",
    anexos: list[dict] | None = None,
    tag: str = "",
) -> str:
    """Envia um email transacional. Retorna o messageId do Brevo.

    `anexos` no formato Brevo: [{"content": "<base64>", "name": "poster.png"}].
    """
    body = {
        "sender": sender,
        "to": [{"email": to_email, "name": to_name or to_email}],
        "subject": subject,
        "htmlContent": html,
        "textContent": texto,
        "tags": [tag or settings.campaign_tag],
    }
    if anexos:
        body["attachment"] = anexos
    if settings.mail_reply_to:
        body["replyTo"] = {"email": settings.mail_reply_to}
    if settings.mail_unsubscribe_email:
        body["headers"] = {
            "List-Unsubscribe": f"<mailto:{settings.mail_unsubscribe_email}?subject=Descadastrar>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        }

    with httpx.Client(timeout=60) as client:
        r = client.post(f"{API}/smtp/email", headers=_headers(), json=body)
    if r.status_code not in (200, 201):
        raise BrevoError(f"HTTP {r.status_code}: {r.text[:300]}")
    return r.json().get("messageId", "")


def eventos(tag: str | None = "", dias: int = 45, limite_paginas: int = 100) -> list[dict]:
    """Puxa os eventos dos ultimos `dias`. `tag=None` traz tudo, sem filtrar por tag."""
    todos: list[dict] = []
    offset, limit = 0, 100
    with httpx.Client(timeout=45) as client:
        for _ in range(limite_paginas):
            params = {
                "days": max(1, int(dias)),
                "limit": limit,
                "offset": offset,
                "sort": "desc",
            }
            if tag is not None:
                params["tags"] = tag or settings.campaign_tag
            r = client.get(f"{API}/smtp/statistics/events", headers=_headers(), params=params)
            if r.status_code == 404:  # nenhum evento ainda
                break
            if r.status_code != 200:
                raise BrevoError(f"HTTP {r.status_code}: {r.text[:300]}")
            lote = r.json().get("events", [])
            if not lote:
                break
            todos.extend(lote)
            if len(lote) < limit:
                break
            offset += limit
    return todos
