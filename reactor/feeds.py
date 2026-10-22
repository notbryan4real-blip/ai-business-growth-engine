"""Fixed-host, read-only data adapters. No user URLs are fetched and no orders exist."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
import threading
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import httpx

from .models import Evidence, dt, iso, now

ASSETS = {"BTC": None, "ETH": None, "AAVE": "aave", "UNI": "uniswap"}


def fetch(url, params=None, xml=False):
    # URLs are constants in the adapters below. Never return request objects or secret-bearing errors.
    with httpx.Client(timeout=httpx.Timeout(12, connect=5), follow_redirects=False) as client:
        with client.stream("GET", url, params=params, headers={"User-Agent": "GrowthEngineResearch/1.0", "Accept": "application/xml" if xml else "application/json"}) as response:
            response.raise_for_status()
            chunks, size = [], 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > 3_000_000:
                    raise ValueError("Source response exceeds the research size limit.")
                chunks.append(chunk)
    raw = b"".join(chunks)
    return raw if xml else json.loads(raw)


def number(value, positive=False):
    n = float(value)
    if not math.isfinite(n) or n < 0 or (positive and n <= 0):
        raise ValueError("Invalid source number.")
    return n


def event(kind, asset, url, published, metrics, headline="", event_at=None, reference=None):
    item = Evidence(reference=reference or hashlib.sha256((url + iso(published)).encode()).hexdigest()[:32],
                    kind=kind, asset=asset, source_url=url, published_at=published,
                    observed_at=now(), event_at=event_at, metrics=metrics, headline=headline, confirmed=True)
    return {**item.model_dump(mode="json"), "provenance": "direct_provider_read", "received_at": iso()}


def quote(asset):
    url = f"https://api.exchange.coinbase.com/products/{asset}-USD/ticker"
    data = fetch(url)
    bid, ask = number(data["bid"], True), number(data["ask"], True)
    if bid > ask:
        raise ValueError("Crossed quote.")
    at = dt(data["time"])
    if at.tzinfo is None or at > now() + timedelta(seconds=30) or now() - at > timedelta(minutes=5):
        raise ValueError("Source ticker is stale or future-dated.")
    return {"asset": asset, "bid": bid, "ask": ask, "price": number(data["price"], True),
            "volume_24h": number(data["volume"]), "quote_at": iso(at), "fetched_at": iso(), "source_url": url,
            "spread_bps": round((ask-bid) / ((bid+ask)/2)*10000, 3)}


def revenue(asset, protocol):
    url = f"https://api.llama.fi/summary/fees/{protocol}"
    data = fetch(url, {"dataType": "dailyRevenue", "excludeTotalDataChart": "false", "excludeTotalDataChartBreakdown": "true"})
    today = int(now().replace(hour=0, minute=0, second=0, microsecond=0).timestamp())
    rows = {}
    for t, value in data.get("totalDataChart", []):
        t = int(t)
        if t % 86400 == 0 and t < today:
            rows[t] = number(value)
    if not rows:
        raise ValueError("Revenue history unavailable.")
    last = max(rows)
    required = [last - 86400 * i for i in range(14)]
    if any(t not in rows for t in required):
        raise ValueError("Fourteen consecutive completed revenue days required.")
    end = datetime.fromtimestamp(last + 86400, timezone.utc)
    # Retrieval time is when this mutable history became available to this system.
    return event("revenue", asset, url, now(),
                 {"recent_7d_usd": sum(rows[t] for t in required[:7]), "previous_7d_usd": sum(rows[t] for t in required[7:])},
                 headline=f"{protocol} completed weekly protocol revenue", event_at=end,
                 reference=f"revenue-{protocol}-{last}")


def regulation():
    raw = fetch("https://www.sec.gov/news/pressreleases.rss", xml=True)
    if b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise ValueError("Unsafe feed document.")
    root = ET.fromstring(raw)
    events = []
    for item in root.findall("./channel/item")[:50]:
        title = (item.findtext("title") or "").strip()
        text = title.lower()
        if not any(word in text for word in ("bitcoin", "ethereum", "ether ", "crypto", "digital asset")):
            continue
        try:
            published = parsedate_to_datetime(item.findtext("pubDate"))
            if now() - published > timedelta(days=7):
                continue
            assets = ["BTC"] if "bitcoin" in text else ["ETH"] if "ethereum" in text or "ether " in text else ["BTC", "ETH"]
            url = (item.findtext("link") or "").strip()
            for asset in assets:
                events.append(event("regulation", asset, url, published, {}, title,
                                    reference=hashlib.sha256((url+asset).encode()).hexdigest()[:32]))
        except (ValueError, TypeError, KeyError):
            continue
    return events


def miners():
    key = os.getenv("GLASSNODE_API_KEY")
    if not key:
        return None
    url = "https://api.glassnode.com/v1/metrics/mining/miners_outflow_multiple"
    rows = fetch(url, {"a": "BTC", "i": "24h", "s": int((now()-timedelta(days=4)).timestamp()), "api_key": key})
    if not isinstance(rows, list) or not rows:
        raise ValueError("Miner metric unavailable.")
    valid = [row for row in rows if int(row["t"]) + 86400 <= now().timestamp()]
    if not valid:
        raise ValueError("No completed miner interval.")
    row = max(valid, key=lambda row: row["t"])
    end = datetime.fromtimestamp(row["t"] + 86400, timezone.utc)
    return event("miner", "BTC", url, now(), {"outflow_multiple": number(row["v"])},
                 "Completed daily miner outflow multiple", event_at=end, reference="miner-"+str(row["t"]))


class FeedHub:
    def __init__(self):
        self.lock = threading.Lock()
        self.cached = None
        self.cached_at = 0
        self.product_ids = None

    def listings(self):
        url = "https://api.exchange.coinbase.com/products"
        rows = fetch(url)
        ids = {r["id"] for r in rows if r.get("quote_currency") == "USD" and r.get("status") == "online"}
        # A cold start establishes a baseline, never labels every pair a new listing.
        changes = set() if self.product_ids is None else ids - self.product_ids
        self.product_ids = ids
        result = []
        for product in sorted(changes)[:20]:
            asset = product.split("-")[0]
            if asset not in ASSETS:
                continue
            result.append(event("listing", asset, url, now(), {"stage": "observed_pair"},
                                "Product newly observed since last catalog read", reference="pair-"+product))
        return result

    def snapshot(self):
        with self.lock:
            if self.cached and time.monotonic() - self.cached_at < 90:
                return copy.deepcopy(self.cached)
            jobs = {"coinbase_"+a: (quote, (a,)) for a in ASSETS}
            jobs.update({"revenue_"+a: (revenue, (a, p)) for a, p in ASSETS.items() if p})
            jobs.update({"sec": (regulation, ()), "listings": (self.listings, ()), "miners": (miners, ())})
            snapshot = {"fetched_at": iso(), "quotes": {}, "events": [], "sources": {}, "cache_seconds": 90}
            with ThreadPoolExecutor(max_workers=6) as pool:
                pending = {pool.submit(fn, *args): name for name, (fn, args) in jobs.items()}
                for future in as_completed(pending):
                    name = pending[future]
                    try:
                        data = future.result()
                        if data is None:
                            snapshot["sources"][name] = {"status": "not_configured", "detail": "Needs GLASSNODE_API_KEY with metric access, or a sourced import."}
                            continue
                        if name.startswith("coinbase_"):
                            snapshot["quotes"][data["asset"]] = data
                        elif isinstance(data, list):
                            snapshot["events"].extend(data)
                        else:
                            snapshot["events"].append(data)
                        snapshot["sources"][name] = {"status": "ok", "at": iso()}
                    except Exception:
                        snapshot["sources"][name] = {"status": "unavailable", "detail": "Source request or validation failed. No replacement data fabricated."}
            snapshot["sources"]["unlocks"] = {"status": "import_required", "detail": "Import confirmed issuer unlock schedules with source URLs and timestamps."}
            self.cached, self.cached_at = snapshot, time.monotonic()
            return copy.deepcopy(snapshot)
