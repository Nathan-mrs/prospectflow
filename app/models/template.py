"""Templates de mensagem por etapa."""

from __future__ import annotations

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin
from app.models.enums import InteractionType, str_enum

#: Variáveis aceitas nos templates.
TEMPLATE_VARIABLES = ("nome", "empresa", "servico", "cidade")


class MessageTemplate(TimestampMixin, Base):
    """Mensagem pronta para uma etapa. ``stage`` = tipo de interação que ela gera."""

    __tablename__ = "message_templates"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    stage: Mapped[InteractionType] = mapped_column(str_enum(InteractionType), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    def __repr__(self) -> str:
        return f"<MessageTemplate {self.id} {self.stage.value} {self.name!r}>"
