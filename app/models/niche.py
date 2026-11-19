"""Nicho de mercado (um por dia da semana)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.lead import Lead

WEEKDAY_LABELS = ("Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo")


class Niche(TimestampMixin, Base):
    """Nicho prospectado. ``weekday`` segue ``date.weekday()`` (segunda = 0)."""

    __tablename__ = "niches"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    weekday: Mapped[int | None] = mapped_column(Integer)
    keywords: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    color: Mapped[str] = mapped_column(String(9), default="#6366F1", nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    leads: Mapped[list[Lead]] = relationship(back_populates="niche")

    @property
    def weekday_label(self) -> str:
        """Nome do dia da semana em português (ou ``—``)."""
        return WEEKDAY_LABELS[self.weekday] if self.weekday is not None else "—"

    def __repr__(self) -> str:
        return f"<Niche {self.id} {self.name!r}>"
