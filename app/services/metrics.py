"""Métricas do dashboard: abordagens, conversão por nicho, funil, faturamento e MRR.

A conversão usa o **histórico de status**: um lead "chegou" a uma etapa se em
algum momento passou por ela (ou por uma posterior), mesmo que depois tenha
sido perdido. As taxas são calculadas sobre os leads **abordados**.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import FUNNEL_ORDER, Interaction, InteractionType, Lead, LeadStatus, Niche, Payment, Sale, StatusHistory
from app.services.billing import current_mrr

_RANK = {status: index for index, status in enumerate(FUNNEL_ORDER)}


def _rate(part: int, whole: int) -> float:
    return part / whole if whole else 0.0


@dataclass
class NicheMetrics:
    """Conversão de um nicho (``niche_id`` 0 = sem nicho)."""

    niche_id: int
    name: str
    color: str
    leads: int = 0
    contacted: int = 0
    replied: int = 0
    previews: int = 0
    won: int = 0
    revenue: Decimal = Decimal("0")

    @property
    def response_rate(self) -> float:
        return _rate(self.replied, self.contacted)

    @property
    def preview_rate(self) -> float:
        return _rate(self.previews, self.contacted)

    @property
    def close_rate(self) -> float:
        return _rate(self.won, self.contacted)


def max_stage_reached(session: Session) -> dict[int, int]:
    """Maior etapa (índice em ``FUNNEL_ORDER``) que cada lead já alcançou."""
    reached: dict[int, int] = defaultdict(int)
    for lead_id, status in session.execute(select(StatusHistory.lead_id, StatusHistory.to_status)):
        if status in _RANK:
            reached[lead_id] = max(reached[lead_id], _RANK[status])
    return reached


def first_contacts(session: Session) -> dict[int, datetime]:
    """Data do primeiro contato de cada lead."""
    stmt = (
        select(Interaction.lead_id, func.min(Interaction.occurred_at))
        .where(Interaction.type == InteractionType.FIRST_CONTACT)
        .group_by(Interaction.lead_id)
    )
    return {lead_id: moment for lead_id, moment in session.execute(stmt)}


def _cohort(session: Session, since: datetime | None) -> set[int] | None:
    """Leads cujo primeiro contato foi a partir de ``since`` (``None`` = todos)."""
    if since is None:
        return None
    return {lead_id for lead_id, moment in first_contacts(session).items() if moment >= since}


def niche_metrics(session: Session, since: datetime | None = None) -> list[NicheMetrics]:
    """Métricas por nicho, ordenadas pelo ranking (fechamento, vendas, resposta)."""
    niches = {n.id: n for n in session.scalars(select(Niche))}
    result: dict[int, NicheMetrics] = {
        n.id: NicheMetrics(n.id, n.name, n.color) for n in niches.values()
    }
    reached = max_stage_reached(session)
    cohort = _cohort(session, since)
    revenue = dict(session.execute(select(Sale.lead_id, Sale.amount)).all())

    for lead_id, niche_id in session.execute(select(Lead.id, Lead.niche_id)):
        key = niche_id or 0
        if key not in result:
            result[key] = NicheMetrics(0, "Sem nicho", "#71717A")
        metrics = result[key]
        metrics.leads += 1
        if cohort is not None and lead_id not in cohort:
            continue
        stage = reached.get(lead_id, 0)
        metrics.contacted += stage >= _RANK[LeadStatus.CONTACTED]
        metrics.replied += stage >= _RANK[LeadStatus.REPLIED]
        metrics.previews += stage >= _RANK[LeadStatus.PREVIEW_SENT]
        metrics.won += stage >= _RANK[LeadStatus.WON]
        metrics.revenue += revenue.get(lead_id, Decimal("0"))

    ranked = [m for m in result.values() if m.leads]
    return sorted(ranked, key=lambda m: (m.close_rate, m.won, m.response_rate, m.contacted), reverse=True)


def funnel_counts(session: Session, since: datetime | None = None) -> list[tuple[LeadStatus, int]]:
    """Quantos leads chegaram a cada etapa do funil."""
    reached = max_stage_reached(session)
    cohort = _cohort(session, since)
    counts: Counter[int] = Counter()
    for lead_id, stage in reached.items():
        if cohort is not None and lead_id not in cohort:
            continue
        for rank in range(stage + 1):
            counts[rank] += 1
    if cohort is not None:
        counts[0] = len(cohort)
    return [(status, counts[index]) for index, status in enumerate(FUNNEL_ORDER)]


def approaches_by_day(session: Session, start: date, end: date) -> list[tuple[date, int]]:
    """Primeiros contatos por dia, incluindo dias sem abordagem (zero)."""
    stmt = select(Interaction.occurred_at).where(
        Interaction.type == InteractionType.FIRST_CONTACT,
        Interaction.occurred_at.between(datetime.combine(start, time.min), datetime.combine(end, time.max)),
    )
    per_day = Counter(moment.date() for moment in session.scalars(stmt))
    days = (end - start).days + 1
    return [(start + timedelta(days=i), per_day[start + timedelta(days=i)]) for i in range(days)]


def revenue_by_month(session: Session, at: datetime, months: int = 6) -> list[tuple[str, Decimal, Decimal]]:
    """``(AAAA-MM, vendas, mensalidades pagas)`` dos últimos ``months`` meses."""
    keys: list[str] = []
    current = date(at.year, at.month, 1)
    for _ in range(months):
        keys.append(current.strftime("%Y-%m"))
        current = (current - timedelta(days=1)).replace(day=1)
    keys.reverse()
    sales: dict[str, Decimal] = defaultdict(Decimal)
    for amount, closed_at in session.execute(select(Sale.amount, Sale.closed_at)):
        sales[closed_at.strftime("%Y-%m")] += amount
    recurring: dict[str, Decimal] = defaultdict(Decimal)
    for amount, paid_at in session.execute(
        select(Payment.amount, Payment.paid_at).where(Payment.paid_at.is_not(None))
    ):
        recurring[paid_at.strftime("%Y-%m")] += amount
    return [(k, sales[k], recurring[k]) for k in keys]


@dataclass(frozen=True, slots=True)
class Kpis:
    approaches_week: int
    approaches_prev_week: int
    response_rate: float
    close_rate: float
    revenue_month: Decimal
    mrr: Decimal
    clients: int


def kpis(session: Session, at: datetime) -> Kpis:
    """Indicadores do topo do dashboard."""
    week_start = at.date() - timedelta(days=at.weekday())
    this_week = sum(c for _, c in approaches_by_day(session, week_start, at.date()))
    prev_start = week_start - timedelta(days=7)
    prev_week = sum(c for _, c in approaches_by_day(session, prev_start, week_start - timedelta(days=1)))
    funnel = dict(funnel_counts(session))
    contacted = funnel[LeadStatus.CONTACTED]
    month = at.strftime("%Y-%m")
    revenue = next((s + r for k, s, r in revenue_by_month(session, at, 1) if k == month), Decimal("0"))
    clients = session.scalar(select(func.count(Sale.id))) or 0
    return Kpis(
        approaches_week=this_week,
        approaches_prev_week=prev_week,
        response_rate=_rate(funnel[LeadStatus.REPLIED], contacted),
        close_rate=_rate(funnel[LeadStatus.WON], contacted),
        revenue_month=revenue,
        mrr=current_mrr(session),
        clients=clients,
    )
