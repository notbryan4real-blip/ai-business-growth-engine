# Growth Engine Dashboard

A phone-first command center for the prospect-to-revenue workflow.

## Features
- Add, edit, search, and rank prospects using a transparent scoring rubric.
- Track opportunities through Research → Demo → Proposal → Won.
- Generate editable outreach drafts and proposal outlines.
- Review-gate outbound messaging; nothing is sent automatically.
- Track received payments separately from estimated pipeline value.
- Export a JSON backup.
- AI Agent Lab UI for submitting evidence to the protected specialist-agent API and viewing structured run reports.

## Hosting
The dashboard is intended to be served from GitHub Pages at:

https://notbryan4real-blip.github.io/ai-business-growth-engine/

The Pages deployment workflow is committed, but its attempts currently fail because the connected GitHub integration cannot create/enable the Pages site. The repository owner must enable GitHub Pages with the GitHub Actions build source in repository settings, or use another authorized static host.

## AI Agent Lab setup
The API must be deployed separately using the repository's `render.yaml` blueprint. Configure `AI_API_KEY` with an Anthropic API key and `APP_API_TOKEN` with a long random secret in the hosting environment. Then open the Agent Lab tab and enter the API base URL and token. The API token is held in browser session storage, not persistent local storage. Configure the API's CORS origin to the dashboard's actual public origin.

The agents perform separate sequential model calls to analyze submitted evidence. They do not browse the live web, verify business details, or send outreach. Free hosting may sleep, and the default JSON file storage is not durable across some restarts; use managed persistent storage before relying on it for business-critical records.

The seeded Shiraz Plumbing record is a carry-over lead. Re-verify current business details before outreach.
