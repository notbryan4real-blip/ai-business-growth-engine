# Architecture

The JARVIS council uses the existing specialist hierarchy, owner memory, approval
records and bounded call budget. Its agenda-based context retrieval, run previews,
measured health panel and browser speech controls are documented in
[JARVIS personal control](personal-brain.md). These are application-level additions;
no new agent framework or paid infrastructure is required.

## Initial flow

1. Discovery adapters retrieve candidate businesses.
2. Candidates are normalized into the Prospect model.
3. Deterministic qualification scores each prospect.
4. A sales queue receives the highest-value opportunities.
5. Human review happens before outreach.

## Why deterministic scoring first?

We want every qualification decision to be explainable and testable. AI will enrich and interpret data, but the core ranking rules remain inspectable.

## Next milestone

Connect a real business-discovery provider, collect 20 prospects for one local service category, inspect the results manually, and tune the scoring model against actual sales potential.
