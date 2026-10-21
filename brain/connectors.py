"""Read-only Composio bridge. Account connections in ChatGPT stay separate.

Only these fixed read tools are callable; model output never selects a tool or
receives credentials. No generic execution/proxy endpoint is exposed to clients.
"""
from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from datetime import timedelta

from brain.council import Observation, now, stamp


READ_TOOLS = {
    "gmail": {"GMAIL_FETCH_EMAILS"},
    "instagram": {"INSTAGRAM_GET_USER_INFO", "INSTAGRAM_GET_USER_INSIGHTS"},
}


def configured_sources():
    key = bool(os.getenv("COMPOSIO_API_KEY"))
    return {source: key and bool(os.getenv("BRAIN_" + source.upper() + "_ACCOUNT_ID")) for source in READ_TOOLS}


def execute(source, slug, arguments):
    if slug not in READ_TOOLS.get(source, set()):
        raise ValueError("Only allowlisted read tools are available to the brain.")
    key = os.getenv("COMPOSIO_API_KEY")
    account = os.getenv("BRAIN_" + source.upper() + "_ACCOUNT_ID", "")
    if not key or not re.fullmatch(r"[A-Za-z0-9_-]{3,200}", account):
        raise ValueError("Server-side connector is not configured.")
    request = urllib.request.Request("https://backend.composio.dev/api/v3/tools/execute/" + slug,
        data=json.dumps({"connected_account_id": account, "version": "latest", "arguments": arguments}).encode(),
        headers={"Content-Type": "application/json", "x-api-key": key}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.loads(response.read(1_000_001))
        if not data.get("successful"):
            raise ValueError("Connector read failed.")
        if not isinstance(data.get("data"), dict):
            raise ValueError("Connector returned an invalid result.")
        return data["data"]
    except (urllib.error.URLError, TimeoutError, ValueError) as exc:
        # Never include provider response bodies, URLs, headers or tokens in logs.
        raise RuntimeError("Connector read failed. Check its server-side account authorization.") from None


def gmail_observation():
    messages, token, seen = [], None, set()
    for _ in range(5):
        arguments = {"user_id": "me", "query": "in:inbox newer_than:2d", "max_results": 100,
                     "include_payload": False, "verbose": False}
        if token:
            arguments["page_token"] = token
        data = execute("gmail", "GMAIL_FETCH_EMAILS", arguments)
        for m in data.get("messages") or []:
            if not isinstance(m, dict):
                continue
            mid = m.get("messageId") or m.get("id")
            if not isinstance(mid, str) or mid in seen:
                continue
            seen.add(mid)
            labels = m.get("labelIds") or m.get("label_ids") or []
            messages.append({"id": mid, "subject": str(m.get("subject") or "(no subject)")[:300],
                             "sender": str(m.get("sender") or m.get("from") or "Unknown")[:200],
                             "received_at": str(m.get("messageTimestamp") or m.get("internalDate") or "")[:80],
                             "important": "IMPORTANT" in labels, "unread": "UNREAD" in labels})
        next_token = data.get("nextPageToken")
        if not next_token:
            token = None
            break
        if next_token == token:
            raise RuntimeError("Repeated inbox pagination cursor; previous evidence retained.")
        token = next_token
    # This is a bounded inbox review, explicitly label any pagination truncation.
    messages.sort(key=lambda m: (m["important"], m["received_at"]), reverse=True)
    timestamp = now()
    sample = messages[:20]
    return Observation(source="gmail", reference="gmail-" + timestamp.strftime("%Y%m%d%H%M%S%f"), observed_at=timestamp,
        summary=f"Read {len(messages)} inbox messages from the last two days; {sum(m['important'] for m in messages)} marked important by Gmail. "
                + ("Review is partial; more pages remain." if token else "Pagination completed.") + " No messages changed.",
        details={"messages": sample, "message_count": len(messages), "complete": not bool(token), "sample_size": len(sample)})


def instagram_observation():
    profile = execute("instagram", "INSTAGRAM_GET_USER_INFO", {"ig_user_id": "me", "fields": "username,name,followers_count,media_count"})
    timestamp = now()
    insights = execute("instagram", "INSTAGRAM_GET_USER_INSIGHTS", {
        "metric": ["views", "reach", "accounts_engaged", "total_interactions", "profile_views", "shares", "saves"],
        "period": "day", "metric_type": "total_value", "since": int((timestamp - timedelta(days=7)).timestamp()), "until": int(timestamp.timestamp())})
    metrics = {}
    for metric in insights.get("data") or []:
        if isinstance(metric, dict) and isinstance(metric.get("total_value"), dict):
            metrics[metric["name"]] = metric["total_value"].get("value")
    return Observation(source="instagram", reference="instagram-" + timestamp.strftime("%Y%m%d%H%M%S%f"), observed_at=timestamp,
        summary="Instagram account @" + str(profile.get("username", "unknown")) + ": " + str(profile.get("followers_count", "unknown")) + " followers. Returned insights cover the requested seven-day window and may lag.",
        details={"profile": {k: profile.get(k) for k in ("username", "name", "followers_count", "media_count")}, "metrics": metrics, "window_days": 7})


def sync_sources(brain, force=True):
    configured = configured_sources()
    state = brain.transact(lambda s: s["connector_runs"])
    results = {}
    for source, enabled in configured.items():
        if not enabled:
            results[source] = {"status": "not_configured"}
            continue
        last = state.get(source, {}).get("at")
        if not force and last:
            from datetime import datetime
            if now() - datetime.fromisoformat(last) < timedelta(hours=1):
                continue
        try:
            observation = gmail_observation() if source == "gmail" else instagram_observation()
            item = brain.ingest(observation, "server_api")
            result = {"status": "synced", "at": stamp(), "observation_id": item["id"]}
        except Exception:
            result = {"status": "failed", "at": stamp(), "error": "Read failed; previous evidence retained. Check server credentials and account authorization."}
        brain.transact(lambda s: s["connector_runs"].update({source: result}))
        results[source] = result
    return {"sources": results, "external_writes": []}
