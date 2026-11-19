"""Testes da listagem/filtros de leads."""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Interaction, InteractionType, Lead, LeadStatus, Niche, StatusHistory, WebsiteStatus
from app.repositories import NO_NICHE, LeadQuery, LeadRepository
from app.services.bootstrap import ensure_defaults


@pytest.fixture
def repo(session: Session) -> LeadRepository:
    ensure_defaults(session)
    niches = {n.name: n for n in session.scalars(select(Niche))}
    repo = LeadRepository(session)
    data = [
        ("Salão Bella", "São Paulo", "Salões de Beleza", "5511911112222", 90, LeadStatus.NEW, WebsiteStatus.NONE),
        ("Barbearia do Zé", "Guarulhos", "Barbearias", "5511933334444", 70, LeadStatus.CONTACTED, WebsiteStatus.BAD),
        ("Pet Feliz", "São Paulo", "Pet Shops", "5511955556666", 50, LeadStatus.WON, WebsiteStatus.YES),
        ("Contabilidade Silva", "Osasco", None, None, 20, LeadStatus.NEW, WebsiteStatus.NONE),
    ]
    for company, city, niche, phone, score, status, website in data:
        lead = Lead(
            company_name=company, city=city, phone=phone, priority_score=score,
            niche=niches.get(niche) if niche else None, website_status=website,
        )
        repo.add_new(lead)
        lead.status = status
    session.flush()
    return repo


def names(leads: list[Lead]) -> list[str]:
    return [lead.company_name for lead in leads]


def test_default_order_is_score_desc(repo: LeadRepository) -> None:
    assert names(repo.search(LeadQuery())) == [
        "Salão Bella", "Barbearia do Zé", "Pet Feliz", "Contabilidade Silva",
    ]


@pytest.mark.parametrize("term", ["salao", "SALÃO", "bella", "sao paulo"])
def test_search_ignores_accents_and_case(repo: LeadRepository, term: str) -> None:
    assert "Salão Bella" in names(repo.search(LeadQuery(search=term)))


def test_search_by_phone_digits(repo: LeadRepository) -> None:
    assert names(repo.search(LeadQuery(search="(11) 93333-4444"))) == ["Barbearia do Zé"]


def test_filters_combine(repo: LeadRepository, session: Session) -> None:
    barber = session.scalar(select(Niche).where(Niche.name == "Barbearias"))
    assert barber is not None
    query = LeadQuery(niche_ids=[barber.id], statuses=[LeadStatus.CONTACTED], min_score=60)
    assert names(repo.search(query)) == ["Barbearia do Zé"]
    assert repo.count(query) == 1


def test_filter_without_niche(repo: LeadRepository) -> None:
    assert names(repo.search(LeadQuery(niche_ids=[NO_NICHE]))) == ["Contabilidade Silva"]


def test_filter_city_and_website(repo: LeadRepository) -> None:
    query = LeadQuery(cities=["São Paulo"], website=[WebsiteStatus.NONE])
    assert names(repo.search(query)) == ["Salão Bella"]


def test_sort_by_name_ascending(repo: LeadRepository) -> None:
    result = names(repo.search(LeadQuery(sort_by="company_name", descending=False)))
    assert result == sorted(result)


def test_unknown_sort_falls_back_to_score(repo: LeadRepository) -> None:
    assert names(repo.search(LeadQuery(sort_by="DROP TABLE")))[0] == "Salão Bella"


def test_cities_are_distinct_and_sorted(repo: LeadRepository) -> None:
    assert repo.cities() == ["Guarulhos", "Osasco", "São Paulo"]


def test_delete_many_cascades(repo: LeadRepository, session: Session) -> None:
    lead = repo.search(LeadQuery(search="bella"))[0]
    lead.interactions.append(Interaction(type=InteractionType.FIRST_CONTACT))
    session.flush()
    assert repo.delete_many([lead.id]) == 1
    session.expire_all()
    assert session.scalars(select(Interaction)).first() is None
    assert all(h.lead_id != lead.id for h in session.scalars(select(StatusHistory)))


def test_set_niche_many(repo: LeadRepository, session: Session) -> None:
    pet = session.scalar(select(Niche).where(Niche.name == "Pet Shops"))
    assert pet is not None
    ids = [lead.id for lead in repo.search(LeadQuery(niche_ids=[NO_NICHE]))]
    assert repo.set_niche_many(ids, pet.id) == 1
    session.expire_all()
    assert repo.count(LeadQuery(niche_ids=[NO_NICHE])) == 0
