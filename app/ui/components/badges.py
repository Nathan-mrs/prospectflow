"""Badges coloridos (status, nicho, score)."""

from __future__ import annotations

import re
from html import escape

from nicegui import ui

from app.models.enums import LeadStatus
from app.services.score import score_label

_HEX = re.compile(r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})")

#: Cor base de cada etapa do funil.
STATUS_COLORS: dict[LeadStatus, str] = {
    LeadStatus.NEW: "#64748B",
    LeadStatus.CONTACTED: "#0EA5E9",
    LeadStatus.REPLIED: "#8B5CF6",
    LeadStatus.PREVIEW_ACCEPTED: "#F59E0B",
    LeadStatus.PREVIEW_SENT: "#EC4899",
    LeadStatus.PROPOSAL: "#4F46E5",
    LeadStatus.WON: "#16A34A",
    LeadStatus.LOST: "#DC2626",
}


def safe_color(color: str | None, fallback: str = "#71717A") -> str:
    """Aceita só ``#RGB``/``#RRGGBB`` (cores de nicho são editáveis pelo usuário)."""
    return color if color and _HEX.fullmatch(color) else fallback


def badge_html(text: str, color: str, dot: bool = True) -> str:
    """HTML de um badge com fundo translúcido da cor (funciona em claro e escuro)."""
    color = safe_color(color)
    if len(color) == 4:  # #RGB → #RRGGBB, para poder anexar a opacidade
        color = "#" + "".join(ch * 2 for ch in color[1:])
    dot_html = f'<span class="pf-dot" style="background:{color}"></span>' if dot else ""
    return (
        f'<span class="pf-badge" style="background:{color}1F;color:{color}">'
        f"{dot_html}{escape(text)}</span>"
    )


def soft_badge(text: str, color: str, dot: bool = False) -> ui.html:
    """Badge genérico."""
    return ui.html(badge_html(text, color, dot), sanitize=False, tag="span")


def status_badge(status: LeadStatus) -> ui.html:
    return soft_badge(status.label, STATUS_COLORS[status], dot=True)


def niche_badge(name: str | None, color: str | None) -> ui.html:
    return soft_badge(name or "Sem nicho", color or "#71717A", dot=True)


def score_color(score: int) -> str:
    if score >= 80:
        return "#16A34A"
    if score >= 60:
        return "#0EA5E9"
    if score >= 40:
        return "#D97706"
    return "#71717A"


def score_badge(score: int) -> ui.html:
    return soft_badge(f"{score} · {score_label(score)}", score_color(score))
