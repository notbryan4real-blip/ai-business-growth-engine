# AI Business Growth Engine

A phone-first, approval-gated workflow for qualifying local-business prospects, generating focused offers, and tracking sales opportunities.

## Current product

- `dashboard/index.html`: mobile-first command center for prospect records, transparent scoring, sales drafts, pipeline tracking, revenue logging, and JSON backup.
- `app.py`: FastAPI service for prospect scoring and protected specialist-agent runs.
- `agents/runtime.py`: six role-specific agents — Opportunity Qualification, Market Intelligence, Digital Presence Audit, Offer Strategist, Sales Drafting, and Quality Assurance. Each specialist is a separate Anthropic model invocation; outputs are passed forward sequentially and saved with a run ID.
- `tests/test_scoring.py` and `tests/test_runtime.py`: automated regression tests.
- `render.yaml`: deployment blueprint for the API on Render's free tier.
- `demos/shiraz-plumbing/index.html`: existing customer-facing website demo.
- `docs/prospects/shiraz-plumbing-audit.md`: existing audit notes.

## Run the API

Python 3.11+ recommended.

```bash
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

API routes:
- `GET /api/health` — health and configuration status
- `GET /api/agents` — specialist-agent catalog
- `GET /api/prospects` — stored prospect and run records
- `POST /api/prospects` — score and save a prospect
- `POST /api/agents/run` — run selected specialist agents in sequence

Set `AI_API_KEY` to an Anthropic API key in the hosting environment. Set `AI_MODEL` to a model enabled for that account; default: `claude-haiku-4-5`. Set `APP_API_TOKEN` to a long random secret. Mutating endpoints and agent runs require `Authorization: Bearer <APP_API_TOKEN>`. Never put either secret in source control or in browser-side JavaScript.

Example agent request:

```json
{
  "prospect": {
    "business_name": "Example Plumbing",
    "category": "Plumbing",
    "location": "Alpharetta, GA",
    "website_url": null,
    "verified_observations": ["Business owner confirmed service area"]
  },
  "agent_ids": ["qualification", "offer", "sales", "qa"]
}
```

## Deployment status

The API deployment blueprint is ready, but the service is **not considered live until it is deployed with secrets configured and tested**. The browser dashboard deployment is also not confirmed live: the GitHub Pages workflow failed because the connected GitHub integration cannot create/enable a Pages site. This requires hosting permissions or a different authorized deployment path.

The Render free-tier blueprint is a deployment starting point. Free instances may sleep; the JSON file store is ephemeral on typical free instances and is not production-grade persistent storage. Use a managed database/persistent volume before relying on it for ongoing business records.

## Evidence and safety

- The specialist agents analyze only the evidence submitted in a run. They do not claim to browse the web, scrape Google, verify business facts, or contact prospects.
- No messages are sent automatically. Human review is required before outreach.
- Scores are transparent heuristics, not probabilities of a sale.
- Never commit API keys or other secrets.
- Do not claim a business has been researched or verified unless it actually has been.

## Initial prospect experiment

The first prospect experiment is **Shiraz Plumbing in Alpharetta, GA**:
- Audit: `docs/prospects/shiraz-plumbing-audit.md`
- Sales demo: `demos/shiraz-plumbing/index.html`
- Re-verify current business details before any customer contact.
