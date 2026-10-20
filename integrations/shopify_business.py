"""Read-only, server-side Greenify connector. No customer records are requested."""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import timedelta

from business.operations import CatalogItem, Metrics, SnapshotInput, iso, now


CATALOG_QUERY = """query SwarmCatalog($after: String) {
  shop { name myshopifyDomain currencyCode }
  products(first: 50, after: $after) {
    nodes { id title status totalInventory productType }
    pageInfo { hasNextPage endCursor }
  }
}"""

REPORT_QUERY = """query SwarmSales($report: String!) {
  shopifyqlQuery(query: $report) {
    tableData { columns { name dataType } rows }
    parseErrors
  }
}"""


def query_shop(query, variables):
    domain = os.getenv("SHOPIFY_STORE_DOMAIN", "").strip().lower()
    token = os.getenv("SHOPIFY_ADMIN_TOKEN", "")
    version = os.getenv("SHOPIFY_API_VERSION", "2026-07")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.myshopify\.com", domain):
        raise ValueError("SHOPIFY_STORE_DOMAIN must be a myshopify.com shop domain.")
    if domain not in {"greenifyhomeandgarden.myshopify.com", "dcxnfg-q1.myshopify.com"}:
        raise ValueError("The configured shop does not match the verified Greenify store.")
    if not re.fullmatch(r"20\d{2}-(01|04|07|10)", version):
        raise ValueError("Invalid Shopify API version.")
    if not token:
        raise ValueError("A server-side Shopify token is required; the ChatGPT connection is separate.")
    req = urllib.request.Request(f"https://{domain}/admin/api/{version}/graphql.json",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Content-Type": "application/json", "X-Shopify-Access-Token": token}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            result = json.loads(response.read(4_000_000))
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Shopify read failed (HTTP {exc.code}). Check token and read scopes.") from None
    except (urllib.error.URLError, TimeoutError):
        raise RuntimeError("Shopify could not be reached; no snapshot was updated.") from None
    if result.get("errors") or not result.get("data"):
        raise RuntimeError("Shopify did not return complete query data. Check API scopes and version.")
    return result["data"]


def sync_greenify(engine):
    products, cursor, seen = [], None, set()
    for _ in range(20):
        data = query_shop(CATALOG_QUERY, {"after": cursor})
        shop = data["shop"]
        if shop["myshopifyDomain"] not in {"greenifyhomeandgarden.myshopify.com", "dcxnfg-q1.myshopify.com"}:
            raise ValueError("Shopify returned a different shop; import stopped.")
        if shop["currencyCode"] != "USD":
            raise ValueError("This portfolio currently supports USD only; no currency conversion was assumed.")
        page = data["products"]
        products.extend(CatalogItem(id=p["id"], title=p["title"], status=p["status"],
            product_type=p["productType"], recorded_inventory=p["totalInventory"]) for p in page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
        if not cursor or cursor in seen:
            raise RuntimeError("Shopify pagination was incomplete; old snapshot retained.")
        seen.add(cursor)
    else:
        raise RuntimeError("Catalog exceeds 1,000 products; no partial catalog was labeled complete.")
    timestamp = now()
    # This is a sales report, not evidence of collected cash or profit.
    report_status = "Sales report not available; cash ledger unchanged."
    metrics = Metrics()
    try:
        report = query_shop(REPORT_QUERY, {"report": "FROM sales SHOW net_sales SINCE " +
            (timestamp - timedelta(days=6)).date().isoformat() + " UNTIL " + timestamp.date().isoformat()})["shopifyqlQuery"]
        if not report["parseErrors"] and report["tableData"]:
            table = report["tableData"]
            index = next(i for i, c in enumerate(table["columns"]) if c["name"] == "net_sales")
            from decimal import Decimal
            metrics.net_sales_cents = int(Decimal(str(table["rows"][0][index])) * 100)
            report_status = "Shopify net sales for seven calendar days; excludes unreported costs and is not cash profit."
    except (RuntimeError, ValueError, KeyError, IndexError, StopIteration):
        pass
    return engine.ingest("greenify", SnapshotInput(reference="shopify-" + timestamp.strftime("%Y%m%dT%H%M%S%f"),
        source="shopify", observed_at=timestamp, summary=report_status, catalog=products,
        catalog_complete=True, metrics=metrics), verification="direct_api")
