# Approval queue API

All routes require `Authorization: Bearer <APP_API_TOKEN>`.

- `GET /api/approvals` lists approval requests.
- `POST /api/approvals` creates a pending approval request for outreach, website publication, financial commitments, sensitive customer-data access, or another consequential action.
- `PATCH /api/approvals/{approval_id}` records one approved/rejected decision with rationale. A request can only be decided once.

Example create body:

```json
{
  "action_type": "outreach",
  "target": "Example Plumbing",
  "summary": "Review the first-contact message before sending.",
  "payload": {"draft_id": "draft-123"},
  "evidence": ["The public contact page was reviewed"]
}
```

An approval record is an auditable decision record, not an execution engine. Recording an approval does not send a message, publish a website, make a purchase, or perform any external action. Those actions require separate integrations, explicit permissions, and their own safety checks. Do not put credentials or unnecessary sensitive data into approval payloads.
