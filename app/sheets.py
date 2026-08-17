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


TOKEN_URI = "https://oauth2.googleapis.com/token"


def configurado() -> bool:
    # all(): a tupla ("", "") e truthy, entao testar o par direto daria falso positivo
    return bool(settings.sheet_id and (_credencial_bruta() or all(_par_email_chave())))


def _credencial_bruta() -> str:
    """A credencial pode vir como JSON inteiro na env (Coolify) ou como caminho."""
    if settings.google_credentials_json:
        return settings.google_credentials_json
    if settings.google_credentials_file and Path(settings.google_credentials_file).exists():
        return Path(settings.google_credentials_file).read_text(encoding="utf-8")
    return ""


def _par_email_chave() -> tuple[str, str]:
    return settings.google_sa_email, settings.google_sa_private_key


def _normalizar_chave(chave: str) -> str:
    """Repoe as quebras de linha que o painel de env engole.

    Chave privada e PEM: sem os \\n reais a biblioteca nao consegue ler. Coolify e
    afins costumam entregar tudo numa linha so, com \\n literal ou nada.
    """
    chave = chave.strip().strip('"').strip("'").replace("\\n", "\n")
    if "\n" in chave.strip("\n"):
        return chave if chave.endswith("\n") else chave + "\n"
    # veio numa linha unica sem separador nenhum: reconstroi o PEM
    corpo = chave.replace("-----BEGIN PRIVATE KEY-----", "") \
                 .replace("-----END PRIVATE KEY-----", "").replace(" ", "").strip()
    if not corpo:
        return chave
    linhas = [corpo[i:i + 64] for i in range(0, len(corpo), 64)]
    return "-----BEGIN PRIVATE KEY-----\n" + "\n".join(linhas) + "\n-----END PRIVATE KEY-----\n"


def _conferir_chave(chave: str) -> None:
    """Erro comum: copiar 'private_key_id' (hash curto) em vez de 'private_key' (PEM)."""
    if "PRIVATE KEY" in chave:
        return
    limpa = chave.strip()
    if re.fullmatch(r"[0-9a-f]{20,60}", limpa):
        raise SheetsError(
            "GOOGLE_SA_PRIVATE_KEY recebeu o campo errado do JSON. Esse valor curto e o "
            '"private_key_id". O que vale e o campo "private_key", que e longo e comeca '
            'com "-----BEGIN PRIVATE KEY-----".')
    raise SheetsError(
        'GOOGLE_SA_PRIVATE_KEY nao parece uma chave privada: falta o trecho '
        '"-----BEGIN PRIVATE KEY-----". Copie o campo "private_key" do JSON da conta '
        "de servico, inteiro.")


def _do_par() -> dict:
    email, chave = _par_email_chave()
    _conferir_chave(chave)
    if "@" not in email:
        raise SheetsError('GOOGLE_SA_EMAIL deve ser o campo "client_email" do JSON '
                          "(algo como conta@projeto.iam.gserviceaccount.com).")
    return {"type": "service_account", "client_email": email,
            "private_key": _normalizar_chave(chave), "token_uri": TOKEN_URI}


def _info_credencial() -> dict:
    """Aceita o JSON inteiro OU so o par email + chave privada.

    Nao existe versao com client_id/client_secret: numa conta de servico quem assina
    e a CHAVE PRIVADA, nao um segredo curto. Ver GOOGLE_SA_PRIVATE_KEY no .env.example.
    """
    bruto = _credencial_bruta().strip()
    tem_par = all(_par_email_chave())

    if not bruto:
        if tem_par:
            return _do_par()
        raise SheetsError(
            "Credencial do Google ausente. Use GOOGLE_SA_EMAIL + GOOGLE_SA_PRIVATE_KEY "
            "(duas variaveis), ou GOOGLE_CREDENTIALS_JSON com o JSON inteiro da conta "
            "de servico, ou GOOGLE_CREDENTIALS_FILE com o caminho do arquivo.")

    try:
        info = json.loads(bruto)
    except json.JSONDecodeError as exc:
        # Painel de env costuma truncar JSON com quebra de linha, sobrando so "{".
        # Se o par estiver preenchido, ele resolve — nao faz sentido travar por causa
        # de uma variavel quebrada que o usuario nem pretendia usar.
        if tem_par:
            return _do_par()
        raise SheetsError(
            f"GOOGLE_CREDENTIALS_JSON nao e um JSON valido ({exc}). O painel do Coolify "
            "quebra JSON com varias linhas — cole tudo numa linha so, ou (mais simples) "
            "apague essa variavel e use GOOGLE_SA_EMAIL + GOOGLE_SA_PRIVATE_KEY.") from exc

    if info.get("type") != "service_account":
        if tem_par:
            return _do_par()
        raise SheetsError("A credencial precisa ser de uma CONTA DE SERVICO "
                          '(o JSON tem "type": "service_account"). client_id/client_secret '
                          "de OAuth nao servem aqui — nao ha ninguem para autorizar no servidor.")
    info.setdefault("token_uri", TOKEN_URI)
    if "private_key" in info:
        _conferir_chave(info["private_key"])
        info["private_key"] = _normalizar_chave(info["private_key"])
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
