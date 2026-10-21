from datetime import datetime, timedelta, timezone
import json
import threading
import time

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError

from agents import runtime
from brain.council import Brain, Meeting, Memory, Observation, Settings, hierarchy, now, router
from brain import connectors


@pytest.fixture
def brain(tmp_path):
    return Brain(tmp_path / "brain.sqlite3")


def observation(source="instagram", age=0, reference="reference-001", **kw):
    return Observation(source=source, reference=reference, observed_at=now()-timedelta(hours=age),
                       summary="Verified account observation", **kw)


def result(summary="Evidence reviewed", actions=None):
    return {"summary": summary, "findings": ["Supplied data only"], "risks": [],
            "next_actions": actions or ["Choose the next content experiment"], "evidence_gaps": [], "confidence": "low"}


def wait(brain, meeting_id):
    deadline = time.monotonic()+3
    while time.monotonic() < deadline:
        meeting = brain.meeting(meeting_id)
        if meeting["status"] not in {"queued", "running"}:
            return meeting
        time.sleep(.01)
    raise AssertionError("Council did not finish")


def test_hierarchy_is_acyclic_and_qa_reports_directly_to_owner():
    rows = {a["id"]: a for a in hierarchy()}
    assert len(rows) == 25
    assert rows["qa"]["reports_to"] == "owner"
    for row in rows.values():
        seen = set()
        while row["reports_to"]:
            assert row["id"] not in seen
            seen.add(row["id"])
            row = rows[row["reports_to"]]
        assert row["id"] == "owner"


def test_observations_and_memory_survive_restart_and_reject_conflicting_evidence(brain):
    item = observation()
    first = brain.ingest(item)
    assert brain.ingest(item)["id"] == first["id"]
    with pytest.raises(HTTPException) as conflict:
        brain.ingest(item.model_copy(update={"summary":"Changed"}))
    assert conflict.value.status_code == 409
    memory = Memory(kind="goal", text="Build reliable systems", source="Owner instruction")
    brain.remember(memory)
    brain.remember(memory)
    restored = Brain(brain.path).overview()
    assert len(restored["observations"]) == len(restored["memory"]) == 1
    assert restored["memory"][0]["verified_by"] == "owner"


def test_future_or_naive_evidence_and_unknown_zones_are_rejected():
    for timestamp in [datetime(2026, 1, 1), now()+timedelta(days=1)]:
        with pytest.raises(ValidationError):
            Observation(source="owner", reference="test-ref", observed_at=timestamp, summary="Observed")
    with pytest.raises(ValidationError):
        Settings(timezone="Unknown/Zone")
    with pytest.raises(ValidationError):
        observation(details={"oversized":"a"*12001})


def test_rules_meeting_is_honest_idempotent_and_excludes_stale_evidence(brain, monkeypatch):
    monkeypatch.setattr(runtime, "_call_anthropic", lambda *a: pytest.fail("Rules must not call a model"))
    brain.ingest(observation("gmail"))
    brain.ingest(observation("instagram", age=30))
    brain.remember(Memory(kind="commitment", text="Review project delivery", source="Owner", due_at=now()+timedelta(hours=4)))
    request = Meeting(request_id="meeting-rule-001")
    first = brain.start(request)
    assert brain.start(request)["id"] == first["id"]
    meeting = brain.meeting(first["id"])
    assert meeting["execution_mode"] == "deterministic_planning"
    assert meeting["model_calls"] == 0 and meeting["external_actions"] == []
    assert meeting["messages"][0]["from"] == "system"
    assert "instagram" in meeting["missing_sources"]
    state = brain.overview()
    assert {t["owner"] for t in state["tasks"]} == {"inbox", "calendar"}
    assert all(d["action"] == "prioritize_internal_tasks" for d in state["decisions"])
    second = brain.start(Meeting(request_id="meeting-rule-002"))
    assert second["id"] != first["id"] and len(brain.overview()["tasks"]) == 2
    with pytest.raises(HTTPException):
        brain.start(request.model_copy(update={"agenda":"Different work"}))


def test_morning_runs_once_on_local_date_through_dst_and_respects_pause(brain):
    # After the US fall-back, 08:00 Eastern is 13:00 UTC.
    early = datetime(2026, 11, 1, 12, 59, tzinfo=timezone.utc)
    due = datetime(2026, 11, 1, 13, 1, tzinfo=timezone.utc)
    assert brain.tick(early)["status"] == "not_due"
    meeting = brain.tick(due)
    assert brain.tick(due+timedelta(hours=2))["id"] == meeting["id"]
    assert meeting["request_id"] == "morning-2026-11-01"
    brain.transact(lambda s:s["settings"].update(enabled=False))
    assert brain.tick(due+timedelta(days=1))["status"] == "paused"


def test_ai_reports_handoff_to_qa_and_chief_without_external_execution(brain, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "not-a-live-key")
    calls = []
    for source in ("gmail", "instagram", "business", "calendar"):
        brain.ingest(observation(source))
    def provider(agent, evidence, prior):
        calls.append((agent["id"], evidence, json.loads(json.dumps(prior))))
        return result(agent["id"], ["Send a message to a customer"]), "test-provider"
    monkeypatch.setattr(runtime, "_call_anthropic", provider)
    request = Meeting(request_id="meeting-ai-001", mode="ai")
    summary = brain.start(request)
    meeting = wait(brain, summary["id"])
    assert [c[0] for c in calls] == ["inbox", "social", "project", "calendar", "qa", "orchestrator"]
    assert {r["agent_id"] for r in calls[-1][2]} == {"inbox", "social", "project", "calendar", "qa"}
    assert "qa" not in {r["agent_id"] for r in calls[-2][2]}
    assert meeting["status"] == "completed" and meeting["model_calls"] == 6
    assert [m["sequence"] for m in meeting["messages"]] == list(range(1, 13))
    assert meeting["external_actions"] == []
    assert all(d["status"] == "proposed" for d in brain.overview()["decisions"])
    assert brain.start(request)["id"] == meeting["id"] and len(calls) == 6
    assert not brain.overview()["memory"]  # AI recommendations never become owner facts.


def test_failed_meeting_preserves_reports_and_budget_without_auto_retry(brain, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "fake-key")
    def provider(agent, *args):
        if agent["id"] == "qa":
            raise RuntimeError("Provider credit unavailable; secret-provider-response")
        return result(), "test"
    monkeypatch.setattr(runtime, "_call_anthropic", provider)
    request = Meeting(request_id="meeting-ai-fail", mode="ai")
    meeting = wait(brain, brain.start(request)["id"])
    assert meeting["status"] == "failed" and meeting["model_calls"] == 2
    assert len([m for m in meeting["messages"] if m["type"] == "agent_report"]) == 1
    assert "secret-provider-response" not in json.dumps(meeting)
    before = brain.overview()["model_calls_reserved_today"]
    assert brain.start(request)["id"] == meeting["id"]
    assert brain.overview()["model_calls_reserved_today"] == before
    brain.transact(lambda s:s["settings"].update(daily_model_call_limit=before))
    with pytest.raises(HTTPException):
        brain.start(Meeting(request_id="meeting-over-budget", mode="ai"))


def test_cancel_stops_next_call_and_shared_slot_blocks_other_paid_work(brain, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "fake-key")
    entered, release = threading.Event(), threading.Event()
    calls = []
    def provider(agent, *args):
        calls.append(agent["id"])
        entered.set()
        assert release.wait(3)
        return result(), "test"
    monkeypatch.setattr(runtime, "_call_anthropic", provider)
    meeting = brain.start(Meeting(request_id="cancel-meeting-001", mode="ai"))
    try:
        assert entered.wait(1)
        assert not brain.slot.acquire(blocking=False)
        with pytest.raises(HTTPException) as exc:
            brain.start(Meeting(request_id="second-meeting-001", mode="ai"))
        assert exc.value.status_code == 409
        brain.update_meeting(meeting["id"], lambda m,s:m.update(cancel_requested=True))
    finally:
        release.set()
    assert wait(brain, meeting["id"])["status"] == "cancelled"
    assert calls == ["personal"]


def test_recovery_does_not_replay_interrupted_paid_work(brain, monkeypatch):
    def seed(s):
        s["meetings"].append({"id":"interrupted", "status":"running", "model_calls":2, "messages":[{"text":"Partial report"}]})
    brain.transact(seed)
    monkeypatch.setattr(runtime, "_call_anthropic", lambda *a:pytest.fail("Recovery cannot replay paid calls"))
    brain.recover()
    meeting = brain.meeting("interrupted")
    assert meeting["status"] == "interrupted" and meeting["model_calls"] == 2
    assert meeting["messages"][0]["text"] == "Partial report"


def test_private_api_end_to_end_and_accepting_decisions_does_not_execute_them(brain, monkeypatch):
    from app import require_api_token
    monkeypatch.setenv("APP_API_TOKEN", "owner-test-token")
    api = FastAPI()
    api.include_router(router(brain, require_api_token))
    client = TestClient(api)
    h = {"Authorization":"Bearer owner-test-token"}
    for path in ("/overview", "/export", "/meetings/not-found"):
        assert client.get("/api/brain"+path).status_code == 401
    data = observation().model_dump(mode="json")
    assert client.post("/api/brain/observations",json=data).status_code == 401
    assert client.post("/api/brain/observations",json=data,headers=h).status_code == 200
    memory = Memory(kind="goal", text="Focus on the first customer", source="Owner").model_dump(mode="json")
    assert client.post("/api/brain/memory",json=memory,headers=h).status_code == 200
    response = client.post("/api/brain/meetings",json={"request_id":"api-meeting-001"},headers=h)
    assert response.status_code == 202
    mid = response.json()["id"]
    assert client.get("/api/brain/meetings/"+mid,headers=h).json()["model_calls"] == 0
    task_id = client.get("/api/brain/overview",headers=h).json()["tasks"][0]["id"]
    assert client.patch("/api/brain/tasks/"+task_id,json={"status":"done","note":"Reviewed source evidence"},headers=h).status_code == 200
    def proposal(s):
        s["decisions"].append({"id":"outbound-proposal", "status":"proposed", "action":"Send an email", "external_actions":[]})
    brain.transact(proposal)
    response = client.patch("/api/brain/decisions/outbound-proposal",json={"status":"accepted","note":"Owner accepted plan"},headers=h)
    assert response.json()["external_actions"] == []
    assert client.get("/api/brain/export",headers=h).json()["memory"]


def test_connector_allows_fixed_reads_only_and_does_not_disclose_configuration(monkeypatch):
    monkeypatch.setenv("COMPOSIO_API_KEY", "secret-project-key")
    monkeypatch.setenv("BRAIN_GMAIL_ACCOUNT_ID", "ca-test-account")
    assert connectors.configured_sources()["gmail"]
    with pytest.raises(ValueError):
        connectors.execute("gmail", "GMAIL_SEND_EMAIL", {})
    monkeypatch.setenv("BRAIN_GMAIL_ACCOUNT_ID", "https://attacker.example")
    with pytest.raises(ValueError):
        connectors.execute("gmail", "GMAIL_FETCH_EMAILS", {})


def test_failed_sync_retains_previous_evidence_and_uses_sanitized_error(brain, monkeypatch):
    old = brain.ingest(observation("gmail"))
    monkeypatch.setenv("COMPOSIO_API_KEY", "secret")
    monkeypatch.setenv("BRAIN_GMAIL_ACCOUNT_ID", "ca-account")
    def fail():
        raise RuntimeError("credential-bearing-response")
    monkeypatch.setattr(connectors, "gmail_observation", fail)
    result = connectors.sync_sources(brain)
    assert result["sources"]["gmail"]["status"] == "failed"
    assert "credential-bearing-response" not in json.dumps(result)
    assert brain.overview()["observations"][0]["id"] == old["id"]


def test_inbox_paginates_and_reads_metadata_without_modifying_messages(monkeypatch):
    calls = []
    def execute(source, slug, args):
        calls.append((source, slug, args))
        if len(calls) == 1:
            return {"messages":[{"messageId":"m1", "subject":None, "labelIds":["IMPORTANT"]}], "nextPageToken":"cursor-2"}
        return {"messages":[{"messageId":"m2", "subject":"Project update"}]}
    monkeypatch.setattr(connectors, "execute", execute)
    item = connectors.gmail_observation()
    assert item.details["complete"] and item.details["message_count"] == 2
    assert calls[-1][2]["page_token"] == "cursor-2"
    assert all(c[1] == "GMAIL_FETCH_EMAILS" and not c[2]["include_payload"] for c in calls)


def test_background_ai_requires_explicit_setting_and_uses_daily_request_once(brain, monkeypatch):
    monkeypatch.setenv("AI_API_KEY", "fake-key")
    calls=[]
    monkeypatch.setattr(runtime,"_call_anthropic",lambda agent,*args:(calls.append(agent["id"]) or result(),"test"))
    due = now().replace(hour=23, minute=0)
    first=brain.tick(due)
    assert first["mode"] == "rules" and not calls
    brain.transact(lambda s:s["settings"].update(automatic_ai=True))
    assert brain.tick(due)["id"] == first["id"]
    second=brain.tick(due+timedelta(days=1))
    assert wait(brain, second["id"])["mode"] == "ai" and calls


def test_unchanged_poll_does_not_duplicate_or_reopen_completed_task(brain):
    brain.ingest(observation())
    brain.start(Meeting(request_id="dedup-meeting-001"))
    task_id=brain.overview()["tasks"][0]["id"]
    brain.transact(lambda s:s["tasks"][0].update(status="done"))
    brain.ingest(observation(reference="second-poll"))
    brain.start(Meeting(request_id="dedup-meeting-002"))
    assert len(brain.overview()["tasks"]) == 1
    assert brain.overview()["tasks"][0]["status"] == "done"
    changed=observation(reference="third-poll").model_copy(update={"summary":"A meaningful account change"})
    brain.ingest(changed)
    brain.start(Meeting(request_id="dedup-meeting-003"))
    assert brain.overview()["tasks"][0]["id"] == task_id
    assert brain.overview()["tasks"][0]["status"] == "open"


def test_council_receives_owner_decisions_and_completed_work_without_promoting_claims(brain, monkeypatch):
    monkeypatch.setenv("AI_API_KEY","test-key")
    brain.transact(lambda s:s["decisions"].append({"action":"Focus on one project", "status":"accepted", "owner_note":"Confirmed by owner"}))
    brain.transact(lambda s:s["tasks"].append({"title":"Review inbox", "status":"done", "note":"Reviewed by owner"}))
    evidence=[]
    def provider(agent, data, prior):
        evidence.append(data)
        return result(),"test"
    monkeypatch.setattr(runtime,"_call_anthropic",provider)
    wait(brain,brain.start(Meeting(request_id="feedback-meeting-001",mode="ai"))["id"])
    assert evidence[0]["owner_decisions"][0]["owner_note"] == "Confirmed by owner"
    assert evidence[0]["previous_task_state"][0]["status"] == "done"
