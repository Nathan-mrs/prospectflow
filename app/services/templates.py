"""Templates de mensagem: variáveis, escolha automática e link do WhatsApp."""

from __future__ import annotations

import re
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AWAITING_REPLY, TEMPLATE_VARIABLES, InteractionType, Lead, LeadStatus, MessageTemplate

_VARIABLE = re.compile(r"\{(\w+)\}")


def template_variables(lead: Lead, service_name: str) -> dict[str, str]:
    """Valores das variáveis para um lead. ``{nome}`` cai no nome da empresa se faltar o contato."""
    return {
        "nome": lead.contact_name or lead.company_name,
        "empresa": lead.company_name,
        "servico": service_name,
        "cidade": lead.city or "sua cidade",
    }


def render(body: str, values: dict[str, str]) -> str:
    """Substitui ``{variavel}``; variáveis desconhecidas ficam como estão."""
    return _VARIABLE.sub(lambda m: values.get(m.group(1), m.group(0)), body)


def unknown_variables(body: str) -> list[str]:
    """Variáveis usadas no texto que não existem (para validar o editor)."""
    return sorted({v for v in _VARIABLE.findall(body) if v not in TEMPLATE_VARIABLES})


def whatsapp_link(phone: str | None, text: str = "") -> str | None:
    """Link ``wa.me`` com a mensagem preenchida."""
    if not phone:
        return None
    return f"https://wa.me/{phone}" + (f"?text={quote(text)}" if text else "")


def suggested_stage(lead: Lead) -> InteractionType | None:
    """Qual mensagem faz sentido enviar agora para este lead."""
    if lead.status is LeadStatus.NEW:
        return InteractionType.FIRST_CONTACT
    if lead.status in AWAITING_REPLY:
        return InteractionType.FOLLOW_UP
    if lead.status in (LeadStatus.REPLIED, LeadStatus.PREVIEW_ACCEPTED):
        return InteractionType.PREVIEW_SENT
    return None


def templates_by_stage(session: Session) -> dict[InteractionType, list[MessageTemplate]]:
    """Templates ativos agrupados por etapa (padrão primeiro)."""
    stmt = (
        select(MessageTemplate)
        .where(MessageTemplate.active)
        .order_by(MessageTemplate.is_default.desc(), MessageTemplate.name)
    )
    grouped: dict[InteractionType, list[MessageTemplate]] = {}
    for template in session.scalars(stmt):
        grouped.setdefault(template.stage, []).append(template)
    return grouped
