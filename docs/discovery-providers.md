# Prospect discovery providers

## Provider strategy

Prospect discovery is provider-agnostic. The first implementation used OpenWeb
Ninja, but the local-business endpoint currently returns HTTP 403 for the
connected account. Do not block the pipeline on that provider.

The current fallback is Yelp via Composio. Yelp search and business-detail
calls are working and can supply candidate businesses, ratings, review counts,
phones, addresses, and directory URLs.

### Production flow

1. Search Yelp by category + target market.
2. Normalize results into the Prospect model.
3. Enrich finalists with Yelp business details.
4. Verify the official website independently through web search.
5. Score website presence/quality and demand signals.
6. Store the prospect and source evidence.
7. Keep OpenWeb Ninja as an optional provider and retry it periodically.

## Important

Yelp's url field is a Yelp directory URL, not necessarily the business's own
website. Never treat it as website_url. Official domains must be verified
separately.
