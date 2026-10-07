"""Core prospect domain models."""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Prospect:
    business_name: str
    category: Optional[str] = None
    location: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website_url: Optional[str] = None
    social_urls: list[str] = field(default_factory=list)
    rating: Optional[float] = None
    review_count: int = 0
    website_quality_score: Optional[int] = None
    opportunity_score: Optional[int] = None
    source: Optional[str] = None
    source_url: Optional[str] = None
    notes: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not self.business_name.strip():
            raise ValueError("business_name cannot be empty")
        if self.rating is not None and not 0 <= self.rating <= 5:
            raise ValueError("rating must be between 0 and 5")
        if self.review_count < 0:
            raise ValueError("review_count cannot be negative")
        for name, score in (
            ("website_quality_score", self.website_quality_score),
            ("opportunity_score", self.opportunity_score),
        ):
            if score is not None and not 0 <= score <= 100:
                raise ValueError(f"{name} must be between 0 and 100")
