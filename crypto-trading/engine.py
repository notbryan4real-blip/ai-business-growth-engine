"""Crypto Nexus research engine — safe-by-default paper-trading foundation.

No private exchange credentials, order placement, or withdrawals are implemented.
Public market candles are used for analysis; any order is a local paper-trade record.
"""
from __future__ import annotations
import json, math, os, time, urllib.parse, urllib.request
from dataclasses import dataclass, asdict
from typing import Any

BINANCE_BASE = os.getenv("MARKET_DATA_BASE_URL", "https://api.binance.com")
SYMBOL_DEFAULT = "BTCUSDT"
INTERVAL_DEFAULT = "1h"
PAPER_ONLY = True

AGENTS = [
 {"id":"orchestrator","name":"Executive Orchestrator","role":"sequence the workflow and preserve evidence lineage"},
 {"id":"market_data","name":"Market Data Ingestion","role":"fetch and timestamp public market candles"},
 {"id":"momentum","name":"Trend & Momentum","role":"measure trend direction and momentum"},
 {"id":"volatility","name":"Volatility Regime","role":"measure volatility and unstable regimes"},
 {"id":"liquidity","name":"Order Book & Liquidity","role":"evaluate spread and liquidity when data exists"},
 {"id":"onchain","name":"On-chain Intelligence","role":"evaluate verified on-chain inputs when configured"},
 {"id":"sentiment","name":"Sentiment Analysis","role":"summarize timestamped sentiment inputs"},
 {"id":"macro","name":"Macro Correlation","role":"evaluate supplied cross-asset context"},
 {"id":"technical","name":"Technical Analysis","role":"compute indicators from candles"},
 {"id":"quant","name":"Quant Strategy","role":"create explicit testable strategy hypotheses"},
 {"id":"ensemble","name":"Signal Ensemble","role":"aggregate signals and preserve disagreement"},
 {"id":"allocation","name":"Portfolio Allocation","role":"propose exposure limits"},
 {"id":"risk","name":"Risk Manager","role":"veto proposals outside risk limits"},
 {"id":"sizing","name":"Position Sizing","role":"size positions from fixed risk budget"},
 {"id":"execution","name":"Trade Execution Planner","role":"plan paper orders only"},
 {"id":"costs","name":"Slippage & Fees","role":"model costs and uncertainty"},
 {"id":"backtest","name":"Backtest & Validation","role":"validate on historical data"},
 {"id":"guardrails","name":"Compliance & Guardrails","role":"enforce paper-only mode and key safety"},
 {"id":"audit","name":"Final Trade Auditor","role":"record rationale and checks"},
]

class MarketDataError(RuntimeError): pass

def fetch_klines(symbol: str = SYMBOL_DEFAULT, interval: str = INTERVAL_DEFAULT, limit: int = 200) -> list[dict[str, Any]]:
    """Fetch public Binance candles. This uses no account key and cannot trade."""
    symbol = symbol.upper()
    if not symbol.isalnum() or len(symbol) > 20:
        raise ValueError("Invalid market symbol")
    if interval not in {"1m","3m","5m","15m","30m","1h","2h","4h","6h","8h","12h","1d","3d","1w"}:
        raise ValueError("Unsupported candle interval")
    limit = max(50, min(int(limit), 1000))
    query = urllib.parse.urlencode({"symbol": symbol, "interval": interval, "limit": limit})
    req = urllib.request.Request(f"{BINANCE_BASE}/api/v3/klines?{query}", headers={"User-Agent":"CryptoNexus-Paper/0.1"})
    try:
        with urllib.request.urlopen(req, timeout=12) as res:
            rows = json.loads(res.read().decode("utf-8"))
    except Exception as exc:
        raise MarketDataError(f"Public market-data request failed: {exc}") from exc
    if not isinstance(rows, list) or not rows:
        raise MarketDataError("Market-data provider returned no candles")
    return [{"open_time":int(r[0]),"open":float(r[1]),"high":float(r[2]),"low":float(r[3]),"close":float(r[4]),"volume":float(r[5]),"close_time":int(r[6])} for r in rows]

def sma(values: list[float], period: int) -> float:
    if len(values) < period: raise ValueError(f"Need at least {period} values")
    return sum(values[-period:]) / period

def rsi(values: list[float], period: int = 14) -> float:
    if len(values) <= period: raise ValueError("Not enough values for RSI")
    gains=[]; losses=[]
    for a,b in zip(values[-period-1:-1], values[-period:]):
        change=b-a; gains.append(max(change,0)); losses.append(max(-change,0))
    avg_gain=sum(gains)/period; avg_loss=sum(losses)/period
    if avg_loss == 0: return 100.0 if avg_gain else 50.0
    return 100 - (100 / (1 + avg_gain/avg_loss))

def analyze_market(symbol: str = SYMBOL_DEFAULT, interval: str = INTERVAL_DEFAULT) -> dict[str, Any]:
    candles=fetch_klines(symbol, interval, 200)
    closes=[c["close"] for c in candles]
    last=closes[-1]; fast=sma(closes,20); slow=sma(closes,50); momentum=(closes[-1]/closes[-6]-1)*100
    returns=[(b/a-1) for a,b in zip(closes[-25:-1],closes[-24:]) if a]
    volatility=(sum((x-sum(returns)/len(returns))**2 for x in returns)/max(1,len(returns)-1))**0.5*100 if returns else 0
    strength=rsi(closes)
    if fast > slow and momentum > 0 and 45 <= strength <= 70: signal="LONG_BIAS"
    elif fast < slow and momentum < 0 and 30 <= strength <= 55: signal="DEFENSIVE"
    else: signal="NO_TRADE"
    return {
      "mode":"PAPER_ONLY","symbol":symbol.upper(),"interval":interval,
      "as_of_ms":candles[-1]["close_time"],"last_price":last,
      "indicators":{"sma20":fast,"sma50":slow,"rsi14":strength,"momentum_5_candles_pct":momentum,"recent_return_volatility_pct":volatility},
      "signal":signal,"confidence":"low",
      "evidence_gaps":["No order-book feed","No on-chain provider","No news/sentiment provider","No backtest or out-of-sample validation in this response"],
      "decision":"ANALYSIS_ONLY_NO_ORDER",
      "disclaimer":"A simple indicator rule is not a validated profitable strategy. This result is not a prediction or guarantee."
    }

@dataclass
class PaperPosition:
    symbol: str
    side: str
    quantity: float
    entry_price: float
    entry_fee: float
    opened_at: float

class PaperPortfolio:
    """Tiny in-memory ledger for demo/testing; no exchange orders are sent."""
    def __init__(self, cash: float = 1000.0, fee_rate: float = 0.001, max_risk_fraction: float = 0.005):
        if cash <= 0 or not (0 <= fee_rate < 0.1) or not (0 < max_risk_fraction <= 0.01):
            raise ValueError("Invalid paper portfolio risk parameters")
        self.starting_cash=cash; self.cash=cash; self.fee_rate=fee_rate
        self.max_risk_fraction=max_risk_fraction; self.positions=[]; self.ledger=[]
    def paper_buy(self, symbol: str, price: float, notional: float) -> dict[str, Any]:
        if not PAPER_ONLY: raise RuntimeError("Safety invariant violated")
        if price <= 0 or notional <= 0: raise ValueError("Price and notional must be positive")
        notional=min(notional, self.cash/(1+self.fee_rate))
        if notional <= 0: raise ValueError("Insufficient paper cash")
        fee=notional*self.fee_rate; qty=notional/price
        self.cash-=notional+fee
        p=PaperPosition(symbol.upper(),"LONG",qty,price,fee,time.time()); self.positions.append(p)
        event={"mode":"PAPER_ONLY","type":"PAPER_BUY","symbol":p.symbol,"quantity":qty,"price":price,"notional":notional,"fee":fee,"cash_after":self.cash,"timestamp":p.opened_at}
        self.ledger.append(event); return event
    def snapshot(self, prices: dict[str,float] | None = None) -> dict[str, Any]:
        prices=prices or {}; market_value=sum(p.quantity*prices.get(p.symbol,p.entry_price) for p in self.positions)
        return {"mode":"PAPER_ONLY","starting_cash":self.starting_cash,"cash":self.cash,"positions":[asdict(p) for p in self.positions],"market_value":market_value,"equity":self.cash+market_value,"realized_ledger":self.ledger[-100:],"real_orders_enabled":False}

if __name__ == "__main__":
    print(json.dumps(analyze_market(), indent=2))
