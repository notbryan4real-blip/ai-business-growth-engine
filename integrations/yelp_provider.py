"""Yelp-backed local-business discovery fallback.

Execution is performed through Composio; this module only documents the
normalized contract used by the application. Credentials stay in Composio.
"""

from __future__ import annotations

from typing import Any


def normalize_yelp_business(business: dict[str, Any], category: str) -> dict[str, Any]:
    location = business.get("location") or {}
    return {
        "business_name": business.get("name"),
        "category": category,
        "location": ", ".join(
            p for p in [location.get("city"), location.get("state")] if p
        ),
        "phone": business.get("display_phone") or business.get("phone"),
        "website_url": business.get("website"),
        "rating": business.get("rating"),
        "review_count": business.get("review_count", 0),
        "source": "yelp",
        "source_url": business.get("url"),
        "external_id": business.get("id"),
    }
