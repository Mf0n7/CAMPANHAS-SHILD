"""Pessoas (espelho da planilha) e envios (status por canal).

A planilha manda: cada sincronizacao traz o estado atual dela para a tabela `pessoas`.
O que o sistema produz — quem ja recebeu, erro, abertura — fica em `envios`, ligado
pela linha da planilha. Assim a planilha nunca precisa carregar coluna de campanha.

Uma correcao feita na tela grava na celula da planilha *e* no espelho, para a tela
responder na hora sem esperar a proxima sincronizacao.
"""
from __future__ import annotations

from sqlalchemy import and_, delete, func, insert, or_, select, update

from . import fones, sheets
from .config import settings
from .db import agora, conta_se, engine, envios, pessoas

CANAIS = ("email", "whatsapp")


# --------------------------------------------------------------------------- #
# sincronizacao com a planilha
# --------------------------------------------------------------------------- #
def sincronizar(nome_aba: str = "") -> dict:
    lido = sheets.ler(nome_aba)
    aba = lido["aba"]
    vistos: set[int] = set()
    novos = atualizados = 0

    with engine().begin() as c:
        atuais = {r.linha: r for r in c.execute(
            select(pessoas).where(pessoas.c.aba == aba)).fetchall()}

        for it in lido["itens"]:
            telefone, erro_fone = fones.normalizar(it["telefone"], settings.wa_ddd_padrao)
            valores = {
                "empresa": it["empresa"], "logo_url": it["logo_url"], "nome": it["nome"],
                "email": it["email"], "telefone": telefone, "telefone_erro": erro_fone,
                "ativo": True, "sincronizado_em": agora(),
            }
            vistos.add(it["linha"])
            antigo = atuais.get(it["linha"])
            if antigo is None:
                c.execute(insert(pessoas).values(aba=aba, linha=it["linha"], **valores))
                novos += 1
                continue
            if antigo.telefone != telefone:
                valores.update(jid="", tem_whatsapp=-1)   # numero mudou: revalidar
            mudou = any(getattr(antigo, k) != v for k, v in valores.items()
                        if k != "sincronizado_em")
            c.execute(update(pessoas).where(pessoas.c.id == antigo.id).values(**valores))
            atualizados += int(mudou)

        sumiram = [r.id for linha, r in atuais.items() if linha not in vistos and r.ativo]
        if sumiram:
            c.execute(update(pessoas).where(pessoas.c.id.in_(sumiram)).values(ativo=False))

    return {"aba": aba, "linha_cabecalho": lido["linha_cabecalho"],
            "colunas_reconhecidas": list(lido["colunas"]),
            "lidos": len(lido["itens"]), "novos": novos, "atualizados": atualizados,
            "removidos_da_planilha": len(sumiram), "total_ativos": _conta_ativos()}


def _conta_ativos() -> int:
    with engine().connect() as c:
        return c.execute(select(func.count()).select_from(pessoas)
                         .where(pessoas.c.ativo.is_(True))).scalar_one()


def precisa_sincronizar() -> bool:
    return _conta_ativos() == 0


# --------------------------------------------------------------------------- #
# edicao (grava na planilha e no espelho)
# --------------------------------------------------------------------------- #
def editar(pessoa_id: int, mudancas: dict) -> dict:
    limpas = {k: str(v).strip() for k, v in (mudancas or {}).items()
              if k in sheets.CAMPOS_EDITAVEIS}
    if not limpas:
        raise ValueError(f"Nada para editar. Campos aceitos: {', '.join(sheets.CAMPOS_EDITAVEIS)}")

    with engine().connect() as c:
        p = c.execute(select(pessoas).where(pessoas.c.id == pessoa_id)).first()
    if p is None:
        raise ValueError("Pessoa nao encontrada.")

    if "telefone" in limpas:
        numero, erro = fones.normalizar(limpas["telefone"], settings.wa_ddd_padrao)
        if erro:
            raise ValueError(f"Telefone invalido: {erro}")
        limpas["telefone"] = numero
    if "email" in limpas:
        limpas["email"] = limpas["email"].lower()

    sheets.gravar(p.linha, limpas, p.aba)          # planilha primeiro: ela e a fonte

    espelho = dict(limpas, sincronizado_em=agora())
    if "telefone" in limpas and limpas["telefone"] != p.telefone:
        espelho.update(jid="", tem_whatsapp=-1, telefone_erro="")
    with engine().begin() as c:
        c.execute(update(pessoas).where(pessoas.c.id == pessoa_id).values(**espelho))
    return {"id": pessoa_id, "linha": p.linha, "aba": p.aba, "gravado": limpas}


# --------------------------------------------------------------------------- #
# consultas
# --------------------------------------------------------------------------- #
def _junta(canal: str, tag: str):
    return envios.outerjoin(
        pessoas, and_(envios.c.pessoa_id == pessoas.c.id,
                      envios.c.canal == canal, envios.c.tag == tag))


def _colunas(canal: str, tag: str):
    """SELECT de pessoas + o envio daquele canal/campanha (pode nao existir ainda)."""
    e = envios.alias("e")
    origem = pessoas.outerjoin(e, and_(e.c.pessoa_id == pessoas.c.id,
                                       e.c.canal == canal, e.c.tag == tag))
    cols = [pessoas.c.id, pessoas.c.linha, pessoas.c.aba, pessoas.c.empresa, pessoas.c.logo_url,
            pessoas.c.nome, pessoas.c.email, pessoas.c.telefone, pessoas.c.telefone_erro,
            pessoas.c.jid, pessoas.c.tem_whatsapp,
            func.coalesce(e.c.status, "pendente").label("status"),
            func.coalesce(e.c.erro, "").label("erro"),
            func.coalesce(e.c.opened_count, 0).label("opened_count"),
            func.coalesce(e.c.clicked_count, 0).label("clicked_count"),
            func.coalesce(e.c.opened, 0).label("opened"),
            func.coalesce(e.c.clicked, 0).label("clicked"),
            func.coalesce(e.c.bounced, 0).label("bounced"),
            func.coalesce(e.c.delivered, 0).label("delivered"),
            e.c.sent_at]
    return origem, cols, e


def _filtro_canal(canal: str):
    """Quem esta apto a receber por aquele canal."""
    if canal == "email":
        return and_(pessoas.c.email != "", pessoas.c.email.is_not(None))
    return and_(pessoas.c.telefone != "", pessoas.c.telefone.is_not(None))


def listar(canal: str, tag: str, status: str = "", busca: str = "",
           empresa: str = "", limite: int = 500) -> list[dict]:
    origem, cols, e = _colunas(canal, tag)
    q = select(*cols).select_from(origem).where(
        pessoas.c.ativo.is_(True), _filtro_canal(canal))
    if status == "sem_whatsapp":
        q = q.where(pessoas.c.tem_whatsapp == 0)
    elif status == "pendente":
        q = q.where(or_(e.c.status.is_(None), e.c.status == "pendente"))
    elif status:
        q = q.where(e.c.status == status)
    if empresa:
        q = q.where(pessoas.c.empresa == empresa)
    if busca:
        alvo = f"%{busca}%"
        q = q.where(or_(pessoas.c.nome.ilike(alvo), pessoas.c.empresa.ilike(alvo),
                        pessoas.c.email.ilike(alvo), pessoas.c.telefone.ilike(alvo)))
    q = q.order_by(pessoas.c.empresa, pessoas.c.linha).limit(limite)
    with engine().connect() as c:
        return [dict(r._mapping) for r in c.execute(q).fetchall()]


def alvos(canal: str, tag: str, modo: str = "pendentes", empresa: str = "",
          pular_sem_whatsapp: bool = True, limite: int = 0) -> list[dict]:
    origem, cols, e = _colunas(canal, tag)
    q = select(*cols).select_from(origem).where(
        pessoas.c.ativo.is_(True), _filtro_canal(canal))
    if modo == "reenviar_erros":
        q = q.where(or_(e.c.status.is_(None), e.c.status.in_(("pendente", "erro"))))
    elif modo != "todos":
        q = q.where(or_(e.c.status.is_(None), e.c.status == "pendente"))
    if empresa:
        q = q.where(pessoas.c.empresa == empresa)
    if canal == "whatsapp" and pular_sem_whatsapp:
        q = q.where(pessoas.c.tem_whatsapp != 0)
    q = q.order_by(pessoas.c.empresa, pessoas.c.linha)
    if limite:
        q = q.limit(limite)
    with engine().connect() as c:
        return [dict(r._mapping) for r in c.execute(q).fetchall()]


def resumo(canal: str, tag: str) -> dict:
    origem, _cols, e = _colunas(canal, tag)
    pendente = or_(e.c.status.is_(None), e.c.status == "pendente")
    q = select(
        func.count().label("total"),
        conta_se(e.c.status == "enviado").label("enviados"),
        conta_se(pendente).label("pendentes"),
        conta_se(e.c.status == "erro").label("erros"),
        conta_se(e.c.delivered > 0).label("entregues"),
        conta_se(e.c.opened > 0).label("abertos"),
        conta_se(e.c.clicked > 0).label("clicados"),
        conta_se(e.c.bounced > 0).label("bounces"),
        conta_se(pessoas.c.tem_whatsapp == 1).label("com_whatsapp"),
        conta_se(pessoas.c.tem_whatsapp == 0).label("sem_whatsapp"),
        conta_se(pessoas.c.tem_whatsapp == -1).label("nao_verificados"),
    ).select_from(origem).where(pessoas.c.ativo.is_(True), _filtro_canal(canal))
    with engine().connect() as c:
        d = {k: (v or 0) for k, v in c.execute(q).first()._mapping.items()}
    d["taxa_abertura"] = round(100 * d["abertos"] / d["enviados"], 1) if d["enviados"] else 0.0
    d["taxa_clique"] = round(100 * d["clicados"] / d["enviados"], 1) if d["enviados"] else 0.0
    d["sem_canal"] = _sem_canal(canal)
    return d


def _sem_canal(canal: str) -> int:
    """Pessoas ativas que nao tem o dado daquele canal (ficam de fora do disparo)."""
    with engine().connect() as c:
        return c.execute(select(func.count()).select_from(pessoas)
                         .where(pessoas.c.ativo.is_(True), ~_filtro_canal(canal))).scalar_one()


def empresas(canal: str, tag: str) -> list[dict]:
    origem, _cols, e = _colunas(canal, tag)
    q = (select(pessoas.c.empresa,
                func.count().label("total"),
                conta_se(e.c.status == "enviado").label("enviados"),
                conta_se(e.c.opened > 0).label("abertos"),
                conta_se(pessoas.c.tem_whatsapp == 0).label("sem_whatsapp"),
                func.max(pessoas.c.logo_url).label("logo_url"))
         .select_from(origem)
         .where(pessoas.c.ativo.is_(True), _filtro_canal(canal))
         .group_by(pessoas.c.empresa).order_by(func.count().desc()))
    with engine().connect() as c:
        return [dict(r._mapping) for r in c.execute(q).fetchall()]


# --------------------------------------------------------------------------- #
# gravacao de status
# --------------------------------------------------------------------------- #
def _upsert_envio(c, pessoa_id: int, canal: str, tag: str, valores: dict) -> None:
    achou = c.execute(select(envios.c.id).where(
        envios.c.pessoa_id == pessoa_id, envios.c.canal == canal, envios.c.tag == tag)).first()
    if achou:
        c.execute(update(envios).where(envios.c.id == achou[0]).values(**valores))
    else:
        c.execute(insert(envios).values(pessoa_id=pessoa_id, canal=canal, tag=tag, **valores))


def marcar_enviado(pessoa_id: int, canal: str, tag: str, message_id: str) -> None:
    with engine().begin() as c:
        _upsert_envio(c, pessoa_id, canal, tag,
                      {"status": "enviado", "message_id": message_id or "", "erro": "",
                       "sent_at": agora()})


def marcar_erro(pessoa_id: int, canal: str, tag: str, erro: str) -> None:
    with engine().begin() as c:
        _upsert_envio(c, pessoa_id, canal, tag, {"status": "erro", "erro": str(erro)[:300]})


def marcar_whatsapp(pessoa_id: int, tem: bool, jid: str = "") -> None:
    with engine().begin() as c:
        c.execute(update(pessoas).where(pessoas.c.id == pessoa_id)
                  .values(tem_whatsapp=1 if tem else 0, jid=jid or ""))


def resetar(canal: str, tag: str) -> int:
    with engine().begin() as c:
        return c.execute(delete(envios).where(
            envios.c.canal == canal, envios.c.tag == tag)).rowcount or 0


def aplicar_eventos(agg: dict[str, dict], canal: str, tag: str) -> int:
    """Casa os eventos do Brevo (por email) com as pessoas da base."""
    atualizados = 0
    with engine().begin() as c:
        for email, a in agg.items():
            p = c.execute(select(pessoas.c.id).where(
                func.lower(pessoas.c.email) == email.lower())).first()
            if not p:
                continue
            _upsert_envio(c, p[0], canal, tag, {
                "delivered": a["delivered"], "opened": a["opened"],
                "opened_count": a["opened_count"], "clicked": a["clicked"],
                "clicked_count": a["clicked_count"], "bounced": a["bounced"],
                "last_link": a["last_link"] or "", "last_event_at": a["last_event_at"] or "",
            })
            atualizados += 1
    return atualizados


def por_id(pessoa_id: int) -> dict | None:
    with engine().connect() as c:
        r = c.execute(select(pessoas).where(pessoas.c.id == pessoa_id)).first()
    return dict(r._mapping) if r else None
