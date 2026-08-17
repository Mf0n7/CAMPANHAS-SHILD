"""Normaliza telefone brasileiro para o formato que o WhatsApp usa (E.164 sem '+').

`(86) 99999-9999` -> `5586999999999`

Sobre o nono digito: em DDDs a partir de 31 o WhatsApp costuma guardar o numero
*sem* o 9 inicial, mesmo o numero tendo 9 digitos. Adivinhar isso da errado com
frequencia — por isso existe a validacao pela propria Evolution API
(`whatsapp.checar_numeros`), que devolve o JID correto. Aqui so arrumamos o formato.
"""
from __future__ import annotations

import re

DDDS_VALIDOS = {
    11, 12, 13, 14, 15, 16, 17, 18, 19, 21, 22, 24, 27, 28, 31, 32, 33, 34, 35, 37, 38,
    41, 42, 43, 44, 45, 46, 47, 48, 49, 51, 53, 54, 55, 61, 62, 63, 64, 65, 66, 67, 68,
    69, 71, 73, 74, 75, 77, 79, 81, 82, 83, 84, 85, 86, 87, 88, 89, 91, 92, 93, 94, 95,
    96, 97, 98, 99,
}


def normalizar(bruto: str, ddd_padrao: str = "") -> tuple[str, str]:
    """Devolve (numero, erro). Numero vazio significa que nao deu para usar."""
    d = re.sub(r"\D", "", str(bruto or ""))
    if not d:
        return "", "telefone vazio"
    if d.startswith("00"):
        d = d[2:]

    if d.startswith("55") and len(d) in (12, 13):
        pass                                    # ja veio completo
    elif len(d) in (10, 11):
        d = "55" + d                            # DDD + numero
    elif len(d) in (8, 9):
        if not ddd_padrao:
            return "", f"sem DDD ({d}) — informe um DDD padrao ou corrija a planilha"
        d = "55" + re.sub(r"\D", "", ddd_padrao)[:2] + d
    else:
        return "", f"quantidade de digitos invalida ({len(d)}): {d}"

    if len(d) not in (12, 13):
        return "", f"numero fora do padrao apos normalizar: {d}"
    ddd = int(d[2:4])
    if ddd not in DDDS_VALIDOS:
        return "", f"DDD {ddd} nao existe"
    return d, ""


def formatar(numero: str) -> str:
    """`5586999998888` -> `+55 (86) 99999-8888`, so para mostrar na tela."""
    d = re.sub(r"\D", "", numero or "")
    if len(d) == 13:
        return f"+{d[:2]} ({d[2:4]}) {d[4:9]}-{d[9:]}"
    if len(d) == 12:
        return f"+{d[:2]} ({d[2:4]}) {d[4:8]}-{d[8:]}"
    return numero or ""
