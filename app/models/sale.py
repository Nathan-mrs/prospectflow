"""Venda fechada e pagamentos mensais."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.clock import now
from app.models.base import Base, TimestampMixin
from app.models.enums import SalePlan, str_enum

if TYPE_CHECKING:
    from app.models.lead import Lead

ONE_TIME_PRICE = Decimal("497.00")
RECURRING_SETUP_PRICE = Decimal("297.00")
RECURRING_MONTHLY_PRICE = Decimal("49.00")

Money = Numeric(10, 2, asdecimal=True)


class Sale(TimestampMixin, Base):
    """Venda de um site. Um lead tem no máximo uma venda."""

    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    plan: Mapped[SalePlan] = mapped_column(str_enum(SalePlan), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    monthly_amount: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"), nullable=False)
    closed_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False, index=True)
    billing_day: Mapped[int | None] = mapped_column(Integer)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    lead: Mapped[Lead] = relationship(back_populates="sale")
    payments: Mapped[list[Payment]] = relationship(
        back_populates="sale", cascade="all, delete-orphan", order_by="Payment.reference_month"
    )

    @classmethod
    def for_plan(
        cls, plan: SalePlan, closed_at: datetime | None = None, lead_id: int | None = None
    ) -> Sale:
        """Cria uma venda com os preços padrão do plano.

        ``lead_id`` pode ficar vazio quando a venda for ligada via ``lead.sale = ...``.
        """
        closed_at = closed_at or now()
        extra = {"lead_id": lead_id} if lead_id is not None else {}
        if plan is SalePlan.ONE_TIME:
            return cls(plan=plan, amount=ONE_TIME_PRICE, closed_at=closed_at, **extra)
        return cls(
            **extra,
            plan=plan,
            amount=RECURRING_SETUP_PRICE,
            monthly_amount=RECURRING_MONTHLY_PRICE,
            closed_at=closed_at,
            billing_day=min(closed_at.day, 28),
        )

    def __repr__(self) -> str:
        return f"<Sale {self.id} lead={self.lead_id} {self.plan.value} {self.amount}>"


class Payment(Base):
    """Mensalidade de uma venda recorrente. ``paid_at`` nulo = pendente."""

    __tablename__ = "payments"
    __table_args__ = (UniqueConstraint("sale_id", "reference_month", name="uq_payment_month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sale_id: Mapped[int] = mapped_column(
        ForeignKey("sales.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reference_month: Mapped[str] = mapped_column(String(7), nullable=False)  # "AAAA-MM"
    amount: Mapped[Decimal] = mapped_column(Money, nullable=False)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime)

    sale: Mapped[Sale] = relationship(back_populates="payments")

    @property
    def is_paid(self) -> bool:
        return self.paid_at is not None
