"""Testes da normalização de valores da planilha."""

from __future__ import annotations

import math

import pytest

from app.models import WebsiteStatus
from app.services.importing.normalizer import (
    clean_str,
    normalize_instagram,
    normalize_name,
    normalize_phone,
    normalize_place,
    normalize_url,
    parse_rating,
    parse_review_count,
    parse_website,
)


class TestPhone:
    @pytest.mark.parametrize(
        "raw",
        [
            "(11) 98765-4321",
            "11 98765 4321",
            "+55 11 98765-4321",
            "5511987654321",
            "011 98765-4321",
            11987654321,
            11987654321.0,
            "11987654321.0",
        ],
    )
    def test_mobile_formats(self, raw: object) -> None:
        result = normalize_phone(raw)
        assert result.value == "5511987654321"
        assert not result.errors and not result.warnings

    def test_without_ddd_uses_default(self) -> None:
        result = normalize_phone("98765-4321", default_ddd="21")
        assert result.value == "5521987654321"
        assert any("DDD" in w for w in result.warnings)

    def test_landline_gets_warning(self) -> None:
        result = normalize_phone("(11) 3456-7890")
        assert result.value == "551134567890"
        assert any("fixo" in w for w in result.warnings)

    def test_old_mobile_without_ninth_digit_is_not_invented(self) -> None:
        result = normalize_phone("(11) 8765-4321")
        assert result.value == "551187654321"  # não acrescenta o 9
        assert any("9º dígito" in w for w in result.warnings)

    @pytest.mark.parametrize(
        "raw",
        ["123", "0800 123 4567", "(10) 98765-4321", "11 88765-43210", "(00) 99999-9999"],
    )
    def test_invalid(self, raw: str) -> None:
        result = normalize_phone(raw)
        assert result.value is None and result.errors

    def test_nine_digits_must_start_with_nine(self) -> None:
        assert normalize_phone("(11) 18765-4321").errors

    @pytest.mark.parametrize("raw", ["", None, float("nan"), "  "])
    def test_empty_is_warning_not_error(self, raw: object) -> None:
        result = normalize_phone(raw)
        assert result.value is None and not result.errors and result.warnings


class TestNames:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("BARBEARIA DO ZÉ", "Barbearia do Zé"),
            ("  pet   shop   amigo fiel ", "Pet Shop Amigo Fiel"),
            ("BarberKing", "BarberKing"),
            ("Studio da Ana", "Studio da Ana"),
            ("DO ZÉ", "Do Zé"),
            ("", None),
            (None, None),
        ],
    )
    def test_normalize_name(self, raw: object, expected: str | None) -> None:
        assert normalize_name(raw) == expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("SÃO PAULO - SP", "São Paulo"),
            ("Guarulhos/SP", "Guarulhos"),
            ("santo andré, sp", "Santo André"),
            ("Osasco (SP)", "Osasco"),
            ("Vila Mariana", "Vila Mariana"),
            ("", None),
        ],
    )
    def test_normalize_place(self, raw: str, expected: str | None) -> None:
        assert normalize_place(raw) == expected

    def test_clean_str_handles_nan_and_placeholders(self) -> None:
        assert clean_str(math.nan) == ""
        assert clean_str("-") == ""
        assert clean_str(" a   b ") == "a b"
        assert clean_str(42.0) == "42"


class TestNumbers:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("4,8", 4.8), ("4.8", 4.8), (4.75, 4.8), ("4,7 estrelas", 4.7), ("5", 5.0), ("", None)],
    )
    def test_rating(self, raw: object, expected: float | None) -> None:
        assert parse_rating(raw).value == expected

    @pytest.mark.parametrize("raw", ["7,5", "abc", "10"])
    def test_invalid_rating_is_warning(self, raw: str) -> None:
        result = parse_rating(raw)
        assert result.value is None and result.warnings

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("312", 312), ("1.234", 1234), ("(87)", 87), ("312 avaliações", 312), (45.0, 45), ("", None)],
    )
    def test_review_count(self, raw: object, expected: int | None) -> None:
        assert parse_review_count(raw).value == expected


class TestWebsiteAndSocial:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("", WebsiteStatus.NONE),
            ("Não", WebsiteStatus.NONE),
            ("sem site", WebsiteStatus.NONE),
            ("ruim", WebsiteStatus.BAD),
            ("Desatualizado", WebsiteStatus.BAD),
            ("https://instagram.com/barber", WebsiteStatus.BAD),
            ("linktr.ee/salao", WebsiteStatus.BAD),
            ("Sim", WebsiteStatus.YES),
            ("www.petfeliz.com.br", WebsiteStatus.YES),
        ],
    )
    def test_parse_website(self, raw: str, expected: WebsiteStatus) -> None:
        assert parse_website(raw) is expected

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("@Barber.King", "@barber.king"),
            ("barber_king", "@barber_king"),
            ("https://www.instagram.com/barber.king/?hl=pt", "@barber.king"),
            ("não tem", None),
            ("", None),
        ],
    )
    def test_instagram(self, raw: str, expected: str | None) -> None:
        assert normalize_instagram(raw) == expected

    def test_url_gets_scheme(self) -> None:
        assert normalize_url("maps.app.goo.gl/abc") == "https://maps.app.goo.gl/abc"
        assert normalize_url("http://x.com") == "http://x.com"
        assert normalize_url("texto com espaço") is None
