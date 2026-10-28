"""Stripe Connect marketplace MVP router. Mount with app.include_router(router).
Requires: pip install stripe; env STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET,
MARKETPLACE_BASE_URL. Uses Connect destination charges, one seller per checkout.
Seller account IDs must be provisioned and verified server-side before use.
"""
import os
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
import stripe

router = APIRouter(prefix="/api/marketplace", tags=["marketplace"])
stripe.api_key = os.getenv("STRIPE_SECRET_KEY")
BASE_URL = os.getenv("MARKETPLACE_BASE_URL", "").rstrip("/")
# DEMO ONLY: replace with persistent DB, authenticated seller ownership,
# verified pricing, order inventory and webhook event deduplication.
LISTINGS = {}

class Listing(BaseModel):
    id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    title: str = Field(min_length=1, max_length=140)
    amount_cents: int = Field(ge=50, le=100000000)
    currency: str = Field(default="usd", pattern="^usd$")
    seller_account_id: str = Field(pattern=r"^acct_[A-Za-z0-9]+$")

@router.get("/listings")
def list_listings():
    return list(LISTINGS.values())

@router.post("/checkout/{listing_id}")
def create_checkout(listing_id: str):
    if os.getenv("MARKETPLACE_ENABLE_CHECKOUT") != "true":
        raise HTTPException(503, "Checkout disabled until production readiness is verified")
    if not stripe.api_key or not BASE_URL.startswith("https://"):
        raise HTTPException(503, "Stripe marketplace is not configured")
    item = LISTINGS.get(listing_id)
    if item is None:
        raise HTTPException(404, "Listing not found")
    # Verify the seller's account belongs to this platform and is charge-ready.
    try:
        account = stripe.Account.retrieve(item["seller_account_id"])
        if not account.get("charges_enabled"):
            raise HTTPException(409, "Seller is not ready for payments")
        fee = (item["amount_cents"] * 10) // 100
        session = stripe.checkout.Session.create(
            mode="payment",
            line_items=[{"price_data": {
                "currency": item["currency"],
                "unit_amount": item["amount_cents"],
                "product_data": {"name": item["title"]}
            }, "quantity": 1}],
            payment_intent_data={
                "application_fee_amount": fee,
                "transfer_data": {"destination": item["seller_account_id"]}
            },
            success_url=BASE_URL + "/marketplace.html?checkout=success",
            cancel_url=BASE_URL + "/marketplace.html?checkout=cancel",
            metadata={"listing_id": listing_id}
        )
        return {"url": session.url}
    except stripe.error.StripeError:
        raise HTTPException(502, "Payment provider unavailable")

@router.post("/webhook")
async def webhook(request: Request):
    secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    if not secret:
        raise HTTPException(503, "Webhook not configured")
    body = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            body, request.headers.get("stripe-signature", ""), secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        raise HTTPException(400, "Invalid webhook signature")
    # TODO: persist unique event.id and fulfill paid orders transactionally.
    # Never fulfill from the browser success redirect.
    return {"received": True, "type": event["type"]}
