"""Testes do CRUD de leads (validação, normalização, duplicados, score)."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AppSetting, Lead, LeadStatus, Niche, StatusHistory, WebsiteStatus
from app.services.bootstrap import ensure_defaults
from app.services.leads import LeadForm, LeadService, LeadValidationError, clean_form


@pytest.fixture
def service(session: Session) -> LeadService:
    ensure_defaults(session)
    return LeadService(session)


def _form(**kwargs: object) -> LeadForm:
    base = {"company_name": "barbearia do zé", "phone": "(11) 98765-4321", "city": "SÃO PAULO - SP"}
    return LeadForm(**(base | kwargs))  # type: ignore[arg-type]


def test_create_normalizes_and_scores(service: LeadService, session: Session) -> None:
    lead, warnings = service.create(
        _form(google_rating="4,8", review_count="1.200", instagram="instagram.com/BarberZe")
    )
    assert lead.company_name == "Barbearia do Zé"
    assert lead.phone == "5511987654321"
    assert lead.city == "São Paulo"
    assert lead.instagram == "@barberze"
    assert lead.google_rating == 4.8 and lead.review_count == 1200
    assert lead.status is LeadStatus.NEW
    assert lead.priority_score == 98  # 38,4 (nota) + 30 (avaliações ≥ teto) + 30 (sem site)
    assert warnings == []
    history = session.scalars(select(StatusHistory).where(StatusHistory.lead_id == lead.id)).all()
    assert [h.to_status for h in history] == [LeadStatus.NEW]


def test_create_returns_phone_warnings(service: LeadService) -> None:
    _, warnings = service.create(_form(phone="3456-7890"))
    assert any("DDD" in w for w in warnings)
    assert any("fixo" in w for w in warnings)


def test_validation_errors_per_field() -> None:
    with pytest.raises(LeadValidationError) as info:
        clean_form(LeadForm(company_name="  ", phone="123", google_rating="9", instagram="não sei"))
    assert set(info.value.errors) == {"company_name", "phone", "google_rating", "instagram"}


def test_phone_is_optional() -> None:
    assert clean_form(LeadForm(company_name="Sem Fone")).values["phone"] is None


def test_duplicate_phone_is_blocked(service: LeadService) -> None:
    service.create(_form())
    with pytest.raises(LeadValidationError) as info:
        service.create(_form(company_name="Outro Nome", phone="11 98765 4321"))
    assert "phone" in info.value.errors and "Barbearia do Zé" in info.value.errors["phone"]


def test_duplicate_name_and_city_is_blocked(service: LeadService) -> None:
    service.create(_form())
    with pytest.raises(LeadValidationError) as info:
        service.create(_form(phone="", company_name="BARBEARIA DO ZE", city="são paulo"))
    assert "company_name" in info.value.errors


def test_update_keeps_status_and_ignores_itself_in_dedup(service: LeadService) -> None:
    lead, _ = service.create(_form())
    lead.status = LeadStatus.CONTACTED
    updated, _ = service.update(lead.id, _form(notes="Dono: Zé", website_status=WebsiteStatus.YES))
    assert updated.notes == "Dono: Zé"
    assert updated.status is LeadStatus.CONTACTED
    assert updated.priority_score == 0  # sem nota/avaliações e com site


def test_update_cannot_steal_another_phone(service: LeadService) -> None:
    service.create(_form())
    other, _ = service.create(_form(company_name="Pet Feliz", phone="11912345678"))
    with pytest.raises(LeadValidationError):
        service.update(other.id, _form(company_name="Pet Feliz", phone="11987654321"))


def test_invalid_niche_is_rejected(service: LeadService) -> None:
    with pytest.raises(LeadValidationError) as info:
        service.create(_form(niche_id=9999))
    assert "niche_id" in info.value.errors


def test_set_niche_and_delete(service: LeadService, session: Session) -> None:
    lead, _ = service.create(_form())
    niche = session.scalars(select(Niche)).first()
    assert niche is not None
    assert service.set_niche([lead.id], niche.id) == 1
    assert service.delete([lead.id]) == 1
    assert session.scalars(select(Lead)).first() is None


def test_recalculate_scores_after_weight_change(service: LeadService, session: Session) -> None:
    lead, _ = service.create(_form(google_rating="5", review_count="500"))
    assert lead.priority_score == 100
    session.get(AppSetting, "score_weight_website").value = 0  # type: ignore[union-attr]
    assert service.recalculate_scores() == 1
    assert lead.priority_score == 70
