from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def now():
    return datetime.now(timezone.utc)


def iso(at=None):
    return (at or now()).isoformat()


def dt(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


Kind = Literal["unlock", "revenue", "regulation", "listing", "miner"]


class Evidence(Strict):
    reference: str = Field(min_length=3, max_length=160)
    kind: Kind
    asset: str = Field(pattern=r"^[A-Z0-9]{2,12}$")
    source_url: str = Field(max_length=1000)
    published_at: datetime
    observed_at: datetime
    event_at: datetime | None = None
    headline: str = Field(default="", max_length=1000)
    metrics: dict[str, float | str] = Field(default_factory=dict)
    confirmed: bool = False

    @field_validator("source_url")
    @classmethod
    def https_source(cls, value):
        u = urlsplit(value)
        if u.scheme != "https" or not u.hostname or u.username or u.password or u.query or u.fragment:
            raise ValueError("Use a public HTTPS evidence URL without credentials, query parameters or fragments.")
        return value

    @field_validator("published_at", "observed_at", "event_at")
    @classmethod
    def aware(cls, value):
        if value and value.tzinfo is None:
            raise ValueError("Evidence timestamps require a timezone.")
        return value.astimezone(timezone.utc) if value else value

    @model_validator(mode="after")
    def valid(self):
        if self.published_at > self.observed_at or self.observed_at > now():
            raise ValueError("Require published_at <= observed_at <= current time.")
        required = {"unlock": {"unlock_pct_float", "unlock_to_daily_volume"},
                    "revenue": {"recent_7d_usd", "previous_7d_usd"},
                    "miner": {"outflow_multiple"}, "listing": {"stage"}, "regulation": set()}[self.kind]
        if set(self.metrics) != required:
            raise ValueError("Required metrics for " + self.kind + ": " + ", ".join(sorted(required)))
        for key, value in self.metrics.items():
            if key == "stage":
                if value not in {"roadmap", "announced", "trading", "observed_pair"}:
                    raise ValueError("Unsupported public listing stage.")
            elif not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or not 0 <= value <= 1e15:
                raise ValueError("Metrics must be finite, nonnegative numbers.")
        if self.kind == "unlock" and (self.event_at is None or self.metrics["unlock_pct_float"] > 100):
            raise ValueError("Unlocks require event_at and a circulating-supply percentage from 0 to 100.")
        if self.kind == "revenue" and (self.event_at is None or self.event_at > self.observed_at):
            raise ValueError("Revenue requires a completed measurement period in event_at.")
        if self.kind == "regulation" and len(self.headline.strip()) < 10:
            raise ValueError("Include the actual regulation headline.")
        return self


class ImportEvidence(Strict):
    events: list[Evidence] = Field(min_length=1, max_length=100)


class Settings(Strict):
    automatic_paper: bool = False
    paused: bool = False
    initial_cash: float = Field(default=300, ge=10, le=100000)
    position_cap_pct: float = Field(default=10, ge=1, le=20)
    exposure_cap_pct: float = Field(default=30, ge=1, le=50)
    risk_per_trade_pct: float = Field(default=.5, ge=.1, le=1)
    daily_loss_pct: float = Field(default=2, ge=.5, le=5)
    max_drawdown_pct: float = Field(default=5, ge=1, le=15)
    stop_loss_pct: float = Field(default=2, ge=.5, le=10)
    take_profit_pct: float = Field(default=3, ge=1, le=20)
    max_hold_hours: int = Field(default=6, ge=1, le=48)
    fee_bps: float = Field(default=60, ge=0, le=200)
    slippage_bps: float = Field(default=10, ge=0, le=200)
    daily_board_call_limit: int = Field(default=2, ge=0, le=24)


class RunRequest(Strict):
    request_id: str = Field(min_length=8, max_length=120)
    board: Literal["rules", "ai", "full_ai"] = "rules"
    paper_execute: bool = True


class Candle(Strict):
    open_at: datetime
    close_at: datetime
    open: float = Field(gt=0)
    high: float = Field(gt=0)
    low: float = Field(gt=0)
    close: float = Field(gt=0)

    @model_validator(mode="after")
    def valid(self):
        if not self.open_at.tzinfo or not self.close_at.tzinfo or self.open_at >= self.close_at or self.close_at > now():
            raise ValueError("Only completed candles with ordered timezone-aware timestamps are allowed.")
        if self.high < max(self.open, self.close, self.low) or self.low > min(self.open, self.close, self.high):
            raise ValueError("Invalid candle price range.")
        return self


class Replay(Strict):
    asset: str = Field(pattern=r"^[A-Z0-9]{2,12}$")
    candles: list[Candle] = Field(min_length=30, max_length=3000)
    events: list[Evidence] = Field(min_length=1, max_length=500)
    settings: Settings = Field(default_factory=Settings)

    @model_validator(mode="after")
    def ordered(self):
        if any(a.close_at > b.open_at for a, b in zip(self.candles, self.candles[1:])):
            raise ValueError("Candles must be ordered, unique and non-overlapping.")
        if any(e.asset != self.asset for e in self.events):
            raise ValueError("Every event must match the replay asset.")
        return self
