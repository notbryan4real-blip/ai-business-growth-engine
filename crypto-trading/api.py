"""Minimal HTTP API for Crypto Nexus. Paper-only; no exchange order endpoints."""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from engine import analyze_market, MarketDataError, AGENTS

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
