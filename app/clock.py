"""Relógio da aplicação.

Todas as datas são gravadas como ``datetime`` *naive* no fuso configurado
(``PF_TIMEZONE``). Centralizar aqui facilita congelar o tempo nos testes.
"""

from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.config import get_settings


def now() -> datetime:
    """Data/hora atual no fuso da aplicação, sem tzinfo e sem microssegundos."""
    tz = ZoneInfo(get_settings().timezone)
    return datetime.now(tz).replace(tzinfo=None, microsecond=0)


def today() -> date:
    """Data atual no fuso da aplicação."""
    return now().date()
