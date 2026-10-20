# Business operations

Open `business.html` from the existing dashboard or 3D swarm. The page reuses
the existing API URL and session token. It does not replace the 19-agent runtime.

## What runs

The server performs an operations tick on startup and every six hours while it
is awake. This is a rules-based internal planner, with zero automatic model
calls. It creates deduplicated tasks, records its decisions and prioritizes
Greenify fulfillment, Rillmark evidence and the existing website-service offer.
Changing priorities or importing new evidence permits another review within
the same six-hour window. The pause control stops subsequent automatic ticks;
an in-flight read may finish.

The 15-project register includes Greenify, Rillmark, website services, digital
products, social content, MYERS PRO, Resurrection, Shiraz, Ramlal's, Jarvis,
PrintPreview, Paperclip, Little Legends Lab, PLASTOLINE and crypto research.
Client demo projects are explicitly prospects, not paying clients. Research
and simulated trading never count as business income.

Each project links to the existing 19-agent swarm with its private portfolio
context. Connect/resume to load that context before starting a focused or full
model run. Model runs still use the owner's existing AI credit and only analyze
evidence; external actions are not implemented by the operations planner.

## Greenify

Verified ChatGPT store access and server-side access are distinct. For optional
automatic reads set these on the existing backend, never in frontend code:

```
SHOPIFY_STORE_DOMAIN=greenifyhomeandgarden.myshopify.com
SHOPIFY_ADMIN_TOKEN=<server-side store token>
SHOPIFY_API_VERSION=2026-07
```

The connector accepts only the two verified Greenify shop-domain aliases.
It requests product metadata and aggregate net sales, not customer records.
Required read access includes products/inventory and reports for the optional
sales query. It paginates the complete catalog up to 1,000 products. Incomplete
pagination or a different shop/currency stops the import. A failed report leaves
the sales figure unknown while retaining the valid product snapshot. Read
errors retain earlier evidence and do not expose provider responses or secrets.

Source documentation:
- https://shopify.dev/docs/api/admin-graphql/2026-07
- https://shopify.dev/docs/api/shopifyql/2026-07
- https://shopify.dev/docs/api/shopifyql/2026-07/syntax/since-until-during

Without a server token, use the private evidence import. Imported records retain
their source and observation time and are labeled `owner_import`, not as a live
connection. Zero recorded inventory is a check for stock, tracking settings and
supplier fulfillment, not proof of an unavailable product.

## Rillmark / Polsia

No undocumented Polsia API is assumed. There is a receiver for a future
authorized Polsia integration, and owner import works independently.

Set a new server-side `POLSIA_BRIDGE_TOKEN` distinct from `APP_API_TOKEN`.
Only share that scoped token with the specific authorized Rillmark integration.
The receiver is `POST /api/business/bridge/polsia`, with
`Authorization: Bearer <scoped token>` and the following contract:

```json
{
  "reference": "unique-report-id",
  "source": "polsia",
  "observed_at": "2026-10-20T20:00:00+00:00",
  "summary": "Actual aggregate business observations only",
  "metrics": {"sessions": 0, "signups": 0, "paying_customers": 0}
}
```

The zero values above are schema examples, not Rillmark results. Omit unknown
metrics. Reports are restricted to Rillmark, cannot read the portfolio or write
cash, and are labeled `polsia_reported`. Never send customers' bank transactions,
account identifiers or credentials to this bridge. Nothing here executes a
command in Polsia. Its authenticated dashboard and supported integration route
must be inspected before connecting the sender.

## Income target

The goal defaults to USD 1,000 per rolling seven days. The tracker uses
owner-reported receipts minus recorded expenses and refunds, with unique
references to reject duplicate clicks. Future and timezone-free timestamps,
unknown projects and fractional cents are rejected. This is recorded net cash,
not audited profit: missing expenses can overstate progress. Shopify sales,
proposals, hypothetical subscriptions and paper trading do not create cash.

## Storage and hosting

The operations database is SQLite at `BUSINESS_DB_PATH` (default
`data/business.sqlite3`). Keep it and all private imports out of git.
Transactions serialize updates and survive ordinary process restarts when the
filesystem survives. Existing agent-run storage is unchanged.

Render free hosting can sleep and its filesystem is ephemeral. Six-hour ticks
are not an always-on guarantee. Use the authenticated export control for private
backups. For durable operation point `BUSINESS_DB_PATH` at an existing persistent
volume, then set `BUSINESS_DURABLE_STORAGE=true`. That flag declares an actual
hosting choice; it does not provision a disk. No hosting purchase is automatic.

## Validation

Run `python -m pytest -q`. The business tests cover auth, scoped bridge access,
pause, restart persistence, idempotent cycles/imports/cash, cash refunds and
expenses, freshness, changed evidence, catalog completeness, and safe shop
destination restrictions. Provider behavior is tested with fixtures; live
server credentials and Polsia sender execution require separate verification.
