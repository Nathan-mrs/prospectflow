"""Testes das métricas do dashboard."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import InteractionType, LeadStatus, Niche, SalePlan
from app.services.billing import ensure_monthly_payments, mark_paid, pending_charges
from app.services.bootstrap import ensure_defaults
from app.services.funnel import FunnelService
from app.services.leads import LeadForm, LeadService
from app.services.metrics import approaches_by_day, funnel_counts, kpis, niche_metrics, revenue_by_month

T0 = datetime(2026, 11, 16, 10, 0)  # segunda


@pytest.fixture
def db(session: Session) -> Session:
    """Barbearias: 4 abordados, 2 responderam, 1 fechou. Pet: 2 abordados, 0 respostas."""
    ensure_defaults(session)
    niches = {n.name: n for n in session.scalars(select(Niche))}
    service, funnel = LeadService(session), FunnelService(session)

    def lead(name: str, niche: str):  # noqa: ANN202
        return service.create(LeadForm(company_name=name, niche_id=niches[niche].id))[0]

    barbers = [lead(f"Barber {i}", "Barbearias") for i in range(5)]  # 1 nunca abordado
    pets = [lead(f"Pet {i}", "Pet Shops") for i in range(2)]
    for item in barbers[:4] + pets:
        funnel.register(item, InteractionType.FIRST_CONTACT, at=T0)
    for item in barbers[:2]:
        funnel.register(item, InteractionType.REPLY, at=T0 + timedelta(hours=2))
    funnel.register(barbers[0], InteractionType.PREVIEW_SENT, at=T0 + timedelta(days=1))
    funnel.move(barbers[0], LeadStatus.WON, plan=SalePlan.ONE_TIME, at=T0 + timedelta(days=2))
    funnel.move(barbers[1], LeadStatus.LOST, lost_reason="Sem verba", at=T0 + timedelta(days=2))
    return session


def test_niche_metrics_and_ranking(db: Session) -> None:
    metrics = niche_metrics(db)
    assert [m.name for m in metrics][:2] == ["Barbearias", "Pet Shops"]
    barber = metrics[0]
    assert (barber.leads, barber.contacted, barber.replied, barber.previews, barber.won) == (5, 4, 2, 1, 1)
    assert barber.response_rate == 0.5 and barber.close_rate == 0.25
    assert barber.revenue == Decimal("497.00")
    pet = metrics[1]
    assert (pet.contacted, pet.replied, pet.response_rate) == (2, 0, 0.0)


def test_lost_leads_still_count_stages_reached(db: Session) -> None:
    barber = niche_metrics(db)[0]
    assert barber.replied == 2  # o perdido também respondeu antes


def test_funnel_counts_are_cumulative(db: Session) -> None:
    counts = dict(funnel_counts(db))
    assert counts[LeadStatus.NEW] == 7
    assert counts[LeadStatus.CONTACTED] == 6
    assert counts[LeadStatus.REPLIED] == 2
    assert counts[LeadStatus.PREVIEW_SENT] == 1
    assert counts[LeadStatus.WON] == 1


def test_cohort_filter_by_first_contact(db: Session) -> None:
    assert dict(funnel_counts(db, since=T0 + timedelta(days=1)))[LeadStatus.CONTACTED] == 0


def test_approaches_by_day_fills_zeros(db: Session) -> None:
    days = approaches_by_day(db, date(2026, 11, 15), date(2026, 11, 17))
    assert days == [(date(2026, 11, 15), 0), (date(2026, 11, 16), 6), (date(2026, 11, 17), 0)]


def test_revenue_and_kpis(db: Session) -> None:
    lead = LeadService(db).create(LeadForm(company_name="Cliente Mensal"))[0]
    FunnelService(db).move(lead, LeadStatus.WON, plan=SalePlan.RECURRING, at=datetime(2026, 10, 5))
    at = datetime(2026, 11, 18, 12)
    ensure_monthly_payments(db, at)
    mark_paid(db, pending_charges(db, at)[0].payment_id, at)

    months = dict((k, (s, r)) for k, s, r in revenue_by_month(db, at, months=2))
    assert months["2026-10"] == (Decimal("297.00"), Decimal("0"))
    assert months["2026-11"] == (Decimal("497.00"), Decimal("49.00"))

    result = kpis(db, at)
    assert result.approaches_week == 6 and result.approaches_prev_week == 0
    assert result.mrr == Decimal("49.00") and result.clients == 2
    assert result.revenue_month == Decimal("546.00")
    assert result.close_rate == pytest.approx(2 / 7)  # movido direto p/ Fechado também conta como abordado
