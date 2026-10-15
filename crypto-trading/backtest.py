"""Historical, fee-aware, long-only crypto strategy backtest.
Signals are calculated using data available at the candle close and executed at the next candle open.
No look-ahead into future candles; no exchange orders are ever sent.
"""
from __future__ import annotations
import math
from typing import Any

def _sma(xs, n):
    return sum(xs[-n:]) / n if len(xs) >= n else None

def _rsi(xs, n=14):
    if len(xs) <= n: return None
    changes=[xs[i]-xs[i-1] for i in range(len(xs)-n, len(xs))]
    gains=sum(max(x,0) for x in changes)/n
    losses=sum(max(-x,0) for x in changes)/n
    if losses == 0: return 100.0 if gains else 50.0
    return 100 - 100/(1+gains/losses)

def _signal(closes, strategy):
    if len(closes) < 55: return 0
    fast=_sma(closes,20); slow=_sma(closes,50); strength=_rsi(closes)
    momentum=closes[-1]/closes[-6]-1
    if strategy == "sma_momentum":
        return 1 if fast > slow and momentum > 0 and 45 <= strength <= 70 else 0
    if strategy == "sma_cross":
        prior_fast=sum(closes[-21:-1])/20
        prior_slow=sum(closes[-51:-1])/50
        return 1 if fast > slow and prior_fast <= prior_slow else (0 if fast < slow else -1)
    if strategy == "rsi_reversion":
        return 1 if strength < 30 else (0 if strength > 55 else -1)
    raise ValueError("Unsupported strategy")

def _run(candles, strategy, initial_cash, fee_rate, slippage_rate):
    cash=initial_cash; qty=0.0; equity=[]; trades=[]; entry=0.0; wins=0; gross_profit=0.0; gross_loss=0.0
    for i in range(55, len(candles)-1):
        closes=[c["close"] for c in candles[:i+1]]
        sig=_signal(closes, strategy)
        # Equity is marked at current close before the next-bar execution.
        mark=float(candles[i]["close"])
        equity.append({"time":candles[i]["close_time"],"equity":cash+qty*mark})
        next_open=float(candles[i+1]["open"])
        if sig == 1 and qty == 0:
            fill=next_open*(1+slippage_rate)
            spend=cash/(1+fee_rate)
            if spend > 0:
                fee=spend*fee_rate; qty=spend/fill; cash-=spend+fee; entry=fill
                trades.append({"side":"BUY","time":candles[i+1]["open_time"],"price":fill,"fee":fee,"strategy":strategy})
        elif sig <= 0 and qty > 0:
            fill=next_open*(1-slippage_rate)
            proceeds=qty*fill; fee=proceeds*fee_rate
            pnl=proceeds-fee-qty*entry
            if pnl > 0: wins+=1; gross_profit+=pnl
            else: gross_loss+=abs(pnl)
            cash+=proceeds-fee
            trades.append({"side":"SELL","time":candles[i+1]["open_time"],"price":fill,"fee":fee,"realized_pnl":pnl,"strategy":strategy})
            qty=0.0
    last=float(candles[-1]["close"])
    if qty:
        proceeds=qty*last*(1-slippage_rate); fee=proceeds*fee_rate; pnl=proceeds-fee-qty*entry
        if pnl>0: wins+=1; gross_profit+=pnl
        else: gross_loss+=abs(pnl)
        cash+=proceeds-fee
        trades.append({"side":"SELL_END_OF_TEST","time":candles[-1]["close_time"],"price":last*(1-slippage_rate),"fee":fee,"realized_pnl":pnl,"strategy":strategy})
        qty=0.0
    final=cash
    if not equity: equity=[{"time":candles[-1]["close_time"],"equity":final}]
    peak=initial_cash; max_dd=0.0
    for point in equity:
        peak=max(peak,point["equity"])
        if peak: max_dd=max(max_dd,(peak-point["equity"])/peak)
    # Include ending equity in drawdown path.
    peak=max(peak,final)
    max_dd=max(max_dd,(peak-final)/peak if peak else 0)
    total_return=(final/initial_cash-1)*100
    period_returns=[]
    prev=initial_cash
    for point in equity:
        if prev: period_returns.append(point["equity"]/prev-1)
        prev=point["equity"]
    mean=sum(period_returns)/len(period_returns) if period_returns else 0
    variance=sum((x-mean)**2 for x in period_returns)/max(1,len(period_returns)-1) if period_returns else 0
    vol=math.sqrt(variance)
    sharpe=(mean/vol*math.sqrt(365*24) if vol else 0) if len(candles)>300 else (mean/vol*math.sqrt(max(1,len(period_returns))) if vol else 0)
    closed=sum(1 for t in trades if t["side"] in ("SELL","SELL_END_OF_TEST"))
    return {"strategy":strategy,"starting_cash":initial_cash,"ending_equity":round(final,2),"net_return_pct":round(total_return,3),"max_drawdown_pct":round(max_dd*100,3),"closed_trades":closed,"win_rate_pct":round(wins/closed*100,2) if closed else 0,"profit_factor":round(gross_profit/gross_loss,3) if gross_loss else (None if gross_profit==0 else "infinite"),"sharpe_proxy":round(sharpe,3),"fees_and_slippage_included":True,"equity_curve":equity[-500:],"trades":trades[-200:]}

def run_backtest(candles: list[dict[str, Any]], symbol="BTCUSDT", interval="1h", initial_cash=1000.0, fee_bps=10, slippage_bps=5):
    if len(candles)<160: raise ValueError("Need at least 160 historical candles for warm-up and a meaningful holdout.")
    if initial_cash<=0: raise ValueError("initial_cash must be positive")
    if not 0<=fee_bps<=100 or not 0<=slippage_bps<=100: raise ValueError("Fee and slippage must be between 0 and 100 basis points.")
    # Data are ordered oldest-to-newest. Last 30% is held out; parameters are fixed,
    # so this is a temporal holdout rather than a parameter-optimized test.
    split=max(100,int(len(candles)*0.70))
    train=candles[:split]; test=candles[split:]
    strategies=["sma_momentum","sma_cross","rsi_reversion"]
    fee=fee_bps/10000; slip=slippage_bps/10000
    full={s:_run(candles,s,initial_cash,fee,slip) for s in strategies}
    holdout={s:_run(test,s,initial_cash,fee,slip) for s in strategies if len(test)>=160}
    # Buy-and-hold baseline uses same first/last test prices and both-side costs.
    start=float(test[0]["open"])*(1+slip); end=float(test[-1]["close"])*(1-slip)
    buyhold=((end*(1-fee))/(start*(1+fee))-1)*100
    ranked=sorted(full.values(),key=lambda x:x["net_return_pct"],reverse=True)
    return {"mode":"HISTORICAL_BACKTEST_PAPER_ONLY","symbol":symbol.upper(),"interval":interval,"candles":len(candles),"train_candles":len(train),"holdout_candles":len(test),"holdout_start_ms":test[0]["open_time"],"holdout_end_ms":test[-1]["close_time"],"assumptions":{"initial_cash":initial_cash,"fee_bps_per_side":fee_bps,"slippage_bps_per_side":slippage_bps,"long_only":True,"leverage":False,"signal_calculated_at_close_execution_at_next_open":True,"no_parameter_optimization":True},"buy_and_hold_holdout_return_pct":round(buyhold,3),"full_period_results":full,"holdout_results":holdout,"top_full_period_strategy":ranked[0]["strategy"],"profitability_warning":"A positive historical result is not proof of future profitability. Review the untouched holdout, drawdown, trade count, cost assumptions, and robustness across symbols and periods. AI-agent outputs are not evaluated by this deterministic baseline."}
