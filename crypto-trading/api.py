"""Minimal HTTP API for Crypto Nexus. Paper-only; no exchange order endpoints."""
import os
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from engine import analyze_market, fetch_klines, MarketDataError, AGENTS
from ai_pipeline import run_crypto_agents
from backtest import run_backtest

app=FastAPI(title="Crypto Nexus Research API",version="0.2.0",description="Historical strategy evaluation and optional AI-agent research. Paper-only; no real orders.")
app.add_middleware(CORSMiddleware,allow_origins=["*"],allow_methods=["GET"],allow_headers=["*"])

@app.get("/health")
def health():
    return {"status":"ok","mode":"PAPER_ONLY","real_orders_enabled":False,"agent_count":len(AGENTS),"backtest_enabled":True,"ai_key_configured":bool(os.getenv("AI_API_KEY") or os.getenv("ANTHROPIC_API_KEY"))}

@app.get("/api/agents")
def agents():
    return {"mode":"PAPER_ONLY","agents":AGENTS}

@app.get("/api/market")
def market(symbol: str=Query(default="BTCUSDT",max_length=20), interval: str=Query(default="1h")):
    try: return analyze_market(symbol,interval)
    except (ValueError,MarketDataError) as exc: raise HTTPException(status_code=400,detail=str(exc))

@app.get("/api/backtest")
def backtest(symbol: str=Query(default="BTCUSDT",max_length=20), interval: str=Query(default="1h"), limit: int=Query(default=1000,ge=160,le=1000), initial_cash: float=Query(default=1000,gt=0,le=1000000), fee_bps: int=Query(default=10,ge=0,le=100), slippage_bps: int=Query(default=5,ge=0,le=100)):
    """Run deterministic, fee-aware historical strategies with a final temporal holdout."""
    try:
        candles=fetch_klines(symbol,interval,limit)
        return run_backtest(candles,symbol,interval,initial_cash,fee_bps,slippage_bps)
    except (ValueError,MarketDataError) as exc: raise HTTPException(status_code=400,detail=str(exc))

@app.get("/api/ai-analysis")
def ai_analysis(symbol: str=Query(default="BTCUSDT",max_length=20), interval: str=Query(default="1h")):
    """Run 19 paid specialist calls on current data. Analysis only; never trades."""
    if not (os.getenv("AI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")):
        raise HTTPException(status_code=503,detail="AI API is not configured. Add a private server-side AI_API_KEY only when ready to fund model usage.")
    try:
        snapshot=analyze_market(symbol,interval)
        return run_crypto_agents(snapshot)
    except (ValueError,MarketDataError) as exc: raise HTTPException(status_code=400,detail=str(exc))
    except RuntimeError as exc: raise HTTPException(status_code=502,detail=str(exc))

@app.get("/api/ai-backtest")
def ai_backtest(symbol: str=Query(default="BTCUSDT",max_length=20), interval: str=Query(default="1h"), limit: int=Query(default=500,ge=180,le=1000), samples: int=Query(default=3,ge=1,le=10), horizon: int=Query(default=6,ge=1,le=48), fee_bps: int=Query(default=10,ge=0,le=100), slippage_bps: int=Query(default=5,ge=0,le=100)):
    """Bounded historical AI test. Each sample invokes 19 paid model calls; defaults to 57 calls."""
    if not (os.getenv("AI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")):
        raise HTTPException(status_code=503,detail="AI API is not configured. Set a private server-side AI_API_KEY first. No key should be put in the browser or GitHub.")
    try:
        candles=fetch_klines(symbol,interval,limit)
        if len(candles)<180: raise ValueError("Need at least 180 candles.")
        # Spread test points over history; each snapshot only uses candles before that point.
        start=max(60,int(len(candles)*0.55))
        end=len(candles)-horizon-1
        if end<=start: raise ValueError("Not enough candles for requested forward horizon.")
        indices=sorted(set(round(start+(end-start)*i/max(1,samples-1)) for i in range(samples)))
        results=[]
        for idx in indices:
            history=candles[:idx+1]
            closes=[c["close"] for c in history]
            sma20=sum(closes[-20:])/20; sma50=sum(closes[-50:])/50
            changes=[closes[j]/closes[j-1]-1 for j in range(len(closes)-24,len(closes)) if closes[j-1]]
            avg=sum(changes)/len(changes) if changes else 0
            vol=(sum((x-avg)**2 for x in changes)/max(1,len(changes)-1))**0.5*100 if changes else 0
            deltas=[closes[j]-closes[j-1] for j in range(len(closes)-14,len(closes))]
            gains=sum(max(x,0) for x in deltas)/14; losses=sum(max(-x,0) for x in deltas)/14
            rsi=100-100/(1+gains/losses) if losses else (100 if gains else 50)
            mom=(closes[-1]/closes[-6]-1)*100
            signal="LONG_BIAS" if sma20>sma50 and mom>0 and 45<=rsi<=70 else ("DEFENSIVE" if sma20<sma50 and mom<0 and 30<=rsi<=55 else "NO_TRADE")
            snapshot={"mode":"HISTORICAL_SNAPSHOT","symbol":symbol.upper(),"interval":interval,"as_of_ms":history[-1]["close_time"],"last_price":closes[-1],"indicators":{"sma20":sma20,"sma50":sma50,"rsi14":rsi,"momentum_5_candles_pct":mom,"recent_return_volatility_pct":vol},"signal":signal,"confidence":"low","evidence_gaps":["Historical test only contains OHLCV candles; no historical order book, on-chain, news, sentiment, or macro feed."],"decision":"ANALYSIS_ONLY_NO_ORDER"}
            output=run_crypto_agents(snapshot)
            entry=float(candles[idx+1]["open"])*(1+slippage_bps/10000)
            exit_price=float(candles[idx+horizon]["close"])*(1-slippage_bps/10000)
            forward=(exit_price/entry-1)*100 - 2*fee_bps/100
            proposal=output["consensus"]["proposed_signal"]
            if proposal=="LONG_BIAS": strategy_return=forward
            else: strategy_return=0.0
            results.append({"sample":len(results)+1,"as_of_ms":history[-1]["close_time"],"entry_ms":candles[idx+1]["open_time"],"evaluation_end_ms":candles[idx+horizon]["close_time"],"agent_signal":proposal,"long_bias_votes":output["consensus"]["long_bias_votes"],"defensive_votes":output["consensus"]["defensive_votes"],"paper_decision":output["paper_decision"],"forward_buy_return_after_costs_pct":round(forward,4),"signal_strategy_return_pct":round(strategy_return,4),"agents_completed":output["agents_completed"]})
        returns=[x["signal_strategy_return_pct"] for x in results]
        invested=[x["forward_buy_return_after_costs_pct"] for x in results if x["agent_signal"]=="LONG_BIAS"]
        return {"mode":"HISTORICAL_AI_AGENT_EVALUATION_PAPER_ONLY","symbol":symbol.upper(),"interval":interval,"samples_requested":samples,"samples_completed":len(results),"model_calls":len(results)*len(AGENTS),"model":os.getenv("AI_MODEL","claude-haiku-4-5"),"horizon_candles":horizon,"cost_assumptions":{"fee_bps_per_side":fee_bps,"slippage_bps_per_side":slippage_bps},"results":results,"summary":{"long_bias_rate_pct":round(len(invested)/len(results)*100,2),"mean_signal_return_per_sample_pct":round(sum(returns)/len(returns),4),"profitable_long_signals":sum(1 for x in invested if x>0),"long_signals_evaluated":len(invested),"mean_return_when_long_pct":round(sum(invested)/len(invested),4) if invested else None,"buy_and_hold_mean_on_long_samples_pct":round(sum(invested)/len(invested),4) if invested else None},"limitations":["This is a small-sample diagnostic, not a statistically valid profitability claim.","Each sample consumes 19 paid model calls; default 3 samples = 57 calls; maximum 10 samples = 190 calls.","AI models may behave inconsistently between runs. Historical external data are not reconstructed; agents only see the supplied OHLCV snapshot and previous agent outputs.","Signals are evaluated on a fixed forward horizon, without overlapping-position portfolio accounting, so this is not a full deployable strategy backtest.","No exchange orders are placed."],"profitability_warning":"Do not treat a positive sample result as proof of an edge. Repeat across multiple assets and market regimes, then validate on untouched data and paper trade."}
    except (ValueError,MarketDataError) as exc: raise HTTPException(status_code=400,detail=str(exc))
    except RuntimeError as exc: raise HTTPException(status_code=502,detail=str(exc))
