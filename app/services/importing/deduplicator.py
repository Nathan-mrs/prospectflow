"""Detecção de leads duplicados: mesmo telefone OU mesmo nome + cidade."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from app.services.text import compact_key


@dataclass(frozen=True, slots=True)
class DuplicateMatch:
    """Indica com quem a linha conflita e por quê."""

    lead_id: int | None  # None = repetida dentro da própria planilha
    reason: str
    row_number: int | None = None  # linha da planilha original (duplicata interna)


def name_city_key(company: str | None, city: str | None) -> tuple[str, str] | None:
    """Chave ``(nome, cidade)`` normalizada; ``None`` se faltar o nome."""
    name = compact_key(company)
    return (name, compact_key(city)) if name else None


@dataclass
class DuplicateIndex:
    """Índice em memória dos leads existentes + linhas já vistas na planilha."""

    by_phone: dict[str, int] = field(default_factory=dict)
    by_name_city: dict[tuple[str, str], int] = field(default_factory=dict)
    _seen_phone: dict[str, int] = field(default_factory=dict)
    _seen_name_city: dict[tuple[str, str], int] = field(default_factory=dict)

    @classmethod
    def from_leads(
        cls, leads: Iterable[tuple[int, str | None, str | None, str | None]]
    ) -> DuplicateIndex:
        """Monta o índice a partir de tuplas ``(id, telefone, empresa, cidade)``."""
        index = cls()
        for lead_id, phone, company, city in leads:
            if phone:
                index.by_phone.setdefault(phone, lead_id)
            key = name_city_key(company, city)
            if key:
                index.by_name_city.setdefault(key, lead_id)
        return index

    def check(
        self, phone: str | None, company: str | None, city: str | None
    ) -> DuplicateMatch | None:
        """Procura duplicata no banco e, depois, nas linhas já vistas desta planilha."""
        key = name_city_key(company, city)
        if phone and phone in self.by_phone:
            return DuplicateMatch(self.by_phone[phone], "Mesmo telefone")
        if key and key in self.by_name_city:
            return DuplicateMatch(self.by_name_city[key], "Mesmo nome e cidade")
        if phone and phone in self._seen_phone:
            row = self._seen_phone[phone]
            return DuplicateMatch(None, f"Telefone repetido na planilha (linha {row})", row)
        if key and key in self._seen_name_city:
            row = self._seen_name_city[key]
            return DuplicateMatch(None, f"Nome e cidade repetidos na planilha (linha {row})", row)
        return None

    def remember(
        self, row_number: int, phone: str | None, company: str | None, city: str | None
    ) -> None:
        """Registra uma linha aceita para detectar repetições internas."""
        if phone:
            self._seen_phone.setdefault(phone, row_number)
        key = name_city_key(company, city)
        if key:
            self._seen_name_city.setdefault(key, row_number)
