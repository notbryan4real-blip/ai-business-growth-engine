"""Owner-controlled, checkpointed workflows over the existing council.

Only code-defined operations run. A model report is data, never a tool request.
Starting is explicit; reopening a mission never replays model calls.
"""
from __future__ import annotations

import copy
import uuid
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import Field, field_validator

from brain.council import Meeting, MeetingPreview, Strict, stamp


class MissionInput(Strict):
    request_id: str = Field(min_length=8, max_length=150)
    goal: str = Field(min_length=3, max_length=2000)
    mode: Literal["rules", "ai"] = "rules"

    @field_validator("goal")
    @classmethod
    def meaningful_goal(cls, value):
        value = value.strip()
        if len(value) < 3:
            raise ValueError("Describe the goal in at least three characters.")
        return value


class StartMission(Strict):
    plan_id: str = Field(min_length=32, max_length=32)
    approved_model_calls: int = Field(ge=0, le=6, strict=True)


class ReviewMission(Strict):
    outcome: Literal["useful", "needs_revision"]
    note: str = Field(min_length=3, max_length=1000)
    lesson: str = Field(default="", max_length=1500)

    @field_validator("note", "lesson")
    @classmethod
    def reviewed_text(cls, value, info):
        value = value.strip()
        if (info.field_name == "note" or value) and len(value) < 3:
            raise ValueError("Use at least three characters.")
        return value


OPERATIONS = [
    {"id": "retrieve_context", "name": "Check evidence and memory", "effect": "read_local", "model_calls": 0},
    {"id": "council", "name": "Run the selected council", "effect": "internal_planning", "model_calls": "approved_cap"},
    {"id": "owner_review", "name": "Pause for your review", "effect": "owner_gate", "model_calls": 0},
    {"id": "save_lesson", "name": "Save an optional reviewed lesson", "effect": "owner_memory", "model_calls": 0},
]


class Missions:
    def __init__(self, brain, portfolio=None):
        self.brain = brain
        self.portfolio = portfolio or (lambda: None)

    @staticmethod
    def find(state, mission_id):
        item = next((m for m in state.get("missions", []) if m["id"] == mission_id), None)
        if item is None:
            raise HTTPException(404, "Mission not found.")
        return item

    @staticmethod
    def meeting(state, mission):
        return next((m for m in state["meetings"] if m["request_id"] == "mission-" + mission["id"]), None)

    @staticmethod
    def event(mission, action):
        mission["events"].append({"at": stamp(), "action": action})
        mission["events"] = mission["events"][-40:]

    @staticmethod
    def result(meeting):
        if not meeting:
            return None
        reports = [m for m in meeting["messages"] if m["type"] == "agent_report"]
        chief = next((m["output"] for m in reversed(reports) if m["from"] == "orchestrator"), {})
        qa = next((m["output"] for m in reports if m["from"] == "qa"), {})
        return {"meeting_id": meeting["id"], "status": meeting["status"],
                "summary": meeting.get("summary", ""), "error": meeting.get("error"),
                "model_calls": meeting["model_calls"], "completed_at": meeting.get("completed_at"),
                "actions": chief.get("next_actions", [])[:3],
                "risks": (qa.get("risks", []) + chief.get("risks", []))[:12],
                "evidence_gaps": chief.get("evidence_gaps", meeting.get("missing_sources", [])),
                "task_ids": meeting.get("task_ids", []),
                "context": meeting.get("context_summary", meeting.get("memory_selection", {})),
                "external_actions": []}

    def view(self, state, mission, detail=True):
        meeting = self.meeting(state, mission)
        status = mission["status"]
        if mission.get("review"):
            status = "reviewed"
        elif mission.get("cancel_requested"):
            status = "stopping" if meeting and meeting["status"] in {"queued", "running"} else "cancelled"
        elif meeting:
            status = ("awaiting_review" if meeting["status"] == "completed" else
                      "running" if meeting["status"] in {"queued", "running"} else "interrupted")
        elif status == "started":
            status = "interrupted"
        value = {k: mission[k] for k in ("id", "goal", "mode", "created_at")}
        value.update(status=status, review=mission.get("review"))
        if detail:
            value.update(plan=mission["plan"], plan_id=mission["plan_id"], events=mission["events"],
                         result=mission.get("result") or self.result(meeting), error=mission.get("error"),
                         reports_available=bool(meeting), operations=copy.deepcopy(OPERATIONS), external_execution=False)
        return value

    def get(self, mission_id):
        return self.brain.transact(lambda s: self.view(s, self.find(s, mission_id)))

    def list(self):
        def read(s):
            rows = [self.view(s, m, False) for m in reversed(s.get("missions", []))]
            useful = sum(m.get("review", {}).get("outcome") == "useful" for m in rows if m.get("review"))
            reviewed = sum(bool(m.get("review")) for m in rows)
            return {"missions": rows, "metrics": {"total": len(rows), "reviewed": reviewed,
                    "owner_rated_useful": useful, "useful_percent": round(100 * useful / reviewed, 1) if reviewed else None},
                    "storage_notice": "Checkpoints use this server's storage. Export a private backup before a restart or deploy; permanent hosting storage is not configured by this feature."}
        return self.brain.transact(read)

    def plan(self, goal, mode):
        plan = self.brain.preview(MeetingPreview(mode=mode, agenda=goal), self.portfolio())
        # Keep an inspectable bounded preview; the meeting retains actual prompt context.
        plan["memory"] = [{k: m[k] for k in ("id", "kind", "text", "source")} for m in plan["memory"]]
        return plan

    def create(self, request):
        payload = request.model_dump()
        existing = self.brain.transact(lambda s: next((m for m in s.get("missions", []) if m["request"] == payload), None))
        if existing:
            return self.get(existing["id"])
        plan = self.plan(request.goal, request.mode)
        def save(s):
            rows = s.setdefault("missions", [])
            old = next((m for m in rows if m["request"]["request_id"] == request.request_id), None)
            if old:
                if old["request"] != payload:
                    raise HTTPException(409, "Mission request ID already used for another goal or mode.")
                return self.view(s, old)
            if len(rows) >= 60:
                raise HTTPException(409, "Mission history is full. Export it before starting a new workspace.")
            item = {"id": uuid.uuid4().hex, "goal": request.goal, "mode": request.mode, "request": payload,
                    "created_at": stamp(), "status": "awaiting_start", "plan": plan,
                    "plan_id": uuid.uuid4().hex, "events": []}
            self.event(item, "Plan saved; no model calls made")
            rows.append(item)
            return self.view(s, item)
        return self.brain.transact(save)

    def refresh(self, mission_id):
        item = self.get(mission_id)
        if item["status"] != "awaiting_start":
            raise HTTPException(409, "Only an unstarted mission can receive a new plan.")
        plan = self.plan(item["goal"], item["mode"])
        def save(s):
            mission = self.find(s, mission_id)
            if self.view(s, mission)["status"] != "awaiting_start":
                raise HTTPException(409, "This mission has already started.")
            mission.update(plan=plan, plan_id=uuid.uuid4().hex, error=None)
            self.event(mission, "Plan refreshed; no model calls made")
            return self.view(s, mission)
        return self.brain.transact(save)

    def start(self, mission_id, approval):
        def claim(s):
            mission = self.find(s, mission_id)
            if approval.plan_id != mission["plan_id"] or approval.approved_model_calls != mission["plan"]["model_calls_required"]:
                raise HTTPException(409, "The approved plan changed. Open the current plan before starting.")
            view = self.view(s, mission)
            if view["status"] in {"starting", "running", "awaiting_review"}:
                return mission, False
            if view["status"] != "awaiting_start":
                raise HTTPException(409, "This mission cannot restart. Review its record or create a new mission explicitly.")
            if not mission["plan"]["can_start"]:
                raise HTTPException(409, "Resolve the plan's blockers and refresh it before starting.")
            mission.update(status="starting", error=None)
            self.event(mission, "Owner approved the plan and model-call cap")
            return mission, True
        item, claimed = self.brain.transact(claim)
        if not claimed:
            return self.get(mission_id)
        def guard(s):
            mission = self.find(s, mission_id)
            if mission.get("cancel_requested") or mission["status"] != "starting":
                raise HTTPException(409, "Mission stopped before the council started.")
        try:
            portfolio = self.portfolio()
            if portfolio:
                self.brain.ingest(portfolio, "internal_state")
            meeting = self.brain.start(Meeting(request_id="mission-" + mission_id, mode=item["mode"],
                agenda=item["goal"], max_model_calls=approval.approved_model_calls or None), guard=guard)
        except Exception as error:
            def failed(s):
                mission = self.find(s, mission_id)
                if not self.meeting(s, mission) and not mission.get("cancel_requested"):
                    mission.update(status="awaiting_start", error="Council did not start. Refresh the plan before retrying.")
                    mission["plan"]["can_start"] = False
                self.event(mission, "Start stopped; no automatic retry")
            self.brain.transact(failed)
            if isinstance(error, HTTPException):
                raise
            raise HTTPException(503, "The council could not start. Inspect the saved mission before retrying.") from None
        def submitted(s):
            mission = self.find(s, mission_id)
            mission.update(status="started", meeting_id=meeting["id"])
            self.event(mission, "Council execution recorded")
            return self.view(s, mission)
        return self.brain.transact(submitted)

    def cancel(self, mission_id):
        def stop(s):
            mission = self.find(s, mission_id)
            if mission.get("review"):
                raise HTTPException(409, "This mission has already been reviewed.")
            if not mission.get("cancel_requested"):
                mission["cancel_requested"] = True
                self.event(mission, "Owner stopped the mission; no automatic replay")
            meeting = self.meeting(s, mission)
            if meeting and meeting["status"] in {"queued", "running"}:
                meeting["cancel_requested"] = True
            else:
                mission["result"] = self.result(meeting)
            return self.view(s, mission)
        return self.brain.transact(stop)

    def review(self, mission_id, request):
        payload = request.model_dump()
        def save(s):
            mission = self.find(s, mission_id)
            if mission.get("review"):
                if mission["review"]["input"] != payload:
                    raise HTTPException(409, "This review has already been recorded.")
                return self.view(s, mission)
            view = self.view(s, mission)
            if view["status"] not in {"awaiting_review", "interrupted"}:
                raise HTTPException(409, "Wait for the council to finish before reviewing its results.")
            if view["status"] == "interrupted" and request.outcome == "useful":
                raise HTTPException(409, "An interrupted mission must be marked as needing revision.")
            lesson_id = None
            if request.lesson:
                if len(s["memory"]) >= 150:
                    raise HTTPException(409, "Memory is full. Review without a lesson, or export your memory first.")
                lesson_id = "mission-lesson-" + mission_id
                s["memory"].append({"id": lesson_id, "kind": "procedure", "text": request.lesson,
                    "source": "Owner review of mission " + mission_id, "due_at": None,
                    "created_at": stamp(), "verified_by": "owner"})
            mission["review"] = {"input": payload, "outcome": request.outcome, "note": request.note,
                                 "at": stamp(), "lesson_id": lesson_id}
            mission["result"] = self.result(self.meeting(s, mission))
            self.event(mission, "Owner review saved" + (" with an owner-written lesson" if lesson_id else ""))
            return self.view(s, mission)
        return self.brain.transact(save)


def router(brain, authorize, portfolio):
    api = APIRouter(prefix="/missions")
    missions = Missions(brain, portfolio)

    @api.get("")
    def list_missions(authorization: str | None = Header(default=None)):
        authorize(authorization)
        return missions.list()

    @api.post("", status_code=201)
    def create(request: MissionInput, authorization: str | None = Header(default=None)):
        authorize(authorization)
        return missions.create(request)

    @api.get("/{mission_id}")
    def detail(mission_id: str, authorization: str | None = Header(default=None)):
        authorize(authorization)
        return missions.get(mission_id)

    @api.post("/{mission_id}/refresh")
    def refresh(mission_id: str, authorization: str | None = Header(default=None)):
        authorize(authorization)
        return missions.refresh(mission_id)

    @api.post("/{mission_id}/start", status_code=202)
    def start(mission_id: str, request: StartMission, authorization: str | None = Header(default=None)):
        authorize(authorization)
        return missions.start(mission_id, request)

    @api.post("/{mission_id}/cancel")
    def cancel(mission_id: str, authorization: str | None = Header(default=None)):
        authorize(authorization)
        return missions.cancel(mission_id)

    @api.post("/{mission_id}/review")
    def review(mission_id: str, request: ReviewMission, authorization: str | None = Header(default=None)):
        authorize(authorization)
        return missions.review(mission_id, request)

    return api
