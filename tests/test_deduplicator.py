"""Testes da detecção de duplicados."""

from __future__ import annotations

from app.services.importing.deduplicator import DuplicateIndex


def _index() -> DuplicateIndex:
    return DuplicateIndex.from_leads(
        [
            (1, "5511987654321", "Barbearia do Zé", "São Paulo"),
            (2, None, "Pet Feliz", "Guarulhos"),
        ]
    )


def test_same_phone_is_duplicate() -> None:
    match = _index().check("5511987654321", "Outro Nome", "Osasco")
    assert match is not None and match.lead_id == 1 and "telefone" in match.reason.lower()


def test_same_name_and_city_ignoring_case_and_accents() -> None:
    match = _index().check(None, "BARBEARIA DO ZE", "sao paulo")
    assert match is not None and match.lead_id == 1


def test_same_name_other_city_is_not_duplicate() -> None:
    assert _index().check(None, "Pet Feliz", "São Paulo") is None


def test_phone_has_priority_over_name() -> None:
    match = _index().check("5511987654321", "Pet Feliz", "Guarulhos")
    assert match is not None and match.lead_id == 1


def test_duplicates_inside_the_same_file() -> None:
    index = _index()
    assert index.check("5521999998888", "Nova Barbearia", "Rio") is None
    index.remember(5, "5521999998888", "Nova Barbearia", "Rio")

    by_phone = index.check("5521999998888", "Outra", "Rio")
    assert by_phone is not None and by_phone.lead_id is None and by_phone.row_number == 5

    by_name = index.check(None, "nova barbearia", "RIO")
    assert by_name is not None and by_name.row_number == 5


def test_empty_values_never_match() -> None:
    index = DuplicateIndex.from_leads([(1, None, "", None)])
    assert index.check(None, "", None) is None
