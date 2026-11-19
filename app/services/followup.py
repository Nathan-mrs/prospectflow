"""Follow-up automático.

* Um lead que aguarda resposta (Abordado, Prévia enviada, Proposta) e cujo
  ``next_followup_at`` já passou está com **follow-up pendente**.
* Depois de ``max_followups`` follow-ups sem resposta, em vez de outro
  follow-up o sistema **sugere marcar como Perdido**.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import AWAITING_REPLY, Lead


def is_due(lead: Lead, at: datetime) -> bool:
    """Lead aguardando resposta com prazo de follow-up vencido."""
    return (
        lead.status in AWAITING_REPLY
        and lead.next_followup_at is not None
        and lead.next_followup_at <= at
    )


def should_suggest_lost(lead: Lead, at: datetime, max_followups: int) -> bool:
    """Prazo vencido e já foram enviados todos os follow-ups permitidos."""
    return is_due(lead, at) and lead.followup_count >= max_followups


@dataclass
class FollowupBuckets:
    """Leads vencidos separados entre "fazer follow-up" e "sugerir perdido"."""

    pending: list[Lead]
    suggest_lost: list[Lead]


def due_followups(session: Session, at: datetime, max_followups: int) -> FollowupBuckets:
    """Busca leads com follow-up vencido (mais antigos primeiro)."""
    stmt = (
        select(Lead)
        .where(
            Lead.status.in_(AWAITING_REPLY),
            Lead.next_followup_at.is_not(None),
            Lead.next_followup_at <= at,
        )
        .options(selectinload(Lead.niche))
        .order_by(Lead.next_followup_at)
    )
    leads = list(session.scalars(stmt))
    return FollowupBuckets(
        pending=[lead for lead in leads if lead.followup_count < max_followups],
        suggest_lost=[lead for lead in leads if lead.followup_count >= max_followups],
    )
