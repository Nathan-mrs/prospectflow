"""Testes do gerador de dados fictícios: coerência do histórico com o funil."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AWAITING_REPLY, InteractionType, Lead, LeadStatus, SalePlan
from scripts.seed import seed_database
from tests.conftest import REFERENCE_NOW


def _seed(session: Session, count: int = 120) -> list[Lead]:
    seed_database(session, lead_count=count, rng_seed=1, reference=REFERENCE_NOW)
    return list(session.scalars(select(Lead)))


def test_seed_creates_requested_leads_for_every_niche(session: Session) -> None:
    leads = _seed(session, 70)
    assert len(leads) == 70
    assert len({lead.niche_id for lead in leads}) == 7
    assert len({lead.phone for lead in leads}) == 70  # telefones únicos


def test_seed_is_deterministic(session: Session) -> None:
    first = [(lead.company_name, lead.status) for lead in _seed(session, 30)]
    from app.db import create_db_engine, init_db

    engine = create_db_engine("sqlite://")
    init_db(engine)
    with Session(engine) as other:
        seed_database(other, lead_count=30, rng_seed=1, reference=REFERENCE_NOW)
        second = [(lead.company_name, lead.status) for lead in other.scalars(select(Lead))]
    assert first == second


def test_status_history_is_consistent(session: Session) -> None:
    for lead in _seed(session):
        history = lead.status_history
        assert history[0].from_status is None and history[0].to_status is LeadStatus.NEW
        assert history[-1].to_status is lead.status
        for prev, cur in zip(history, history[1:]):
            assert cur.from_status is prev.to_status
            assert cur.changed_at >= prev.changed_at
        assert all(h.changed_at <= REFERENCE_NOW for h in history)


def test_contacted_leads_have_first_contact(session: Session) -> None:
    for lead in _seed(session):
        types = {i.type for i in lead.interactions}
        if lead.status is LeadStatus.NEW:
            assert not lead.interactions and lead.last_contact_at is None
        else:
            assert InteractionType.FIRST_CONTACT in types
            assert lead.last_contact_at is not None


def test_followups_respect_limit_and_schedule(session: Session) -> None:
    for lead in _seed(session):
        followups = [i for i in lead.interactions if i.type is InteractionType.FOLLOW_UP]
        assert len(followups) == lead.followup_count <= 3
        if lead.status in AWAITING_REPLY:
            assert lead.next_followup_at is not None
        else:
            assert lead.next_followup_at is None


def test_won_leads_have_sale_with_valid_plan(session: Session) -> None:
    leads = _seed(session, 200)
    won = [lead for lead in leads if lead.status is LeadStatus.WON]
    assert won, "o seed deve gerar ao menos uma venda"
    for lead in won:
        assert lead.sale is not None
        if lead.sale.plan is SalePlan.ONE_TIME:
            assert not lead.sale.payments
        for payment in lead.sale.payments:
            assert payment.reference_month > lead.sale.closed_at.strftime("%Y-%m")
    assert all(lead.sale is None for lead in leads if lead.status is not LeadStatus.WON)


def test_lost_leads_have_reason(session: Session) -> None:
    for lead in _seed(session):
        if lead.status is LeadStatus.LOST:
            assert lead.lost_reason


def test_interactions_happen_before_lost(session: Session) -> None:
    for lead in _seed(session, 200):
        if lead.status is LeadStatus.LOST:
            lost_at = lead.status_changed_at
            assert all(i.occurred_at <= lost_at for i in lead.interactions)


def test_interactions_never_in_future(session: Session) -> None:
    for lead in _seed(session):
        assert all(i.occurred_at <= REFERENCE_NOW for i in lead.interactions)
