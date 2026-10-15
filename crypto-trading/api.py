"""Minimal HTTP API for Crypto Nexus. Paper-only; no exchange order endpoints."""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from engine import analyze_market, MarketDataError, AGENTS
from ai_pipeline import run_crypto_agents

app=FastAPI(title="Crypto Nexus Paper API",version="0.1.0",description="Public market analysis and paper-only trading foundation. No real orders.")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["GET"],allow_headers=["*"])

@app.get("/health")
def health():
    return {"status":"ok","mode":"PAPER_ONLY","real_orders_enabled":False,"agent_count":len(AGENTS)}

@app.get("/api/agents")
def agents():
    return {"mode":"PAPER_ONLY","agents":AGENTS}

@app.get("/api/market")
def market(symbol: str=Query(default="BTCUSDT",max_length=20), interval: str=Query(default="1h")):
    try: return analyze_market(symbol,interval)
    except (ValueError,MarketDataError) as exc: raise HTTPException(status_code=400,detail=str(exc))

@app.get("/api/ai-analysis")
def ai_analysis(symbol: str=Query(default="BTCUSDT",max_length=20), interval: str=Query(default="1h")):
    """Run the 19 paid specialist calls. This endpoint only analyzes; it never trades."""
    import os
    if not (os.getenv("AI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")):
        raise HTTPException(status_code=503,detail="AI API is not configured. Add a private server-side AI_API_KEY only when ready to fund model usage.")
    try:
        market=analyze_market(symbol,interval)
        return run_crypto_agents(market)
    except (ValueError,MarketDataError) as exc:
        raise HTTPException(status_code=400,detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=502,detail=str(exc))
