"""Testes da detecção automática de colunas."""

from __future__ import annotations

import pandas as pd

from app.services.importing.column_mapper import (
    mapping_from_suggestions,
    suggest_mapping,
    validate_mapping,
)


def _mapping(columns: list[str], sample: pd.DataFrame | None = None) -> dict[str, str]:
    return mapping_from_suggestions(suggest_mapping(columns, sample))


def test_detects_common_portuguese_headers() -> None:
    columns = [
        "Nome", "Categoria", "Fone", "Nota", "Nº de Avaliações", "Site",
        "Instagram", "Bairro", "Cidade", "Link do Google Maps", "Obs",
    ]
    assert _mapping(columns) == {
        "company_name": "Nome",
        "category": "Categoria",
        "phone": "Fone",
        "google_rating": "Nota",
        "review_count": "Nº de Avaliações",
        "website": "Site",
        "instagram": "Instagram",
        "neighborhood": "Bairro",
        "city": "Cidade",
        "maps_url": "Link do Google Maps",
        "notes": "Obs",
    }


def test_phone_synonyms() -> None:
    for header in ("Telefone", "WhatsApp", "Celular", "TEL.", "Telefone (WhatsApp)"):
        assert _mapping([header]) == {"phone": header}


def test_contact_vs_company_name() -> None:
    mapping = _mapping(["Nome da Empresa", "Nome do Contato"])
    assert mapping == {"company_name": "Nome da Empresa", "contact_name": "Nome do Contato"}


def test_rating_vs_review_count() -> None:
    mapping = _mapping(["Avaliação", "Avaliações"])
    assert mapping == {"google_rating": "Avaliação", "review_count": "Avaliações"}


def test_each_field_used_once() -> None:
    mapping = _mapping(["Telefone", "WhatsApp"])
    assert list(mapping) == ["phone"]
    assert mapping["phone"] == "Telefone"  # mais à esquerda vence o empate


def test_unknown_column_is_ignored() -> None:
    suggestions = suggest_mapping(["Coluna X"])
    assert suggestions[0].field is None and suggestions[0].confidence == 0


def test_detects_phone_by_values_when_header_is_unknown() -> None:
    df = pd.DataFrame(
        {
            "Empresa": ["A", "B", "C", "D"],
            "Col2": ["(11) 98765-4321", "11 91234-5678", "+55 21 99876-5432", "1133334444"],
        }
    )
    mapping = _mapping(list(df.columns), df)
    assert mapping["phone"] == "Col2"


def test_validate_mapping_requires_company() -> None:
    assert validate_mapping({"phone": "Fone"}) == ["Mapeie a coluna de “Empresa”."]
    assert validate_mapping({"company_name": "Nome"}) == []


def test_validate_mapping_rejects_repeated_column() -> None:
    errors = validate_mapping({"company_name": "Nome", "contact_name": "Nome"})
    assert any("mais de um campo" in e for e in errors)
