"""Carrega a configuracao a partir do .env."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# Problemas encontrados ao ler o ambiente. Vao para a tela e para /saude em vez de
# derrubar o processo: uma variavel numerica malformada nao deve impedir o sistema de
# subir — se impedir, voce nem consegue abrir a tela para descobrir qual e.
PROBLEMAS: list[str] = []


def _bool(raw: str) -> bool:
    return str(raw).strip().lower() in ("1", "true", "sim", "yes", "on")


def _num(nome: str, padrao: str, tipo):
    bruto = os.getenv(nome, padrao)
    texto = str(bruto).strip().strip('"').strip("'")
    try:
        return tipo(texto)
    except (TypeError, ValueError):
        PROBLEMAS.append(
            f"{nome} tem valor invalido ({texto[:60]!r}); usando o padrao {padrao}. "
            "Causa tipica: as variaveis foram coladas grudadas e uma engoliu a seguinte — "
            "confira se cada uma esta numa linha propria."
        )
        return tipo(padrao)


def _int(nome: str, padrao: str) -> int:
    return _num(nome, padrao, int)


def _float(nome: str, padrao: str) -> float:
    return _num(nome, padrao, float)


def _database_url() -> str:
    """Postgres em producao; SQLite num arquivo local quando nada for definido."""
    bruto = os.getenv("DATABASE_URL", "").strip()
    if not bruto:
        arquivo = BASE_DIR / os.getenv("DB_FILE", "saidas/campanhas.db")
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{arquivo.as_posix()}"
    # o Coolify entrega postgres://; o SQLAlchemy 2 quer o driver explicito
    if bruto.startswith("postgres://"):
        bruto = bruto.replace("postgres://", "postgresql+psycopg://", 1)
    elif bruto.startswith("postgresql://"):
        bruto = bruto.replace("postgresql://", "postgresql+psycopg://", 1)
    return bruto


@dataclass
class Settings:
    host: str = os.getenv("HOST", "127.0.0.1")
    port: int = _int("PORT", "8010")
    output_dir: Path = BASE_DIR / os.getenv("OUTPUT_DIR", "saidas")
    database_url: str = _database_url()

    # ---- Brevo ----
    brevo_api_key: str = os.getenv("BREVO_API_KEY", "").strip()
    # Relay SMTP: unico caminho que embute a imagem DENTRO do email (a API v3 nao
    # suporta CID/inline — so aceita anexo ou URL publica).
    smtp_host: str = os.getenv("BREVO_SMTP_HOST", "smtp-relay.brevo.com").strip()
    smtp_port: int = _int("BREVO_SMTP_PORT", "587")
    smtp_login: str = os.getenv("BREVO_SMTP_LOGIN", "").strip()
    smtp_key: str = os.getenv("BREVO_SMTP_KEY", "").strip()
    transporte: str = os.getenv("TRANSPORTE", "auto").strip().lower()
    mail_from_domain: str = os.getenv("MAIL_FROM_DOMAIN", "shild.click").strip().lstrip("@")
    mail_from_prefix: str = os.getenv("MAIL_FROM_PREFIX", "comunicados").strip()
    mail_from_name: str = os.getenv("MAIL_FROM_NAME", "Comunicados {empresa}").strip()
    mail_from_per_empresa: bool = _bool(os.getenv("MAIL_FROM_PER_EMPRESA", "0"))
    mail_reply_to: str = os.getenv("MAIL_REPLY_TO", "").strip()
    mail_unsubscribe_email: str = os.getenv("MAIL_UNSUBSCRIBE_EMAIL", "").strip()
    mail_test_to: str = os.getenv("MAIL_TEST_TO", "").strip()
    campaign_tag: str = os.getenv("CAMPAIGN_TAG", "campanha-interna").strip()
    send_delay_seconds: float = _float("SEND_DELAY_SECONDS", "1.5")

    # ---- WhatsApp (Evolution API, instancia propria) ----
    evo_url: str = os.getenv("EVOLUTION_API_URL", "").strip()
    evo_key: str = os.getenv("EVOLUTION_API_KEY", "").strip()
    evo_instance: str = os.getenv("EVOLUTION_INSTANCE", "").strip()
    wa_delay_seconds: float = _float("WA_DELAY_SECONDS", "8")
    wa_ddd_padrao: str = os.getenv("WA_DDD_PADRAO", "").strip()

    # ---- Marca ----
    email_logo_url: str = os.getenv("EMAIL_LOGO_URL", "").strip()
    shild_site_url: str = os.getenv("SHILD_SITE_URL", "https://shild.click/").strip()
    instagram_url: str = os.getenv("INSTAGRAM_URL", "").strip()

    @property
    def uploads_dir(self) -> Path:
        return self.output_dir / "uploads"

    @property
    def brand_dir(self) -> Path:
        return Path(__file__).resolve().parent / "static" / "brand"

    def smtp_configurado(self) -> bool:
        return bool(self.smtp_login and self.smtp_key)

    @property
    def campanha_json(self) -> Path:
        return self.output_dir / "campanha.json"


settings = Settings()
settings.output_dir.mkdir(parents=True, exist_ok=True)
settings.uploads_dir.mkdir(parents=True, exist_ok=True)
