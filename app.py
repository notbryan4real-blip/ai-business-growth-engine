from __future__ import annotations
import json, os, uuid
from pathlib import Path
from threading import Lock
from typing import Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from agents.runtime import AGENTS, AgentRuntimeError, run_specialists
from agents.prospecting.models import Prospect
from agents.qualification.scoring import score_prospect

DATA_PATH = Path(os.getenv("GROWTH_ENGINE_DATA_PATH", "data/runtime_store.json"))
LOCK = Lock()
app = FastAPI(title="AI Business Growth Engine API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(","), allow_credentials=False, allow_methods=["GET", "POST", "PUT", "OPTIONS"], allow_headers=["Content-Type", "Authorization"])

class ProspectInput(BaseModel):
    business_name: str = Field(min_length=1, max_length=200)
    category: str | None = Field(default=None, max_length=100)
    location: str | None = Field(default=None, max_length=200)
    website_url: str | None = Field(default=None, max_length=1000)
    source_url: str | None = Field(default=None, max_length=1000)
    rating: float | None = Field(default=None, ge=0, le=5)
    review_count: int = Field(default=0, ge=0)
    website_quality_score: int | None = Field(default=None, ge=0, le=100)
    social_urls: list[str] = Field(default_factory=list, max_length=20)
    verified_observations: list[str] = Field(default_factory=list, max_length=30)
    notes: list[str] = Field(default_factory=list, max_length=30)

class RunInput(BaseModel):
    prospect: ProspectInput
    agent_ids: list[str] = Field(default_factory=lambda: [a["id"] for a in AGENTS], max_length=6)

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
    return {"status":"ok","service":"growth-engine-api","ai_configured":bool(os.getenv("AI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")),"agent_count":len(AGENTS),"persistence":str(DATA_PATH)}

@app.get("/api/agents")
def list_agents():
    return {"agents":AGENTS,"execution_mode":"sequential_specialist_model_calls","outreach_enabled":False}

@app.get("/api/prospects")
def list_prospects():
    with LOCK: return read_store()

@app.post("/api/prospects")
def create_prospect(p: ProspectInput):
    record=p.model_dump()
    model=Prospect(business_name=record["business_name"],category=record["category"],location=record["location"],website_url=record["website_url"],source_url=record["source_url"],rating=record["rating"],review_count=record["review_count"],website_quality_score=record["website_quality_score"],social_urls=record["social_urls"],notes=record["notes"]+record["verified_observations"])
    model.validate()
    score=score_prospect(model)
    record.update({"id":uuid.uuid4().hex,"opportunity_score":score.total,"score_factors":score.factors,"stage":"research"})
    with LOCK:
        store=read_store(); store["prospects"].append(record); write_store(store)
    return record

@app.post("/api/agents/run")
def run_agents(request: RunInput):
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
