"""Reconhecimento das colunas da planilha de funcionarios.

A planilha de controle da SHILD tem o cabecalho
`EMPRESA | LOGO DA EMPRESA | NOME COMPLETO | RG | CPF | EMAIL | TELEFONE | DATA NASC. | DATA INGRESSO`
mas o mapeamento aceita variacoes: quem digita a planilha nao deveria precisar
decorar o nome exato que o sistema espera. RG, CPF e datas sao simplesmente ignorados.
"""
from __future__ import annotations

import re
import unicodedata

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# sinonimos aceitos no cabecalho (sem acento, minusculo)
ALIAS = {
    "email": ("email", "e mail", "e-mail", "mail", "endereco de email", "emails"),
    "empresa": ("empresa", "nome da empresa", "nome empresa", "company", "razao social",
                "razao", "cliente", "organizacao", "unidade"),
    "logo_url": ("logo", "logo url", "logourl", "link da logo", "link logo",
                 "link da logo da empresa", "url da logo", "logo da empresa", "imagem", "link"),
    "nome": ("nome", "nome do funcionario", "funcionario", "colaborador", "nome completo",
             "nome do colaborador"),
    "telefone": ("telefone", "celular", "whatsapp", "whats", "fone", "tel", "numero",
                 "num", "contato", "telefone celular", "telefone whatsapp"),
}


def _norm(h: str) -> str:
    t = unicodedata.normalize("NFKD", str(h or ""))
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9 ]+", " ", t.lower()).strip()


def mapear(cabecalho: list[str]) -> dict[str, int]:
    """Cabecalho -> {campo: indice da coluna}. Campo sem coluna simplesmente nao aparece."""
    idx: dict[str, int] = {}
    normalizado = [_norm(h) for h in cabecalho]
    for campo, nomes in ALIAS.items():
        for i, h in enumerate(normalizado):
            if h in nomes and campo not in idx:
                idx[campo] = i
                break
    return idx
