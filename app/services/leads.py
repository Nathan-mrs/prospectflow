"""Regras de criação, edição e exclusão de leads.

A interface envia um :class:`LeadForm` com os valores digitados; este módulo
normaliza com as mesmas regras da importação, valida, bloqueia duplicatas e
recalcula o score.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, fields
from typing import Any

from sqlalchemy.orm import Session

from app.config import get_settings
from app.models import Lead, WebsiteStatus
from app.repositories import LeadQuery, LeadRepository, NicheRepository, SettingRepository
from app.services.importing.deduplicator import DuplicateIndex
from app.services.importing.normalizer import (
    normalize_instagram,
    normalize_name,
    normalize_phone,
    normalize_place,
    normalize_text,
    normalize_url,
    parse_rating,
    parse_review_count,
)
from app.services.score import ScoreWeights, calculate_priority_score


class LeadValidationError(ValueError):
    """Erros de validação por campo, em português."""

    def __init__(self, errors: dict[str, str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors.values()))


@dataclass
class LeadForm:
    """Valores brutos vindos do formulário (tudo opcional exceto a empresa)."""

    company_name: str = ""
    contact_name: str = ""
    niche_id: int | None = None
    phone: str = ""
    instagram: str = ""
    category: str = ""
    google_rating: Any = None
    review_count: Any = None
    website_status: WebsiteStatus = WebsiteStatus.NONE
    neighborhood: str = ""
    city: str = ""
    maps_url: str = ""
    notes: str = ""

    @classmethod
    def from_lead(cls, lead: Lead) -> LeadForm:
        """Pré-preenche o formulário de edição."""
        return cls(
            company_name=lead.company_name,
            contact_name=lead.contact_name or "",
            niche_id=lead.niche_id,
            phone=lead.phone or "",
            instagram=lead.instagram or "",
            category=lead.category or "",
            google_rating=lead.google_rating,
            review_count=lead.review_count,
            website_status=lead.website_status,
            neighborhood=lead.neighborhood or "",
            city=lead.city or "",
            maps_url=lead.maps_url or "",
            notes=lead.notes or "",
        )

    def as_dict(self) -> dict[str, Any]:
        return {f.name: getattr(self, f.name) for f in fields(self)}


@dataclass(frozen=True, slots=True)
class CleanLead:
    """Resultado da validação: valores prontos para gravar + avisos."""

    values: dict[str, Any]
    warnings: list[str]


def clean_form(form: LeadForm, default_ddd: str | None = None) -> CleanLead:
    """Normaliza e valida o formulário.

    Raises:
        LeadValidationError: com uma mensagem por campo inválido.
    """
    ddd = default_ddd or get_settings().default_ddd
    errors: dict[str, str] = {}
    warnings: list[str] = []

    company = normalize_name(form.company_name)
    if not company:
        errors["company_name"] = "Informe o nome da empresa."

    phone = None
    if str(form.phone or "").strip():
        parsed_phone = normalize_phone(form.phone, ddd)
        if parsed_phone.errors:
            errors["phone"] = parsed_phone.errors[0]
        phone = parsed_phone.value
        warnings += parsed_phone.warnings

    rating = parse_rating(form.google_rating)
    if rating.warnings:
        errors["google_rating"] = "A nota deve estar entre 0 e 5."
    reviews = parse_review_count(form.review_count)
    if reviews.warnings:
        errors["review_count"] = "Informe um número de avaliações válido."

    if str(form.instagram or "").strip() and normalize_instagram(form.instagram) is None:
        errors["instagram"] = "Instagram inválido (use @perfil ou o link)."
    if str(form.maps_url or "").strip() and normalize_url(form.maps_url) is None:
        errors["maps_url"] = "Link inválido."

    if errors:
        raise LeadValidationError(errors)

    values: dict[str, Any] = {
        "company_name": company,
        "contact_name": normalize_name(form.contact_name),
        "niche_id": form.niche_id or None,
        "phone": phone,
        "instagram": normalize_instagram(form.instagram),
        "category": normalize_text(form.category),
        "google_rating": rating.value,
        "review_count": reviews.value,
        "website_status": WebsiteStatus(form.website_status or WebsiteStatus.NONE),
        "neighborhood": normalize_place(form.neighborhood),
        "city": normalize_place(form.city),
        "maps_url": normalize_url(form.maps_url),
        "notes": normalize_text(form.notes),
    }
    return CleanLead(values, warnings)


class LeadService:
    """Casos de uso de leads sobre uma sessão (sem commit — quem chama decide)."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.leads = LeadRepository(session)

    def _weights(self) -> ScoreWeights:
        return ScoreWeights.from_settings(SettingRepository(self.session).all())

    def _check_duplicate(self, values: dict[str, Any], exclude_id: int | None) -> None:
        index = DuplicateIndex.from_leads(self.leads.dedup_keys(exclude_id=exclude_id))
        match = index.check(values["phone"], values["company_name"], values["city"])
        if match and match.lead_id is not None:
            other = self.leads.get(match.lead_id)
            name = other.company_name if other else f"#{match.lead_id}"
            field = "phone" if "telefone" in match.reason.lower() else "company_name"
            raise LeadValidationError({field: f"{match.reason} de “{name}” (lead #{match.lead_id})."})

    def _check_niche(self, niche_id: int | None) -> None:
        if niche_id is not None and NicheRepository(self.session).get(niche_id) is None:
            raise LeadValidationError({"niche_id": "Nicho inexistente."})

    def create(self, form: LeadForm) -> tuple[Lead, list[str]]:
        """Cria um lead em ``Novo``. Retorna o lead e avisos de normalização."""
        clean = clean_form(form)
        self._check_niche(clean.values["niche_id"])
        self._check_duplicate(clean.values, exclude_id=None)
        lead = Lead(**clean.values)
        lead.priority_score = self._score(lead)
        self.leads.add_new(lead)
        self.session.flush()
        return lead, clean.warnings

    def update(self, lead_id: int, form: LeadForm) -> tuple[Lead, list[str]]:
        """Atualiza os dados cadastrais (status e histórico não mudam aqui)."""
        lead = self.leads.get(lead_id)
        if lead is None:
            raise LeadValidationError({"id": "Lead não encontrado."})
        clean = clean_form(form)
        self._check_niche(clean.values["niche_id"])
        self._check_duplicate(clean.values, exclude_id=lead_id)
        for key, value in clean.values.items():
            setattr(lead, key, value)
        lead.priority_score = self._score(lead)
        self.session.flush()
        return lead, clean.warnings

    def _score(self, lead: Lead) -> int:
        return calculate_priority_score(
            lead.google_rating, lead.review_count, lead.website_status, self._weights()
        )

    def delete(self, ids: Sequence[int]) -> int:
        """Exclui leads e tudo ligado a eles. Retorna quantos foram excluídos."""
        return self.leads.delete_many(list(ids))

    def set_niche(self, ids: Sequence[int], niche_id: int | None) -> int:
        """Define o nicho de vários leads de uma vez."""
        self._check_niche(niche_id)
        return self.leads.set_niche_many(list(ids), niche_id)

    def recalculate_scores(self) -> int:
        """Recalcula o score de todos os leads (após mudar os pesos)."""
        weights = self._weights()
        changed = 0
        for lead in self.leads.search(LeadQuery()):
            score = calculate_priority_score(
                lead.google_rating, lead.review_count, lead.website_status, weights
            )
            if score != lead.priority_score:
                lead.priority_score = score
                changed += 1
        self.session.flush()
        return changed
