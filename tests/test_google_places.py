import json
from unittest.mock import patch

import pytest

from agents.prospecting.google_places import FIELD_MASK, PlacesDiscoveryError, search_places


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_normalizes_places_without_enterprise_fields_and_keeps_website_unknown():
    payload = {"places": [{
        "id": "place-id-123",
        "displayName": {"text": "Example Plumbing"},
        "primaryTypeDisplayName": {"text": "Plumber"},
        "formattedAddress": "Alpharetta, GA",
        "googleMapsUri": "https://maps.google.com/?q=example",
    }]}
    with patch("urllib.request.urlopen", return_value=FakeResponse(payload)) as mocked:
        result = search_places("plumbers in Alpharetta GA", api_key="test-key")

    assert result[0]["business_name"] == "Example Plumbing"
    assert result[0]["place_id"] == "place-id-123"
    assert result[0]["website_url"] is None
    assert result[0]["website_status"] == "unknown"
    assert "verify independently" in result[0]["verification_note"]
    assert mocked.call_args.args[0].get_header("X-goog-fieldmask") == FIELD_MASK
    assert "places.websiteUri" not in FIELD_MASK
    assert "places.nationalPhoneNumber" not in FIELD_MASK
    assert "places.rating" not in FIELD_MASK
    assert "places.userRatingCount" not in FIELD_MASK


def test_missing_api_key_is_actionable():
    with patch.dict("os.environ", {}, clear=True):
        with pytest.raises(PlacesDiscoveryError, match="BUSINESS_DATA_API_KEY"):
            search_places("plumbers")


@pytest.mark.parametrize("query,max_results", [("", 5), ("plumbers", 0), ("plumbers", 21)])
def test_rejects_invalid_search_input(query, max_results):
    with pytest.raises(ValueError):
        search_places(query, max_results=max_results, api_key="test-key")
