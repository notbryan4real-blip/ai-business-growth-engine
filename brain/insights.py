"""Local context retrieval and measured council health; no model or network calls."""
from __future__ import annotations

from datetime import datetime, timedelta
import json
import re


STOP_WORDS = {"the", "and", "for", "with", "from", "that", "this", "what", "your", "you", "are", "our", "review"}


def select_memory(memory, agenda, timestamp, limit=30, max_chars=14000):
    """Rank saved owner records, retaining provenance within a serialized budget.

    Due commitments come first, then keyword overlap, then preferences/goals.
    Recency breaks ties. This is transparent keyword retrieval, not embeddings.
    """
    terms = set(re.findall(r"\w{3,}", agenda.casefold())) - STOP_WORDS

    def rank(pair):
        index, item = pair
        due = datetime.fromisoformat(item["due_at"]) if item.get("due_at") else None
        urgent = bool(due and due <= timestamp + timedelta(days=2))
        words = set(re.findall(r"\w{3,}", item["text"].casefold()))
        return (urgent, len(terms & words), item["kind"] in {"preference", "goal"}, index)

    selected = []
    for _, item in sorted(enumerate(memory), key=rank, reverse=True):
        if len(selected) >= limit:
            break
        if len(json.dumps(selected + [item], ensure_ascii=False)) <= max_chars:
            selected.append(item)
    return selected


def run_metrics(meetings):
    """Count recorded outcomes; completion is not proof of business success."""
    metrics = {}
    for mode in ("rules", "ai"):
        rows = [m for m in meetings if m.get("mode") == mode]
        counts = {status: sum(m.get("status") == status for m in rows)
                  for status in ("queued", "running", "completed", "failed", "cancelled", "interrupted")}
        terminal = sum(counts[s] for s in ("completed", "failed", "cancelled", "interrupted"))
        durations = []
        for meeting in rows:
            if meeting.get("status") != "completed" or not meeting.get("created_at") or not meeting.get("completed_at"):
                continue
            try:
                elapsed = (datetime.fromisoformat(meeting["completed_at"]) -
                           datetime.fromisoformat(meeting["created_at"])).total_seconds()
                if elapsed >= 0:
                    durations.append(elapsed)
            except (TypeError, ValueError):
                continue  # Legacy records with no valid timing are not zero-duration runs.
        metrics[mode] = {
            **counts, "total": len(rows), "terminal": terminal,
            "completion_rate": round(counts["completed"] / terminal * 100, 1) if terminal else None,
            "model_calls_attempted": sum(m.get("model_calls", 0) for m in rows),
            "mean_completed_seconds": round(sum(durations) / len(durations), 2) if durations else None,
            "timed_completed_runs": len(durations),
        }
    return {"retained_runs": len(meetings), "by_mode": metrics,
            "provider_cost_usd": None, "tool_call_accuracy": None}
