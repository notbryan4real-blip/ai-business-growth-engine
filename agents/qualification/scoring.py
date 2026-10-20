"""Transparent opportunity scoring."""

from dataclasses import dataclass

from agents.prospecting.models import Prospect


@dataclass(frozen=True)
class ScoreBreakdown:
    total: int
    factors: dict[str, int]


def score_prospect(prospect: Prospect) -> ScoreBreakdown:
    """Score a prospect using explicit, deterministic signals.

    An omitted website URL is not proof that a business has no website. The
    no-website bonus is applied only when absence was independently confirmed.
    """
    factors: dict[str, int] = {}

    if prospect.website_url:
        if prospect.website_quality_score is not None:
            if prospect.website_quality_score <= 30:
                factors["poor_website"] = 20
            elif prospect.website_quality_score <= 60:
                factors["average_website"] = 10
    elif prospect.website_status == "confirmed_missing":
        factors["no_website"] = 30

    if prospect.rating is not None and prospect.rating >= 4.5:
        factors["strong_rating"] = 15

    if prospect.review_count >= 20:
        factors["review_volume"] = 10

    if prospect.social_urls:
        factors["active_social_presence"] = 10

    return ScoreBreakdown(total=min(100, sum(factors.values())), factors=factors)
