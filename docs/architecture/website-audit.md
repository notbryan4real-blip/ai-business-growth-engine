# Website audit endpoint

The authenticated `POST /api/audit/website` endpoint performs a bounded static HTML inspection of a public website.

Example request:

```http
POST /api/audit/website
Authorization: Bearer <APP_API_TOKEN>
Content-Type: application/json

{"url":"https://business.example"}
```

The auditor extracts only observable signals from the fetched HTML: page title, meta description, viewport tag, H1 count, forms, anchors, buttons, labeled CTA text, and image alt attributes. It returns evidence-bound findings and explicit limitations. It does not store page content.

## Safety and limits

- Only HTTP/HTTPS public hosts are accepted.
- Localhost, private, loopback, link-local, and reserved IPs are rejected.
- Redirect destinations are revalidated; redirects are bounded.
- Each connection resolves and validates every DNS answer, then connects to the validated literal IP. HTTPS keeps the original hostname for SNI and certificate checks. Environment proxies are disabled and redirects repeat validation. Public hosts cannot rebind the outbound connection to a private address.
- The response body is capped at 1 MB and the request has a short timeout.
- Non-HTML responses are rejected.
- This is not a full browser, Lighthouse, accessibility, SEO, or performance certification. JavaScript-rendered content, authenticated pages, third-party resources, and real conversion behavior may not be visible.
- A missing signal is a finding about the fetched response only. Do not claim that a site lacks a feature without additional evidence.
