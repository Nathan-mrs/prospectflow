"""Score de prioridade do lead (0–100).

Quanto maior a nota no Google, mais avaliações e pior a presença online,
maior a chance do negócio querer (e poder pagar) um site.

Composição padrão (pesos configuráveis):

* **Nota Google** — até 40 pts, linear de 0 a 5 estrelas.
* **Avaliações** — até 30 pts, escala logarítmica; ``reviews_cap`` avaliações = máximo.
* **Site** — até 30 pts: sem site = 100%, site ruim = 2/3, tem site = 0.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.models.enums import WebsiteStatus

WEBSITE_FACTOR: dict[WebsiteStatus, float] = {
    WebsiteStatus.NONE: 1.0,
    WebsiteStatus.BAD: 2 / 3,
    WebsiteStatus.YES: 0.0,
}


@dataclass(frozen=True, slots=True)
class ScoreWeights:
    """Pesos do score. A soma dos três pesos define o score máximo."""

    rating: float = 40
    reviews: float = 30
    website: float = 30
    reviews_cap: int = 500

    @classmethod
    def from_settings(cls, settings: Mapping[str, Any]) -> ScoreWeights:
        """Monta os pesos a partir do dicionário de configurações."""
        default = cls()
        return cls(
            rating=float(settings.get("score_weight_rating", default.rating)),
            reviews=float(settings.get("score_weight_reviews", default.reviews)),
            website=float(settings.get("score_weight_website", default.website)),
            reviews_cap=int(settings.get("score_reviews_cap", default.reviews_cap)),
        )


def calculate_priority_score(
    rating: float | None,
    review_count: int | None,
    website_status: WebsiteStatus | None,
    weights: ScoreWeights | None = None,
) -> int:
    """Calcula o score de prioridade, limitado a 0–100.

    Valores ausentes contam como zero; ``website_status`` ausente conta como "sem site",
    que é o caso típico de leads coletados no Google Maps.
    """
    w = weights or ScoreWeights()

    rating_part = (min(max(rating or 0.0, 0.0), 5.0) / 5.0) * w.rating

    reviews = max(review_count or 0, 0)
    cap = max(w.reviews_cap, 1)
    reviews_ratio = min(math.log10(reviews + 1) / math.log10(cap + 1), 1.0)
    reviews_part = reviews_ratio * w.reviews

    website_part = WEBSITE_FACTOR[website_status or WebsiteStatus.NONE] * w.website

    total = rating_part + reviews_part + website_part
    return int(round(min(max(total, 0.0), 100.0)))


def score_label(score: int) -> str:
    """Faixa textual do score, usada em badges."""
    if score >= 80:
        return "Máxima"
    if score >= 60:
        return "Alta"
    if score >= 40:
        return "Média"
    return "Baixa"
