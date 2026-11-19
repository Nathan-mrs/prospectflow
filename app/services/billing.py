"""Cobrança mensal dos clientes no plano recorrente (R$ 297 + R$ 49/mês)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models import Payment, Sale, SalePlan


def _months(start: date, end: date) -> list[date]:
    """Primeiro dia de cada mês entre ``start`` e ``end`` (inclusive)."""
    months, current = [], date(start.year, start.month, 1)
    while current <= end:
        months.append(current)
        current = date(current.year + (current.month == 12), current.month % 12 + 1, 1)
    return months


def due_date(sale: Sale, month: date) -> date:
    return month.replace(day=sale.billing_day or min(sale.closed_at.day, 28))


def _recurring_sales(session: Session) -> list[Sale]:
    stmt = (
        select(Sale)
        .where(Sale.plan == SalePlan.RECURRING, Sale.active)
        .options(selectinload(Sale.payments), selectinload(Sale.lead))
    )
    return list(session.scalars(stmt))


def ensure_monthly_payments(session: Session, at: datetime) -> int:
    """Cria as mensalidades vencidas que ainda não existem (idempotente).

    A primeira mensalidade vence no mês seguinte ao fechamento.
    Retorna quantas foram criadas.
    """
    created = 0
    today = at.date()
    for sale in _recurring_sales(session):
        existing = {p.reference_month for p in sale.payments}
        closed = sale.closed_at.date()
        for month in _months(closed, today):
            if (month.year, month.month) == (closed.year, closed.month):
                continue
            if due_date(sale, month) > today:
                continue
            key = month.strftime("%Y-%m")
            if key not in existing:
                sale.payments.append(Payment(reference_month=key, amount=sale.monthly_amount))
                created += 1
    session.flush()
    return created


@dataclass(frozen=True, slots=True)
class PendingCharge:
    payment_id: int
    lead_id: int
    company: str
    phone: str | None
    reference_month: str
    amount: Decimal
    due: date
    days_late: int


def pending_charges(session: Session, at: datetime) -> list[PendingCharge]:
    """Mensalidades em aberto, mais atrasadas primeiro."""
    charges: list[PendingCharge] = []
    for sale in _recurring_sales(session):
        for payment in sale.payments:
            if payment.paid_at is not None:
                continue
            year, month = map(int, payment.reference_month.split("-"))
            due = due_date(sale, date(year, month, 1))
            charges.append(PendingCharge(
                payment.id, sale.lead_id, sale.lead.company_name, sale.lead.phone,
                payment.reference_month, payment.amount, due, (at.date() - due).days,
            ))
    return sorted(charges, key=lambda c: c.due)


def mark_paid(session: Session, payment_id: int, at: datetime) -> None:
    payment = session.get(Payment, payment_id)
    if payment is None:
        raise ValueError("Mensalidade não encontrada.")
    payment.paid_at = at
    session.flush()


def current_mrr(session: Session) -> Decimal:
    """Receita recorrente mensal: soma das mensalidades dos contratos ativos."""
    return sum((s.monthly_amount for s in _recurring_sales(session)), Decimal("0"))
