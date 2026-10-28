import hashlib
import hmac
import json
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
from integrations.stripe_checkout import router

app = FastAPI()
app.include_router(router)
client = TestClient(app)

def test_checkout_requires_admin(monkeypatch):
    monkeypatch.setenv("STRIPE_ADMIN_TOKEN", "test-admin-token")
    response = client.post("/api/stripe/checkout", json={"price_id": "price_123"})
    assert response.status_code == 401

def test_live_key_refused(monkeypatch):
    monkeypatch.setenv("STRIPE_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_live_invalid")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")
    response = client.post("/api/stripe/checkout", json={"price_id": "price_123"}, headers={"Authorization": "Bearer test-admin-token"})
    assert response.status_code == 503

def test_connected_account_rejected(monkeypatch):
    monkeypatch.setenv("STRIPE_ADMIN_TOKEN", "test-admin-token")
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.com")
    response = client.post("/api/stripe/checkout", json={"price_id": "price_123", "connected_account_id": "acct_123"}, headers={"Authorization": "Bearer test-admin-token"})
    assert response.status_code == 403

def test_webhook_signature(monkeypatch):
    secret = "whsec_test"
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", secret)
    body = json.dumps({"id": "evt_test", "type": "checkout.session.completed"}).encode()
    timestamp = str(int(time.time()))
    digest = hmac.new(secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
    response = client.post("/api/stripe/webhook", content=body, headers={"Stripe-Signature": f"t={timestamp},v1={digest}"})
    assert response.status_code == 200
    assert client.post("/api/stripe/webhook", content=body, headers={"Stripe-Signature": f"t={timestamp},v1=bad"}).status_code == 400
