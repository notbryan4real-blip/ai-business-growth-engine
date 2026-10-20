# Growth Engine User Manual

## Current scope

The current application is a phone-first prospect and sales workspace with a separate FastAPI backend. It supports manual prospect records, transparent heuristic scoring, outreach/proposal drafts, local pipeline and revenue tracking, sequential AI specialist runs, live Google Places search (once configured), and a persistent approval queue.

It is not yet a fully autonomous agency. Website crawling, publishing to customer platforms, external outreach execution, Google Analytics ingestion, durable managed database storage, and the named email/task-management integrations are not implemented as end-to-end production workflows.

## Dashboard

1. Open the deployed dashboard URL.
2. In **AI Agent Lab**, enter the API base URL and the private API bearer token. The base URL is saved in local storage; the token is kept in session storage only.
3. Add a prospect manually when the business facts have been independently verified. Enter evidence in the observations field rather than guessing.
4. Use the prospect list and transparent score to prioritize research. A score is a screening heuristic, not a probability of sale.
5. In **Sales drafts**, select a prospect, add a specific verified observation, and generate an outreach draft or proposal outline. Review all claims and remove internal notes before using the text.
6. Use **Approvals** to submit an outreach draft for a persistent review record, then approve or reject it with a rationale. This records the decision only; it does not send the message.
7. In **Pipeline & revenue**, track opportunity stages and log payments only after funds are received.
8. Export a JSON backup regularly. Browser-local records do not automatically sync across devices.

## Live Google Places discovery

1. Configure a server-side Google Maps Platform key in the API hosting environment using `BUSINESS_DATA_API_KEY`. Enable Places API (New), set budget/quota alerts, and restrict the key to the required API and server-side use.
2. Configure `APP_API_TOKEN` in the hosting environment and the API CORS allowlist for the dashboard origin.
3. In **AI Agent Lab**, enter the API base URL and token.
4. Open **Live business discovery**, enter a specific industry/location query, and run the search.
5. Results are temporary and displayed with Google Maps attribution. The backend retains place IDs only. A missing website field is not proof that a business has no website.
6. Verify prospects independently using authorized sources before creating permanent CRM records or making claims in outreach.

## Website audit

1. In **AI Agent Lab**, enter the API base URL and bearer token.
2. Enter a public business website URL under **Live website audit**.
3. Run the audit and review the reported HTML signals and findings. The page content is not stored.
4. Treat results as a limited static HTML inspection, not a full browser, Lighthouse, accessibility, or SEO certification. Missing signals can be caused by JavaScript-rendered content.

## AI API configuration

Set `AI_API_KEY` to an authorized Anthropic API key in the backend environment. Set `AI_MODEL` to a model available to the account. The current specialist runtime makes sequential model calls using supplied evidence; it does not browse the web or perform external actions.

Never place provider keys in the dashboard, source files, public GitHub, or client-side environment variables.

## Approval queue API

- `GET /api/approvals` — list approval records.
- `POST /api/approvals` — create a pending request.
- `PATCH /api/approvals/{id}` — record an approved/rejected decision and rationale.

All require `Authorization: Bearer <APP_API_TOKEN>`. A decision is one-time. Approval records do not trigger the underlying action.

## Backups and persistence

The current backend uses a JSON file at `GROWTH_ENGINE_DATA_PATH`. On many free hosting plans local files are not durable across restarts or redeployments. Do not treat this as business-critical storage until a managed database or persistent volume is configured and backup/restore has been tested.

The dashboard uses browser local storage for the founder workspace. Export a JSON backup before clearing browser data or changing devices.

## Troubleshooting

- **401 response:** confirm the bearer token matches the private `APP_API_TOKEN` in the backend.
- **503 response for AI runs:** configure `AI_API_KEY` and verify the model name.
- **503 response for Google Places:** configure `BUSINESS_DATA_API_KEY`, enable Places API (New), check API restrictions and billing.
- **Browser CORS error:** set `CORS_ORIGINS` to the exact dashboard origin, with no trailing slash.
- **Data missing after restart:** JSON-file persistence may be ephemeral on the hosting plan; configure managed storage before relying on records.
- **Website not listed in Places:** mark it unverified until an independent source confirms absence.

## Release checklist

Before production use:
- Complete the operator contact details in the draft Terms and Privacy pages.
- Deploy and verify the backend health endpoint.
- Configure provider keys only in server-side secrets.
- Configure durable storage, backups, and restore testing.
- Verify CORS, API token access, usage quotas, and cost limits.
- Test each enabled integration against real accounts.
- Confirm approval gates cannot be bypassed.
- Review applicable platform terms and communication laws.
- Do not claim revenue or customer outcomes without evidence.

## Live Swarm 0.2

Open `swarm.html` from the dashboard, or `/swarm.html` on the backend itself. The backend URL is prefilled. Enter the private **APP_API_TOKEN**, then select **Connect / resume**. The AI provider key belongs only in server-side hosting settings.

Enter the business and verified observations. Optionally supply an official website for a live static HTML audit. The focused workflow makes five model calls (qualification, audit, offer, sales, QA); the full option runs all 19 roles. QA is always last. Earlier outputs are passed as four short handoffs rather than the full accumulated transcript.

**Start live run** creates a job and shows actual backend events. The data bus displays the exact compact prior context submitted to each role and its returned report. Background visual motion carries no claim of work; data packets are created only for real `agent_started` events. If 3D is unavailable, run controls and text reports still work. Three.js is hosted with the dashboard, avoiding an external CDN dependency.

**Stop** cancels before the next model call; a call already in flight may finish and consume credit. **Report** downloads the result. A successful sales run creates a pending item in **Approvals**, where its complete output and evidence can be inspected before a decision. Approval never sends a message.

Jobs use request IDs to prevent accidental duplicate paid calls after a network interruption. **Connect / resume** reconnects to the current browser session's run. Partial outputs are saved after each agent, including on provider failures. Restarted jobs become `interrupted` and are not replayed. The worker supports one active run per process; use a single Uvicorn worker with this file-based store. JSON storage still requires a persistent disk or migration to a managed database before business-critical use.

`POST /api/runs`, `GET /api/runs/{id}?after=<sequence>`, and `POST /api/runs/{id}/cancel` all require the private bearer token. Prospect reads also require authorization. Corrupt data fails closed rather than silently discarding records.
