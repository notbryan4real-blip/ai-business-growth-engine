import json
import threading
import time

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app as api
from agents import runtime


def output(summary):
    return {"summary": summary, "findings": [], "risks": [],
            "next_actions": [], "evidence_gaps": [], "confidence": "low"}


@pytest.fixture
def configured(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "DATA_PATH", tmp_path / "store.json")
    monkeypatch.setenv("APP_API_TOKEN", "test-token")
    monkeypatch.setenv("AI_API_KEY", "fake-key-not-used")
    return {"authorization": "Bearer test-token"}


def wait_for_job(run_id):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if api.RUN_SLOT.acquire(blocking=False):
            api.RUN_SLOT.release()
            return api.get_run(run_id, authorization="Bearer test-token")
        time.sleep(.01)
    raise AssertionError("Worker did not finish")


def test_live_events_are_actual_ordered_handoffs_and_qa_is_last(monkeypatch):
    calls, events = [], []
    def provider(agent, prospect, prior):
        calls.append((agent["id"], json.loads(json.dumps(prior))))
        return output(agent["id"]), "test-model"
    monkeypatch.setattr(runtime, "_call_anthropic", provider)
    result = runtime.run_specialists({"business_name": "Example"},
        ["qa", "sales", "qualification"], on_event=events.append)
    assert [c[0] for c in calls] == ["qualification", "sales", "qa"]
    assert events[2]["context"] == calls[1][1]
    assert events[2]["source_agent_id"] == "qualification"
    assert events[3]["output"] == output("sales")
    assert result["outreach_sent"] is False


def test_context_cost_is_bounded_and_reports_are_retained(monkeypatch):
    contexts = []
    def provider(agent, prospect, prior):
        contexts.append(prior)
        return {**output("s" * 3000), "findings": ["f" * 1000] * 10}, "test"
    monkeypatch.setattr(runtime, "_call_anthropic", provider)
    result = runtime.run_specialists({"business_name": "Example"})
    assert max(len(c) for c in contexts) == 4
    assert max(len(json.dumps(c)) for c in contexts) < 8000
    assert len(result["results"][0]["output"]["summary"]) == 3000
    assert len(result["results"]) == 19


def test_failed_job_preserves_completed_results_and_idempotency(configured, monkeypatch):
    calls = []
    def provider(agent, prospect, prior):
        calls.append(agent["id"])
        if agent["id"] == "sales":
            raise runtime.AgentRuntimeError("Provider credit exhausted")
        return output("Verified input only"), "test"
    monkeypatch.setattr(runtime, "_call_anthropic", provider)
    request = api.JobInput(prospect={"business_name":"Example"},
                           agent_ids=["qualification","sales"], request_id="request-0001")
    job = api.start_run(request, **configured)
    finished = wait_for_job(job["run_id"])
    assert finished["status"] == "failed"
    assert len(finished["results"]) == 1
    assert finished["error"] == "Provider credit exhausted"
    assert [e["sequence"] for e in finished["events"]] == [1,2,3,4]
    repeated = api.start_run(request, **configured)
    assert repeated["run_id"] == job["run_id"]
    assert calls == ["qualification","sales"]
    assert len(api.get_run(job["run_id"], after=3, **configured)["events"]) == 1
    with pytest.raises(HTTPException) as exc:
        api.get_run(job["run_id"], authorization=None)
    assert exc.value.status_code == 401


def test_stop_and_concurrent_start_do_not_create_more_paid_calls(configured, monkeypatch):
    started, release = threading.Event(), threading.Event()
    calls=[]
    def provider(agent, prospect, prior):
        calls.append(agent["id"]); started.set()
        assert release.wait(3)
        return output("done"), "test"
    monkeypatch.setattr(runtime, "_call_anthropic", provider)
    request=api.JobInput(prospect={"business_name":"Example"},
                         agent_ids=["qualification","sales"], request_id="request-0002")
    job=api.start_run(request, **configured)
    try:
        assert started.wait(1)
        with pytest.raises(HTTPException) as exc:
            api.start_run(request.model_copy(update={"request_id":"request-0003"}), **configured)
        assert exc.value.status_code == 409
        api.cancel_run(job["run_id"], **configured)
    finally:
        release.set()
    assert wait_for_job(job["run_id"])["status"] == "cancelled"
    assert calls == ["qualification"]


def test_restart_marks_work_interrupted_without_replay(configured):
    api.write_store({"prospects":[],"runs":[],"jobs":[{"run_id":"old-run", "status":"running"}]})
    with TestClient(api.app) as client:
        assert client.get('/api/health').json()["live_run_events"] is True
        assert client.get('/swarm.html').status_code == 200
        assert client.get('/api/prospects').status_code == 401
    assert api.read_store()["jobs"][0]["status"] == "interrupted"


def test_corrupt_store_is_never_overwritten(configured):
    api.DATA_PATH.write_text("broken-json")
    with pytest.raises(HTTPException):
        api.read_store()
    assert api.DATA_PATH.read_text() == "broken-json"


def test_successful_sales_run_enters_review_queue_without_sending(configured, monkeypatch):
    monkeypatch.setattr(runtime, "_call_anthropic", lambda *args: (output("Draft for review"), "test"))
    job=api.start_run(api.JobInput(prospect={"business_name":"Example", "verified_observations":["Checked contact page"]},
        agent_ids=["sales", "qa"], request_id="request-0004"), **configured)
    finished=wait_for_job(job["run_id"])
    approval=api.list_approvals(**configured)["approvals"][0]
    assert finished["status"] == "completed"
    assert approval["id"] == finished["approval_id"]
    assert approval["status"] == "pending"
    assert approval["payload"]["sales_output"]["summary"] == "Draft for review"
    assert finished["outreach_sent"] is False


def test_request_id_cannot_be_reused_for_different_work(configured, monkeypatch):
    monkeypatch.setattr(runtime, "_call_anthropic", lambda *args: (output("test"), "test"))
    request=api.JobInput(prospect={"business_name":"Example"}, agent_ids=["qa"], request_id="request-0005")
    job=api.start_run(request, **configured)
    wait_for_job(job["run_id"])
    changed=request.model_copy(update={"agent_ids":["sales"]})
    with pytest.raises(HTTPException) as exc:
        api.start_run(changed, **configured)
    assert exc.value.status_code == 409
