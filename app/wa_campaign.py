"""Campanha por WhatsApp: imagem composta por empresa e disparo pela Evolution API.

Separado do envio por email de proposito — outro transporte e outro ritmo. O *conteudo*
e o mesmo e os destinatarios saem da mesma planilha (ver `dados.py`).
"""
from __future__ import annotations

import time
from pathlib import Path

from . import arquivos, campaign, compositor, dados, textfmt, whatsapp
from .config import settings
from .links import apresentar_empresa

SEND_PROG: dict = {"status": "ocioso"}


# --------------------------------------------------------------------------- #
# validacao dos numeros no WhatsApp
# --------------------------------------------------------------------------- #
def validar_numeros() -> dict:
    """Pergunta ao WhatsApp quem existe e guarda o JID certo (resolve o nono digito)."""
    tag = campaign.tag_atual()
    pessoas = dados.listar("whatsapp", tag, limite=100000)
    numeros = [p["telefone"] for p in pessoas if p["telefone"]]
    if not numeros:
        return {"verificados": 0, "com_whatsapp": 0, "sem_whatsapp": 0,
                "resumo": dados.resumo("whatsapp", tag)}

    mapa = whatsapp.checar_numeros(numeros)
    com = sem = 0
    for p in pessoas:
        info = mapa.get(p["telefone"])
        if info is None:
            continue
        if info["existe"]:
            com += 1
            dados.marcar_whatsapp(p["id"], True, info["numero"])
        else:
            sem += 1
            dados.marcar_whatsapp(p["id"], False)
    return {"verificados": com + sem, "com_whatsapp": com, "sem_whatsapp": sem,
            "resumo": dados.resumo("whatsapp", tag)}


# --------------------------------------------------------------------------- #
# texto e imagem
# --------------------------------------------------------------------------- #
def montar_texto(camp: dict, empresa_bruta: str = "", nome: str = "") -> str:
    """Texto no formato do WhatsApp, com as mesmas variaveis do email."""
    from .template import _aplicar, _saudacao, _vars

    empresa = apresentar_empresa(empresa_bruta) or "sua equipe"
    v = _vars(camp, empresa, nome)

    proprio = (camp.get("whatsapp_texto") or "").strip()
    if proprio:
        corpo = textfmt.para_whatsapp(_aplicar(proprio, v))
    else:
        titulo = _aplicar(camp.get("titulo") or "", v).strip()
        partes = []
        if titulo:
            partes.append(f"*{titulo}*")
        partes.append(_saudacao(camp, v))
        partes.append(textfmt.para_whatsapp(_aplicar(camp.get("mensagem") or "", v)))
        corpo = "\n\n".join(p for p in partes if p)

    assinatura = (camp.get("whatsapp_assinatura") or "").strip()
    return f"{corpo}\n\n_{assinatura}_" if assinatura else corpo


def imagem_da_empresa(camp: dict, empresa_bruta: str, logo_url: str,
                      usar_cache: bool = True) -> dict:
    poster = arquivos.caminho_poster()
    if poster is None:
        raise compositor.CompositorError(
            "Nenhum poster enviado. Suba a arte no passo 1 antes de disparar no WhatsApp.")
    return compositor.para_empresa(poster, apresentar_empresa(empresa_bruta), logo_url or "",
                                   usar_cache=usar_cache)


def plano(camp: dict) -> dict:
    """O que vai acontecer no disparo — mostrado na tela antes de confirmar."""
    texto = montar_texto(camp, "Empresa Exemplo Ltda", "Maria Silva")
    legenda, resto = textfmt.dividir_para_whatsapp(texto, whatsapp.LIMITE_LEGENDA)
    avisos: list[str] = []
    if not whatsapp.configurado():
        avisos.append("Evolution API nao configurada: preencha EVOLUTION_API_URL, "
                      "EVOLUTION_API_KEY e EVOLUTION_INSTANCE.")
    if arquivos.caminho_poster() is None:
        avisos.append("Nenhum poster enviado — o WhatsApp precisa da imagem.")
    if resto:
        avisos.append(f"O texto tem {len(texto)} caracteres e a legenda da imagem cabe "
                      f"{whatsapp.LIMITE_LEGENDA}. O restante vai numa segunda mensagem.")
    return {"caracteres": len(texto), "legenda": legenda, "resto": resto,
            "duas_mensagens": bool(resto), "avisos": avisos,
            "evolution_configurada": whatsapp.configurado()}


# --------------------------------------------------------------------------- #
# disparo
# --------------------------------------------------------------------------- #
def enviar_campanha(params: dict, progress: dict) -> None:
    modo = params.get("modo", "pendentes")
    max_envios = int(params.get("max_envios", 0) or 0)
    empresa_filtro = (params.get("empresa") or "").strip()
    apenas_teste = bool(params.get("apenas_teste"))
    pular_sem_whatsapp = params.get("pular_sem_whatsapp", True)

    progress.update({"status": "rodando", "etapa": "Preparando", "enviados": 0, "erros": 0,
                     "total": 0, "atual": "", "cancelar": False, "erro": None, "ultimos": []})
    try:
        camp = campaign.carregar_campanha()
        if arquivos.caminho_poster() is None:
            raise ValueError("Nenhum poster enviado. Suba a arte da campanha primeiro.")
        if not whatsapp.configurado():
            raise ValueError("Evolution API nao configurada.")
        tag = campaign.tag_atual()

        if apenas_teste:
            destino = (params.get("test_to") or "").strip()
            if not destino:
                raise ValueError("Informe um numero de teste.")
            from .fones import normalizar
            numero, erro = normalizar(destino, settings.wa_ddd_padrao)
            if erro:
                raise ValueError(f"Numero de teste invalido: {erro}")
            empresa = (params.get("test_empresa") or "Empresa Exemplo Ltda").strip()
            progress.update({"total": 1, "etapa": f"Enviando teste para {numero}"})
            img = imagem_da_empresa(camp, empresa, (params.get("test_logo") or "").strip(),
                                    usar_cache=False)
            _enviar_um(camp, numero, empresa, params.get("test_nome", ""), img["arquivo"])
            progress.update({"enviados": 1, "status": "concluido", "etapa": "Teste enviado"})
            return

        alvos = dados.alvos("whatsapp", tag, modo=modo, empresa=empresa_filtro,
                            pular_sem_whatsapp=pular_sem_whatsapp, limite=max_envios)
        progress["total"] = len(alvos)
        if not alvos:
            progress.update({"status": "concluido", "etapa": "Nada a enviar (0 destinatarios)"})
            return

        cache_img: dict[tuple, Path] = {}
        for p in alvos:
            if progress.get("cancelar"):
                progress.update({"status": "parado", "etapa": "Cancelado pelo usuario"})
                return
            progress["atual"] = p["telefone"]
            chave = (p["empresa"] or "", p["logo_url"] or "")
            try:
                if chave not in cache_img:      # uma composicao por empresa, nao por pessoa
                    progress["etapa"] = f"Montando imagem de {p['empresa'] or 'sem empresa'}"
                    cache_img[chave] = imagem_da_empresa(camp, chave[0], chave[1])["arquivo"]
                numero = p["jid"] or p["telefone"]
                mid = _enviar_um(camp, numero, p["empresa"] or "", p["nome"] or "",
                                 cache_img[chave])
                dados.marcar_enviado(p["id"], "whatsapp", tag, mid)
                progress["enviados"] += 1
            except Exception as exc:  # noqa: BLE001
                dados.marcar_erro(p["id"], "whatsapp", tag, str(exc))
                progress["erros"] += 1
                progress["ultimos"] = ([f"{p['telefone']}: {str(exc)[:120]}"]
                                       + progress.get("ultimos", []))[:8]
            feitos = progress["enviados"] + progress["erros"]
            progress["etapa"] = f"Enviando {feitos}/{progress['total']}"
            time.sleep(settings.wa_delay_seconds)

        progress.update({"status": "concluido", "etapa": "Envio concluido"})
    except Exception as exc:  # noqa: BLE001
        progress.update({"status": "erro", "erro": f"{type(exc).__name__}: {exc}", "etapa": "Erro"})


def _enviar_um(camp: dict, numero: str, empresa: str, nome: str, imagem: Path) -> str:
    texto = montar_texto(camp, empresa, nome)
    legenda, resto = textfmt.dividir_para_whatsapp(texto, whatsapp.LIMITE_LEGENDA)
    mid = whatsapp.enviar_imagem(numero, imagem, legenda)
    if resto:
        time.sleep(1.5)
        whatsapp.enviar_texto(numero, resto)
    return mid
