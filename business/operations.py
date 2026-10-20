"""Evidence-based portfolio planning. Internal decisions cost no model tokens.

External systems remain separate: a connection in ChatGPT does not give this
server its credentials. Imports and connector observations never create cash.
"""
from __future__ import annotations

import copy
import hashlib
import hmac
import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator


def now():
    return datetime.now(timezone.utc)


def iso(value=None):
    return (value or now()).isoformat()


PROJECTS = [
    ("greenify", "Greenify Home and Garden", "commerce", "owned", 90,
     "https://greenifyhomeandgarden.myshopify.com", "shopify"),
    ("rillmark", "Rillmark", "saas", "owned", 85, "", "polsia"),
    ("website-services", "Website and automation services", "services", "owned", 95, "", "internal"),
    ("digital-products", "Obsidian vault and digital products", "digital", "owned", 70, "", "internal"),
    ("social-content", "Facebook, Instagram and YouTube", "content", "owned", 60, "", "manual"),
    ("myers", "MYERS PRO", "services", "prospect_demo", 60, "", "internal"),
    ("resurrection", "Resurrection Autoworks website", "services", "prospect_demo", 60, "", "internal"),
    ("shiraz", "Shiraz Plumbing website", "services", "prospect_demo", 60, "", "internal"),
    ("ramlals", "Ramlal's Auto Supplies concept", "services", "prospect_demo", 35, "", "manual"),
    ("jarvis", "Jarvis Android", "software", "owned", 25, "", "internal"),
    ("printpreview", "PrintPreview", "software", "concept", 20, "", "manual"),
    ("paperclip", "Paperclip deployment", "software", "concept", 15, "", "manual"),
    ("little-legends", "Little Legends Lab", "content", "concept", 20, "", "manual"),
    ("plastoline", "PLASTOLINE research", "research", "owned", 10, "", "manual"),
    ("crypto-research", "Crypto research", "research", "owned", 10, "", "internal"),
]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CatalogItem(StrictModel):
    id: str = Field(min_length=1, max_length=150)
    title: str = Field(min_length=1, max_length=400)
    status: Literal["ACTIVE", "DRAFT", "ARCHIVED"]
    product_type: str = Field(default="", max_length=200)
    recorded_inventory: int | None = None


class Metrics(StrictModel):
    net_sales_cents: int | None = Field(default=None, ge=-100000000000)
    sessions: int | None = Field(default=None, ge=0)
    signups: int | None = Field(default=None, ge=0)
    paying_customers: int | None = Field(default=None, ge=0)


class SnapshotInput(StrictModel):
    reference: str = Field(min_length=3, max_length=200)
    source: Literal["owner", "shopify", "polsia"] = "owner"
    observed_at: datetime
    summary: str = Field(default="", max_length=3000)
    catalog: list[CatalogItem] = Field(default_factory=list, max_length=1000)
    catalog_complete: bool = False
    metrics: Metrics = Field(default_factory=Metrics)

    @field_validator("observed_at")
    @classmethod
    def timestamp_is_real(cls, value):
        if value.tzinfo is None or value > now() + timedelta(minutes=5):
            raise ValueError("Use an observed timestamp with a timezone, not a future time.")
        return value.astimezone(timezone.utc)


class CashInput(StrictModel):
    project_id: str = Field(min_length=1, max_length=80)
    kind: Literal["receipt", "expense", "refund"]
    amount_cents: int = Field(gt=0, le=100000000000, strict=True)
    reference: str = Field(min_length=3, max_length=200)
    occurred_at: datetime
    note: str = Field(default="", max_length=1000)

    _timestamp = field_validator("occurred_at")(SnapshotInput.timestamp_is_real.__func__)


class TaskUpdate(StrictModel):
    status: Literal["open", "done", "dismissed"]
    note: str = Field(min_length=3, max_length=1000)


class ProjectUpdate(StrictModel):
    priority: int | None = Field(default=None, ge=0, le=100)
    active: bool | None = None


class SettingsInput(StrictModel):
    autonomy_enabled: bool
    weekly_target_cents: int = Field(default=100000, ge=100, le=100000000)


class BootstrapItem(StrictModel):
    project_id: str = Field(min_length=1, max_length=80)
    snapshot: SnapshotInput


class Operations:
    def __init__(self, path=None):
        self.path = Path(path or os.getenv("BUSINESS_DB_PATH", "data/business.sqlite3"))
        self.lock = threading.Lock()

    def transact(self, fn):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock, sqlite3.connect(self.path, timeout=15) as db:
            db.execute("CREATE TABLE IF NOT EXISTS state (id INTEGER PRIMARY KEY CHECK(id=1), body TEXT NOT NULL)")
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT body FROM state WHERE id=1").fetchone()
            state = json.loads(row[0]) if row else self.initial()
            result = fn(state)
            db.execute("INSERT OR REPLACE INTO state(id,body) VALUES(1,?)", (json.dumps(state),))
            return copy.deepcopy(result)

    @staticmethod
    def initial():
        return {"schema_version": 1, "settings": {"autonomy_enabled": True, "weekly_target_cents": 100000},
                "projects": [{"id": p[0], "name": p[1], "type": p[2], "relationship": p[3],
                              "priority": p[4], "url": p[5], "connector": p[6], "active": True}
                             for p in PROJECTS],
                "snapshots": [], "tasks": [], "decisions": [], "cash": [], "cycles": [], "connector_runs": {}}

    @staticmethod
    def project(state, project_id):
        project = next((p for p in state["projects"] if p["id"] == project_id), None)
        if not project:
            raise HTTPException(404, "Project not found.")
        return project

    @staticmethod
    def latest(state, project_id):
        items = [s for s in state["snapshots"] if s["project_id"] == project_id]
        return max(items, key=lambda s: s["observed_at"]) if items else None

    def _insert_snapshot(self, state, project_id, request, verification):
        payload = request.model_dump(mode="json")
        self.project(state, project_id)
        previous = next((s for s in state["snapshots"] if s["project_id"] == project_id
                         and s["reference"] == payload["reference"]), None)
        if previous:
            if any(previous.get(k) != v for k, v in payload.items()):
                raise HTTPException(409, "Snapshot reference already used for different data.")
            return previous
        item = {**payload, "project_id": project_id, "verification": verification, "imported_at": iso()}
        state["snapshots"].append(item)
        return item

    def ingest(self, project_id, request, verification="owner_import"):
        return self.transact(lambda s: self._insert_snapshot(s, project_id, request, verification))

    def bootstrap(self, raw):
        """Restore owner-provided baseline evidence from private hosting config.

        This does not grant API access or turn imported claims into live data.
        The full batch is atomic; repeated startup preserves edits and cash.
        """
        if not raw:
            return {"configured": False, "loaded": False, "snapshots": 0}
        if len(raw.encode()) > 2_000_000:
            raise ValueError("Bootstrap document exceeds the configured size limit.")
        document = json.loads(raw)
        if not isinstance(document, dict) or not isinstance(document.get("snapshots"), list):
            raise ValueError("Bootstrap requires a snapshots array.")
        if not 1 <= len(document["snapshots"]) <= 20:
            raise ValueError("Bootstrap requires one to twenty snapshots.")
        entries = [BootstrapItem.model_validate(item) for item in document["snapshots"]]
        def change(state):
            for item in entries:
                self._insert_snapshot(state, item.project_id, item.snapshot, "owner_import")
            return {"configured": True, "loaded": True, "snapshots": len(entries)}
        return self.transact(change)

    def cash_entry(self, request):
        payload = request.model_dump(mode="json")
        def change(state):
            self.project(state, payload["project_id"])
            # A provider reference is unique per project and kind; repeated clicks cannot inflate income.
            old = next((c for c in state["cash"] if all(c[k] == payload[k]
                        for k in ("project_id", "kind", "reference"))), None)
            if old:
                if any(old[k] != v for k, v in payload.items()):
                    raise HTTPException(409, "Cash reference already used for different data.")
                return old
            entry = {**payload, "id": hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24],
                     "verification": "owner_reported", "created_at": iso()}
            state["cash"].append(entry)
            return entry
        return self.transact(change)

    @staticmethod
    def money(state, at):
        entries = [c for c in state["cash"] if at - timedelta(days=7) <= datetime.fromisoformat(c["occurred_at"]) <= at]
        sums = {kind: sum(c["amount_cents"] for c in entries if c["kind"] == kind)
                for kind in ("receipt", "expense", "refund")}
        net = sums["receipt"] - sums["expense"] - sums["refund"]
        return {**{k + "_cents": v for k, v in sums.items()}, "recorded_net_cash_cents": net,
                "target_cents": state["settings"]["weekly_target_cents"],
                "gap_cents": max(0, state["settings"]["weekly_target_cents"] - net),
                "entry_count": len(entries), "period": "rolling_7_days", "currency": "USD",
                "basis": "Owner-reported receipts minus recorded expenses and refunds. Costs may be incomplete; not verified profit."}

    def cycle(self, at=None):
        at = at or now()
        def change(state):
            revision = {"projects": [(p["id"], p["priority"], p["active"]) for p in state["projects"]],
                        "snapshots": [(s["project_id"], s["reference"]) for s in state["snapshots"]],
                        "settings": state["settings"]}
            digest = hashlib.sha256(json.dumps(revision, sort_keys=True).encode()).hexdigest()[:12]
            key = at.strftime("%Y-%m-%d") + ":" + str(at.hour // 6) + ":" + digest
            if not state["settings"]["autonomy_enabled"]:
                return {"status": "paused", "model_calls": 0, "external_actions": []}
            old = next((c for c in state["cycles"] if c["key"] == key), None)
            if old:
                return {**old, "reused": True}
            created = []
            def task(project, code, title, details, agent, priority=None):
                task_id = project["id"] + ":" + code
                item = next((t for t in state["tasks"] if t["id"] == task_id), None)
                if item:
                    if item["status"] == "open":
                        item["priority"] = priority if priority is not None else project["priority"]
                    return
                item = {"id": task_id, "project_id": project["id"], "title": title, "details": details,
                        "agent": agent, "priority": priority if priority is not None else project["priority"],
                        "status": "open", "created_at": iso(at), "execution": "internal_plan",
                        "outcome": None}
                state["tasks"].append(item)
                created.append(task_id)
            for p in sorted(state["projects"], key=lambda p: -p["priority"]):
                if not p["active"]:
                    continue
                snapshot = self.latest(state, p["id"])
                if p["id"] == "greenify":
                    task(p, "fulfillment", "Verify Greenify supplier costs and fulfillment", "Confirm supplier availability, shipping times, landed cost and margin before scaling promotion. Recorded inventory is not a fulfillment guarantee.", "finance", 100)
                    if snapshot:
                        active = [c for c in snapshot["catalog"] if c["status"] == "ACTIVE"]
                        no_type = sum(not c["product_type"] for c in active)
                        zeros = sum(c["recorded_inventory"] == 0 for c in active)
                        if no_type:
                            task(p, "catalog", "Prepare product classification improvements", f"Observed {no_type} active products without a product type. Draft accurate classifications and a focused collection before editing Shopify.", "copywriting")
                        if zeros:
                            task(p, "stock", "Check products with zero recorded inventory", f"Observed {zeros} active products with zero recorded inventory. Check tracking, continue-selling settings and supplier stock; do not assume they cannot be sold.", "qa", 99)
                    task(p, "merchandising", "Draft a focused Greenify merchandising plan", "Choose products only after fulfillment and margin checks. Use measured sessions, carts and sales to evaluate one organic campaign; do not buy ads automatically.", "market")
                elif p["id"] == "rillmark":
                    task(p, "connect", "Connect Rillmark's Polsia operations report", "Import an aggregate operations report or configure the scoped Polsia bridge. Company URL, live product status and payment activity still need evidence. Do not import customers' bank transactions.", "automation", 98)
                    task(p, "validation", "Prepare Rillmark activation and conversion review", "Use actual visits, signups, activation, paying users and support issues. Identify one measurable activation experiment. Pricing in an old plan is a hypothesis until verified live.", "qualification")
                elif p["id"] == "website-services":
                    task(p, "sales", "Prepare the next fixed-scope website offer", "Prioritize a verified prospect with an existing demo. Use the established $500 offer as a pricing hypothesis, confirm delivery costs, and prepare the proposal. Two $500 sales equal $1,000 gross before expenses; no sales are assumed.", "sales", 97)
                elif p["relationship"] == "prospect_demo":
                    task(p, "demo-review", "Review demo and prepare a proposal", "Confirm business facts, verify the mobile demo, define deliverables and draft a proposal. This project is a prospect/demo, not an active paying client.", "project")
                elif p["type"] == "research":
                    task(p, "research", "Maintain a research-only project brief", "Summarize existing evidence, unresolved tests and next validation gate. Exclude forecasts and paper trading from business cash; no live trades or equipment operation.", "qa")
                else:
                    task(p, "brief", "Prepare a bounded project progress brief", "Review the latest source, list the current blocker, and choose one small task with a measurable deliverable. Give near-term customer revenue work priority over new development.", "project")
                if p["connector"] in {"shopify", "polsia"} and (not snapshot or
                        at - datetime.fromisoformat(snapshot["observed_at"]) > timedelta(days=2)):
                    task(p, "refresh", "Refresh business evidence", "No recent operational snapshot is available. Refresh aggregate business data before changing a plan based on performance.", "verification", 96)
                state["decisions"].append({"at": iso(at), "project_id": p["id"], "agent": "orchestrator",
                    "decision": "Prioritize internal work at score " + str(p["priority"]),
                    "basis": "Configured priority, project relationship and snapshot freshness; rules-based, not an LLM prediction.",
                    "snapshot_at": snapshot["observed_at"] if snapshot else None})
            state["decisions"] = state["decisions"][-600:]
            record = {"key": key, "at": iso(at), "status": "completed", "tasks_created": len(created),
                      "model_calls": 0, "external_actions": [], "money": self.money(state, at)}
            state["cycles"].append(record)
            state["cycles"] = state["cycles"][-120:]
            return record
        return self.transact(change)

    def overview(self):
        def read(state):
            projects = []
            for p in state["projects"]:
                snapshot = self.latest(state, p["id"])
                projects.append({**p, "snapshot": snapshot, "snapshot_stale": bool(snapshot and
                    now() - datetime.fromisoformat(snapshot["observed_at"]) > timedelta(days=2))})
            return {"projects": projects, "settings": state["settings"], "money": self.money(state, now()),
                    "tasks": sorted(state["tasks"], key=lambda t: (-t["priority"], t["created_at"])),
                    "decisions": state["decisions"][-30:][::-1], "last_cycle": state["cycles"][-1] if state["cycles"] else None,
                    "connector_runs": state["connector_runs"],
                    "connectors": {"shopify_server_configured": bool(os.getenv("SHOPIFY_ADMIN_TOKEN") and os.getenv("SHOPIFY_STORE_DOMAIN")),
                                   "polsia_bridge_configured": bool(os.getenv("POLSIA_BRIDGE_TOKEN"))},
                    "autonomy": {"interval_hours": 6, "runs_while_service_awake": True, "automatic_model_calls": False,
                                 "automatic_actions": ["prioritize", "plan", "create_internal_tasks", "read_configured_shopify"],
                                 "external_writes_enabled": False},
                    "storage": {"durable_configured": os.getenv("BUSINESS_DURABLE_STORAGE") == "true",
                                "notice": "Export backups. Default Render free storage can reset during redeployment or restart."}}
        return self.transact(read)


def router(engine, require_token):
    api = APIRouter(prefix="/api/business", tags=["Business operations"])

    @api.get("/overview")
    def overview(authorization: str | None = Header(default=None)):
        require_token(authorization)
        return engine.overview()

    @api.post("/cycle")
    def cycle(authorization: str | None = Header(default=None)):
        require_token(authorization)
        return engine.cycle()

    @api.post("/projects/{project_id}/snapshot")
    def snapshot(project_id: str, request: SnapshotInput, authorization: str | None = Header(default=None)):
        require_token(authorization)
        return engine.ingest(project_id, request)

    @api.post("/cash")
    def cash(request: CashInput, authorization: str | None = Header(default=None)):
        require_token(authorization)
        return engine.cash_entry(request)

    @api.patch("/tasks/{task_id}")
    def task(task_id: str, request: TaskUpdate, authorization: str | None = Header(default=None)):
        require_token(authorization)
        def change(state):
            item = next((t for t in state["tasks"] if t["id"] == task_id), None)
            if not item:
                raise HTTPException(404, "Task not found.")
            item.update(status=request.status, outcome=request.note, updated_at=iso())
            return item
        return engine.transact(change)

    @api.patch("/projects/{project_id}")
    def project(project_id: str, request: ProjectUpdate, authorization: str | None = Header(default=None)):
        require_token(authorization)
        def change(state):
            p = engine.project(state, project_id)
            p.update(request.model_dump(exclude_none=True))
            return p
        return engine.transact(change)

    @api.put("/settings")
    def settings(request: SettingsInput, authorization: str | None = Header(default=None)):
        require_token(authorization)
        return engine.transact(lambda s: s.update(settings=request.model_dump()) or s["settings"])

    @api.get("/export")
    def export(authorization: str | None = Header(default=None)):
        require_token(authorization)
        return engine.transact(lambda s: s)

    @api.post("/bridge/polsia")
    def polsia(request: SnapshotInput, authorization: str | None = Header(default=None)):
        expected = os.getenv("POLSIA_BRIDGE_TOKEN", "")
        supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
        if not expected:
            raise HTTPException(503, "Polsia bridge has not been configured.")
        if expected == os.getenv("APP_API_TOKEN"):
            raise HTTPException(503, "The Polsia bridge must use a separate, scoped token.")
        if not hmac.compare_digest(expected, supplied):
            raise HTTPException(401, "A valid scoped bridge token is required.")
        if request.source != "polsia" or request.catalog:
            raise HTTPException(422, "The Polsia bridge accepts Rillmark aggregate reports only.")
        return engine.ingest("rillmark", request, verification="polsia_reported")

    return api
