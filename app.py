from __future__ import annotations
import hmac, json, os, uuid
from pathlib import Path
from threading import Lock
from typing import Any, Literal
from datetime import datetime, timezone
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from agents.runtime import AGENTS, AgentRuntimeError, run_specialists
from agents.prospecting.models import Prospect
from agents.qualification.scoring import score_prospect
from agents.prospecting.google_places import PlacesDiscoveryError, search_places
from agents.prospecting.google_places import PlacesDiscoveryError, search_places

DATA_PATH = Path(os.getenv("GROWTH_ENGINE_DATA_PATH", "data/runtime_store.json"))
LOCK = Lock()
app = FastAPI(title="AI Business Growth Engine API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(","), allow_credentials=False, allow_methods=["GET", "POST", "PUT", "OPTIONS"], allow_headers=["Content-Type", "Authorization"])

class ProspectInput(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=200)
    website_url: str | None = Field(default=None, max_length=1000)
    website_status: Literal["unknown", "listed", "not_listed_unverified", "confirmed_missing"] = "unknown"
    provider_id: str | None = Field(default=None, max_length=300)
    source: str | None = Field(default=None, max_length=100)
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
    except (json.JSONDecodeError, OSError): return {"prospects": [], "runs": []}

def write_store(store: dict[str, Any]) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = DATA_PATH.with_suffix(".tmp")
    temp.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(DATA_PATH)

@app.get("/api/health")
def health():
    return {"status":"ok","service":"growth-engine-api","ai_configured":bool(os.getenv("AI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")),"api_token_configured":bool(os.getenv("APP_API_TOKEN")),"google_places_configured":bool(os.getenv("BUSINESS_DATA_API_KEY") or os.getenv("GOOGLE_MAPS_API_KEY")),"agent_count":len(AGENTS),"persistence":str(DATA_PATH)}

@app.get("/api/agents")
def list_agents():
    return {"agents":AGENTS,"execution_mode":"sequential_specialist_model_calls","outreach_enabled":False}

@app.get("/api/prospects")
def list_prospects():
    with LOCK: return read_store()

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
    """Discover candidate businesses through the configured Google Places API."""
    require_api_token(authorization)
    try:
        candidates = search_places(request.query, max_results=request.max_results)
    except PlacesDiscoveryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    created: list[dict[str, Any]] = []
    duplicates = 0
    with LOCK:
        store = read_store()
        existing = store.setdefault("prospects", [])
        for item in candidates:
            provider_id = item.get("provider_id")
            source_url = item.get("source_url")
            name_key = (item.get("business_name") or "").strip().casefold()
            location_key = (item.get("location") or "").strip().casefold()
            duplicate = any(
                (provider_id and row.get("provider_id") == provider_id)
                or (source_url and row.get("source_url") == source_url)
                or (
                    name_key
                    and location_key
                    and name_key == (row.get("business_name") or "").strip().casefold()
                    and location_key == (row.get("location") or "").strip().casefold()
                )
                for row in existing
            )
            if duplicate:
                duplicates += 1
                continue
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
                source_url=source_url,
            )
            score = score_prospect(model)
            record = {
                **item,
                "id": uuid.uuid4().hex,
                "opportunity_score": score.total,
                "score_factors": score.factors,
                "stage": "research",
                "discovery_query": request.query,
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            }
            existing.append(record)
            created.append(record)
        write_store(store)
    return {
        "status": "completed",
        "provider": "google_places",
        "query": request.query,
        "results_returned": len(candidates),
        "prospects_created": len(created),
        "duplicates_skipped": duplicates,
        "website_absence_verified": False,
        "prospects": created,
        "notice": "A missing website URL in Google Places is unverified, not proof that the business has no website.",
    }


class DiscoveryInput(BaseModel):
    query: str = Field(min_length=3, max_length=300)
    max_results: int = Field(default=10, ge=1, le=20)


@app.post("/api/discovery/search")
def discover_businesses(request: DiscoveryInput, authorization: str | None = Header(default=None)):
    """Discover candidate businesses through the configured Google Places API."""
    require_api_token(authorization)
    try:
        candidates = search_places(request.query, max_results=request.max_results)
    except PlacesDiscoveryError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    created: list[dict[str, Any]] = []
    duplicates = 0
    with LOCK:
        store = read_store()
        existing = store.setdefault("prospects", [])
        for item in candidates:
            provider_id = item.get("provider_id")
            source_url = item.get("source_url")
            name_key = (item.get("business_name") or "").strip().casefold()
            location_key = (item.get("location") or "").strip().casefold()
            duplicate = any(
                (provider_id and row.get("provider_id") == provider_id)
                or (source_url and row.get("source_url") == source_url)
                or (
                    name_key and location_key
                    and name_key == (row.get("business_name") or "").strip().casefold()
                    and location_key == (row.get("location") or "").strip().casefold()
                )
                for row in existing
            )
            if duplicate:
                duplicates += 1
                continue
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
                source_url=source_url,
            )
            score = score_prospect(model)
            record = {
                **item,
                "id": uuid.uuid4().hex,
                "opportunity_score": score.total,
                "score_factors": score.factors,
                "stage": "research",
                "discovery_query": request.query,
                "discovered_at": datetime.now(timezone.utc).isoformat(),
            }
            existing.append(record)
            created.append(record)
        write_store(store)
    return {
        "status": "completed",
        "provider": "google_places",
        "query": request.query,
        "results_returned": len(candidates),
        "prospects_created": len(created),
        "duplicates_skipped": duplicates,
        "website_absence_verified": False,
        "prospects": created,
        "notice": "A missing website URL in Google Places is unverified, not proof that the business has no website.",
    }


@app.post("/api/agents/run")
def run_agents(request: RunInput, authorization: str | None = Header(default=None)):
    require_api_token(authorization)
    evidence=request.prospect.model_dump()
    if not evidence.get("verified_observations") and not evidence.get("notes"):
        evidence["evidence_warning"]="No observations or notes supplied; avoid business-specific claims."
    try: result=run_specialists(evidence,request.agent_ids)
    except AgentRuntimeError as exc: raise HTTPException(status_code=503,detail=str(exc)) from exc
    except ValueError as exc: raise HTTPException(status_code=422,detail=str(exc)) from exc
    run_id=uuid.uuid4().hex; result["run_id"]=run_id
    with LOCK:
        store=read_store(); store["runs"].append({"run_id":run_id,"business_name":evidence["business_name"],"result":result}); write_store(store)
    return result
