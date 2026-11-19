"""Testes do funil, follow-up, templates, cobrança e fila do dia."""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InteractionType, Lead, LeadStatus, Niche, Payment, Sale, SalePlan
from app.services.billing import current_mrr, ensure_monthly_payments, mark_paid, pending_charges
from app.services.bootstrap import ensure_defaults
from app.services.daily_queue import build_daily_queue
from app.services.followup import due_followups, is_due, should_suggest_lost
from app.services.funnel import FunnelError, FunnelService
from app.services.leads import LeadForm, LeadService
from app.services.templates import render, suggested_stage, template_variables, unknown_variables, whatsapp_link

T0 = datetime(2026, 11, 16, 10, 0)  # segunda-feira


@pytest.fixture
def db(session: Session) -> Session:
    ensure_defaults(session)
    return session


def _lead(db: Session, name: str = "Barbearia do Zé", **kwargs: object) -> Lead:
    lead, _ = LeadService(db).create(LeadForm(company_name=name, **kwargs))  # type: ignore[arg-type]
    return lead


def statuses(lead: Lead) -> list[LeadStatus]:
    return [h.to_status for h in lead.status_history]


# --------------------------------------------------------------------------- funil


def test_first_contact_advances_and_schedules_followup(db: Session) -> None:
    lead = _lead(db)
    FunnelService(db).register(lead, InteractionType.FIRST_CONTACT, message="Oi", at=T0)
    assert lead.status is LeadStatus.CONTACTED
    assert lead.last_contact_at == T0
    assert lead.next_followup_at == T0 + timedelta(days=2)
    assert statuses(lead) == [LeadStatus.NEW, LeadStatus.CONTACTED]


def test_followup_increments_counter_and_reschedules(db: Session) -> None:
    lead = _lead(db)
    funnel = FunnelService(db)
    funnel.register(lead, InteractionType.FIRST_CONTACT, at=T0)
    later = T0 + timedelta(days=2)
    funnel.register(lead, InteractionType.FOLLOW_UP, at=later)
    assert lead.followup_count == 1
    assert lead.status is LeadStatus.CONTACTED
    assert lead.next_followup_at == later + timedelta(days=2)


def test_reply_moves_contacted_to_replied_and_cancels_followup(db: Session) -> None:
    lead = _lead(db)
    funnel = FunnelService(db)
    funnel.register(lead, InteractionType.FIRST_CONTACT, at=T0)
    funnel.register(lead, InteractionType.REPLY, note="Quero ver", at=T0 + timedelta(hours=3))
    assert lead.status is LeadStatus.REPLIED
    assert lead.next_followup_at is None


def test_status_never_goes_backwards(db: Session) -> None:
    lead = _lead(db)
    funnel = FunnelService(db)
    funnel.register(lead, InteractionType.PROPOSAL, at=T0)
    funnel.register(lead, InteractionType.FIRST_CONTACT, at=T0 + timedelta(hours=1))
    assert lead.status is LeadStatus.PROPOSAL


def test_won_requires_plan_and_creates_sale(db: Session) -> None:
    lead = _lead(db)
    funnel = FunnelService(db)
    with pytest.raises(FunnelError):
        funnel.move(lead, LeadStatus.WON)
    funnel.move(lead, LeadStatus.WON, plan=SalePlan.RECURRING, at=T0)
    assert lead.sale is not None and lead.sale.monthly_amount == Decimal("49.00")
    funnel.move(lead, LeadStatus.PROPOSAL, at=T0)  # reabre: venda é removida
    db.flush()
    assert lead.sale is None and db.scalars(select(Sale)).first() is None


def test_lost_records_reason_and_blocks_messages(db: Session) -> None:
    lead = _lead(db)
    funnel = FunnelService(db)
    funnel.move(lead, LeadStatus.LOST, lost_reason="Achou caro", at=T0)
    assert lead.lost_reason == "Achou caro"
    assert any(i.note == "Perdido: Achou caro" for i in lead.interactions)
    with pytest.raises(FunnelError):
        funnel.register(lead, InteractionType.FOLLOW_UP)
    funnel.register(lead, InteractionType.NOTE, note="Tentar em 2027")  # anotação continua permitida


def test_move_to_same_status_is_noop(db: Session) -> None:
    lead = _lead(db)
    assert FunnelService(db).move(lead, LeadStatus.NEW) is False
    assert len(lead.status_history) == 1


# --------------------------------------------------------------------------- follow-up


def test_followup_due_and_lost_suggestion(db: Session) -> None:
    lead = _lead(db)
    funnel = FunnelService(db)
    funnel.register(lead, InteractionType.FIRST_CONTACT, at=T0)
    assert not is_due(lead, T0 + timedelta(days=1))
    assert is_due(lead, T0 + timedelta(days=2))
    moment = T0
    for _ in range(3):
        moment += timedelta(days=2)
        funnel.register(lead, InteractionType.FOLLOW_UP, at=moment)
    after = moment + timedelta(days=2)
    assert should_suggest_lost(lead, after, max_followups=3)
    buckets = due_followups(db, after, 3)
    assert buckets.suggest_lost == [lead] and buckets.pending == []


# --------------------------------------------------------------------------- templates


def test_render_and_whatsapp_link(db: Session) -> None:
    lead = _lead(db, contact_name="Zé", city="Osasco", phone="11987654321")
    values = template_variables(lead, "criação de site")
    text = render("Oi {nome}! Site da {empresa} em {cidade} — {servico}. {outra}", values)
    assert text == "Oi Zé! Site da Barbearia do Zé em Osasco — criação de site. {outra}"
    assert unknown_variables("{nome} {foo} {bar}") == ["bar", "foo"]
    link = whatsapp_link(lead.phone, "Olá, tudo bem?")
    assert link == "https://wa.me/5511987654321?text=Ol%C3%A1%2C%20tudo%20bem%3F"
    assert whatsapp_link(None, "x") is None


def test_name_falls_back_to_company(db: Session) -> None:
    assert template_variables(_lead(db), "x")["nome"] == "Barbearia do Zé"


@pytest.mark.parametrize(
    ("status", "stage"),
    [
        (LeadStatus.NEW, InteractionType.FIRST_CONTACT),
        (LeadStatus.CONTACTED, InteractionType.FOLLOW_UP),
        (LeadStatus.PREVIEW_ACCEPTED, InteractionType.PREVIEW_SENT),
        (LeadStatus.WON, None),
    ],
)
def test_suggested_stage(status: LeadStatus, stage: InteractionType | None) -> None:
    assert suggested_stage(Lead(company_name="x", status=status)) is stage


# --------------------------------------------------------------------------- cobrança


def test_monthly_payments_are_created_once_and_paid(db: Session) -> None:
    lead = _lead(db)
    FunnelService(db).move(lead, LeadStatus.WON, plan=SalePlan.RECURRING, at=datetime(2026, 9, 10, 9))
    at = datetime(2026, 11, 18, 12)
    assert ensure_monthly_payments(db, at) == 2  # outubro e novembro (dia 10 já passou)
    assert ensure_monthly_payments(db, at) == 0  # idempotente
    charges = pending_charges(db, at)
    assert [c.reference_month for c in charges] == ["2026-10", "2026-11"]
    assert charges[0].days_late == 39
    mark_paid(db, charges[0].payment_id, at)
    assert len(pending_charges(db, at)) == 1
    assert current_mrr(db) == Decimal("49.00")
    assert db.scalars(select(Payment)).all()[0].paid_at == at


def test_one_time_sales_have_no_payments(db: Session) -> None:
    lead = _lead(db)
    FunnelService(db).move(lead, LeadStatus.WON, plan=SalePlan.ONE_TIME, at=datetime(2026, 1, 5))
    assert ensure_monthly_payments(db, datetime(2026, 11, 18)) == 0
    assert current_mrr(db) == 0


# --------------------------------------------------------------------------- fila do dia


def test_daily_queue_uses_niche_of_the_day_and_goal(db: Session) -> None:
    monday = db.scalar(select(Niche).where(Niche.weekday == 0))
    other = db.scalar(select(Niche).where(Niche.weekday == 1))
    assert monday is not None and other is not None
    for i in range(12):
        _lead(db, f"Barbearia {i:02d}", niche_id=monday.id, google_rating=str(3 + i * 0.1)[:3])
    _lead(db, "Salão Fora do Dia", niche_id=other.id, google_rating="5")

    queue = build_daily_queue(db, T0)
    assert queue.niche is not None and queue.niche.id == monday.id
    assert len(queue.new_leads) == 10 and queue.remaining_new == 2
    scores = [lead.priority_score for lead in queue.new_leads]
    assert scores == sorted(scores, reverse=True)

    funnel = FunnelService(db)
    for lead in queue.new_leads[:4]:
        funnel.register(lead, InteractionType.FIRST_CONTACT, at=T0)
    queue = build_daily_queue(db, T0)
    assert queue.done_today == 4 and len(queue.new_leads) == 6
    assert build_daily_queue(db, T0, extra=5).remaining_new == 0


def test_daily_queue_includes_due_followups(db: Session) -> None:
    lead = _lead(db, "Pet Feliz")
    FunnelService(db).register(lead, InteractionType.FIRST_CONTACT, at=T0 - timedelta(days=3))
    queue = build_daily_queue(db, T0)
    assert queue.followups == [lead]
