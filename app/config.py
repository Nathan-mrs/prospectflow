"""Configuração da aplicação carregada de variáveis de ambiente / arquivo .env."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"


class Settings(BaseSettings):
    """Configurações globais. Todas podem ser sobrescritas com o prefixo ``PF_`` no .env."""

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_prefix="PF_",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite:///{(DATA_DIR / 'prospectflow.db').as_posix()}"
    timezone: str = "America/Sao_Paulo"
    default_ddd: str = "11"
    host: str = "127.0.0.1"
    port: int = 8080
    storage_secret: str = "troque-este-segredo"
    debug: bool = False


@lru_cache
def get_settings() -> Settings:
    """Retorna a instância única (cacheada) das configurações."""
    return Settings()
