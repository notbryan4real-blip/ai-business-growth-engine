"""Consent-based local personal intelligence model.

Only caller-provided, opt-in events are processed. No covert collection,
network access, external action, or automatic identity inference.
"""
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import sqrt
from typing import Optional


@dataclass(frozen=True)
class Activity:
    category: str
    occurred_at: datetime
    source: str = "user"
    consented: bool = False


@dataclass(frozen=True)
class Prediction:
    category: str
    confidence: float
    evidence_count: int


@dataclass
class PersonalIntelligence:
    enabled: bool = False
    events: list[Activity] = field(default_factory=list)
    feedback: dict[str, list[bool]] = field(default_factory=dict)
    max_events: int = 500

    def observe(self, event: Activity) -> bool:
        if not self.enabled or not event.consented:
            return False
        if event.occurred_at.tzinfo is None:
            raise ValueError("Timestamp must include timezone")
        if not event.category or len(event.category) > 80:
            raise ValueError("Invalid category")
        if event.source not in {"user", "authorized_app"}:
            raise ValueError("Source not authorized")
        self.events.append(event)
        self.events = self.events[-self.max_events:]
        return True

    def predict(self, at: Optional[datetime] = None) -> Optional[Prediction]:
        if not self.enabled or len(self.events) < 5:
            return None
        now = at or datetime.now(timezone.utc)
        if now.tzinfo is None:
            raise ValueError("Timestamp must include timezone")
        # Use recent, preceding events only to prevent future-data leakage.
        recent = [e for e in self.events if 0 <= (now - e.occurred_at).total_seconds() <= 30 * 86400]
        if len(recent) < 5:
            return None
        counts = Counter(e.category for e in recent)
        category, count = counts.most_common(1)[0]
        # Conservative, sample-size-aware confidence heuristic, not a calibrated probability.
        base = count / len(recent)
        confidence = round(base * min(1.0, sqrt(len(recent) / 30)), 3)
        return Prediction(category, confidence, count)

    def record_feedback(self, category: str, correct: bool) -> None:
        if not self.enabled:
            return
        self.feedback.setdefault(category, []).append(bool(correct))
        self.feedback[category] = self.feedback[category][-100:]

    def clear(self) -> None:
        self.events.clear()
        self.feedback.clear()

    def disable(self, erase: bool = False) -> None:
        self.enabled = False
        if erase:
            self.clear()
