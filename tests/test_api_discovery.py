import json

import pytest
from fastapi import HTTPException

import app as api


def test_discovery_only_persists_place_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_API_TOKEN", "test-token")
    monkeypatch.setattr(api, "DATA_PATH", tmp_path / "store.json")
    monkeypatch.setattr(api, "search_places", lambda query, max_results: [{
        "place_id": "place-id-123",
        "business_name": "Example Plumbing",
        "category": "Plumber",
        "location": "Alpharetta, GA",
        "phone": "555-0100",
        "website_url": None,
        "website_status": "unknown",
        "rating": None,
        "review_count": 0,
        "source": "google_places",
        "source_url": "https://maps.google.com/?q=example",
        "verification_note": "Website absence is unverified.",
    }])

    result = api.discover_businesses(
        api.DiscoveryInput(query="plumbers in Alpharetta, Georgia", max_results=10),
        authorization="Bearer test-token",
    )

    assert result["results_are_transient"] is True
    assert result["results_returned"] == 1
    assert result["prospects"][0]["opportunity_score"] == 0
    stored = json.loads((tmp_path / "store.json").read_text(encoding="utf-8"))
    assert stored["google_place_ids"] == ["place-id-123"]
    assert stored["prospects"] == []
    assert "Example Plumbing" not in json.dumps(stored)
    assert "555-0100" not in json.dumps(stored)


def test_discovery_requires_bearer_token(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "DATA_PATH", tmp_path / "store.json")
    monkeypatch.delenv("APP_API_TOKEN", raising=False)
    with pytest.raises(HTTPException) as exc:
        api.discover_businesses(
            api.DiscoveryInput(query="plumbers in Alpharetta, Georgia"),
            authorization=None,
        )
    assert exc.value.status_code == 503
