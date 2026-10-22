# Crypto Reactor

Open **https://ai-business-growth-engine-api.onrender.com/reactor.html**.
The same page is published by the existing GitHub Pages workflow. This is part
of the Growth Engine API, using the existing private Swarm token. It does not
require the separate legacy Crypto Nexus backend.

## What is implemented

The board coordinates eight stages: Planner → Collector → Analyst → Skeptic →
Risk → Builder → Verifier → Executor → next planning cycle. Each run records
timestamped handoffs, source provenance, stage latency, a hash chain, policy,
decisions and any paper fills. Hashes help detect accidental changes; they are
not signatures, a tamper-proof external ledger, or proof that evidence is true.

Three modes are available:

| Mode | Model calls | Behavior |
| --- | --- | --- |
| Rules | 0 | Eight deterministic stages, repeatable scoring and enforced risk controls. |
| AI board | 1 | Same stages plus a real model review that may veto new paper entries. |
| Full AI ring | Up to 9 | Eight separately prompted real worker calls with peer handoffs, then a board review. |

The default board model is `claude-opus-5-5`, configurable through
`REACTOR_BOARD_MODEL`. Workers use `REACTOR_WORKER_MODEL`, then the existing
`AI_MODEL`, then `claude-haiku-4-5`. This does not change the business or personal
council's model. All calls use the existing server-side `AI_API_KEY` /
`ANTHROPIC_API_KEY`. Model availability and funded credit are not inferred from
the presence of a key. No paid calls are needed for public data or rules mode.

The daily Reactor cap defaults to **two reserved calls**. To use Full AI, change
the cap to at least nine in Controls. Calls are reserved before execution and
remain reserved after failures, conservatively. A worker failure skips later
model calls and the board, blocks new entries, and preserves deterministic
reports and risk exits. A failed board also blocks new entries. Paid calls are
never automatically retried. The global model semaphore is shared with existing
business/council runs. Worker prompts cannot change policies or execute tools.

The Builder prepares a paper plan. It does not autonomously rewrite or deploy
source code. The Verifier recomputes the deterministic assessment and checks
handoff integrity. Actual full-code regression tests remain in GitHub Actions.
`python tools/verify_reactor.py` measures local syntax parsing and the full
regression suite; it does not promise a fixed latency or count imagined guards.

## Five event strategies and actual data

| Strategy | Input | Implementation / current limit |
| --- | --- | --- |
| Unlock grading | Float percentage, unlock value/daily volume, event time | Sourced owner imports; large near-term unlocks create a negative veto. No fabricated calendar. |
| Revenue momentum | Two consecutive completed seven-day revenue windows | DefiLlama dailyRevenue history for AAVE and UNI. Missing days fail validation; fees are not substituted for revenue. |
| Regulation NLP | Exact official headline, affected asset, timestamp | SEC RSS plus imports from allowlisted regulator domains. A transparent keyword baseline abstains on tentative/negated/conflicting language. It is not a trained classifier. |
| Public listing signals | Official roadmap, announcement, trading status | Coinbase product-catalog differences plus official announcement imports. The first read establishes a baseline. A newly observed pair is not a new-listing guarantee or an insider signal. |
| Miner outflows | Daily outflow / historical baseline | Optional Glassnode `miners_outflow_multiple` with `GLASSNODE_API_KEY` and metric entitlement, or sourced imports. Outflow does not establish a sale. |

Public Coinbase quotes cover BTC, ETH, AAVE and UNI in USD. Importing events for
another symbol allows grading but cannot create paper fills without an available
validated quote. Requests use fixed hosts, bounded responses, no redirect
following, finite-number validation, provider timestamps and a 90-second cache.
Failures are explicit and never replaced with invented data. Public endpoints
expose public market data and capabilities only. Private evidence, runs,
settings, exports and the paper portfolio require the existing bearer token.

Every event distinguishes published time, observed time, optional event /
measurement time, and system receipt time. Owner imports are labeled
`owner_attested` or `owner_unverified`; supplying a URL does not independently
verify its contents. Reusing an evidence reference with changed content is
rejected. Receipt times prevent newly imported data from becoming historical
knowledge in the live ledger. Refreshing old data cannot refresh its underlying
measurement/publication date.

Scores are **unvalidated heuristic points, not probabilities**. Only one latest
graded event per strategy and asset votes. Two distinct strategy types with
scores at least 25, aggregate score at least 80, and no score at or below −40
are required for a paper candidate. Multiple articles cannot stack one strategy's
vote. Scoring alone does not prove predictive value or causation.

## Paper execution and control

Defaults: $300 virtual cash, 10% position cap, 30% exposure cap, 0.5% risk budget
per trade, 2% daily loss limit, 5% drawdown limit, 2% stop trigger, 3% profit trigger,
six-hour maximum hold, 60 basis points fee and 10 basis points slippage per side.
These are adjustable test assumptions, not verified exchange fees or financial
recommendations. Buy fills use ask plus slippage; sells use bid less slippage.
Both-side fees are included in net realized P&L. Equity marks estimate liquidation
cost. The ledger reconciles cash, positions, fees and realized results.

New entries also require a quote no older than five minutes, spread at most
50 basis points, and at least $1 million estimated daily traded volume. No quote
means no fabricated fill. Existing positions with missing quotes retain a stale
mark, block new entries and display the incomplete valuation. Risk is checked
again immediately before fills using current controls, so a pause during a model
review takes effect. Pausing entries keeps risk exits active. Loss circuit
breakers stay latched; resetting a browser does not clear them. Stop triggers
are observed on cycles, not resting exchange orders, so gaps can exceed limits.

Repeated request IDs return the original run. Changed requests with reused IDs
conflict. Paper fills and completed runs commit in one SQLite transaction.
Interrupted jobs are marked interrupted on restart and never replayed. Records
are bounded at 1,000 runs / 2,000 evidence events and then require export and
deliberate archival; they are not silently deleted to make room.

There is **no exchange order, withdrawal, wallet-signing, leverage or shorting
capability**. Simulated P&L never writes to business revenue. Completed research
is shared as a `crypto` observation with the JARVIS council; Finance can review
the evidence in its normal meetings. Rules meetings create an internal follow-up.

## Historical testing

The Historical test tab accepts a JSON object with `asset`, `candles`, `events`
and optional `settings`. The UI shows the schema. Supply 30–3,000 completed,
ordered, non-overlapping candles and up to 500 events for one asset. Each candle
has `open_at`, `close_at`, `open`, `high`, `low`, `close`. Event records use the
Evidence tab's fields and metrics. All timestamps require timezones.

Entries occur at the next candle open using only events observed and published
by the preceding close. Both-side costs and capped allocations apply. Adverse
opening gaps use the opening price. If both stop and target occur within one
bar, the stop wins. Intrabar times are only known to the bar interval. Equity
uses sampled open/close marks, not a tick-perfect drawdown history.

The final 30% is replayed independently with fresh starting cash and fixed
parameters; no parameter search fits the holdout. Full-period, holdout, trade
count, fee totals, drawdown, net P&L and a full-allocation buy-and-hold baseline
are reported. The strategy uses capped positions, so benchmark allocations differ.
Fewer than 30 closed holdout trades is explicitly insufficient evidence, and
more trades alone does not establish profitability. Historical inputs are
owner-supplied and not independently authenticated; their claimed observation
times need archived evidence. Spread/depth/liquidity are unmeasured replay
assumptions. The replay does not evaluate model-generated decisions.

Live provider histories fetched today are **not** backfilled into past trade
decisions. There is no claimed event-strategy profit result without an actual
point-in-time dataset. Tests use clearly isolated fixtures and do not seed the
live ledger with invented gains.

## Operations and API

Automatic paper cycles are opt-in in Controls. They use zero model calls, at
most one cycle per 15-minute window while the host is awake. Free Render hosts
can sleep; this is not continuous or low-latency trading. No paid hosting or
data subscription is provisioned by this change.

`REACTOR_DB_PATH` defaults to `data/reactor.sqlite3`. Existing free-host disk is
ephemeral: deployment or restart may remove records. Export private backups.
`REACTOR_DURABLE_STORAGE=true` is only an operator assertion after real persistent
storage is configured and tested; it does not make local disk durable. Existing
business and council storage limitations also remain.

- Public: `GET /api/reactor/status`, `GET /api/reactor/market`.
- Protected: `GET /api/reactor/overview`, `GET /api/reactor/export`.
- Protected: `POST /api/reactor/evidence` with `{ "events": [...] }`.
- Protected: `PUT /api/reactor/settings` (strict Settings schema).
- Protected: `POST /api/reactor/runs` with `request_id`, `board` (`rules`, `ai`,
  `full_ai`), and `paper_execute`; `GET /api/reactor/runs/{id}` polls actual handoffs.
- Protected: `POST /api/reactor/replay` validates and runs an event replay.

## Claims in the source post

The social post provides no reproducible dataset supporting its 80% narrative
fade statistic, 128-module / 0.12-second verification, Touhou parity, or 421,000
guards. These are not acceptance criteria. A $1,200–$1,900 weekly profit on $300
would mean 400%–633% per week. This implementation does not promise those returns.

Primary references inspected during implementation:
- https://www.anthropic.com/claude-opus-5-5
- https://api-docs.defillama.com/llms-free.txt
- https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-ticker
- https://docs.cdp.coinbase.com/api-reference/exchange-api/rest-api/products/get-product-candles
- https://docs.glassnode.com/basic-api/endpoints/mining
- https://www.sec.gov/news/pressreleases.rss
- https://www.cftc.gov/LearnAndProtect/AdvisoriesAndArticles/AITradingBots.html
