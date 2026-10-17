# Google Places discovery integration

## What it does

The API provides an authenticated `POST /api/discovery/search` endpoint backed by Google Places API (New) Text Search. It normalizes business name, category, address, phone, website URL, rating, review count, Maps URL, and provider ID; scores each prospect with transparent rules; stores new records; and skips duplicates.

## Required configuration

Set `BUSINESS_DATA_API_KEY` in the API hosting environment to a Google Maps Platform API key with Places API (New) enabled. `GOOGLE_MAPS_API_KEY` is accepted as an alternative variable name. Restrict the key to the required API and appropriate server-side use. Do not place it in the browser or source control. Google Cloud billing and quotas may apply.

## Request

```http
POST /api/discovery/search
Authorization: Bearer <APP_API_TOKEN>
Content-Type: application/json

{"query":"plumbers in Alpharetta, Georgia","max_results":10}
```

The result reports returned, created, and duplicate counts. Repeated queries skip matching records based on provider ID, Maps URL, or normalized business name and address.

## Website evidence semantics

- `listed`: Places returned a website URL.
- `not_listed_unverified`: Places did not return a website URL. This is not proof that the business has no website.
- `confirmed_missing`: an operator or separate authorized verification process has independently confirmed the website is absent.
- `unknown`: no determination has been made.

The scoring engine should award the no-website factor only for `confirmed_missing`. This prevents an incomplete Places record from being misrepresented as a verified marketing opportunity.

## Limitations

This integration performs discovery only. It does not crawl websites, verify owner identity, read private Google Business Profile data, send outreach, or publish customer assets. Google Places terms, quotas, field billing, and API availability must be reviewed before production use.
