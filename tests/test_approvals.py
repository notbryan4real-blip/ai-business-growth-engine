import json

import pytest
from fastapi import HTTPException

import app as api


def test_approval_lifecycle_is_persisted_and_decision_is_one_time(tmp_path, monkeypatch):
    monkeypatch.setenv("APP_API_TOKEN", "test-token")
    monkeypatch.setattr(api, "DATA_PATH", tmp_path / "store.json")

    created = api.create_approval(
        api.ApprovalInput(
            action_type="outreach",
            target="Example Plumbing",
            summary="Review first-contact email before sending.",
            payload={"draft_id": "draft-123"},
            evidence=["Website contact page checked manually"],
        ),
        authorization="Bearer test-token",
    )
    assert created["status"] == "pending"
    assert api.list_approvals(authorization="Bearer test-token")["approvals"][0]["id"] == created["id"]

    decided = api.decide_approval(
        created["id"],
        api.ApprovalDecisionInput(decision="approved", rationale="Facts and recipient verified."),
        authorization="Bearer test-token",
    )
    assert decided["status"] == "approved"
    stored = json.loads((tmp_path / "store.json").read_text(encoding="utf-8"))
    assert stored["approvals"][0]["decision"]["rationale"] == "Facts and recipient verified."

    with pytest.raises(HTTPException) as exc:
        api.decide_approval(
            created["id"],
            api.ApprovalDecisionInput(decision="rejected", rationale="Changed my mind"),
            authorization="Bearer test-token",
        )
    assert exc.value.status_code == 409


def test_approval_queue_requires_api_token(tmp_path, monkeypatch):
    monkeypatch.setattr(api, "DATA_PATH", tmp_path / "store.json")
    monkeypatch.delenv("APP_API_TOKEN", raising=False)
    with pytest.raises(HTTPException) as exc:
        api.list_approvals(authorization=None)
    assert exc.value.status_code == 503
