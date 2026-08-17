"""Planilha Google como fonte da verdade dos funcionarios.

A planilha e privada, entao o acesso e por **conta de servico** — que tambem e o
unico jeito que funciona num servidor, onde nao ha ninguem para clicar num consentimento.

O cabecalho nao fica na primeira linha (na planilha da SHILD comeca na linha 5), por
isso `SHEET_HEADER_ROW` e configuravel. A partir dele, cada registro carrega o **numero
da linha** — e o endereco usado para gravar uma correcao de volta na celula certa.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .config import settings
from .recipients import mapear as _mapear

ESCOPOS = ["https://www.googleapis.com/auth/spreadsheets"]


class SheetsError(Exception):
    pass


def configurado() -> bool:
    return bool(settings.sheet_id and _credencial_bruta())


def _credencial_bruta() -> str:
    """A credencial pode vir como JSON inteiro na env (Coolify) ou como caminho."""
    if settings.google_credentials_json:
        return settings.google_credentials_json
    if settings.google_credentials_file and Path(settings.google_credentials_file).exists():
        return Path(settings.google_credentials_file).read_text(encoding="utf-8")
    return ""


def _info_credencial() -> dict:
    bruto = _credencial_bruta().strip()
    if not bruto:
        raise SheetsError(
            "Credencial do Google ausente. Defina GOOGLE_CREDENTIALS_JSON (o JSON inteiro "
            "da conta de servico) ou GOOGLE_CREDENTIALS_FILE (caminho do arquivo).")
    try:
        info = json.loads(bruto)
    except json.JSONDecodeError as exc:
        raise SheetsError(f"GOOGLE_CREDENTIALS_JSON nao e um JSON valido: {exc}") from exc
    if info.get("type") != "service_account":
        raise SheetsError("A credencial precisa ser de uma CONTA DE SERVICO "
                          '(o JSON tem "type": "service_account").')
    # o Coolify costuma escapar as quebras de linha da chave privada
    if "private_key" in info:
        info["private_key"] = info["private_key"].replace("\\n", "\n")
    return info


def email_da_conta() -> str:
    """Email da conta de servico — e com ele que a planilha precisa ser compartilhada."""
    try:
        return _info_credencial().get("client_email", "")
    except SheetsError:
        return ""


def extrair_id(url_ou_id: str) -> str:
    bruto = (url_ou_id or "").strip()
    m = re.search(r"/spreadsheets/d/([a-zA-Z0-9_-]{20,})", bruto)
    return m.group(1) if m else bruto


@lru_cache(maxsize=1)
def _cliente():
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as exc:  # noqa: F841
        raise SheetsError("Faltam dependencias: pip install gspread google-auth") from exc
    cred = Credentials.from_service_account_info(_info_credencial(), scopes=ESCOPOS)
    return gspread.authorize(cred)


def _planilha():
    import gspread

    sid = extrair_id(settings.sheet_id)
    if not sid:
        raise SheetsError("SHEET_ID nao definido no .env (aceita a URL inteira da planilha).")
    try:
        return _cliente().open_by_key(sid)
    except gspread.exceptions.APIError as exc:
        codigo = getattr(exc, "response", None)
        status = getattr(codigo, "status_code", "")
        if status in (403, 404):
            raise SheetsError(
                f"Sem acesso a planilha (HTTP {status}). Compartilhe a planilha com "
                f"{email_da_conta() or 'a conta de servico'} como Editor."
            ) from exc
        raise SheetsError(f"Erro da API do Google: {exc}") from exc


def _aba(nome: str = ""):
    import gspread

    pl = _planilha()
    alvo = nome or settings.sheet_tab
    if not alvo:
        return pl.sheet1
    try:
        return pl.worksheet(alvo)
    except gspread.exceptions.WorksheetNotFound as exc:
        disponiveis = ", ".join(w.title for w in pl.worksheets())
        raise SheetsError(f"A aba '{alvo}' nao existe. Abas na planilha: {disponiveis}") from exc


def abas() -> list[str]:
    return [w.title for w in _planilha().worksheets()]


def testar() -> dict:
    """Diagnostico para a tela: consegue abrir? quantas linhas? cabecalho reconhecido?"""
    pl = _planilha()
    ws = _aba()
    linha_cab = settings.sheet_header_row
    cabecalho = ws.row_values(linha_cab)
    idx = _mapear(cabecalho)
    faltando = [c for c in ("empresa", "nome") if c not in idx]
    if "email" not in idx and "telefone" not in idx:
        faltando.append("email ou telefone")
    return {
        "planilha": pl.title,
        "aba": ws.title,
        "abas": [w.title for w in pl.worksheets()],
        "linha_cabecalho": linha_cab,
        "cabecalho": cabecalho,
        "colunas_reconhecidas": {k: cabecalho[v] for k, v in idx.items() if v < len(cabecalho)},
        "colunas_faltando": faltando,
        "linhas_de_dados": max(0, ws.row_count - linha_cab),
        "conta_de_servico": email_da_conta(),
    }


CAMPOS_EDITAVEIS = ("empresa", "logo_url", "nome", "email", "telefone")


def ler(nome_aba: str = "") -> dict:
    """Le a planilha inteira. Cada item traz `linha` — o endereco para gravar de volta."""
    ws = _aba(nome_aba)
    linha_cab = settings.sheet_header_row
    tudo = ws.get_all_values()
    if len(tudo) < linha_cab:
        raise SheetsError(f"A aba '{ws.title}' tem menos de {linha_cab} linhas — "
                          f"o cabecalho deveria estar na linha {linha_cab}.")
    cabecalho = tudo[linha_cab - 1]
    idx = _mapear(cabecalho)
    if not idx:
        raise SheetsError(
            f"Nao reconheci nenhuma coluna na linha {linha_cab} da aba '{ws.title}'. "
            f"Encontrei: {cabecalho}")

    itens = []
    for deslocamento, linha in enumerate(tudo[linha_cab:], start=linha_cab + 1):
        def g(campo: str) -> str:
            i = idx.get(campo)
            return str(linha[i]).strip() if (i is not None and i < len(linha)) else ""

        if not any(g(c) for c in ("empresa", "nome", "email", "telefone")):
            continue                                   # linha em branco no meio
        itens.append({
            "linha": deslocamento,
            "empresa": g("empresa"), "logo_url": g("logo_url"), "nome": g("nome"),
            "email": g("email").lower(), "telefone": g("telefone"),
        })
    return {"aba": ws.title, "cabecalho": cabecalho, "colunas": idx, "itens": itens,
            "linha_cabecalho": linha_cab}


def _coluna_de(campo: str, idx: dict[str, int]) -> int:
    if campo not in idx:
        raise SheetsError(f"A planilha nao tem coluna para '{campo}', entao nao da para gravar.")
    return idx[campo] + 1                              # gspread conta a partir de 1


def gravar(linha: int, mudancas: dict, nome_aba: str = "") -> dict:
    """Grava as correcoes nas celulas daquela linha. Devolve o que foi escrito."""
    proibidos = [k for k in mudancas if k not in CAMPOS_EDITAVEIS]
    if proibidos:
        raise SheetsError(f"Campos nao editaveis: {', '.join(proibidos)}")
    ws = _aba(nome_aba)
    cabecalho = ws.row_values(settings.sheet_header_row)
    idx = _mapear(cabecalho)

    from gspread.utils import rowcol_to_a1

    lote = [{"range": rowcol_to_a1(linha, _coluna_de(campo, idx)), "values": [[str(valor)]]}
            for campo, valor in mudancas.items()]
    if not lote:
        return {}
    ws.batch_update(lote, value_input_option="USER_ENTERED")
    return mudancas
