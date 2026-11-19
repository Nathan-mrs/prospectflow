"""Acesso a nichos."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Niche


class NicheRepository:
    """Consultas de nichos."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def list(self, only_active: bool = False) -> list[Niche]:
        """Nichos ordenados por dia da semana e nome."""
        stmt = select(Niche).order_by(Niche.weekday.is_(None), Niche.weekday, Niche.name)
        if only_active:
            stmt = stmt.where(Niche.active)
        return list(self.session.scalars(stmt))

    def get(self, niche_id: int) -> Niche | None:
        return self.session.get(Niche, niche_id)

    def for_weekday(self, weekday: int) -> Niche | None:
        """Nicho ativo do dia da semana (segunda = 0)."""
        stmt = select(Niche).where(Niche.weekday == weekday, Niche.active).limit(1)
        return self.session.scalar(stmt)
