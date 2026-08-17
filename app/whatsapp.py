"""Cliente da Evolution API (instancia propria) para disparo no WhatsApp."""
from __future__ import annotations

import base64
from pathlib import Path

import httpx

from .config import settings

# Legenda de midia no WhatsApp. Acima disso o texto e cortado pelo proprio app,
# entao o excedente vai numa segunda mensagem de texto.
LIMITE_LEGENDA = 1024


class EvolutionError(Exception):
    pass


def configurado() -> bool:
    return bool(settings.evo_url and settings.evo_key and settings.evo_instance)


def _base() -> str:
    return settings.evo_url.rstrip("/")


def _headers() -> dict:
    if not configurado():
        raise EvolutionError(
            "Evolution API nao configurada. Defina EVOLUTION_API_URL, EVOLUTION_API_KEY "
            "e EVOLUTION_INSTANCE no .env."
        )
    return {"apikey": settings.evo_key, "Content-Type": "application/json"}


def _erro(r: httpx.Response) -> str:
    try:
        corpo = r.json()
        msg = corpo.get("message") or corpo.get("error") or corpo
    except ValueError:
        msg = r.text[:300]
    return f"HTTP {r.status_code}: {str(msg)[:300]}"


def _pedir(metodo: str, caminho: str, timeout: float = 30, **kw) -> httpx.Response:
    """Toda chamada passa por aqui: servidor fora do ar vira EvolutionError, nao 500.

    Sem isso, um `httpx.ConnectError` sobe pela rota e derruba a tela inteira em vez
    de mostrar 'instancia inacessivel'.
    """
    url = f"{_base()}{caminho}"
    try:
        with httpx.Client(timeout=timeout) as c:
            return c.request(metodo, url, headers=_headers(), **kw)
    except httpx.TimeoutException as exc:
        raise EvolutionError(f"A Evolution API nao respondeu em {timeout}s ({url}).") from exc
    except httpx.HTTPError as exc:
        raise EvolutionError(
            f"Nao consegui falar com a Evolution API em {_base()}: {type(exc).__name__}. "
            "Confira EVOLUTION_API_URL e se o servidor esta no ar.") from exc


def estado() -> dict:
    """Estado da instancia: 'open' = conectada ao WhatsApp."""
    r = _pedir("GET", f"/instance/connectionState/{settings.evo_instance}", timeout=25)
    if r.status_code != 200:
        raise EvolutionError(_erro(r))
    dados = r.json()
    interno = dados.get("instance", dados)
    return {"estado": interno.get("state", "desconhecido"), "instancia": settings.evo_instance}


def checar_numeros(numeros: list[str]) -> dict[str, dict]:
    """Pergunta ao WhatsApp quais numeros existem e qual e o JID correto.

    Resolve de uma vez o problema do nono digito: em vez de adivinhar se o numero
    leva ou nao o 9, usamos o JID que o proprio WhatsApp devolve.
    """
    if not numeros:
        return {}
    resultado: dict[str, dict] = {}
    for i in range(0, len(numeros), 90):              # lotes, para nao estourar o payload
        lote = numeros[i:i + 90]
        r = _pedir("POST", f"/chat/whatsappNumbers/{settings.evo_instance}",
                   timeout=60, json={"numbers": lote})
        if r.status_code not in (200, 201):
            raise EvolutionError(_erro(r))
        for item in r.json() or []:
            consultado = str(item.get("number") or "")
            jid = item.get("jid") or ""
            resultado[consultado] = {
                "existe": bool(item.get("exists")),
                "jid": jid,
                "numero": jid.split("@")[0] if jid else consultado,
            }
    return resultado


def enviar_imagem(numero: str, arquivo: Path, legenda: str = "", delay_ms: int = 0) -> str:
    """Envia a imagem composta. Devolve o id da mensagem."""
    corpo = {
        "number": numero,
        "mediatype": "image",
        "mimetype": "image/jpeg",
        "media": base64.b64encode(arquivo.read_bytes()).decode("ascii"),
        "fileName": arquivo.name,
    }
    if legenda:
        corpo["caption"] = legenda[:LIMITE_LEGENDA]
    if delay_ms:
        corpo["delay"] = delay_ms

    r = _pedir("POST", f"/message/sendMedia/{settings.evo_instance}", timeout=120, json=corpo)
    if r.status_code not in (200, 201):
        raise EvolutionError(_erro(r))
    return _id(r)


def enviar_texto(numero: str, texto: str, delay_ms: int = 0) -> str:
    corpo = {"number": numero, "text": texto}
    if delay_ms:
        corpo["delay"] = delay_ms
    r = _pedir("POST", f"/message/sendText/{settings.evo_instance}", timeout=60, json=corpo)
    if r.status_code not in (200, 201):
        raise EvolutionError(_erro(r))
    return _id(r)


def _id(r: httpx.Response) -> str:
    try:
        return (r.json().get("key") or {}).get("id", "") or ""
    except ValueError:
        return ""
