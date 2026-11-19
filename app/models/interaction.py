"""Interações com o lead (timeline)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.clock import now
from app.models.base import Base
from app.models.enums import InteractionType, str_enum

if TYPE_CHECKING:
    from app.models.lead import Lead
    from app.models.template import MessageTemplate


class Interaction(Base):
    """Um contato, resposta ou anotação ligada a um lead."""

    __tablename__ = "interactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    lead_id: Mapped[int] = mapped_column(
        ForeignKey("leads.id", ondelete="CASCADE"), nullable=False, index=True
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime, default=now, nullable=False, index=True
    )
    type: Mapped[InteractionType] = mapped_column(str_enum(InteractionType), nullable=False)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("message_templates.id", ondelete="SET NULL")
    )
    message: Mapped[str | None] = mapped_column(Text)
    note: Mapped[str | None] = mapped_column(Text)

    lead: Mapped[Lead] = relationship(back_populates="interactions")
    template: Mapped[MessageTemplate | None] = relationship()

    def __repr__(self) -> str:
        return f"<Interaction {self.id} lead={self.lead_id} {self.type.value}>"
