"""Persistencia. Postgres em producao (Coolify), SQLite no desenvolvimento local.

Uma unica `DATABASE_URL` decide qual dos dois. O SQL fica em SQLAlchemy Core em vez
de string crua justamente para os dois falarem a mesma lingua — `SUM(x='y')`,
`INSERT OR IGNORE` e `datetime('now')` sao SQLite e nao existem no Postgres.

O container e sem estado: poster, texto da campanha e status de disparo vivem todos
aqui. Nada de volume para configurar no Coolify.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import (Boolean, Column, DateTime, Integer, LargeBinary, MetaData, String, Table,
                        Text, UniqueConstraint, create_engine, delete, func, insert, select, update)
from sqlalchemy.engine import Engine, make_url

from .config import settings

metadata = MetaData()

# ---- configuracao da campanha (JSON) e arquivos binarios (poster) ------------
config = Table(
    "config", metadata,
    Column("chave", String(64), primary_key=True),
    Column("valor", Text, nullable=False),
    Column("atualizado_em", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)

arquivos = Table(
    "arquivos", metadata,
    Column("nome", String(255), primary_key=True),
    Column("mime", String(100)),
    Column("conteudo", LargeBinary, nullable=False),
    Column("bytes", Integer),
    Column("atualizado_em", DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)),
)

# ---- pessoas: espelho da planilha Google ------------------------------------
# `linha` e o numero da linha na planilha: e a identidade do registro e o endereco
# usado para gravar a correcao de volta.
pessoas = Table(
    "pessoas", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("aba", String(120), nullable=False),
    Column("linha", Integer, nullable=False),
    Column("empresa", Text, default=""),
    Column("logo_url", Text, default=""),
    Column("nome", Text, default=""),
    Column("email", Text, default=""),
    Column("telefone", Text, default=""),
    Column("telefone_erro", Text, default=""),
    Column("jid", Text, default=""),
    Column("tem_whatsapp", Integer, default=-1),      # -1 nao verificado, 0 nao, 1 sim
    Column("ativo", Boolean, default=True),           # False = sumiu da planilha
    Column("sincronizado_em", DateTime(timezone=True)),
    UniqueConstraint("aba", "linha", name="uq_pessoa_linha"),
)

# ---- envios: um por pessoa por canal ----------------------------------------
envios = Table(
    "envios", metadata,
    Column("id", Integer, primary_key=True, autoincrement=True),
    Column("pessoa_id", Integer, nullable=False),
    Column("canal", String(16), nullable=False),      # email | whatsapp
    Column("tag", String(120), default=""),
    Column("status", String(16), default="pendente"), # pendente | enviado | erro
    Column("message_id", Text, default=""),
    Column("erro", Text, default=""),
    Column("sent_at", DateTime(timezone=True)),
    Column("delivered", Integer, default=0),
    Column("opened", Integer, default=0),
    Column("opened_count", Integer, default=0),
    Column("clicked", Integer, default=0),
    Column("clicked_count", Integer, default=0),
    Column("bounced", Integer, default=0),
    Column("last_link", Text, default=""),
    Column("last_event_at", Text, default=""),
    UniqueConstraint("pessoa_id", "canal", "tag", name="uq_envio"),
)

_engine: Engine | None = None


def alvo() -> str:
    """host:porta/base do banco, sem a senha — para log e diagnostico na tela."""
    try:
        u = make_url(settings.database_url)
        if u.drivername.startswith("sqlite"):
            return f"sqlite: {u.database}"
        return f"{u.host}:{u.port or 5432}/{u.database}"
    except Exception:  # noqa: BLE001
        return "(url invalida)"


def engine() -> Engine:
    global _engine
    if _engine is None:
        url = settings.database_url
        kw = {"pool_pre_ping": True, "future": True}
        if url.startswith("sqlite"):
            kw["connect_args"] = {"check_same_thread": False}
        else:
            # sem timeout explicito, host inalcancavel trava a requisicao ate o
            # timeout do SO — e o healthcheck estoura antes de receber resposta.
            kw.update(pool_size=5, max_overflow=5, pool_recycle=1800,
                      connect_args={"connect_timeout": 5})
        novo = create_engine(url, **kw)
        # `create_all` so depois de `create_engine`, e a atribuicao a `_engine` so
        # depois das duas: se o banco estiver fora do ar agora, a proxima chamada
        # tenta tudo de novo. Atribuir antes deixaria o processo com um engine sem
        # tabela nenhuma ate alguem reiniciar o container.
        metadata.create_all(novo)
        _engine = novo
    return _engine


def agora() -> datetime:
    return datetime.now(timezone.utc)


def ping() -> str:
    """Testa a conexao. Devolve a versao do banco."""
    with engine().connect() as c:
        if settings.database_url.startswith("sqlite"):
            return "SQLite " + c.exec_driver_sql("select sqlite_version()").scalar_one()
        return c.exec_driver_sql("select version()").scalar_one()[:80]


# --------------------------------------------------------------------------- #
# config em JSON
# --------------------------------------------------------------------------- #
def ler_config(chave: str, padrao=None):
    with engine().connect() as c:
        linha = c.execute(select(config.c.valor).where(config.c.chave == chave)).first()
    if not linha:
        return padrao
    try:
        return json.loads(linha[0])
    except json.JSONDecodeError:
        return padrao


def gravar_config(chave: str, valor) -> None:
    bruto = json.dumps(valor, ensure_ascii=False)
    with engine().begin() as c:
        existe = c.execute(select(config.c.chave).where(config.c.chave == chave)).first()
        if existe:
            c.execute(update(config).where(config.c.chave == chave)
                      .values(valor=bruto, atualizado_em=agora()))
        else:
            c.execute(insert(config).values(chave=chave, valor=bruto, atualizado_em=agora()))


# --------------------------------------------------------------------------- #
# arquivos (poster)
# --------------------------------------------------------------------------- #
def gravar_arquivo(nome: str, conteudo: bytes, mime: str = "") -> None:
    with engine().begin() as c:
        c.execute(delete(arquivos).where(arquivos.c.nome == nome))
        c.execute(insert(arquivos).values(nome=nome, mime=mime, conteudo=conteudo,
                                          bytes=len(conteudo), atualizado_em=agora()))


def ler_arquivo(nome: str) -> tuple[bytes, str] | None:
    with engine().connect() as c:
        linha = c.execute(
            select(arquivos.c.conteudo, arquivos.c.mime).where(arquivos.c.nome == nome)).first()
    return (bytes(linha[0]), linha[1] or "") if linha else None


def info_arquivo(nome: str) -> dict | None:
    with engine().connect() as c:
        linha = c.execute(select(arquivos.c.nome, arquivos.c.mime, arquivos.c.bytes,
                                 arquivos.c.atualizado_em)
                          .where(arquivos.c.nome == nome)).first()
    if not linha:
        return None
    return {"nome": linha[0], "mime": linha[1], "bytes": linha[2] or 0,
            "atualizado_em": linha[3].isoformat() if linha[3] else ""}


def apagar_arquivos_exceto(nome: str) -> int:
    with engine().begin() as c:
        return c.execute(delete(arquivos).where(arquivos.c.nome != nome)).rowcount or 0


# --------------------------------------------------------------------------- #
# helpers de contagem que funcionam nos dois bancos
# --------------------------------------------------------------------------- #
def conta_se(condicao):
    """Equivalente portavel de SUM(condicao) do SQLite."""
    return func.coalesce(func.sum(func.cast(condicao, Integer)), 0)
