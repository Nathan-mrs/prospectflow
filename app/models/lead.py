"""Lead: um negócio prospectado."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.clock import now
from app.models.base import Base, TimestampMixin
from app.models.enums import LeadStatus, WebsiteStatus, str_enum

if TYPE_CHECKING:
    from app.models.import_batch import ImportBatch
    from app.models.interaction import Interaction
    from app.models.niche import Niche
    from app.models.sale import Sale
    from app.models.status_history import StatusHistory


class Lead(TimestampMixin, Base):
    """Negócio prospectado e seu estado no funil."""

    __tablename__ = "leads"

    id: Mapped[int] = mapped_column(primary_key=True)
    company_name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    contact_name: Mapped[str | None] = mapped_column(String(120))
    niche_id: Mapped[int | None] = mapped_column(
        ForeignKey("niches.id", ondelete="SET NULL"), index=True
    )
    phone: Mapped[str | None] = mapped_column(String(20), index=True)
    instagram: Mapped[str | None] = mapped_column(String(80))
    category: Mapped[str | None] = mapped_column(String(120))
    google_rating: Mapped[float | None] = mapped_column(Float)
    review_count: Mapped[int | None] = mapped_column(Integer)
    website_status: Mapped[WebsiteStatus] = mapped_column(
        str_enum(WebsiteStatus), default=WebsiteStatus.NONE, nullable=False
    )
    neighborhood: Mapped[str | None] = mapped_column(String(120))
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    maps_url: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    priority_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    status: Mapped[LeadStatus] = mapped_column(
        str_enum(LeadStatus), default=LeadStatus.NEW, nullable=False, index=True
    )
    status_changed_at: Mapped[datetime] = mapped_column(DateTime, default=now, nullable=False)
    followup_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_followup_at: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    lost_reason: Mapped[str | None] = mapped_column(String(200))

    import_batch_id: Mapped[int | None] = mapped_column(
        ForeignKey("import_batches.id", ondelete="SET NULL")
    )

    niche: Mapped[Niche | None] = relationship(back_populates="leads")
    interactions: Mapped[list[Interaction]] = relationship(
        back_populates="lead",
        cascade="all, delete-orphan",
        order_by="Interaction.occurred_at.desc()",
    )
    status_history: Mapped[list[StatusHistory]] = relationship(
        back_populates="lead",
        cascade="all, delete-orphan",
        order_by="StatusHistory.changed_at",
    )
    sale: Mapped[Sale | None] = relationship(
        back_populates="lead", cascade="all, delete-orphan", uselist=False
    )
    import_batch: Mapped[ImportBatch | None] = relationship(back_populates="leads")

    def __init__(self, **kwargs: Any) -> None:
        # Defaults já no objeto Python (o ``default=`` da coluna só vale no INSERT),
        # para que regras de negócio funcionem antes do flush.
        kwargs.setdefault("status", LeadStatus.NEW)
        kwargs.setdefault("website_status", WebsiteStatus.NONE)
        kwargs.setdefault("priority_score", 0)
        kwargs.setdefault("followup_count", 0)
        super().__init__(**kwargs)

    @property
    def whatsapp_url(self) -> str | None:
        """Link ``wa.me`` para o telefone (sem mensagem)."""
        return f"https://wa.me/{self.phone}" if self.phone else None

    @property
    def display_name(self) -> str:
        """Nome do contato, ou o da empresa quando não houver."""
        return self.contact_name or self.company_name

    def __repr__(self) -> str:
        return f"<Lead {self.id} {self.company_name!r} {self.status.value}>"
