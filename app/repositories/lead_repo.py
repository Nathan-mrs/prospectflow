"""Acesso a leads."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass, field

from sqlalchemy import Select, delete, func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from app.clock import now
from app.models import Lead, LeadStatus, StatusHistory, WebsiteStatus
from app.services.text import simplify

#: Valor usado no filtro de nichos para "leads sem nicho".
NO_NICHE = 0

SORTABLE = {
    "priority_score": Lead.priority_score,
    "company_name": Lead.company_name,
    "created_at": Lead.created_at,
    "last_contact_at": Lead.last_contact_at,
    "google_rating": Lead.google_rating,
    "review_count": Lead.review_count,
    "city": Lead.city,
}


@dataclass
class LeadQuery:
    """Filtros da listagem de leads. Campos vazios não filtram."""

    search: str = ""
    niche_ids: list[int] = field(default_factory=list)  # NO_NICHE = sem nicho
    statuses: list[LeadStatus] = field(default_factory=list)
    cities: list[str] = field(default_factory=list)
    website: list[WebsiteStatus] = field(default_factory=list)
    min_score: int = 0
    sort_by: str = "priority_score"
    descending: bool = True
    limit: int | None = None


class LeadRepository:
    """Persistência e consultas de leads. Regras de negócio ficam nos services."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def get(self, lead_id: int) -> Lead | None:
        return self.session.get(Lead, lead_id)

    def get_with_timeline(self, lead_id: int) -> Lead | None:
        """Lead com interações e histórico já carregados (para a tela de detalhes)."""
        stmt = (
            select(Lead)
            .where(Lead.id == lead_id)
            .options(
                selectinload(Lead.interactions),
                selectinload(Lead.status_history),
                selectinload(Lead.niche),
                selectinload(Lead.sale),
            )
        )
        return self.session.scalar(stmt)

    def add_new(self, lead: Lead) -> Lead:
        """Adiciona um lead novo já com o registro inicial no histórico de status."""
        moment = now()
        lead.status = LeadStatus.NEW
        lead.status_changed_at = moment
        lead.status_history.append(
            StatusHistory(from_status=None, to_status=LeadStatus.NEW, changed_at=moment)
        )
        self.session.add(lead)
        return lead

    def dedup_keys(
        self, exclude_id: int | None = None
    ) -> list[tuple[int, str | None, str | None, str | None]]:
        """Tuplas ``(id, telefone, empresa, cidade)`` para o índice de duplicados."""
        stmt = select(Lead.id, Lead.phone, Lead.company_name, Lead.city)
        if exclude_id is not None:
            stmt = stmt.where(Lead.id != exclude_id)
        return [(r.id, r.phone, r.company_name, r.city) for r in self.session.execute(stmt)]

    # -- listagem --------------------------------------------------------------------

    def _filtered(self, query: LeadQuery) -> Select[tuple[Lead]]:
        stmt = select(Lead)
        term = simplify(query.search)
        if term:
            like = f"%{term}%"
            conditions = [
                func.pf_simplify(column).like(like)
                for column in (
                    Lead.company_name, Lead.contact_name, Lead.city, Lead.neighborhood,
                    Lead.instagram, Lead.category, Lead.notes,
                )
            ]
            digits = re.sub(r"\D", "", query.search)
            if len(digits) >= 4:
                conditions.append(Lead.phone.contains(digits))
            stmt = stmt.where(or_(*conditions))
        if query.niche_ids:
            ids = [i for i in query.niche_ids if i != NO_NICHE]
            niche_conditions = [Lead.niche_id.in_(ids)] if ids else []
            if NO_NICHE in query.niche_ids:
                niche_conditions.append(Lead.niche_id.is_(None))
            stmt = stmt.where(or_(*niche_conditions))
        if query.statuses:
            stmt = stmt.where(Lead.status.in_(query.statuses))
        if query.cities:
            stmt = stmt.where(Lead.city.in_(query.cities))
        if query.website:
            stmt = stmt.where(Lead.website_status.in_(query.website))
        if query.min_score:
            stmt = stmt.where(Lead.priority_score >= query.min_score)
        return stmt

    def search(self, query: LeadQuery) -> list[Lead]:
        """Leads que atendem aos filtros, ordenados, com o nicho já carregado."""
        column = SORTABLE.get(query.sort_by, Lead.priority_score)
        order = column.desc().nulls_last() if query.descending else column.asc().nulls_last()
        stmt = self._filtered(query).options(selectinload(Lead.niche)).order_by(order, Lead.id)
        if query.limit:
            stmt = stmt.limit(query.limit)
        return list(self.session.scalars(stmt))

    def count(self, query: LeadQuery | None = None) -> int:
        stmt = self._filtered(query or LeadQuery()).with_only_columns(func.count(Lead.id))
        return self.session.scalar(stmt) or 0

    def cities(self) -> list[str]:
        """Cidades distintas, em ordem alfabética (para o filtro)."""
        stmt = select(Lead.city).where(Lead.city.is_not(None)).distinct().order_by(Lead.city)
        return [c for c in self.session.scalars(stmt) if c]

    # -- ações em lote ---------------------------------------------------------------

    def delete_many(self, ids: Sequence[int]) -> int:
        """Exclui leads (interações, histórico e venda vão junto por cascata no banco)."""
        if not ids:
            return 0
        result = self.session.execute(delete(Lead).where(Lead.id.in_(ids)))
        return result.rowcount or 0

    def set_niche_many(self, ids: Sequence[int], niche_id: int | None) -> int:
        if not ids:
            return 0
        result = self.session.execute(
            update(Lead).where(Lead.id.in_(ids)).values(niche_id=niche_id, updated_at=now())
        )
        return result.rowcount or 0
