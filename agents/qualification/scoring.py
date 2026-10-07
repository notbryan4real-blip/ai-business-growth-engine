"""Transparent opportunity scoring."""

from dataclasses import dataclass

from agents.prospecting.models import Prospect


@dataclass(frozen=True)
class ScoreBreakdown:
    total: int
    factors: dict[str, int]


def score_prospect(prospect: Prospect) -> ScoreBreakdown:
    """Score a prospect using explicit, deterministic signals."""
    factors: dict[str, int] = {}

    if not prospect.website_url:
        factors["no_website"] = 30
    elif prospect.website_quality_score is not None:
        if prospect.website_quality_score <= 30:
            factors["poor_website"] = 20
        elif prospect.website_quality_score <= 60:
            factors["average_website"] = 10

    if prospect.rating is not None and prospect.rating >= 4.5:
        factors["strong_rating"] = 15

    if prospect.review_count >= 20:
        factors["review_volume"] = 10

    if prospect.social_urls:
        factors["active_social_presence"] = 10

    return ScoreBreakdown(
        total=min(100, sum(factors.values())),
        factors=factors,
    )
