from __future__ import annotations
import asyncio, hmac, json, logging, os, uuid
from pathlib import Path
from threading import Lock, BoundedSemaphore
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from typing import Any, Literal
from datetime import datetime, timezone
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator
from agents.runtime import AGENTS, AgentRuntimeError, run_specialists, select_agents
from agents.prospecting.models import Prospect
from agents.qualification.scoring import score_prospect
from agents.prospecting.google_places import PlacesDiscoveryError, search_places
from agents.audit.website import WebsiteAuditError, audit_website
from business.operations import Operations, router as business_router, iso
from integrations.shopify_business import sync_greenify
from integrations.stripe_checkout import router as stripe_router
from brain.council import Brain, Observation, router as brain_router
from reactor.service import Reactor, router as reactor_router

DATA_PATH = Path(os.getenv("GROWTH_ENGINE_DATA_PATH", "data/runtime_store.json"))
LOCK = Lock()
RUN_SLOT = BoundedSemaphore(1)
WORKER = ThreadPoolExecutor(max_workers=1, thread_name_prefix="swarm")
BUSINESS_BOOTSTRAP = {"configured": False, "loaded": False, "snapshots": 0}

@asynccontextmanager
async def lifespan(app):
    global BUSINESS_BOOTSTRAP
    # A process restart must never silently replay paid model calls.
    with LOCK:
        store = read_store()
        changed = False
        for job in store.get("jobs", []):
            if job["status"] in {"queued", "running"}:
                job.update(status="interrupted", error="Service restarted. Partial results retained; no calls were replayed.")
                changed = True
        if changed:
            write_store(store)
    try:
        BUSINESS_BOOTSTRAP = BUSINESS.bootstrap(os.getenv("BUSINESS_BOOTSTRAP_JSON", ""))
        BUSINESS.cycle()
        overview = BUSINESS.overview()
        logging.getLogger("uvicorn.error").info(
            "Business operations ready: projects=%s snapshots_imported=%s open_tasks=%s; no model calls or external writes.",
            len(overview["projects"]), BUSINESS_BOOTSTRAP["snapshots"],
            sum(t["status"] == "open" for t in overview["tasks"]))
    except Exception:
        BUSINESS_BOOTSTRAP = {"configured": bool(os.getenv("BUSINESS_BOOTSTRAP_JSON")), "loaded": False, "snapshots": 0}
        logging.getLogger("uvicorn.error").error("Business bootstrap failed validation; existing evidence retained. Check private configuration.")
    BRAIN.recover()
    REACTOR.recover()
    scheduler = asyncio.create_task(business_scheduler())
    council_scheduler = asyncio.create_task(brain_scheduler())
    crypto_scheduler = asyncio.create_task(reactor_scheduler())
    try:
        yield
    finally:
        scheduler.cancel()
        council_scheduler.cancel()
        crypto_scheduler.cancel()
        try:
            await scheduler
        except asyncio.CancelledError:
            pass
        try:
            await crypto_scheduler
        except asyncio.CancelledError:
            pass
        try:
            await council_scheduler
        except asyncio.CancelledError:
            pass

app = FastAPI(title="AI Business Growth Engine API", version="0.4.0", lifespan=lifespan)
app.include_router(stripe_router)
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(","), allow_credentials=False, allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"], allow_headers=["Content-Type", "Authorization"])

class ProspectInput(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=200)
    website_url: str | None = Field(default=None, max_length=1000)
    website_status: Literal["unknown", "listed", "not_listed_unverified", "confirmed_missing"] = "unknown"
    provider_id: str | None = Field(default=None, max_length=300)
    source: str | None = Field(default=None, max_length=100)
    source_url: str | None = Field(default=None, max_length=1000)
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int = Field(default=0, ge=0)
    website_quality_score: int | None = Field(default=None, ge=0, le=100)
    social_urls: list[str] = Field(default_factory=list, max_length=20)
    verified_observations: list[str] = Field(default_factory=list, max_length=30)
    notes: list[str] = Field(default_factory=list, max_length=30)

class RunInput(BaseModel):
    prospect: ProspectInput
    agent_ids: list[str] = Field(default_factory=lambda: [a["id"] for a in AGENTS], max_length=19)

    @model_validator(mode="after")
    def bound_evidence(self):
        if len(json.dumps(self.prospect.model_dump(), ensure_ascii=False)) > 16000:
            raise ValueError("Keep prospect evidence under 16,000 characters for a bounded model request.")
        return self

def require_api_token(authorization: str | None) -> None:
    expected = os.getenv("APP_API_TOKEN")
    if not expected:
        raise HTTPException(status_code=503, detail="APP_API_TOKEN is not configured; protected actions are disabled.")
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="A valid bearer token is required.")

def read_store() -> dict[str, Any]:
    if not DATA_PATH.exists(): return {"prospects": [], "runs": []}
    try: return json.loads(DATA_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=503, detail="Stored data is unreadable. Restore a backup before continuing.") from exc

def write_store(store: dict[str, Any]) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = DATA_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(DATA_PATH)


BUSINESS = Operations()
app.include_router(business_router(BUSINESS, require_api_token))
BRAIN = Brain(run_slot=RUN_SLOT)
app.include_router(brain_router(BRAIN, require_api_token, lambda: BUSINESS.overview()))
REACTOR = Reactor(model_slot=RUN_SLOT)
app.include_router(reactor_router(REACTOR, require_api_token))


def publish_crypto_review(run):
    BRAIN.ingest(Observation(source="crypto", reference="reactor-"+run["id"],
        observed_at=datetime.now(timezone.utc), summary=run["summary"][:2500],
        details={"mode": "paper_only", "run_id": run["id"], "real_revenue": False,
                 "board": run["board"], "paper_result": run["paper_result"]}), "internal_paper_research")


REACTOR.on_complete = publish_crypto_review


async def reactor_scheduler():
    while True:
        try:
            await asyncio.to_thread(REACTOR.tick)
        except Exception:
            logging.getLogger(__name__).error("Reactor scheduling unavailable; no external orders or paid retries.")
        await asyncio.sleep(60)


async def brain_scheduler():
    from brain.connectors import sync_sources
    while True:
        try:
            if BRAIN.transact(lambda s: s["settings"]["enabled"]):
                await asyncio.to_thread(sync_sources, BRAIN, False)
                await asyncio.to_thread(BRAIN.tick)
        except Exception:
            logging.getLogger(__name__).error("Council scheduling failed; private state retained.")
        await asyncio.sleep(60)


def business_tick():
    """No automatic model spend or external mutations; retry failed reads next interval."""
    state = BUSINESS.overview()
    if not state["settings"]["autonomy_enabled"]:
        return
    if state["connectors"]["shopify_server_configured"]:
        try:
            sync_greenify(BUSINESS)
            result = {"status": "synced", "at": iso()}
        except Exception:
            # Never persist response bodies or credential-bearing request objects.
            result = {"status": "failed", "at": iso(), "error": "Shopify read failed; check server credentials and scopes. Previous evidence retained."}
        BUSINESS.transact(lambda s: s["connector_runs"].update(shopify=result))
    BUSINESS.cycle()


async def business_scheduler():
    while True:
        try:
            await asyncio.to_thread(business_tick)
        except Exception:
            # A storage outage must not stop the existing agent API.
            import logging
            logging.getLogger(__name__).error("Business operations tick failed; no external writes performed.")
        await asyncio.sleep(6 * 60 * 60)

@app.get("/api/health")
def health():
    return {"status":"ok","service":"growth-engine-api","version":"0.4.0","reactor_version":"1.0","reactor_agents":8,"reactor_live_orders":False,"brain_version":"1.0","brain_agents":24,"business_operations":True,"business_bootstrap_loaded":BUSINESS_BOOTSTRAP["loaded"],"live_run_events":True,"ai_configured":bool(os.getenv("AI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")),"api_token_configured":bool(os.getenv("APP_API_TOKEN")),"google_places_configured":bool(os.getenv("BUSINESS_DATA_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")),"agent_count":len(AGENTS),"persistence":str(DATA_PATH)}

@app.get("/api/agents")
def list_agents():
    return {"agents":AGENTS,"execution_mode":"sequential_specialist_model_calls","outreach_enabled":False}

@app.get("/api/prospects")
def list_prospects(authorization: str | None = Header(default=None)):
    require_api_token(authorization)
    with LOCK: return {"prospects": read_store().get("prospects", [])}

@app.post("/api/prospects")
def create_prospect(p: ProspectInput, authorization: str | None = Header(default=None)):
    require_api_token(authorization)
    record=p.model_dump()
    model=Prospect(business_name=record["business_name"],category=record["category"],location=record["location"],website_url=record["website_url"],website_status=record["website_status"],source=record["source"],source_url=record["source_url"],rating=record["rating"],review_count=record["review_count"],website_quality_score=record["website_quality_score"],social_urls=record["social_urls"],notes=record["notes"]+record["verified_observations"])
    model.validate()
    score=score_prospect(model)
    record.update({"id":uuid.uuid4().hex,"opportunity_score":score.total,"score_factors":score.factors,"stage":"research"})
    with LOCK:
        store=read_store(); store["prospects"].append(record); write_store(store)
    return record

class DiscoveryInput(BaseModel):
    query: str = Field(min_length=3, max_length=300)
    max_results: int = Field(default=10, ge=1, le=20)


@app.post("/api/discovery/search")
def discover_businesses(request: DiscoveryInput, authorization: str | None = Header(default=None)):
    """Search Google Places; persist only place IDs, not restricted Places content."""
    require_api_token(authorization)
    try:
        candidates = search_places(request.query, max_results=request.max_results)
    except PlacesDiscoveryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    results: list[dict[str, Any]] = []
    with LOCK:
        store = read_store()
        saved_ids = set(store.get("google_place_ids", []))
        for item in candidates:
            place_id = item.get("place_id")
            model = Prospect(
                business_name=item["business_name"],
                category=item.get("category"),
                location=item.get("location"),
                phone=item.get("phone"),
                website_url=item.get("website_url"),
                website_status=item.get("website_status", "not_listed_unverified"),
                rating=item.get("rating"),
                review_count=item.get("review_count", 0),
                source=item.get("source"),
                source_url=item.get("source_url"),
            )
            score = score_prospect(model)
            results.append({
                **item,
                "opportunity_score": score.total,
                "score_factors": score.factors,
                "previously_seen": bool(place_id and place_id in saved_ids),
            })
            if place_id:
                saved_ids.add(place_id)
        # Google Places place IDs are exempt from caching restrictions; do not
        # persist names, addresses, phones, ratings, URLs, or other Places content.
        store["google_place_ids"] = sorted(saved_ids)
        write_store(store)

    return {
        "status": "completed",
        "provider": "google_places",
        "query": request.query,
        "results_returned": len(results),
        "place_ids_retained": len(saved_ids),
        "results_are_transient": True,
        "prospects": results,
        "attribution": "Google Maps",
        "notice": "Results are live and are not saved as prospect records. A missing website URL in Places is unverified, not proof that the business has no website. Verify facts independently before adding a prospect to the CRM.",
    }


class WebsiteAuditInput(BaseModel):
    url: str = Field(min_length=8, max_length=2000)


@app.post("/api/audit/website")
def audit_public_website(request: WebsiteAuditInput, authorization: str | None = Header(default=None)):
    """Run a bounded static HTML audit of a publicly accessible website."""
    require_api_token(authorization)
    try:
        return audit_website(request.url)
    except WebsiteAuditError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Invalid website URL.") from exc


class ApprovalInput(BaseModel):
    action_type: Literal["outreach", "publish_website", "financial_commitment", "customer_data_access", "other"]
    target: str = Field(min_length=1, max_length=300)
    summary: str = Field(min_length=1, max_length=2000)
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list, max_length=50)


class ApprovalDecisionInput(BaseModel):
    decision: Literal["approved", "rejected"]
    rationale: str = Field(min_length=3, max_length=2000)


@app.get("/api/approvals")
def list_approvals(authorization: str | None = Header(default=None)):
    require_api_token(authorization)
    with LOCK:
        store = read_store()
        return {"approvals": store.get("approvals", [])}


@app.post("/api/approvals")
def create_approval(request: ApprovalInput, authorization: str | None = Header(default=None)):
    require_api_token(authorization)
    record = {
        "id": uuid.uuid4().hex,
        "action_type": request.action_type,
        "target": request.target,
        "summary": request.summary,
        "payload": request.payload,
        "evidence": request.evidence,
        "status": "pending",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "decision": None,
    }
    with LOCK:
        store = read_store()
        store.setdefault("approvals", []).append(record)
        write_store(store)
    return record


@app.patch("/api/approvals/{approval_id}")
def decide_approval(approval_id: str, request: ApprovalDecisionInput, authorization: str | None = Header(default=None)):
    require_api_token(authorization)
    with LOCK:
        store = read_store()
        approvals = store.setdefault("approvals", [])
        record = next((item for item in approvals if item.get("id") == approval_id), None)
        if record is None:
            raise HTTPException(status_code=404, detail="Approval request not found.")
        if record.get("status") != "pending":
            raise HTTPException(status_code=409, detail="Only pending approval requests can be decided.")
        record["status"] = request.decision
        record["decision"] = {
            "decision": request.decision,
            "rationale": request.rationale,
            "decided_at": datetime.now(timezone.utc).isoformat(),
        }
        write_store(store)
    return record


@app.post("/api/agents/run")
def run_agents(request: RunInput, authorization: str | None = Header(default=None)):
    require_api_token(authorization)
    if not RUN_SLOT.acquire(blocking=False):
        raise HTTPException(status_code=409, detail="A run is already active. Wait for completion before starting another.")
    evidence=request.prospect.model_dump()
    if not evidence.get("verified_observations") and not evidence.get("notes"):
        evidence["evidence_warning"]="No observations or notes supplied; avoid business-specific claims."
    try: result=run_specialists(evidence,request.agent_ids)
    except AgentRuntimeError as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc
    except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc
    finally: RUN_SLOT.release()
    run_id=uuid.uuid4().hex; result["run_id"]=run_id
    with LOCK:
        store=read_store(); store["runs"].append({"run_id":run_id,"business_name":evidence["business_name"],"result":result}); write_store(store)
    return result


class JobInput(RunInput):
    request_id: str = Field(min_length=8, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    audit_website: bool = False


def _find_job(store: dict[str, Any], run_id: str) -> dict[str, Any]:
    job = next((j for j in store.get("jobs", []) if j["run_id"] == run_id), None)
    if job is None:
        raise HTTPException(status_code=404, detail="Run not found.")
    return job


def _job_summary(job: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in job.items() if k not in {"events", "evidence"}}


def _execute_job(run_id: str, request: JobInput) -> None:
    def record(event):
        with LOCK:
            store = read_store()
            job = _find_job(store, run_id)
            event = {**event, "sequence": len(job["events"]) + 1,
                     "timestamp": datetime.now(timezone.utc).isoformat()}
            job["events"].append(event)
            if event["type"] == "agent_completed":
                job["results"].append({k: event[k] for k in ("agent_id", "name", "model", "output")})
            write_store(store)

    def cancelled():
        with LOCK:
            return bool(_find_job(read_store(), run_id).get("cancel_requested"))

    try:
        with LOCK:
            store = read_store()
            _find_job(store, run_id)["status"] = "running"
            write_store(store)
        evidence = request.prospect.model_dump()
        if request.audit_website and evidence.get("website_url"):
            record({"type": "audit_started", "url": evidence["website_url"]})
            try:
                evidence["website_audit"] = audit_website(evidence["website_url"])
                record({"type": "audit_completed", "audit": evidence["website_audit"]})
            except (WebsiteAuditError, ValueError) as exc:
                evidence["website_audit_error"] = str(exc)
                record({"type": "audit_failed", "error": str(exc)})
        result = run_specialists(evidence, request.agent_ids, on_event=record, should_cancel=cancelled)
        record({"type": "run_completed", "agents_completed": result["agents_completed"], "outreach_sent": False})
        with LOCK:
            store = read_store()
            job = _find_job(store, run_id)
            job.update(status="completed", completed_at=datetime.now(timezone.utc).isoformat())
            sales = next((r for r in result["results"] if r["agent_id"] == "sales"), None)
            if sales:
                approval_id = uuid.uuid4().hex
                store.setdefault("approvals", []).append({
                    "id": approval_id, "action_type": "outreach", "target": evidence["business_name"],
                    "summary": "Review AI-generated sales material before any manual outreach.",
                    "payload": {"run_id": run_id, "sales_output": sales["output"], "qa": result["final_qa"]},
                    "evidence": evidence["verified_observations"], "status": "pending",
                    "created_at": job["completed_at"], "decision": None,
                })
                job["approval_id"] = approval_id
            store.setdefault("runs", []).append({"run_id": run_id, "business_name": evidence["business_name"], "result": result})
            write_store(store)
    except Exception as exc:
        record({"type": "run_failed", "error": str(exc)[:600]})
        with LOCK:
            store = read_store()
            job = _find_job(store, run_id)
            job.update(status="cancelled" if job.get("cancel_requested") else "failed",
                       error=str(exc)[:600], completed_at=datetime.now(timezone.utc).isoformat())
            write_store(store)
    finally:
        RUN_SLOT.release()


@app.post("/api/runs", status_code=202)
def start_run(request: JobInput, authorization: str | None = Header(default=None)):
    require_api_token(authorization)
    try:
        select_agents(request.agent_ids)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    with LOCK:
        store = read_store()
        existing = next((j for j in store.get("jobs", []) if j["request_id"] == request.request_id), None)
        if existing:
            if existing["request"] != request.model_dump():
                raise HTTPException(status_code=409, detail="Request ID already used for different input.")
            return _job_summary(existing)
        if not (os.getenv("AI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")):
            raise HTTPException(status_code=503, detail="AI_API_KEY is not configured on the backend.")
        if not RUN_SLOT.acquire(blocking=False):
            raise HTTPException(status_code=409, detail="A run is already active. Reconnect to it or wait for completion.")
        job = {"run_id": uuid.uuid4().hex, "request_id": request.request_id,
               "request": request.model_dump(), "status": "queued", "events": [], "results": [],
               "created_at": datetime.now(timezone.utc).isoformat(), "outreach_sent": False}
        try:
            store.setdefault("jobs", []).append(job)
            write_store(store)
            WORKER.submit(_execute_job, job["run_id"], request)
        except Exception:
            RUN_SLOT.release()
            raise
        return _job_summary(job)


@app.get("/api/runs/{run_id}")
def get_run(run_id: str, after: int = 0, authorization: str | None = Header(default=None)):
    require_api_token(authorization)
    with LOCK:
        job = _find_job(read_store(), run_id)
        return {**_job_summary(job), "events": [e for e in job["events"] if e["sequence"] > max(0, after)]}


@app.post("/api/runs/{run_id}/cancel")
def cancel_run(run_id: str, authorization: str | None = Header(default=None)):
    require_api_token(authorization)
    with LOCK:
        store = read_store()
        job = _find_job(store, run_id)
        if job["status"] in {"queued", "running"}:
            job["cancel_requested"] = True
            write_store(store)
        return _job_summary(job)


# The same backend URL also serves the phone UI, without extra hosting or CORS.
app.mount("/", StaticFiles(directory=Path(__file__).parent / "dashboard", html=True), name="dashboard")
