# Google Places discovery integration

## What it does

The authenticated `POST /api/discovery/search` endpoint uses Google Places API (New) Text Search. It returns business name, category, formatted address, Maps URL, and place ID for the current response. It computes an explainable score for that response only.

## Cost controls

The field mask requests only the ID, display name, primary type display name, formatted address, and Google Maps URI. It deliberately excludes higher-cost Enterprise fields such as website URI, phone number, rating, and review count. Google documents field-level SKU tiers in its [Place Data Fields reference](https://developers.google.com/maps/documentation/places/web-service/data-fields). Confirm current pricing and quota limits before use.

## Required configuration

Set `BUSINESS_DATA_API_KEY` in the API hosting environment to a Google Maps Platform API key with Places API (New) enabled. `GOOGLE_MAPS_API_KEY` is accepted as an alternative variable name. Restrict the key to Places API and server-side use. Do not put it in browser code or source control. Google Cloud billing and quotas may apply.

## Request

```http
POST /api/discovery/search
Authorization: Bearer <APP_API_TOKEN>
Content-Type: application/json

{"query":"plumbers in Alpharetta, Georgia","max_results":10}
```

The endpoint returns live candidates and the dashboard displays them temporarily with Google Maps attribution. It does not create permanent CRM prospect records from Google Places content. The backend retains only Google Places place IDs, which are exempt from Places API caching restrictions. Do not copy returned names, addresses, phone numbers, ratings, website URLs, or other Places content into permanent storage unless a separately applicable agreement or policy permits it.

## Website evidence semantics

- `listed`: an authorized, separate verification process confirmed a website URL.
- `not_listed_unverified`: a source did not return a website URL. This is not proof that the business has no website.
- `confirmed_missing`: an operator or separate authorized verification process independently confirmed the website is absent.
- `unknown`: website status has not been verified.

The scoring engine awards the no-website factor only for `confirmed_missing`. Google Places discovery deliberately does not request website data; candidates require independent website verification before making website-related claims.

## Limitations

This integration performs discovery only. It does not crawl websites, verify owner identity, read private Google Business Profile data, send outreach, or publish customer assets. The application must comply with current Google Maps Platform attribution, terms, and privacy-policy requirements. Review official [Places API policies](https://developers.google.com/maps/documentation/places/web-service/policies) before production use.
