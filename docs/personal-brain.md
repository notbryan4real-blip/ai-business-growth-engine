# JARVIS personal control

The existing Swarm now has a private coordination layer at `/jarvis.html` and
authenticated `/api/brain/*` routes. It uses the existing Swarm token. The original
19-agent business workflow remains available; five new personal roles bring the
catalog to 24. These are separately prompted model calls, not 24 independently
trained neural networks or human-level general intelligence.

## Context, run previews and council health

On your phone, connect with your existing Swarm token and open **Council**.
**Preview AI council** shows the selected specialists, QA and chief, fresh/stale/
missing sources, retrieved owner memory, and the planned model-call count. The
preview makes no model call, reserves no budget and stores no imported observation.
Choose **Start reviewed AI run** to proceed. Agenda changes invalidate the preview.
The server checks the daily limit again and rejects a run if it now needs more
calls than the reviewed maximum. A preview is not a provider-credit check, a dollar
quote, or a reservation of the shared execution slot. Rules planning remains the
default; existing automatic-AI settings retain their separate daily limit.

`POST /api/brain/meetings/preview` accepts `mode` (`ai` or `rules`) and `agenda`.
It uses the same portfolio snapshot adapter and participant selection as starting
a meeting. The existing start route accepts an optional `max_model_calls` (1–6).
Both routes require the owner bearer token. The optional field preserves old API
clients and saved idempotency records. Call-count approval does not authorize any
external action; this council continues to produce recommendations only.

In **Memory**, save a **Reviewed lesson / procedure** after checking it yourself,
or search saved goals, preferences, facts and commitments. AI meetings retrieve
up to 30 records within 14,000 serialized characters: due/overdue commitments first,
then agenda keyword overlap, then goals/preferences, with recency breaking ties.
Record IDs, source and owner verification are retained. This is local keyword
retrieval, not vector similarity or a trained memory model. Rules meetings consider
all saved commitments so older deadlines are not hidden by a last-30 cutoff.

Every meeting records its selected memory IDs and omitted count. AI meetings also
record the actual memory/evidence IDs passed to the provider. The existing combined
input limit may further shorten context; the most relevant selected memories are
kept first, and the meeting view identifies abbreviation. No AI output is promoted
into owner memory automatically. Existing meetings serve as recorded episodes;
reviewed procedures are owner-authored records, not autonomous model retraining.

The **Council health** panel on Today summarizes retained runs (at most 120),
separating rules and AI. It shows completed AI runs out of terminal AI runs, model
calls attempted, mean elapsed time for completed AI runs with valid timestamps,
and all pending owner decisions. Pending decisions remain available for review even
when they are older than the latest 60 decision records. Queued/running runs are excluded from the
completion denominator; failed, canceled and interrupted runs are included. Elapsed
time includes queue time. Missing timing is omitted, not counted as zero. Completing
a run does not prove its recommendations were correct or that revenue was earned.
Provider dollar spending and tool-call accuracy are unmeasured and remain null in
the API; call counts must not be treated as a bill. This is retained-history health,
not lifetime analytics.

These additions use the existing FastAPI/SQLite implementation. They do not
provision a vector database, framework, hosted monitoring service, model provider,
MCP/A2A integration or paid infrastructure. The existing specialist hierarchy,
approval records, source freshness rules and bounded model calls remain the basis
of the system. The swarm's 3D scene and current shared glass design are preserved.

## Agenda dictation and briefing readout

The current page has **Dictate agenda**, **Read briefing**, **Stop audio**, and a
typed agenda field. Dictation fills text only; **Run briefing** explicitly starts
the existing rules meeting with zero model calls. AI runs use the separate council
preview. This is not open-ended conversational voice control or actor voice cloning.
No backend personality change is part of this upgrade.

Readout speaks the selected meeting summary, or the latest briefing when no meeting
is selected, with a 4,000-character cap. It prefers a default British English voice,
then another British English voice, then default English, then another English
voice. Otherwise it requests the browser default with `en-GB`. The chosen name and
language or fallback are shown; voice names do not reliably identify gender and
British speech is not guaranteed. Matching normalizes language-tag case and
underscore separators. Voice lists refresh on `voiceschanged` and every tap.
Loading voices never starts speech automatically.

The controls explain unavailable APIs and playback/microphone failures, and keep
their accessible labels aligned with the action. Stop cancels queued speech and
discards late dictation results; older callbacks cannot reset a newer session.
Dictation and playback interrupt one another to avoid speaking into the microphone.
No microphone request occurs on page load. Browser/OS speech services can be local
or remote, so offline processing and device voice availability are not guaranteed.

Validation commands:

```sh
PYTHONPATH=. python -m pytest -q
node --test tests/jarvis-*.test.cjs
node --check dashboard/jarvis.js
node --check dashboard/jarvis-voice.js
```

Tests use a simulated provider, DOM and speech engine. They cover relevant older
memory, deadlines, bounded context, private/read-only previews, changed call counts,
legacy request IDs, truthful metrics, preview confirmation/races, voice selection,
late voices, playback errors, and stale recognition callbacks. They do not establish
production model credit, Android audio quality, TalkBack behavior, or visual layout.
Before deploying, check Android portrait layout, preview → cancel/start, dictation
permission errors, readout with/without British voices, immediate stop/restart, and
TalkBack action/feedback announcements. Verify the existing 3D swarm still opens.

## Responsibility and communication

- Ryan sets goals, records preferences and reviews decisions.
- The Chief of Staff chairs the council and reports to Ryan.
- Personal Operations manages inbox, scheduling and knowledge roles.
- Project Management coordinates the business specialists and Social Media Analyst.
- Finance reports to the chief; QA reports independently to Ryan.
- Meetings include only specialists relevant to fresh evidence, followed by QA and
  the chief (at most six model calls). Earlier reports reach the next role; the
  chief sees all specialist summaries and QA objections. Actual handoffs, reports,
  timestamps, model-call counts and final recommendations are stored.

## Two honest execution modes

Rules meetings create and prioritize internal follow-up tasks from current source
observations and owner commitments. They cost no model tokens and are labeled
`deterministic_planning`; they do not present invented agent conversations.

AI councils call the existing Anthropic runtime. They use shared, bounded evidence
and owner memory, with peer review and a final chief recommendation. AI
recommendations enter a proposed-decision queue. They never become verified owner
facts automatically. Accepting a proposal records Ryan's decision; this version
does not send mail, publish content, spend money, trade, delete messages or change
external accounts. Existing outbound-message review requirements remain intact.

Duplicate request IDs return the original meeting, with a conflict if the input
changes. The existing Swarm semaphore prevents overlapping paid business/council
runs. Completed reports survive provider failure and cancellation. On restart,
unfinished work becomes interrupted; paid calls are never automatically replayed.

## Shared memory and observations

Owner memory stores goals, preferences, facts and commitments with sources and
optional deadlines. Observations store a source, unique reference, timestamp,
summary, bounded details and provenance. Reusing a source/reference with different
data is rejected. Evidence older than 24 hours remains visible but is excluded from
current council context and does not imply recent activity. Model reports are
recommendations, not independent evidence. Email bodies and attachments are not
fetched by the background inbox connector.

Use `POST /api/brain/memory` for owner memory and `POST /api/brain/observations` for
observations. The dashboard includes forms and an observations JSON importer. A
JSON import is an observation or `{ "observations": [ ... ] }` where each item has:

```json
{
  "source": "owner",
  "reference": "owner-observation-001",
  "observed_at": "2026-10-20T12:00:00-04:00",
  "summary": "An observation personally confirmed by the owner.",
  "details": {}
}
```

Use the actual observation time, not the example date. No private account data or
credentials belong in this repository. All brain reads, exports and writes require
the owner bearer token; the public health response contains capabilities only.

## Morning meetings and monitoring

The default review is 08:00 America/New_York. The scheduler checks each minute and
creates at most one meeting per local date after that time. Rules are the default.
Ryan can enable automatic AI in Memory → Morning review settings. The daily
council cap defaults to 12 reserved model calls and is distinct from a dollar
budget and from the existing business-agent workflow's usage. A failed/cancelled
meeting keeps its reserved allowance conservatively; it may have consumed provider
tokens. Credentials being configured does not prove that provider credit is usable.

The server polls configured account connectors at most once per hour. Failures keep
the previous evidence, record a sanitized status and retry on a later interval.
Manual reads are available in Sources. This is bounded polling while the web
process is awake; it is not continuous real-time monitoring.

Reviews appear in the dashboard. This layer does not create a ChatGPT notification,
voice call or calendar invitation. A ChatGPT morning briefing must be configured
through Automations after successful reads on each required connected app.

## Cloud account bridge

ChatGPT connector access does not automatically authorize a separate Render
process. The optional server bridge uses an owner-controlled Composio project:

- `COMPOSIO_API_KEY`: secret project API key, stored only in hosting settings.
- `BRAIN_GMAIL_ACCOUNT_ID`: actual authorized connected-account ID in that project.
- `BRAIN_INSTAGRAM_ACCOUNT_ID`: actual authorized connected-account ID in that project.

Do not assume ChatGPT account aliases are IDs in that separate Composio project.
No server key or account credential was added by this change. The UI distinguishes
configuration, successful reads, imported observations and stale evidence.

The bridge uses `POST https://backend.composio.dev/api/v3/tools/execute/{tool_slug}`
with `x-api-key`, `connected_account_id`, `version: latest`, and `arguments`, as
documented at https://docs.composio.dev/reference/v3/api-reference/tools/postToolsExecuteByToolSlug.
Only `GMAIL_FETCH_EMAILS`, `INSTAGRAM_GET_USER_INFO`, and
`INSTAGRAM_GET_USER_INSIGHTS` are allowlisted. There is no generic client tool
executor. Gmail pagination reads up to five 100-message pages of the last two days'
inbox, explicitly marking a partial result if more remain. Stored metadata is
limited to 20 messages per observation. Instagram reads profile counts and a
requested seven-day insight window. Returned values can lag and missing metrics
are not converted to zeros. Google Calendar, Facebook, YouTube and other life data
remain unconnected in this version.

## Storage and deployment

SQLite is used for transactional state. `BRAIN_DB_PATH` overrides the database;
otherwise it sits alongside `BUSINESS_DB_PATH` as `brain.sqlite3`. Free Render
storage can be ephemeral, and free web services can sleep. Therefore exact-time
morning delivery, uninterrupted background monitoring and permanent state are not
guaranteed by the existing free plan. Export a private backup from Memory before
deploying/restarting. Do not enable recurring paid operation with valuable memory
until storage and awake-time needs are resolved. A durable volume or externally
managed database would require a separate hosting decision and was not purchased.
`BRAIN_DURABLE_STORAGE=true` is an explicit operator assertion for the UI after
actual persistence has been verified; it does not provision storage.

Pushing the dashboard files to main triggers the existing GitHub Pages workflow.
Backend availability depends on the existing Render deployment settings. Verify
`/api/health` includes `brain_version`, `/jarvis.html` loads, private routes reject
missing tokens, and authenticated import → rules meeting → task completion works.
Model integration tests use a stubbed provider and do not establish live credit.
