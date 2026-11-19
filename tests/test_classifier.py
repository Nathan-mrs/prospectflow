"""Testes da classificação de nicho por palavras-chave."""

from __future__ import annotations

import pytest

from app.services.bootstrap import DEFAULT_NICHES
from app.services.importing.classifier import NicheClassifier, NicheRule


@pytest.fixture
def classifier() -> NicheClassifier:
    rules = [
        NicheRule.build(i + 1, n["name"], n["keywords"]) for i, n in enumerate(DEFAULT_NICHES)
    ]
    return NicheClassifier(rules)


@pytest.mark.parametrize(
    ("category", "name", "expected"),
    [
        ("Barbearia", "Navalha de Ouro", "Barbearias"),
        ("", "Barber King", "Barbearias"),
        ("Salão de beleza", "Espaço Bella", "Salões de Beleza"),
        ("Cabeleireiro", "Studio Glamour", "Salões de Beleza"),
        ("Pet shop", "Casa do Bichinho", "Pet Shops"),
        ("Clínica veterinária", "Amigo Fiel", "Pet Shops"),
        ("Oficina mecânica", "Pit Stop", "Oficinas Mecânicas"),
        ("", "AUTO CENTER SÃO JORGE", "Oficinas Mecânicas"),
        ("Pizzaria", "Bella Napoli", "Restaurantes"),
        ("Clínica de estética", "Renova", "Clínicas de Estética"),
        ("Academia", "Iron", "Academias"),
        ("", "Studio Pilates Movimento", "Academias"),
    ],
)
def test_classifies_by_keywords(
    classifier: NicheClassifier, category: str, name: str, expected: str
) -> None:
    rule = classifier.classify(category=category, company_name=name)
    assert rule is not None and rule.name == expected


def test_keyword_matches_only_at_word_start(classifier: NicheClassifier) -> None:
    assert classifier.classify(category="Loja de carpetes") is None


def test_category_outweighs_name(classifier: NicheClassifier) -> None:
    rule = classifier.classify(category="Barbearia", company_name="Pet Barber Spa")
    assert rule is not None and rule.name == "Barbearias"


def test_explicit_niche_column_wins(classifier: NicheClassifier) -> None:
    rule = classifier.classify(category="Pizzaria", explicit_niche="barbearia")
    assert rule is not None and rule.name == "Barbearias"


def test_unknown_returns_none(classifier: NicheClassifier) -> None:
    assert classifier.classify(category="Contabilidade", company_name="Silva & Filhos") is None
