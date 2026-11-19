"""Configurações editáveis pela interface (chave/valor)."""

from __future__ import annotations

from typing import Any

from sqlalchemy import JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

#: Valores padrão gravados na primeira execução.
DEFAULT_SETTINGS: dict[str, Any] = {
    "daily_goal": 10,
    "followup_days": 2,
    "max_followups": 3,
    "service_name": "criação de site",
    "score_weight_rating": 40,
    "score_weight_reviews": 30,
    "score_weight_website": 30,
    "score_reviews_cap": 500,
}


class AppSetting(Base):
    """Par chave/valor com valor em JSON."""

    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(JSON, nullable=True)
