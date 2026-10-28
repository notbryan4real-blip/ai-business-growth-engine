import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agents import runtime
from brain.council import Brain, Meeting, Memory, Observation, now, router
from brain.missions import MissionInput, Missions, ReviewMission, StartMission


@pytest.fixture
def workflow(tmp_path):
    brain = Brain(tmp_path / "brain.sqlite3")
    yield Missions(brain)
    brain.worker.shutdown(wait=True)


def create(workflow, mode="rules", request_id="mission-request-001"):
    return workflow.create(MissionInput(request_id=request_id, goal="Choose the next print shop delivery step", mode=mode))


def approve(mission):
    return StartMission(plan_id=mission["plan_id"], approved_model_calls=mission["plan"]["model_calls_required"])


def wait(workflow, mission_id):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        value = workflow.get(mission_id)
        if value["status"] not in {"starting", "running", "stopping"}:
            return value
        time.sleep(.01)
    raise AssertionError("Mission did not settle")


def output(agent="agent"):
    return {"summary": agent + " reviewed supplied evidence", "findings": [], "risks": ["Check the source"],
            "next_actions": ["Review a customer message before sending"], "evidence_gaps": [], "confidence": "low"}, "test-provider"


def test_plan_is_free_idempotent_and_does_not_import_preview_evidence(workflow, monkeypatch):
    monkeypatch.setattr(runtime, "_call_anthropic", lambda *args: pytest.fail("Planning spent a model call"))
    workflow.portfolio = lambda: Observation(source="business", reference="portfolio-plan", observed_at=now(), summary="Current tasks")
    mission = create(workflow)
    assert create(workflow)["id"] == mission["id"]
    assert mission["status"] == "awaiting_start"
    assert mission["plan"]["fresh_sources"] == ["business"]
    state = workflow.brain.transact(lambda s: s)
    assert state["observations"] == state["meetings"] == []
    assert state["budget"] == {}
    assert workflow.list()["metrics"]["useful_percent"] is None
    with pytest.raises(HTTPException) as conflict:
        workflow.create(MissionInput(request_id="mission-request-001", goal="Different goal"))
    assert conflict.value.status_code == 409


def test_rules_pause_for_review_and_only_owner_written_lesson_becomes_memory(workflow, monkeypatch):
    monkeypatch.setattr(runtime, "_call_anthropic", lambda *args: pytest.fail("Rules spent a model call"))
    mission = create(workflow)
    result = workflow.start(mission["id"], approve(mission))
    assert result["status"] == "awaiting_review"
    assert result["result"]["model_calls"] == 0
    assert workflow.brain.overview()["memory"] == []
    reopened = Missions(Brain(workflow.brain.path))
    assert reopened.get(mission["id"])["status"] == "awaiting_review"
    review = ReviewMission(outcome="useful", note="The source gap was correctly identified.", lesson="Confirm artwork before delivery.")
    saved = reopened.review(mission["id"], review)
    assert saved["status"] == "reviewed"
    assert reopened.review(mission["id"], review) == saved
    memory = reopened.brain.overview()["memory"]
    assert len(memory) == 1 and memory[0]["verified_by"] == "owner"
    assert memory[0]["kind"] == "procedure" and memory[0]["text"] == review.lesson
    assert reopened.list()["metrics"]["useful_percent"] == 100
    assert saved["external_execution"] is False
    with pytest.raises(HTTPException):
        reopened.review(mission["id"], review.model_copy(update={"note": "A different review"}))


def test_ai_uses_existing_council_and_review_does_not_approve_external_proposals(workflow, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-only")
    calls = []
    monkeypatch.setattr(runtime, "_call_anthropic", lambda agent, evidence, prior: calls.append(agent["id"]) or output(agent["id"]))
    mission = create(workflow, "ai")
    workflow.start(mission["id"], approve(mission))
    result = wait(workflow, mission["id"])
    assert calls == ["personal", "qa", "orchestrator"]
    assert result["status"] == "awaiting_review" and result["result"]["model_calls"] == 3
    assert result["result"]["risks"] and result["result"]["actions"]
    assert workflow.start(mission["id"], approve(mission))["status"] == "awaiting_review"
    assert len(calls) == 3
    workflow.review(mission["id"], ReviewMission(outcome="useful", note="Read and checked the draft."))
    state = workflow.brain.overview()
    assert state["model_calls_reserved_today"] == 3
    assert state["memory"] == []
    assert all(d["status"] == "proposed" and d["external_actions"] == [] for d in state["decisions"])


def test_refresh_invalidates_old_approval_and_rechecks_the_call_cap(workflow, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-only")
    mission = create(workflow, "ai")
    for source in ("gmail", "instagram"):
        workflow.brain.ingest(Observation(source=source, reference="source-" + source, observed_at=now(), summary="Observed update"))
    with pytest.raises(HTTPException) as error:
        workflow.start(mission["id"], approve(mission))
    assert error.value.status_code == 409
    assert workflow.brain.overview()["model_calls_reserved_today"] == 0
    assert not workflow.brain.overview()["meetings"]
    updated = workflow.refresh(mission["id"])
    assert updated["plan"]["model_calls_required"] == 4
    with pytest.raises(HTTPException):
        workflow.start(mission["id"], approve(mission))


def test_wrong_cap_and_blocked_provider_cannot_start(workflow, monkeypatch):
    monkeypatch.delenv("AI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    mission = create(workflow, "ai")
    assert not mission["plan"]["can_start"]
    for approval in [approve(mission), StartMission(plan_id=mission["plan_id"], approved_model_calls=6)]:
        with pytest.raises(HTTPException):
            workflow.start(mission["id"], approval)
    assert not workflow.brain.overview()["meetings"]


def test_budget_is_checked_again_at_start(workflow, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-only")
    mission = create(workflow, "ai")
    workflow.brain.transact(lambda s: s["settings"].update(daily_model_call_limit=0))
    with pytest.raises(HTTPException):
        workflow.start(mission["id"], approve(mission))
    assert not workflow.brain.overview()["meetings"]
    assert workflow.get(mission["id"])["status"] == "awaiting_start"


def test_simultaneous_start_posts_do_not_duplicate_model_work(workflow, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-only")
    calls = []
    monkeypatch.setattr(runtime, "_call_anthropic", lambda *args: calls.append(1) or output())
    mission = create(workflow, "ai")
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: workflow.start(mission["id"], approve(mission)), range(2)))
    assert {r["id"] for r in results} == {mission["id"]}
    wait(workflow, mission["id"])
    assert len(calls) == 3
    assert len(workflow.brain.overview()["meetings"]) == 1


def test_stop_before_start_and_cancel_during_claim_prevent_paid_work(workflow, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-only")
    monkeypatch.setattr(runtime, "_call_anthropic", lambda *args: pytest.fail("Cancelled mission spent a call"))
    mission = create(workflow, "ai")
    entered, release = threading.Event(), threading.Event()
    def portfolio():
        entered.set(); assert release.wait(3); return None
    workflow.portfolio = portfolio
    with ThreadPoolExecutor(max_workers=1) as pool:
        starting = pool.submit(workflow.start, mission["id"], approve(mission))
        assert entered.wait(2)
        assert workflow.cancel(mission["id"])["status"] == "cancelled"
        release.set()
        with pytest.raises(HTTPException):
            starting.result()
    with pytest.raises(HTTPException):
        workflow.start(mission["id"], approve(mission))
    assert not workflow.brain.overview()["meetings"]
    assert workflow.brain.overview()["model_calls_reserved_today"] == 0


def test_stop_during_call_keeps_partial_work_without_next_call(workflow, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-only")
    entered, release = threading.Event(), threading.Event()
    calls = []
    def provider(*args):
        calls.append(1); entered.set(); assert release.wait(3); return output()
    monkeypatch.setattr(runtime, "_call_anthropic", provider)
    mission = create(workflow, "ai")
    workflow.start(mission["id"], approve(mission))
    try:
        assert entered.wait(2)
        assert workflow.cancel(mission["id"])["status"] == "stopping"
    finally:
        release.set()
    assert wait(workflow, mission["id"])["status"] == "cancelled"
    assert len(calls) == 1


def test_restart_interrupts_queued_execution_and_never_replays_it(workflow, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-only")
    monkeypatch.setattr(workflow.brain.worker, "submit", lambda *args: None)
    mission = create(workflow, "ai")
    workflow.start(mission["id"], approve(mission))
    restored = Brain(workflow.brain.path)
    restored.recover()
    reopened = Missions(restored)
    assert reopened.get(mission["id"])["status"] == "interrupted"
    with pytest.raises(HTTPException):
        reopened.start(mission["id"], approve(mission))
    assert restored.overview()["model_calls_reserved_today"] == 3
    with pytest.raises(HTTPException):
        reopened.review(mission["id"], ReviewMission(outcome="useful", note="Cannot mark an unfinished result useful."))
    assert reopened.review(mission["id"], ReviewMission(outcome="needs_revision", note="Restarted before finishing."))["status"] == "reviewed"


def test_restart_between_claim_and_submission_is_reviewable_without_replay(workflow):
    mission = create(workflow)
    workflow.brain.transact(lambda s: s["missions"][0].update(status="starting"))
    workflow.brain.recover()
    assert workflow.get(mission["id"])["status"] == "interrupted"
    with pytest.raises(HTTPException):
        workflow.start(mission["id"], approve(mission))
    assert not workflow.brain.overview()["meetings"]


def test_provider_failure_retains_partial_reports_and_conservative_budget(workflow, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "test-only")
    calls = []
    def provider(*args):
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("Provider detail containing private information")
        return output()
    monkeypatch.setattr(runtime, "_call_anthropic", provider)
    mission = create(workflow, "ai")
    workflow.start(mission["id"], approve(mission))
    stopped = wait(workflow, mission["id"])
    assert stopped["status"] == "interrupted"
    assert stopped["result"]["model_calls"] == 2
    assert "private information" not in str(stopped)
    assert workflow.brain.overview()["model_calls_reserved_today"] == 3


def test_review_and_lesson_are_atomic_when_memory_is_full(workflow):
    mission = create(workflow); workflow.start(mission["id"], approve(mission))
    workflow.brain.transact(lambda s: s.update(memory=[{"id": str(i)} for i in range(150)]))
    with pytest.raises(HTTPException):
        workflow.review(mission["id"], ReviewMission(outcome="useful", note="Checked result", lesson="A checked lesson"))
    assert workflow.get(mission["id"])["status"] == "awaiting_review"
    saved = workflow.review(mission["id"], ReviewMission(outcome="useful", note="Checked result"))
    assert saved["status"] == "reviewed" and saved["review"]["lesson_id"] is None


def test_pending_reviews_pin_reports_and_reviewed_summary_survives_retention(workflow):
    mission = create(workflow); workflow.start(mission["id"], approve(mission))
    for i in range(121):
        workflow.brain.start(Meeting(request_id="retention-run-" + str(i)))
    assert workflow.get(mission["id"])["status"] == "awaiting_review"
    reviewed = workflow.review(mission["id"], ReviewMission(outcome="useful", note="Keep a summary of the result."))
    workflow.brain.start(Meeting(request_id="prune-reviewed-mission"))
    saved = workflow.get(mission["id"])
    assert saved["result"] == reviewed["result"]
    assert not saved["reports_available"]


def test_limits_do_not_discard_old_missions_or_duplicate_existing_requests(workflow):
    first = create(workflow)
    for i in range(59):
        create(workflow, request_id="mission-limit-" + str(i))
    assert create(workflow)["id"] == first["id"]
    with pytest.raises(HTTPException) as error:
        create(workflow, request_id="mission-over-limit")
    assert error.value.status_code == 409 and len(workflow.list()["missions"]) == 60


def test_old_database_without_missions_key_remains_compatible(workflow):
    workflow.brain.transact(lambda s: s.pop("missions", None))
    assert workflow.list()["missions"] == []
    workflow.brain.recover()
    assert create(workflow)["status"] == "awaiting_start"
    assert "missions" in workflow.brain.transact(lambda s: s)


def test_inputs_reject_arbitrary_tools_whitespace_and_noninteger_caps():
    for data in [{"goal": "   "}, {"goal": "Review work", "tools": ["send_email"]}]:
        with pytest.raises(ValidationError):
            MissionInput(request_id="bad-request-01", **data)
    for calls in [True, "3", 7, -1]:
        with pytest.raises(ValidationError):
            StartMission(plan_id="a" * 32, approved_model_calls=calls)


def test_every_mission_route_is_private_and_owner_flow_works(workflow):
    def auth(value):
        if value != "Bearer owner-test":
            raise HTTPException(401, "Unauthorized")
    api = FastAPI(); api.include_router(router(workflow.brain, auth))
    client = TestClient(api)
    for method, path, body in [
        ("GET", "/missions", None), ("GET", "/missions/missing", None),
        ("POST", "/missions", {"request_id": "api-mission-001", "goal": "Review delivery"}),
        ("POST", "/missions/missing/refresh", None), ("POST", "/missions/missing/cancel", None),
        ("POST", "/missions/missing/start", {"plan_id": "a" * 32, "approved_model_calls": 0}),
        ("POST", "/missions/missing/review", {"outcome": "useful", "note": "Checked result"}),
    ]:
        assert client.request(method, "/api/brain" + path, json=body).status_code == 401
    client.headers.update({"Authorization": "Bearer owner-test"})
    mission = client.post("/api/brain/missions", json={"request_id": "api-mission-001", "goal": "Review delivery"}).json()
    response = client.post("/api/brain/missions/" + mission["id"] + "/start", json=approve(mission).model_dump())
    assert response.status_code == 202 and response.json()["status"] == "awaiting_review"
    review = client.post("/api/brain/missions/" + mission["id"] + "/review", json={"outcome": "useful", "note": "Checked the evidence."})
    assert review.status_code == 200 and review.json()["status"] == "reviewed"
