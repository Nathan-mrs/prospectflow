"""Histórico de mudanças de status (base das métricas de conversão)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.clock import now
from app.models.base import Base
from app.models.enums import LeadStatus, str_enum

if TYPE_CHECKING:
    from app.models.lead import Lead


class StatusHistory(Base):
    """Registro de uma transição ``from_status → to_status``."""

    __tablename__ = "status_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status: Mapped[LeadStatus | None] = mapped_column(str_enum(LeadStatus))
    to_status: Mapped[LeadStatus] = mapped_column(str_enum(LeadStatus), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False, index=True)

    lead: Mapped[Lead] = relationship(back_populates="status_history")

    def __repr__(self) -> str:
        origin = self.from_status.value if self.from_status else "∅"
        return f"<StatusHistory lead={self.lead_id} {origin}→{self.to_status.value}>"
