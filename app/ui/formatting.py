"""Formatação de valores para exibição."""

from __future__ import annotations

from datetime import datetime


def relative_time(moment: datetime | None, reference: datetime) -> str:
    """Tempo relativo em português: "hoje", "ontem", "há 3 dias", "há 2 meses"."""
    if moment is None:
        return "—"
    days = (reference.date() - moment.date()).days
    if days < 0:
        return moment.strftime("%d/%m/%Y")
    if days == 0:
        return "hoje"
    if days == 1:
        return "ontem"
    if days < 30:
        return f"há {days} dias"
    months = days // 30
    if months < 12:
        return "há 1 mês" if months == 1 else f"há {months} meses"
    years = days // 365
    return "há 1 ano" if years == 1 else f"há {years} anos"


def format_datetime(moment: datetime | None) -> str:
    return moment.strftime("%d/%m/%Y %H:%M") if moment else "—"


def format_phone(phone: str | None) -> str:
    """``5511987654321`` → ``(11) 98765-4321``; fixo: ``(11) 3456-7890``."""
    if not phone:
        return "—"
    local = phone[2:] if phone.startswith("55") and len(phone) in (12, 13) else phone
    if len(local) == 11:
        return f"({local[:2]}) {local[2:7]}-{local[7:]}"
    if len(local) == 10:
        return f"({local[:2]}) {local[2:6]}-{local[6:]}"
    return phone


def format_int(value: int | None) -> str:
    """Inteiro com separador de milhar brasileiro."""
    return "—" if value is None else f"{value:,}".replace(",", ".")


def format_rating(value: float | None) -> str:
    return "—" if value is None else f"{value:.1f}".replace(".", ",")


def format_money(value: object) -> str:
    """``1234.5`` → ``R$ 1.234,50``."""
    text = f"{float(value or 0):,.2f}"  # type: ignore[arg-type]
    return "R$ " + text.replace(",", "_").replace(".", ",").replace("_", ".")


def format_percent(value: float) -> str:
    """``0.256`` → ``25,6%``."""
    return f"{value * 100:.1f}%".replace(".", ",")
