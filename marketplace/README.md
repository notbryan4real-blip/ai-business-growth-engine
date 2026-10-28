# Vanguard Marketplace — implementation status

This branch contains an isolated **prototype**, not a live marketplace.

## Current implementation
- `marketplace/stripe_routes.py`: FastAPI router for listing reads, single-seller destination-charge Checkout and signature-verified Stripe webhook intake.
- Commission: 10% gross application fee, before Stripe/Connect costs.
- No API secrets are committed.

## Required before deployment
1. Install `stripe` in backend dependencies and mount the router in `app.py`.
2. Implement authenticated seller accounts, ownership checks, and Stripe Accounts v2 onboarding. The current account lookup is a legacy-style scaffold and **does not implement Accounts v2**.
3. Replace in-memory `LISTINGS` with persistent storage and server-authorized listing creation.
4. Implement verified seller-to-platform association and payment eligibility checks.
5. Store orders and webhook event IDs durably; make fulfillment idempotent and process asynchronous payment success/failure.
6. Configure server-only `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `MARKETPLACE_BASE_URL`; use test keys first.
7. Build responsive storefront and seller/admin views, refunds, disputes, tax and compliance workflows.
8. Add integration tests and verify deployment before accepting real payments.

**Security:** Never expose secret keys in browser code. Never trust client-provided prices, sellers, or success redirects. Do not expose a public listing-write endpoint without authentication and authorization.
