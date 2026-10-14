# Growth Engine Dashboard (MVP)

A phone-first workspace for the prospect-to-revenue workflow.

## What works
- Add, edit, search, and rank prospect records using a visible deterministic scoring rubric.
- Track opportunities through Research → Demo → Proposal → Won.
- Generate editable outreach drafts and proposal outlines from your verified observations.
- Require a manual review confirmation before marking a draft approved for manual use.
- Record payments actually received separately from estimated pipeline value.
- Export all locally stored prospects, drafts, and revenue records as a JSON backup.

## Open it
After the GitHub Pages workflow deploys, the dashboard is intended to be available at:

https://notbryan4real-blip.github.io/ai-business-growth-engine/

The workflow deploys the contents of this folder when files change on main. If GitHub Pages is not enabled for GitHub Actions in repository settings, enable Pages with the GitHub Actions build source once.

## Important limits
This is a usable MVP, not a live autonomous agent service. It does not scrape or verify the web, invoke an LLM, run background jobs, send outreach, accept payments, or sync across devices. Data is stored in the browser's local storage on the device/browser where you use it; export backups regularly. The seeded Shiraz Plumbing record is a carry-over lead that must be re-verified before outreach. Its score reflects the website-status field only and is not a verified current buying signal.

The underlying Python project remains separate. Do not represent local template-generated drafts as AI-generated research or claim a prospect has been verified unless you actually verified it.
