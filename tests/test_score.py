"""Testes do score de prioridade."""

from __future__ import annotations

import pytest

from app.models import WebsiteStatus
from app.services.score import ScoreWeights, calculate_priority_score, score_label


def test_max_score_for_great_business_without_site() -> None:
    assert calculate_priority_score(5.0, 500, WebsiteStatus.NONE) == 100


def test_zero_score_when_everything_missing_and_has_site() -> None:
    assert calculate_priority_score(None, None, WebsiteStatus.YES) == 0


def test_missing_website_status_counts_as_no_site() -> None:
    assert calculate_priority_score(0, 0, None) == 30


def test_bad_site_scores_between_none_and_yes() -> None:
    none = calculate_priority_score(4.5, 100, WebsiteStatus.NONE)
    bad = calculate_priority_score(4.5, 100, WebsiteStatus.BAD)
    yes = calculate_priority_score(4.5, 100, WebsiteStatus.YES)
    assert none > bad > yes
    assert none - bad == 10


def test_reviews_are_log_scaled_and_capped() -> None:
    few = calculate_priority_score(0, 10, WebsiteStatus.YES)
    many = calculate_priority_score(0, 100, WebsiteStatus.YES)
    huge = calculate_priority_score(0, 50_000, WebsiteStatus.YES)
    assert 0 < few < many < huge == 30


@pytest.mark.parametrize("rating", [-1, 7.5])
def test_rating_out_of_range_is_clamped(rating: float) -> None:
    score = calculate_priority_score(rating, 0, WebsiteStatus.YES)
    assert score in (0, 40)


def test_more_reviews_and_rating_increase_priority() -> None:
    weak = calculate_priority_score(3.8, 12, WebsiteStatus.NONE)
    strong = calculate_priority_score(4.9, 340, WebsiteStatus.NONE)
    assert strong > weak


def test_custom_weights_from_settings() -> None:
    weights = ScoreWeights.from_settings(
        {"score_weight_rating": 50, "score_weight_reviews": 50, "score_weight_website": 0}
    )
    assert calculate_priority_score(5, 500, WebsiteStatus.NONE, weights) == 100
    assert calculate_priority_score(0, 0, WebsiteStatus.NONE, weights) == 0


@pytest.mark.parametrize(
    ("score", "label"), [(95, "Máxima"), (80, "Máxima"), (65, "Alta"), (45, "Média"), (10, "Baixa")]
)
def test_score_label(score: int, label: str) -> None:
    assert score_label(score) == label
