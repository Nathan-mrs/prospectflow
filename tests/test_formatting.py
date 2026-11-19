"""Testes da formatação de exibição."""

from __future__ import annotations

from datetime import datetime

import pytest

from app.ui.formatting import format_int, format_phone, format_rating, relative_time

REF = datetime(2026, 11, 18, 14, 0)


@pytest.mark.parametrize(
    ("phone", "expected"),
    [
        ("5511987654321", "(11) 98765-4321"),
        ("551134567890", "(11) 3456-7890"),
        (None, "—"),
        ("123", "123"),
    ],
)
def test_format_phone(phone: str | None, expected: str) -> None:
    assert format_phone(phone) == expected


def test_numbers() -> None:
    assert format_int(1234567) == "1.234.567"
    assert format_rating(4.8) == "4,8"
    assert format_rating(None) == "—"


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (None, "—"),
        (datetime(2026, 11, 18, 8, 0), "hoje"),
        (datetime(2026, 11, 17, 23, 0), "ontem"),
        (datetime(2026, 11, 13), "há 5 dias"),
        (datetime(2026, 10, 1), "há 1 mês"),
        (datetime(2026, 5, 1), "há 6 meses"),
        (datetime(2024, 11, 1), "há 2 anos"),
        (datetime(2026, 12, 1), "01/12/2026"),
    ],
)
def test_relative_time(moment: datetime | None, expected: str) -> None:
    assert relative_time(moment, REF) == expected
