"""Servidor local (FastAPI) do disparador de campanhas SHILD."""
from __future__ import annotations

import threading
from pathlib import Path

from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.exc import SQLAlchemyError

from . import (arquivos, campaign, compositor, dados, db, imagem, mailer, sheets,
               smtp_mailer, template, wa_campaign, whatsapp)
from . import config as config_env
from .config import settings

app = FastAPI(title="Campanhas SHILD")

STATIC = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=STATIC), name="static")
COMPOSTAS = settings.output_dir / "compostas"
COMPOSTAS.mkdir(parents=True, exist_ok=True)
app.mount("/compostas", StaticFiles(directory=COMPOSTAS), name="compostas")

_SEND_LOCK = threading.Lock()
_WA_LOCK = threading.Lock()
_SEND_THREAD: threading.Thread | None = None
_WA_THREAD: threading.Thread | None = None

IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


@app.exception_handler(SQLAlchemyError)
def erro_de_banco(_req: Request, exc: SQLAlchemyError):
    """Banco fora do ar vira mensagem na tela, nao 500 sem explicacao."""
    return JSONResponse({"erro": db.explicar_erro(exc)}, status_code=503)


def _seguro(nome: str) -> str:
    return Path(nome or "arquivo").name.replace("..", "_")


def _avisos(camp: dict, plano: dict) -> list[str]:
    avisos = list(config_env.PROBLEMAS) + list(plano["avisos"])
    desconhecidas = template.variaveis_desconhecidas(camp)
    if desconhecidas:
        avisos.append("Variavel que nao existe e vai sair literal no email: "
                      + ", ".join("{" + v + "}" for v in desconhecidas)
                      + ". Validas: {empresa}, {nome}, {primeiro_nome}, {virgula_nome}.")
    if sheets.configurado() and dados.precisa_sincronizar():
        avisos.append("A base esta vazia. Clique em 'Sincronizar com a planilha'.")
    return avisos


@app.get("/", response_class=HTMLResponse)
def index():
    return (STATIC / "index.html").read_text(encoding="utf-8")


@app.get("/whatsapp", response_class=HTMLResponse)
def pagina_whatsapp():
    return (STATIC / "whatsapp.html").read_text(encoding="utf-8")


@app.get("/saude")
def saude():
    """Liveness: 200 se o processo esta de pe, mesmo com o banco fora.

    De proposito NAO falha quando o banco cai. Um healthcheck que morre junto com a
    dependencia so faz o orquestrador reiniciar o container em loop — e voce nunca
    consegue abrir a tela para descobrir qual e o problema. O estado do banco vai no
    corpo da resposta; para uma sonda de readiness, use /saude/pronto.
    """
    corpo = {"ok": True, "banco_alvo": db.alvo(), "config_problemas": config_env.PROBLEMAS}
    try:
        corpo["banco"] = db.ping()
        corpo["banco_ok"] = True
    except Exception as exc:  # noqa: BLE001
        corpo["banco_ok"] = False
        corpo["banco_erro"] = db.explicar_erro(exc)
    return corpo


@app.get("/saude/pronto")
def pronto():
    """Readiness: 503 enquanto o banco nao responder."""
    try:
        return {"ok": True, "banco": db.ping()}
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"ok": False, "banco_alvo": db.alvo(), "erro": db.explicar_erro(exc)},
                            status_code=503)


# =========================================================================== #
# PLANILHA GOOGLE (fonte da verdade)
# =========================================================================== #
@app.get("/api/sheet/estado")
def sheet_estado():
    base = {"configurada": sheets.configurado(), "conta_de_servico": sheets.email_da_conta(),
            "sheet_id": sheets.extrair_id(settings.sheet_id),
            "linha_cabecalho": settings.sheet_header_row, "aba": settings.sheet_tab}
    if not sheets.configurado():
        base["erro"] = ("Faltam SHEET_ID e/ou a credencial da conta de servico "
                        "(GOOGLE_CREDENTIALS_JSON).")
        return base
    try:
        base.update(sheets.testar(), ok=True)
    except Exception as exc:  # noqa: BLE001
        base.update(ok=False, erro=str(exc)[:400])
    return base


@app.post("/api/sheet/sincronizar")
def sheet_sincronizar(body: dict | None = None):
    try:
        return dados.sincronizar((body or {}).get("aba", ""))
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"erro": str(exc)[:400]}, status_code=400)


@app.get("/api/pessoas")
def api_pessoas(canal: str = "email", status: str = "", busca: str = "", empresa: str = ""):
    tag = campaign.tag_atual()
    return {"itens": dados.listar(canal, tag, status=status, busca=busca, empresa=empresa),
            "editaveis": list(sheets.CAMPOS_EDITAVEIS)}


@app.patch("/api/pessoas/{pessoa_id}")
def api_editar_pessoa(pessoa_id: int, body: dict):
    """Grava a correcao na celula da planilha e no espelho local."""
    try:
        return {"ok": True, **dados.editar(pessoa_id, body or {})}
    except (ValueError, sheets.SheetsError) as exc:
        return JSONResponse({"erro": str(exc)[:400]}, status_code=400)


# =========================================================================== #
# CAMPANHA (conteudo, poster) — compartilhado pelos dois canais
# =========================================================================== #
@app.get("/api/config")
def config():
    camp = campaign.carregar_campanha()
    plano = campaign.plano_envio(camp)
    tag = plano["tag"]
    return {
        "brevo_configurado": mailer.configurado(),
        "smtp_configurado": smtp_mailer.configurado(),
        "sheet": {"configurada": sheets.configurado(),
                  "precisa_sincronizar": dados.precisa_sincronizar()},
        "plano": {**{k: plano[k] for k in ("transporte", "poster_como", "poster_no_corpo")},
                  "avisos": _avisos(camp, plano)},
        "campanha": camp,
        "poster": arquivos.info_poster(),
        "remetente_exemplo": template.remetente(camp, "Empresa Exemplo Ltda"),
        "reply_to": settings.mail_reply_to,
        "test_to": settings.mail_test_to,
        "delay": settings.send_delay_seconds,
        "resumo": dados.resumo("email", tag),
        "empresas": dados.empresas("email", tag),
    }


@app.post("/api/campanha")
def salvar_campanha(body: dict):
    camp = campaign.salvar_campanha(body or {})
    return {"ok": True, "campanha": camp,
            "remetente_exemplo": template.remetente(camp, "Empresa Exemplo Ltda")}


@app.post("/api/poster")
async def upload_poster(arquivo: UploadFile = File(...)):
    nome = _seguro(arquivo.filename)
    if Path(nome).suffix.lower() not in IMG_EXT:
        return JSONResponse({"erro": "Use uma imagem .png, .jpg, .gif ou .webp."}, status_code=400)
    conteudo = await arquivo.read()
    if len(conteudo) > 20 * 1024 * 1024:
        return JSONResponse({"erro": "Imagem acima de 20 MB. Exporte em resolucao menor."},
                            status_code=400)

    # 600 px e a largura do email: um PNG gigante so pesa, nao melhora nada.
    temporario = arquivos.cache_dir() / ("upload" + Path(nome).suffix.lower())
    temporario.write_bytes(conteudo)
    otim = imagem.otimizar(temporario)
    if otim["erro"]:
        temporario.unlink(missing_ok=True)
        return JSONResponse({"erro": otim["erro"]}, status_code=400)

    final = arquivos.cache_dir() / otim.get("arquivo", temporario.name)
    nome_final = Path(nome).stem + final.suffix
    arquivos.guardar_poster(nome_final, final.read_bytes())
    final.unlink(missing_ok=True)
    compositor.limpar_cache()                    # poster novo invalida as imagens montadas

    return {"ok": True, "arquivo": nome_final, "preview_url": "/api/poster/arquivo",
            "tamanho_kb": otim["depois_kb"], "otimizacao": otim,
            "campanha": campaign.carregar_campanha()}


@app.get("/api/poster/arquivo")
def poster_arquivo():
    lido = db.ler_arquivo(arquivos.POSTER)
    if lido is None:
        return JSONResponse({"erro": "Nenhum poster."}, status_code=404)
    return Response(content=lido[0], media_type=lido[1] or "image/jpeg",
                    headers={"Cache-Control": "no-store"})


# =========================================================================== #
# EMAIL
# =========================================================================== #
@app.get("/api/preview", response_class=HTMLResponse)
def preview(empresa: str = "Empresa Exemplo Ltda", nome: str = "Maria", logo: str = ""):
    """A previa usa o MESMO plano do envio — o que aparece aqui e o que o funcionario ve."""
    camp = campaign.carregar_campanha()
    plano = campaign.plano_envio(camp)
    _assunto, html, _texto = template.montar(camp, empresa, nome, logo, srcs=plano["srcs_previa"])
    return html


@app.get("/api/preview/info")
def preview_info(empresa: str = "Empresa Exemplo Ltda", nome: str = "Maria"):
    camp = campaign.carregar_campanha()
    plano = campaign.plano_envio(camp)
    assunto, _html, texto = template.montar(camp, empresa, nome, "", srcs=plano["srcs"])
    return {"assunto": assunto, "texto": texto, "remetente": template.remetente(camp, empresa),
            "transporte": plano["transporte"], "poster_como": plano["poster_como"],
            "avisos": _avisos(camp, plano)}


@app.post("/api/smtp/testar")
def smtp_testar():
    try:
        return {"ok": True, "mensagem": smtp_mailer.testar_conexao()}
    except smtp_mailer.SmtpError as exc:
        return JSONResponse({"erro": str(exc)}, status_code=400)


@app.get("/api/resumo")
def api_resumo():
    tag = campaign.tag_atual()
    return {"resumo": dados.resumo("email", tag), "empresas": dados.empresas("email", tag)}


@app.get("/api/destinatarios")
def destinatarios(status: str = "", busca: str = ""):
    tag = campaign.tag_atual()
    return {"itens": dados.listar("email", tag, status=status, busca=busca)}


@app.post("/api/resetar")
def resetar():
    tag = campaign.tag_atual()
    apagados = dados.resetar("email", tag)
    return {"ok": True, "apagados": apagados, "resumo": dados.resumo("email", tag)}


@app.post("/api/enviar")
def enviar(body: dict):
    global _SEND_THREAD
    if not (mailer.configurado() or smtp_mailer.configurado()):
        return JSONResponse(
            {"erro": "Sem credencial: defina BREVO_API_KEY ou BREVO_SMTP_LOGIN/BREVO_SMTP_KEY."},
            status_code=400)
    with _SEND_LOCK:
        if campaign.SEND_PROG.get("status") == "rodando":
            return JSONResponse({"erro": "Ja existe um envio em andamento."}, status_code=409)
        b = body or {}
        params = {k: b.get(k, v) for k, v in
                  {"modo": "pendentes", "max_envios": 0, "empresa": "", "apenas_teste": False,
                   "test_to": "", "test_empresa": "", "test_nome": "", "test_logo": ""}.items()}
        params["apenas_teste"] = bool(params["apenas_teste"])
        campaign.SEND_PROG.clear()
        campaign.SEND_PROG.update({"status": "rodando"})
        _SEND_THREAD = threading.Thread(
            target=campaign.enviar_campanha, args=(params, campaign.SEND_PROG), daemon=True)
        _SEND_THREAD.start()
    return {"ok": True, "modo": params["modo"]}


@app.post("/api/parar")
def parar():
    if campaign.SEND_PROG.get("status") == "rodando":
        campaign.SEND_PROG["cancelar"] = True
        return {"ok": True}
    return {"ok": False}


@app.get("/api/status")
def status():
    p = dict(campaign.SEND_PROG)
    p.pop("cancelar", None)
    return p


@app.post("/api/sync")
def sync():
    try:
        return campaign.sincronizar_eventos()
    except Exception as exc:  # noqa: BLE001
        return JSONResponse({"erro": str(exc)}, status_code=502)


# =========================================================================== #
# WHATSAPP (Evolution API)
# =========================================================================== #
@app.get("/api/wa/config")
def wa_config():
    camp = campaign.carregar_campanha()
    tag = campaign.tag_atual()
    estado = {"estado": "nao configurada"}
    if whatsapp.configurado():
        try:
            estado = whatsapp.estado()
        except whatsapp.EvolutionError as exc:
            estado = {"estado": "erro", "detalhe": str(exc)}
    return {
        "evolution_configurada": whatsapp.configurado(),
        "instancia": settings.evo_instance, "url": settings.evo_url,
        "conexao": estado, "delay": settings.wa_delay_seconds,
        "ddd_padrao": settings.wa_ddd_padrao,
        "sheet": {"configurada": sheets.configurado(),
                  "precisa_sincronizar": dados.precisa_sincronizar()},
        "campanha": {k: camp.get(k, "") for k in ("titulo", "mensagem", "poster_arquivo",
                                                  "whatsapp_texto", "whatsapp_assinatura")},
        "plano": wa_campaign.plano(camp),
        "resumo": dados.resumo("whatsapp", tag),
        "empresas": dados.empresas("whatsapp", tag),
    }


@app.post("/api/wa/campanha")
def wa_salvar(body: dict):
    camp = campaign.salvar_campanha(body or {})
    return {"ok": True, "plano": wa_campaign.plano(camp)}


@app.get("/api/wa/resumo")
def wa_resumo():
    tag = campaign.tag_atual()
    return {"resumo": dados.resumo("whatsapp", tag), "empresas": dados.empresas("whatsapp", tag)}


@app.get("/api/wa/destinatarios")
def wa_destinatarios(status: str = "", busca: str = ""):
    tag = campaign.tag_atual()
    return {"itens": dados.listar("whatsapp", tag, status=status, busca=busca)}


@app.post("/api/wa/validar")
def wa_validar():
    try:
        return wa_campaign.validar_numeros()
    except whatsapp.EvolutionError as exc:
        return JSONResponse({"erro": str(exc)}, status_code=502)


@app.get("/api/wa/previa")
def wa_previa(empresa: str = "", logo: str = ""):
    """Compoe a imagem de uma empresa e devolve a URL para ver na tela."""
    camp = campaign.carregar_campanha()
    if not empresa:
        emp = dados.empresas("whatsapp", campaign.tag_atual())
        empresa = emp[0]["empresa"] if emp else "Empresa Exemplo Ltda"
        logo = (emp[0].get("logo_url") or "") if emp else ""
    try:
        r = wa_campaign.imagem_da_empresa(camp, empresa, logo, usar_cache=False)
    except compositor.CompositorError as exc:
        return JSONResponse({"erro": str(exc)}, status_code=400)
    return {"ok": True, "url": f"/compostas/{r['arquivo'].name}", "kb": r["kb"],
            "logo_ok": r["logo_ok"], "empresa": empresa,
            "texto": wa_campaign.montar_texto(camp, empresa, "Maria Silva"),
            "plano": wa_campaign.plano(camp)}


@app.post("/api/wa/limpar-cache")
def wa_limpar_cache():
    return {"ok": True, "removidos": compositor.limpar_cache()}


@app.post("/api/wa/resetar")
def wa_resetar():
    tag = campaign.tag_atual()
    apagados = dados.resetar("whatsapp", tag)
    return {"ok": True, "apagados": apagados, "resumo": dados.resumo("whatsapp", tag)}


@app.post("/api/wa/enviar")
def wa_enviar(body: dict):
    global _WA_THREAD
    if not whatsapp.configurado():
        return JSONResponse({"erro": "Evolution API nao configurada."}, status_code=400)
    with _WA_LOCK:
        if wa_campaign.SEND_PROG.get("status") == "rodando":
            return JSONResponse({"erro": "Ja existe um envio em andamento."}, status_code=409)
        b = body or {}
        params = {k: b.get(k, v) for k, v in
                  {"modo": "pendentes", "max_envios": 0, "empresa": "",
                   "pular_sem_whatsapp": True, "apenas_teste": False, "test_to": "",
                   "test_empresa": "", "test_nome": "", "test_logo": ""}.items()}
        params["apenas_teste"] = bool(params["apenas_teste"])
        params["pular_sem_whatsapp"] = bool(params["pular_sem_whatsapp"])
        wa_campaign.SEND_PROG.clear()
        wa_campaign.SEND_PROG.update({"status": "rodando"})
        _WA_THREAD = threading.Thread(
            target=wa_campaign.enviar_campanha, args=(params, wa_campaign.SEND_PROG), daemon=True)
        _WA_THREAD.start()
    return {"ok": True}


@app.post("/api/wa/parar")
def wa_parar():
    if wa_campaign.SEND_PROG.get("status") == "rodando":
        wa_campaign.SEND_PROG["cancelar"] = True
        return {"ok": True}
    return {"ok": False}


@app.get("/api/wa/status")
def wa_status():
    p = dict(wa_campaign.SEND_PROG)
    p.pop("cancelar", None)
    return p
