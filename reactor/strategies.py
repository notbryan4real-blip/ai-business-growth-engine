"""Transparent hypotheses, not trained probabilities or validated investment advice."""
import re
from datetime import timedelta
from urllib.parse import urlsplit

from .models import dt, now

STRATEGIES = [
    {"id": "unlock", "name": "Token unlocks", "detail": "Supply expansion and unlock size versus daily trading volume."},
    {"id": "revenue", "name": "Revenue momentum", "detail": "Completed seven-day revenue against the preceding seven days."},
    {"id": "regulation", "name": "Regulation headlines", "detail": "Conservative keyword scoring of official regulator headlines; ambiguous language abstains."},
    {"id": "listing", "name": "Public listing signals", "detail": "Official roadmap and listing announcements. Newly observed pairs are not pre-listing predictions."},
    {"id": "miner", "name": "Miner outflows", "detail": "Outflows relative to historical baseline; transfers do not establish selling."},
]
TTL = {"unlock": 72, "revenue": 72, "regulation": 24, "listing": 24, "miner": 48}


def official(url, domains):
    host = urlsplit(url).hostname or ""
    return any(host == d or host.endswith("." + d) for d in domains)


def grade(event, at=None):
    at = at or now()
    kind, m = event["kind"], event["metrics"]
    result = {"kind": kind, "asset": event["asset"], "reference": event["reference"],
              "source_url": event["source_url"], "provenance": event.get("provenance", "owner_attested"),
              "score": 0, "status": "abstain", "reason": "Evidence is not confirmed."}
    known = max(dt(event["published_at"]), dt(event["observed_at"]), dt(event.get("received_at", event["observed_at"])))
    if known > at:
        return {**result, "reason": "Evidence was not available at this decision time."}
    # Re-importing an old event cannot refresh its publication or measurement time.
    freshness_at = dt(event["event_at"]) if kind in {"revenue", "miner"} and event.get("event_at") else dt(event["published_at"])
    if at - freshness_at > timedelta(hours=TTL[kind]):
        return {**result, "status": "stale", "reason": "Source event or measurement is outside its freshness window."}
    if not event.get("confirmed"):
        return result
    score = 0
    if kind == "unlock":
        hours = (dt(event["event_at"]) - at).total_seconds() / 3600
        if not -24 <= hours <= 168:
            return {**result, "reason": "Unlock is outside the one-week event window."}
        score = -min(100, m["unlock_pct_float"] * 12 + m["unlock_to_daily_volume"] * 15)
        reason = f"Unlock equals {m['unlock_pct_float']:g}% of float and {m['unlock_to_daily_volume']:g}× daily volume. Sale pressure is a hypothesis."
    elif kind == "revenue":
        prior = m["previous_7d_usd"]
        if prior <= 0:
            return {**result, "reason": "A positive preceding seven-day baseline is required."}
        growth = m["recent_7d_usd"] / prior - 1
        score = max(-100, min(100, growth * 200))
        reason = f"Completed weekly protocol revenue changed {growth*100:+.1f}%. Revenue is not necessarily token-holder income."
    elif kind == "regulation":
        if not official(event["source_url"], ["sec.gov", "cftc.gov", "fca.org.uk", "esma.europa.eu", "consilium.europa.eu"]):
            return {**result, "reason": "Headline requires an allowlisted official regulator source."}
        text = event["headline"].lower()
        if re.search(r"\b(not|no|denies|rumou?r|may|might|could|propos\w*|consult\w*|delay\w*)\b", text):
            return {**result, "reason": "Tentative, negated or ambiguous headline; manual interpretation required."}
        positive = bool(re.search(r"\b(approv\w*|authoriz\w*|licens\w*)\b", text))
        negative = bool(re.search(r"\b(sues|charges|fraud|ban\w*|reject\w*|penalt\w*|enforcement)\b", text))
        score = 45 if positive and not negative else -60 if negative and not positive else 0
        reason = "Keyword NLP baseline only; headline meaning and affected asset require review."
    elif kind == "listing":
        if not official(event["source_url"], ["coinbase.com", "kraken.com", "binance.com"]):
            return {**result, "reason": "Public listing evidence requires an official exchange source."}
        score = {"roadmap": 15, "announced": 40, "trading": 30, "observed_pair": 0}[m["stage"]]
        reason = {"roadmap": "Public roadmap inclusion does not guarantee a listing.",
                  "announced": "Public listing announcement; event may already be priced in.",
                  "trading": "Public trading confirmation, not an early or private signal.",
                  "observed_pair": "First observed in the product catalog; not proof of a new listing."}[m["stage"]]
    else:
        multiple = m["outflow_multiple"]
        score = -min(100, max(0, (multiple - 1) * 50))
        reason = f"Miner outflows are {multiple:g}× baseline. Transfers alone do not prove exchange sales."
    return {**result, "score": round(score, 2), "status": "graded", "reason": reason}


def evaluate(events, at=None):
    """One latest observation per asset/strategy: duplicate articles cannot stack votes."""
    at = at or now()
    graded = [grade(e, at) for e in events]
    latest = {}
    for e, g in zip(events, graded):
        if g["status"] != "graded":
            continue
        key = (e["asset"], e["kind"])
        if key not in latest or dt(e["observed_at"]) > dt(latest[key][0]["observed_at"]):
            latest[key] = (e, g)
    decisions = []
    for asset in sorted({e["asset"] for e in events}):
        rows = [pair[1] for key, pair in latest.items() if key[0] == asset]
        support = [g for g in rows if g["score"] >= 25]
        veto = any(g["score"] <= -40 for g in rows)
        strength = sum(g["score"] for g in rows)
        eligible = len(support) >= 2 and strength >= 80 and not veto
        action = "paper_candidate" if eligible else "avoid" if veto else "watch"
        decisions.append({"asset": asset, "action": action, "score": round(strength, 2),
                          "supporting_strategies": len(support), "veto": veto,
                          "evidence": rows, "reason": "Two strategy types, score >=80 and no strong negative veto required; this is an unvalidated hypothesis."})
    return {"grades": graded, "decisions": decisions, "heuristic_not_probability": True}
