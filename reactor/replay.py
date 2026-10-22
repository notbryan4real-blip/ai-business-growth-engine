"""Event-time replay with untouched holdout, next-open entries and both-side costs."""
from .models import iso
from .paper import initial, step
from .strategies import evaluate


def run_replay(request):
    candles = request.candles
    events = [e.model_dump(mode="json") for e in request.events]
    cfg = request.settings.model_dump()
    cfg.update(paused=False, automatic_paper=False)
    split = max(1, int(len(candles)*.7))

    def run(start):
        book = initial(cfg["initial_cash"])
        for index in range(max(1, start), len(candles)):
            candle, previous = candles[index], candles[index-1]
            # No event first observed after the preceding candle closes can influence this entry.
            assessment = evaluate(events, previous.close_at)
            def q(price, timestamp):
                return {request.asset: {"bid": price, "ask": price, "price": price,
                        "quote_at": iso(timestamp), "volume_24h": 1e12, "spread_bps": 0}}
            step(book, assessment["decisions"], q(candle.open, candle.open_at), cfg,
                 "replay-"+str(index), candle.open_at)
            position = book["positions"].get(request.asset)
            # Conservative OHLC exit: adverse stop wins when stop and target both occur in a bar.
            # No second entry inside the same candle. Opening gaps were already handled above.
            if position:
                stop = position["entry_price"]*(1-cfg["stop_loss_pct"]/100)
                target = position["entry_price"]*(1+cfg["take_profit_pct"]/100)
                exit_price = stop if candle.low <= stop else target if candle.high >= target else None
                if exit_price:
                    # Explicit signal exit forces the conservative threshold fill with sell costs.
                    out = step(book, [], q(exit_price, candle.close_at), cfg, "bar-exit-"+str(index), candle.close_at, False)
                    for trade in out["trades"]:
                        trade["reason"] = "intrabar_stop" if candle.low <= stop else "intrabar_target"
            # Include each close in the marked equity path, not only next-bar opens.
            step(book, assessment["decisions"], q(candle.close, candle.close_at), cfg,
                 "close-"+str(index), candle.close_at, False)
        last = candles[-1]
        step(book, [], {request.asset: {"bid": last.close, "ask": last.close, "price": last.close,
            "quote_at": iso(last.close_at), "volume_24h": 1e12, "spread_bps": 0}}, cfg, "end", last.close_at, False)
        closed = [t for t in book["trades"] if t["side"] == "sell"]
        wins = sum(t["pnl"] > 0 for t in closed)
        gain = sum(max(0, t["pnl"]) for t in closed)
        loss = sum(max(0, -t["pnl"]) for t in closed)
        f, s = cfg["fee_bps"]/10000, cfg["slippage_bps"]/10000
        entry = candles[max(1, start)].open
        baseline = cfg["initial_cash"]/(1+f)/(entry*(1+s))*last.close*(1-s)*(1-f)
        return {"starting_cash": cfg["initial_cash"], "ending_equity": round(book["equity"], 4),
                "net_pnl": round(book["equity"]-cfg["initial_cash"], 4), "fees_paid": round(book["fees_paid"], 4),
                "max_drawdown_pct": round(book["max_drawdown_pct"], 3), "closed_trades": len(closed),
                "win_rate_pct": round(100*wins/len(closed), 2) if closed else None,
                "profit_factor": round(gain/loss, 3) if loss else None,
                "buy_hold_net_pnl": round(baseline-cfg["initial_cash"], 4),
                "curve": book["curve"], "trades": book["trades"], "halted": book["halted"]}
    full, holdout = run(1), run(split)
    return {"mode": "event_time_replay_paper_only", "asset": request.asset, "parameters_optimized": False,
            "holdout_start": iso(candles[split].open_at), "holdout_candles": len(candles)-split,
            "full_period": full, "holdout": holdout, "settings": cfg,
            "conclusion": "Insufficient trade evidence" if holdout["closed_trades"] < 30 else "Research result; independent forward validation still required",
            "assumptions": ["Inputs are owner-supplied; their authenticity and point-in-time availability are not independently certified.",
                "Signals use published/observed timestamps and enter at the next candle open. No parameter fitting on the holdout.",
                "Fees and slippage apply to both sides; stops lose priority to opening gaps and win priority over intrabar targets.",
                "Intrabar exit times are only known to the candle interval. Spread, depth and liquidity are not measured in this replay.",
                "Protocol history fetched today cannot serve as historical event evidence unless archived availability times exist.",
                "Buy-and-hold uses all capital; the strategy uses capped positions. P&L is paper, never business revenue."]}
