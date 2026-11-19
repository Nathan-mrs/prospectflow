"""Fila do dia: os melhores leads novos do nicho do dia + follow-ups pendentes."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.models import Interaction, InteractionType, Lead, LeadStatus, Niche
from app.repositories import NicheRepository, SettingRepository
from app.services.billing import PendingCharge, pending_charges
from app.services.followup import due_followups


@dataclass
class DailyQueue:
    """Tudo o que a tela "Hoje" precisa mostrar."""

    niche: Niche | None
    goal: int
    done_today: int
    new_leads: list[Lead] = field(default_factory=list)
    followups: list[Lead] = field(default_factory=list)
    suggest_lost: list[Lead] = field(default_factory=list)
    charges: list[PendingCharge] = field(default_factory=list)
    remaining_new: int = 0  # leads novos do nicho ainda não exibidos

    @property
    def progress(self) -> float:
        return min(self.done_today / self.goal, 1.0) if self.goal else 1.0


def approaches_on(session: Session, at: datetime) -> int:
    """Quantos primeiros contatos foram feitos no dia de ``at``."""
    start = datetime.combine(at.date(), time.min)
    end = datetime.combine(at.date(), time.max)
    stmt = select(func.count(Interaction.id)).where(
        Interaction.type == InteractionType.FIRST_CONTACT,
        Interaction.occurred_at.between(start, end),
    )
    return session.scalar(stmt) or 0


def build_daily_queue(session: Session, at: datetime, extra: int = 0) -> DailyQueue:
    """Monta a fila do dia.

    Args:
        at: momento de referência (define o dia da semana → nicho).
        extra: leads novos a mais além da meta (botão "carregar mais").
    """
    settings = SettingRepository(session).all()
    goal = int(settings["daily_goal"])
    niche = NicheRepository(session).for_weekday(at.weekday())
    done = approaches_on(session, at)
    queue = DailyQueue(niche=niche, goal=goal, done_today=done)

    if niche is not None:
        base = select(Lead).where(Lead.status == LeadStatus.NEW, Lead.niche_id == niche.id)
        limit = max(goal - done, 0) + extra
        stmt = (
            base.options(selectinload(Lead.niche))
            .order_by(Lead.priority_score.desc(), Lead.created_at)
            .limit(limit)
        )
        queue.new_leads = list(session.scalars(stmt))
        total = session.scalar(base.with_only_columns(func.count(Lead.id))) or 0
        queue.remaining_new = max(total - len(queue.new_leads), 0)

    buckets = due_followups(session, at, int(settings["max_followups"]))
    queue.followups, queue.suggest_lost = buckets.pending, buckets.suggest_lost
    queue.charges = pending_charges(session, at)
    return queue
