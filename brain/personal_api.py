"""Authenticated, opt-in personal pattern API. Local state is not durable on free hosting."""
from datetime import datetime, timezone
from threading import RLock
from fastapi import APIRouter, Header
from pydantic import BaseModel, Field
from brain.personal_intelligence import Activity, PersonalIntelligence


class ActivityInput(BaseModel):
    category: str = Field(min_length=1, max_length=80)


class FeedbackInput(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    correct: bool


class SettingsInput(BaseModel):
    enabled: bool


def router(require_token):
    api = APIRouter(prefix="/api/personal", tags=["personal"])
    lock = RLock()
    state = PersonalIntelligence()

    @api.get("/status")
    def status(authorization: str | None = Header(default=None)):
        require_token(authorization)
        with lock:
            prediction = state.predict()
            return {
                "enabled": state.enabled,
                "event_count": len(state.events),
                "prediction": None if prediction is None else {
                    "category": prediction.category,
                    "heuristic_score": prediction.confidence,
                    "evidence_count": prediction.evidence_count,
                },
                "feedback_count": sum(map(len, state.feedback.values())),
                "storage": "process_memory_only",
                "notice": "No automatic collection. Predictions are heuristic, not calibrated probabilities.",
            }

    @api.put("/settings")
    def settings(payload: SettingsInput, authorization: str | None = Header(default=None)):
        require_token(authorization)
        with lock:
            state.enabled = payload.enabled
            return {"enabled": state.enabled}

    @api.post("/observe")
    def observe(payload: ActivityInput, authorization: str | None = Header(default=None)):
        require_token(authorization)
        with lock:
            accepted = state.observe(Activity(category=payload.category,
                occurred_at=datetime.now(timezone.utc), source="user", consented=True))
            return {"accepted": accepted, "event_count": len(state.events)}

    @api.post("/feedback")
    def feedback(payload: FeedbackInput, authorization: str | None = Header(default=None)):
        require_token(authorization)
        with lock:
            state.record_feedback(payload.category, payload.correct)
            return {"recorded": state.enabled}

    @api.delete("/data")
    def delete_data(authorization: str | None = Header(default=None)):
        require_token(authorization)
        with lock:
            state.disable(erase=True)
            return {"erased": True, "enabled": False}

    return api
