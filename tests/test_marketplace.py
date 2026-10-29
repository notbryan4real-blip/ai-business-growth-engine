"""Marketplace safety regression tests; no Stripe network calls."""
from fastapi.testclient import TestClient
from app import app

client = TestClient(app)

def test_empty_listings():
    response = client.get("/api/marketplace/listings")
    assert response.status_code == 200
    assert response.json() == []

def test_checkout_unknown_listing_rejected_without_credentials():
    response = client.post("/api/marketplace/checkout/nonexistent")
    assert response.status_code in (404, 503)
    assert "url" not in response.json()

def test_webhook_requires_secret(monkeypatch):
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    response = client.post("/api/marketplace/webhook", data=b"{}")
    assert response.status_code == 503

def test_marketplace_page():
    response = client.get("/marketplace.html")
    assert response.status_code == 200
    assert "Checkout unavailable in preview" in response.text
