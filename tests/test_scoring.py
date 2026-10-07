from agents.prospecting.models import Prospect
from agents.qualification.scoring import score_prospect


def test_no_website_high_quality_business_scores_well():
    prospect = Prospect(
        business_name="Example Plumbing",
        rating=4.8,
        review_count=120,
        social_urls=["https://instagram.com/example"],
    )

    result = score_prospect(prospect)

    assert result.total == 65
    assert result.factors["no_website"] == 30


def test_poor_website_is_scored():
    prospect = Prospect(
        business_name="Example Roofing",
        website_url="https://example.com",
        website_quality_score=20,
    )

    result = score_prospect(prospect)

    assert result.total == 20
    assert result.factors["poor_website"] == 20


def test_score_is_capped_at_100():
    prospect = Prospect(
        business_name="Example",
        rating=5,
        review_count=1000,
        social_urls=["https://instagram.com/example"],
    )

    assert score_prospect(prospect).total <= 100
