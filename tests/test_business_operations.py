from datetime import timedelta
import json

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from business.operations import Operations, SnapshotInput, CashInput, router, now
from integrations import shopify_business as shopify


@pytest.fixture
def engine(tmp_path):
    return Operations(tmp_path / "portfolio.sqlite3")


def snapshot(**kw):
    return SnapshotInput(reference="report-001", source="shopify", observed_at=now(), **kw)


def test_cycles_are_idempotent_and_do_not_turn_prospects_into_clients(engine):
    timestamp = now()
    first = engine.cycle(timestamp)
    second = engine.cycle(timestamp)
    assert second["reused"] and first["tasks_created"] > 0
    state = engine.overview()
    assert len(state["tasks"]) == first["tasks_created"]
    assert next(p for p in state["projects"] if p["id"] == "myers")["relationship"] == "prospect_demo"
    assert first["model_calls"] == 0 and first["external_actions"] == []
    assert state["money"]["entry_count"] == 0
    restored = Operations(engine.path).overview()
    assert restored["tasks"] == state["tasks"]


def test_pause_stops_automatic_planning(engine):
    engine.transact(lambda s: s["settings"].update(autonomy_enabled=False))
    assert engine.cycle()["status"] == "paused"
    assert not engine.overview()["tasks"]


def test_private_bootstrap_is_idempotent_and_preserves_existing_cash(engine):
    raw = json.dumps({"snapshots":[{"project_id":"greenify", "snapshot":snapshot().model_dump(mode="json")}]})
    assert engine.bootstrap(raw) == {"configured":True,"loaded":True,"snapshots":1}
    engine.cash_entry(CashInput(project_id="greenify", kind="receipt", amount_cents=100,
        reference="payment-001", occurred_at=now()))
    engine.bootstrap(raw)
    assert len(engine.transact(lambda s:s["snapshots"])) == 1
    assert engine.overview()["money"]["receipt_cents"] == 100
    assert engine.overview()["projects"][0]["snapshot"]["verification"] == "owner_import"


def test_bootstrap_rolls_back_entire_batch_for_unknown_project_or_conflict(engine):
    first = snapshot()
    document = {"snapshots":[{"project_id":"greenify", "snapshot":first.model_dump(mode="json")},
        {"project_id":"unknown", "snapshot":snapshot().model_dump(mode="json")}]}
    with pytest.raises(HTTPException):
        engine.bootstrap(json.dumps(document))
    assert engine.transact(lambda s:s["snapshots"]) == []
    with pytest.raises(ValueError):
        engine.bootstrap(json.dumps({"snapshots":[]}))
    assert engine.bootstrap("")["configured"] is False


def test_startup_bootstrap_and_operations_are_available_without_exposing_private_data(engine, monkeypatch, tmp_path):
    import app as application
    monkeypatch.setattr(application, "BUSINESS", engine)
    monkeypatch.setattr(application, "DATA_PATH", tmp_path / "runs.json")
    monkeypatch.setenv("APP_API_TOKEN", "test-owner-token")
    monkeypatch.delenv("SHOPIFY_ADMIN_TOKEN", raising=False)
    raw = json.dumps({"snapshots":[{"project_id":"greenify", "snapshot":snapshot(summary="private observation").model_dump(mode="json")}]})
    monkeypatch.setenv("BUSINESS_BOOTSTRAP_JSON", raw)
    with TestClient(application.app) as client:
        health = client.get("/api/health").json()
        assert health["business_bootstrap_loaded"] and health["version"] == "0.4.0"
        assert health["reactor_agents"] == 8 and health["reactor_live_orders"] is False
        assert "private observation" not in json.dumps(health)
        assert client.get("/api/business/overview").status_code == 401
        assert engine.overview()["projects"][0]["snapshot"]["summary"] == "private observation"
        assert engine.overview()["tasks"]


def test_new_evidence_reopens_review_without_duplicating_existing_tasks(engine):
    timestamp = now()
    engine.cycle(timestamp)
    engine.ingest("greenify", snapshot(catalog=[{"id":"p1", "title":"Lamp", "status":"ACTIVE",
        "recorded_inventory":0}], catalog_complete=True))
    result = engine.cycle(timestamp)
    assert not result.get("reused")
    tasks = engine.overview()["tasks"]
    assert len({t["id"] for t in tasks}) == len(tasks)
    assert any(t["id"] == "greenify:stock" for t in tasks)
    assert any(t["id"] == "greenify:catalog" for t in tasks)


def test_sales_snapshots_never_create_cash_and_report_import_provenance(engine):
    item = snapshot(metrics={"net_sales_cents":100000})
    engine.ingest("greenify", item)
    engine.ingest("greenify", item)
    assert len(engine.transact(lambda s: s["snapshots"])) == 1
    state = engine.overview()
    assert state["money"]["recorded_net_cash_cents"] == 0
    assert state["money"]["gap_cents"] == 100000
    assert next(p for p in state["projects"] if p["id"] == "greenify")["snapshot"]["verification"] == "owner_import"
    with pytest.raises(HTTPException) as exc:
        engine.ingest("greenify", item.model_copy(update={"summary":"Changed"}))
    assert exc.value.status_code == 409


def test_cash_uses_real_rolling_window_refunds_and_expenses_without_duplicates(engine):
    timestamp = now()
    receipt = CashInput(project_id="website-services", kind="receipt", amount_cents=100000,
        reference="payment-1", occurred_at=timestamp)
    engine.cash_entry(receipt)
    engine.cash_entry(receipt)
    engine.cash_entry(CashInput(project_id="website-services", kind="expense", amount_cents=10000,
        reference="hosting-1", occurred_at=timestamp))
    engine.cash_entry(CashInput(project_id="website-services", kind="refund", amount_cents=5000,
        reference="refund-1", occurred_at=timestamp))
    engine.cash_entry(CashInput(project_id="website-services", kind="receipt", amount_cents=200000,
        reference="old-payment", occurred_at=timestamp-timedelta(days=8)))
    state = engine.overview()
    assert state["money"]["recorded_net_cash_cents"] == 85000
    assert state["money"]["gap_cents"] == 15000
    assert state["money"]["entry_count"] == 3
    with pytest.raises(HTTPException):
        engine.cash_entry(receipt.model_copy(update={"amount_cents":200000}))


def test_unknown_projects_and_invalid_timestamps_are_rejected(engine):
    with pytest.raises(HTTPException):
        engine.ingest("unknown", snapshot())
    with pytest.raises(ValueError):
        SnapshotInput(reference="future", observed_at=now()+timedelta(days=1))
    with pytest.raises(ValueError):
        CashInput(project_id="greenify", kind="receipt", amount_cents=1.5, reference="x12", occurred_at=now())


def test_all_private_routes_require_token_and_bridge_has_separate_scope(engine, monkeypatch):
    from app import require_api_token
    app = FastAPI()
    app.include_router(router(engine, require_api_token))
    client = TestClient(app)
    monkeypatch.setenv("APP_API_TOKEN", "owner-token")
    monkeypatch.setenv("POLSIA_BRIDGE_TOKEN", "bridge-token")
    for path in ("/overview", "/export"):
        assert client.get("/api/business"+path).status_code == 401
    assert client.post("/api/business/cycle").status_code == 401
    body = SnapshotInput(reference="polsia-001", source="polsia", observed_at=now(), metrics={"signups":3}).model_dump(mode="json")
    assert client.post("/api/business/bridge/polsia", json=body, headers={"Authorization":"Bearer owner-token"}).status_code == 401
    assert client.post("/api/business/bridge/polsia", json=body, headers={"Authorization":"Bearer bridge-token"}).status_code == 200
    assert client.get("/api/business/export", headers={"Authorization":"Bearer bridge-token"}).status_code == 401
    assert client.get("/api/business/overview", headers={"Authorization":"Bearer owner-token"}).status_code == 200
    assert engine.latest(engine.transact(lambda s:s), "rillmark")["verification"] == "polsia_reported"
    monkeypatch.setenv("POLSIA_BRIDGE_TOKEN", "owner-token")
    assert client.post("/api/business/bridge/polsia", json=body).status_code == 503


def test_failed_catalog_pagination_retains_previous_snapshot(engine, monkeypatch):
    engine.ingest("greenify", snapshot())
    calls = []
    def query(code, variables):
        calls.append(variables)
        return {"shop":{"myshopifyDomain":"dcxnfg-q1.myshopify.com", "currencyCode":"USD"},
            "products":{"nodes":[], "pageInfo":{"hasNextPage":True,"endCursor":"repeated"}}}
    monkeypatch.setattr(shopify, "query_shop", query)
    with pytest.raises(RuntimeError, match="pagination"):
        shopify.sync_greenify(engine)
    assert len(calls) == 2
    assert len(engine.transact(lambda s:s["snapshots"])) == 1


def test_shopify_complete_catalog_and_sales_report_stay_separate_from_cash(engine, monkeypatch):
    def query(code, variables):
        if "report" in variables:
            return {"shopifyqlQuery":{"parseErrors":[], "tableData":{"columns":[{"name":"net_sales"}],"rows":[["123.45"]]}}}
        return {"shop":{"myshopifyDomain":"dcxnfg-q1.myshopify.com", "currencyCode":"USD"},
            "products":{"nodes":[{"id":"p1","title":"Lamp","status":"ACTIVE","totalInventory":0,"productType":"Lighting"}],
                        "pageInfo":{"hasNextPage":False,"endCursor":None}}}
    monkeypatch.setattr(shopify, "query_shop", query)
    item = shopify.sync_greenify(engine)
    assert item["catalog_complete"] and item["verification"] == "direct_api"
    assert item["metrics"]["net_sales_cents"] == 12345
    assert engine.overview()["money"]["recorded_net_cash_cents"] == 0


def test_connector_rejects_other_shops_and_never_sends_tokens_to_arbitrary_hosts(monkeypatch):
    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "attacker.example.com")
    monkeypatch.setenv("SHOPIFY_ADMIN_TOKEN", "secret-never-sent")
    with pytest.raises(ValueError):
        shopify.query_shop("query { shop { name } }", {})
    monkeypatch.setenv("SHOPIFY_STORE_DOMAIN", "other-store.myshopify.com")
    with pytest.raises(ValueError):
        shopify.query_shop("query { shop { name } }", {})
