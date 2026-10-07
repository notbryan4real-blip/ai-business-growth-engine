# Shiraz Plumbing demo

This is a sales-demo concept, not the official Shiraz Plumbing website.

## Deploy

Serve this directory as a static site. Before a customer-facing launch:

1. Copy form-config.example.js to form-config.js.
2. Set window.SHIRAZ_FORM_ENDPOINT to an HTTPS endpoint owned/approved for lead intake.
3. Accept JSON fields: name, phone, zip, problem, description, source, page, submitted_at.
4. Route submissions to the owner's approved inbox or CRM.
5. Add server-side spam/rate limiting, validation, and logging.
6. Replace demo-only claims and review text with owner-verified facts.

The frontend deliberately does not claim success unless the endpoint returns a successful response.
