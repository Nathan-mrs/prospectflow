"""Classificação automática de nicho por palavras-chave."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from app.services.text import compact_key, simplify


@dataclass(frozen=True, slots=True)
class NicheRule:
    """Nicho com suas palavras-chave já normalizadas."""

    niche_id: int
    name: str
    keywords: tuple[str, ...]

    @classmethod
    def build(cls, niche_id: int, name: str, keywords: Iterable[str]) -> NicheRule:
        normalized = tuple(k for k in (simplify(kw) for kw in keywords) if k)
        return cls(niche_id, name, normalized)


class NicheClassifier:
    """Escolhe o nicho de um lead.

    Prioridade: coluna "nicho" explícita → palavras-chave na categoria (peso 2)
    e no nome da empresa (peso 1). As palavras-chave casam no **início** de
    palavras: ``"pet"`` casa com ``"petshop"`` mas não com ``"carpete"``.
    """

    CATEGORY_WEIGHT = 2
    NAME_WEIGHT = 1

    def __init__(self, rules: Iterable[NicheRule]) -> None:
        self.rules = list(rules)
        self._by_name = {compact_key(r.name): r for r in self.rules}
        self._patterns = {
            r.niche_id: [re.compile(rf"\b{re.escape(kw)}") for kw in r.keywords] for r in self.rules
        }

    def _hits(self, rule: NicheRule, text: str) -> int:
        return sum(1 for pattern in self._patterns[rule.niche_id] if pattern.search(text))

    def classify(
        self,
        category: str | None = None,
        company_name: str | None = None,
        explicit_niche: str | None = None,
    ) -> NicheRule | None:
        """Retorna a regra do nicho vencedor ou ``None`` se nada casar."""
        if explicit_niche:
            key = compact_key(explicit_niche)
            if key in self._by_name:
                return self._by_name[key]
            # aceita singular/plural simples: "Barbearia" → "Barbearias"
            for name_key, rule in self._by_name.items():
                if name_key.rstrip("s") == key.rstrip("s"):
                    return rule

        category_text = simplify(category)
        name_text = simplify(company_name)
        best: tuple[int, NicheRule] | None = None
        for rule in self.rules:
            score = (
                self._hits(rule, category_text) * self.CATEGORY_WEIGHT
                + self._hits(rule, name_text) * self.NAME_WEIGHT
            )
            if score and (best is None or score > best[0]):
                best = (score, rule)
        return best[1] if best else None
