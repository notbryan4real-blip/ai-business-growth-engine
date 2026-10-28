"""Stripe test-mode checkout integration. No Stripe SDK required.

Mount with app.include_router(router). Configure STRIPE_SECRET_KEY (sk_test_...),
STRIPE_WEBHOOK_SECRET (whsec_...), STRIPE_ADMIN_TOKEN, and PUBLIC_BASE_URL.
Never expose secrets in client code or commit them to Git.
"""
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/stripe", tags=["stripe"])

class CheckoutInput(BaseModel):
    price_id: str = Field(pattern=r"^price_[A-Za-z0-9]+$", max_length=120)
    quantity: int = Field(default=1, ge=1, le=20)
    connected_account_id: str | None = Field(default=None, pattern=r"^acct_[A-Za-z0-9]+$", max_length=120)

def _admin(authorization: str | None):
    token = os.getenv("STRIPE_ADMIN_TOKEN", "")
    if not token or not authorization or not hmac.compare_digest(authorization, "Bearer " + token):
        raise HTTPException(401, "Unauthorized")

def _key():
    key = os.getenv("STRIPE_SECRET_KEY", "")
    if not key.startswith("sk_test_"):
        raise HTTPException(503, "Stripe test-mode key is not configured")
    return key

def _stripe_post(path: str, fields: dict, connected_account: str | None = None):
    key = _key()
    headers = {"Authorization": "Bearer " + key, "Content-Type": "application/x-www-form-urlencoded"}
    if connected_account:
        headers["Stripe-Account"] = connected_account
    request = urllib.request.Request(
        "https://api.stripe.com/v1/" + path,
        data=urllib.parse.urlencode(fields).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        # Never forward Stripe's raw error body, which may contain sensitive details.
        raise HTTPException(502, "Stripe rejected the request") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise HTTPException(502, "Stripe service unavailable") from exc

@router.get("/status")
def stripe_status(authorization: str | None = Header(default=None)):
    _admin(authorization)
    return {"mode": "test", "configured": bool(os.getenv("STRIPE_SECRET_KEY", "").startswith("sk_test_")),
            "webhook_configured": bool(os.getenv("STRIPE_WEBHOOK_SECRET"))}

@router.post("/checkout")
def create_checkout(payload: CheckoutInput, authorization: str | None = Header(default=None)):
    _admin(authorization)
    base = os.getenv("PUBLIC_BASE_URL", "").rstrip("/")
    if not base.startswith("https://") or "?" in base or "#" in base:
        raise HTTPException(503, "PUBLIC_BASE_URL must be a public HTTPS origin")
    # Connected accounts are deliberately disabled until merchant ownership is verified
    # against the authenticated platform tenant.
    if payload.connected_account_id:
        raise HTTPException(403, "Connected-account checkout requires merchant authorization")
    session = _stripe_post("checkout/sessions", {
        "mode": "payment",
        "line_items[0][price]": payload.price_id,
        "line_items[0][quantity]": payload.quantity,
        "success_url": base + "/done?session_id={CHECKOUT_SESSION_ID}",
        "cancel_url": base + "/",
    })
    return {"id": session["id"], "url": session["url"]}

@router.post("/webhook")
async def stripe_webhook(request: Request, stripe_signature: str | None = Header(default=None)):
    secret = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(503, "Webhook not configured")
    body = await request.body()
    if len(body) > 1024 * 1024:
        raise HTTPException(413, "Payload too large")
    try:
        parts = dict(piece.split("=", 1) for piece in (stripe_signature or "").split(",") if "=" in piece)
        timestamp = int(parts["t"])
        signatures = [piece[3:] for piece in (stripe_signature or "").split(",") if piece.startswith("v1=")]
        expected = hmac.new(secret.encode(), str(timestamp).encode() + b"." + body, hashlib.sha256).hexdigest()
        valid = abs(time.time() - timestamp) <= 300 and any(
            hmac.compare_digest(expected, signature) for signature in signatures
        )
        if not valid:
            raise ValueError("Signature mismatch")
        event = json.loads(body)
    except (ValueError, KeyError, TypeError, json.JSONDecodeError):
        raise HTTPException(400, "Invalid webhook signature or payload")
    # Acknowledgement only. Before fulfillment, persist event IDs durably and
    # process events idempotently in an authenticated business workflow.
    return {"received": True, "event_type": event.get("type")}
