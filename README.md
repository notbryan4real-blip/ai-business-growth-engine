# AI Business Growth Engine

A phone-first, approval-gated workflow for qualifying local-business prospects, generating focused offers, and tracking sales opportunities.

## Live dashboard

**Open the dashboard:** https://notbryan4real-blip.github.io/ai-business-growth-engine/

The static dashboard is published on GitHub Pages. Its browser-local workspace supports prospect records, transparent scoring, sales drafts, pipeline tracking, revenue logging, and JSON export. Browser-local data remains on the device/browser and should be exported regularly. The AI Agent Lab requires the API deployment and credentials below before it can run model calls.

## Current product

- `dashboard/index.html`: mobile-first command center for prospect records, transparent scoring, sales drafts, pipeline tracking, revenue logging, and JSON backup.
- `app.py`: FastAPI service for prospect scoring and protected specialist-agent runs.
- `agents/runtime.py`: 19 specialist roles with a five-agent focused workflow and a full 19-agent option. Each specialist is a separate Anthropic model invocation; outputs are passed forward sequentially and saved with a run ID.
- `tests/`: automated regression tests for scoring, agent runtime, Google Places discovery, and approval decisions.
- `render.yaml`: deployment blueprint for the API on Render's free tier.
- `demos/shiraz-plumbing/index.html`: existing customer-facing website demo.
- `docs/prospects/shiraz-plumbing-audit.md`: existing audit notes.
- `docs/user-manual.md`: current phone-first operation, setup, troubleshooting, and release checklist.
- `docs/architecture/website-audit.md`: scope, safety controls, and limitations for live website audits.

## Run the API

Python 3.11+ recommended.

```bash
pip install -r requirements.txt
python tools/fetch_web_assets.py
uvicorn app:app --host 0.0.0.0 --port 8000
```

API routes:
- `GET /api/health` — health and configuration status
- `GET /api/agents` — specialist-agent catalog
- `POST /api/runs` — start an authenticated, idempotent live job
- `GET /api/runs/{run_id}` — authenticated progress, partial results, and handoff events
- `POST /api/runs/{run_id}/cancel` — stop before the next model call
- `GET /api/prospects` — stored prospect and run records
- `POST /api/prospects` — score and save a prospect
- `POST /api/discovery/search` — search live candidates with Google Places API (New); requires `BUSINESS_DATA_API_KEY` and the API bearer token; results are transient and only place IDs are retained
- `POST /api/audit/website` — bounded static HTML audit of a public website; does not store page content
- `GET /api/approvals`, `POST /api/approvals`, `PATCH /api/approvals/{id}` — authenticated, persistent approval queue and dashboard review controls; decisions do not execute external actions
- `POST /api/agents/run` — run selected specialist agents in sequence

Set `AI_API_KEY` to an Anthropic API key in the hosting environment. For live business discovery, set `BUSINESS_DATA_API_KEY` to a server-restricted Google Maps Platform key with Places API (New) enabled; `GOOGLE_MAPS_API_KEY` is also accepted. Set `AI_MODEL` to a model enabled for that account; default: `claude-haiku-4-5`. The Render blueprint generates `APP_API_TOKEN` automatically; copy its value from the Render environment settings into the dashboard's session-only token field. Mutating endpoints and agent runs require `Authorization: Bearer <APP_API_TOKEN>`. Never put either secret in source control or commit it to browser-side JavaScript.

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

- **Dashboard:** deployed successfully through GitHub Pages.
- **Deploy the API:** [Open the Render Blueprint deployment](https://render.com/deploy?repo=https://github.com/notbryan4real-blip/ai-business-growth-engine). In Render, review and deploy the blueprint, then set `AI_API_KEY` to an Anthropic API key and set `APP_API_TOKEN` to a strong private token. Do not paste secrets into GitHub files or the public dashboard. After deployment, use the service's `onrender.com` URL as the dashboard's API base URL; test `/api/health` before running agents. Deployment workflow: https://github.com/notbryan4real-blip/ai-business-growth-engine/actions/runs/38516537524
- **Swarm 0.2:** real backend handoff events replace simulated traffic in `dashboard/swarm.html`. All 19 roles are selectable, QA runs last, and the focused default makes five model calls. Prior context is bounded to four concise handoffs. Each completed sales run enters a pending review queue; nothing is sent.
- **Hosting:** the backend also serves the complete dashboard at `/` and the visualizer at `/swarm.html`. The known Render backend returned six agents on October 20, 2026 before this release. All saved Render connections returned HTTP 401; backend deployment and real provider execution still need verification after access is restored.
- **Google Places:** discovery is implemented and requires a server-side Google Maps Platform API key with Places API (New) enabled. Missing website fields remain unverified.
- **Legal readiness:** draft Terms and Privacy pages require operator contact details before public production activation.
- **Persistence:** the API currently writes to a JSON file. Typical free web instances may sleep and may not preserve local files, so use a managed database or persistent volume before relying on it for ongoing business records.
- **Cloudflare:** the connected integration currently fails authentication, so no deployment was made there.

## Evidence and safety

- The Google Places adapter treats a missing website field as `not_listed_unverified`, not as proof that no website exists. Results are displayed transiently with Google Maps attribution; only place IDs are retained, in line with Places API caching restrictions. The scoring engine awards the no-website factor only when absence is independently confirmed. The specialist agents analyze only the evidence submitted in a run. They do not claim to browse the web, scrape Google, verify business facts, or contact prospects.
- No messages are sent automatically. Human review is required before outreach.
- Scores are transparent heuristics, not probabilities of a sale.
- Never commit API keys or other secrets.
- Do not claim a business has been researched or verified unless it actually has been.

## Initial prospect experiment

The first prospect experiment is **Shiraz Plumbing in Alpharetta, GA**:
- Audit: `docs/prospects/shiraz-plumbing-audit.md`
- Sales demo: `demos/shiraz-plumbing/index.html`
- Re-verify current business details before any customer contact.

## Portfolio business operations

Open `business.html` to track Greenify, Rillmark and the project portfolio, run internal operations reviews and record real cash toward the weekly target. See [the operations guide](docs/business-operations.md) for connection status, the scoped Polsia report bridge, server-side Shopify reads and hosting limits.
# Personal control room

The private JARVIS council is available at `/jarvis.html` on the existing API and
dashboard hosting. It adds shared owner memory, 24 specialist roles, recorded
council handoffs, independent QA, a decision queue and morning planning. See
[personal-brain.md](docs/personal-brain.md) for execution modes, connections,
storage limits and scheduling. Existing business workflows remain available.
