"""Google Places API (New) adapter for authorized business discovery.

A missing websiteUri means Places did not list a website; it does not prove
that the business has no website.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
FIELD_MASK = ",".join([
    "places.id", "places.displayName", "places.primaryTypeDisplayName",
    "places.formattedAddress", "places.googleMapsUri",
])


class PlacesDiscoveryError(RuntimeError):
    """A safe, user-presentable Places API error."""


def search_places(query: str, max_results: int = 10, api_key: str | None = None) -> list[dict[str, Any]]:
    """Search Google Places and return normalized business records."""
    clean_query = query.strip()
    if not clean_query:
        raise ValueError("query cannot be empty")
    if not 1 <= max_results <= 20:
        raise ValueError("max_results must be between 1 and 20")
    key = api_key or os.getenv("BUSINESS_DATA_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")
    if not key:
        raise PlacesDiscoveryError(
            "Google Places is not configured. Set BUSINESS_DATA_API_KEY in the API hosting environment."
        )

    payload = json.dumps({
        "textQuery": clean_query, "pageSize": max_results, "languageCode": "en"
    }).encode("utf-8")
    request = urllib.request.Request(
        PLACES_SEARCH_URL,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "X-Goog-Api-Key": key,
            "X-Goog-FieldMask": FIELD_MASK,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code in (400, 401, 403):
            raise PlacesDiscoveryError(
                f"Google Places rejected the request (HTTP {exc.code}). Check API enablement, key restrictions, and billing."
            ) from exc
        raise PlacesDiscoveryError(f"Google Places request failed (HTTP {exc.code}).") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise PlacesDiscoveryError("Google Places could not be reached; retry later.") from exc
    except json.JSONDecodeError as exc:
        raise PlacesDiscoveryError("Google Places returned an unreadable response.") from exc

    results: list[dict[str, Any]] = []
    for place in data.get("places", []):
        display_name = place.get("displayName") or {}
        primary_type = place.get("primaryTypeDisplayName") or {}
        results.append({
            "place_id": place.get("id"),
            "business_name": display_name.get("text") or "Unknown business",
            "category": primary_type.get("text"),
            "location": place.get("formattedAddress"),
            "phone": None,
            "website_url": None,
            "website_status": "unknown",
            "rating": None,
            "review_count": 0,
            "source": "google_places",
            "source_url": place.get("googleMapsUri"),
            "verification_note": "Website status was not requested from Google Places; verify independently.",
        })
    return results
