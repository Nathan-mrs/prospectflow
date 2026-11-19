"""Testes do schema: relacionamentos, constraints e cascatas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    AppSetting,
    Interaction,
    InteractionType,
    Lead,
    LeadStatus,
    MessageTemplate,
    Niche,
    Payment,
    Sale,
    SalePlan,
    StatusHistory,
    WebsiteStatus,
)
from app.services.bootstrap import DEFAULT_NICHES, DEFAULT_TEMPLATES, ensure_defaults


def _lead(session: Session, **kwargs: object) -> Lead:
    lead = Lead(company_name="Barbearia do Zé", phone="5511987654321", city="São Paulo", **kwargs)
    session.add(lead)
    session.flush()
    return lead


def test_lead_defaults(session: Session) -> None:
    lead = _lead(session)
    assert lead.status is LeadStatus.NEW
    assert lead.website_status is WebsiteStatus.NONE
    assert lead.priority_score == 0
    assert lead.followup_count == 0
    assert lead.created_at is not None and lead.status_changed_at is not None
    assert lead.whatsapp_url == "https://wa.me/5511987654321"
    assert lead.display_name == "Barbearia do Zé"


def test_lead_defaults_exist_before_flush() -> None:
    lead = Lead(company_name="Pet Feliz")
    assert lead.status is LeadStatus.NEW
    assert lead.followup_count == 0
    lead.followup_count += 1  # regras de negócio podem operar sem flush
    assert lead.followup_count == 1


def test_enum_is_stored_as_value(session: Session) -> None:
    _lead(session, status=LeadStatus.PREVIEW_SENT)
    raw = session.connection().exec_driver_sql("SELECT status FROM leads").scalar_one()
    assert raw == "preview_sent"


def test_niche_lead_relationship(session: Session) -> None:
    niche = Niche(name="Barbearias", weekday=0, keywords=["barber"], color="#000000")
    lead = _lead(session, niche=niche)
    session.refresh(niche)
    assert niche.leads == [lead]
    assert niche.weekday_label == "Segunda"
    assert niche.keywords == ["barber"]


def test_niche_name_is_unique(session: Session) -> None:
    session.add_all([Niche(name="Pet Shops"), Niche(name="Pet Shops")])
    with pytest.raises(IntegrityError):
        session.flush()


def test_deleting_niche_keeps_leads(session: Session) -> None:
    niche = Niche(name="Academias")
    lead = _lead(session, niche=niche)
    session.delete(niche)
    session.flush()
    session.expire_all()
    assert session.get(Lead, lead.id).niche_id is None


def test_deleting_lead_cascades_children(session: Session) -> None:
    lead = _lead(session)
    lead.interactions.append(Interaction(type=InteractionType.FIRST_CONTACT, message="Oi"))
    lead.status_history.append(StatusHistory(from_status=None, to_status=LeadStatus.NEW))
    lead.sale = Sale.for_plan(SalePlan.RECURRING, closed_at=datetime(2026, 10, 5))
    lead.sale.payments.append(Payment(reference_month="2026-11", amount=Decimal("49")))
    session.flush()

    session.delete(lead)
    session.flush()
    for model in (Interaction, StatusHistory, Sale, Payment):
        assert session.scalars(select(model)).first() is None


def test_interactions_ordered_newest_first(session: Session) -> None:
    lead = _lead(session)
    lead.interactions.extend(
        [
            Interaction(type=InteractionType.FIRST_CONTACT, occurred_at=datetime(2026, 11, 1)),
            Interaction(type=InteractionType.FOLLOW_UP, occurred_at=datetime(2026, 11, 3)),
        ]
    )
    session.flush()
    session.expire(lead)
    assert [i.type for i in lead.interactions] == [
        InteractionType.FOLLOW_UP,
        InteractionType.FIRST_CONTACT,
    ]


def test_sale_one_per_lead(session: Session) -> None:
    lead = _lead(session)
    session.add_all([Sale.for_plan(SalePlan.ONE_TIME, lead_id=lead.id) for _ in range(2)])
    with pytest.raises(IntegrityError):
        session.flush()


def test_sale_plan_prices() -> None:
    one_time = Sale.for_plan(SalePlan.ONE_TIME)
    recurring = Sale.for_plan(SalePlan.RECURRING, closed_at=datetime(2026, 1, 31))
    assert one_time.amount == Decimal("497.00") and one_time.monthly_amount in (None, Decimal("0"))
    assert recurring.amount == Decimal("297.00")
    assert recurring.monthly_amount == Decimal("49.00")
    assert recurring.billing_day == 28  # nunca depois do dia 28


def test_payment_unique_per_month(session: Session) -> None:
    lead = _lead(session)
    lead.sale = Sale.for_plan(SalePlan.RECURRING)
    lead.sale.payments.extend(
        [Payment(reference_month="2026-11", amount=Decimal("49")) for _ in range(2)]
    )
    with pytest.raises(IntegrityError):
        session.flush()


def test_ensure_defaults_is_idempotent(session: Session) -> None:
    ensure_defaults(session)
    ensure_defaults(session)
    assert len(session.scalars(select(Niche)).all()) == len(DEFAULT_NICHES)
    assert len(session.scalars(select(MessageTemplate)).all()) == len(DEFAULT_TEMPLATES)
    assert session.get(AppSetting, "daily_goal").value == 10
    weekdays = sorted(n.weekday for n in session.scalars(select(Niche)))
    assert weekdays == list(range(7))  # um nicho por dia da semana
