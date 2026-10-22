"""Paper-only fills, conservative costs and persistent circuit breakers."""
from datetime import timedelta

from .models import dt, iso, now


def initial(cash):
    return {"initial_cash": cash, "cash": cash, "positions": {}, "trades": [], "equity": cash,
            "peak_equity": cash, "max_drawdown_pct": 0, "fees_paid": 0, "realized_pnl": 0,
            "day": None, "day_start_equity": cash, "halted": False, "halt_reason": None, "curve": []}


def fresh(q, at):
    return q and -30 <= (at - dt(q["quote_at"])).total_seconds() <= 300 and q["bid"] > 0 and q["ask"] >= q["bid"]


def mark(book, quotes, cfg, at):
    missing = []
    value = book["cash"]
    for asset, pos in book["positions"].items():
        q = quotes.get(asset)
        if fresh(q, at):
            pos["last_mark"] = q["bid"] * (1-cfg["slippage_bps"]/10000) * (1-cfg["fee_bps"]/10000)
        else:
            missing.append(asset)
        value += pos["qty"] * pos["last_mark"]
    book["equity"] = value
    book["peak_equity"] = max(book["peak_equity"], value)
    dd = 100 * (1 - value/book["peak_equity"]) if book["peak_equity"] else 0
    book["max_drawdown_pct"] = max(book["max_drawdown_pct"], dd)
    # On a new UTC day, the previous mark is the starting equity, avoiding loss resets at the new mark.
    if book["day"] != at.date().isoformat():
        book["day"] = at.date().isoformat()
        book["day_start_equity"] = book["curve"][-1]["equity"] if book["curve"] else book["initial_cash"]
    loss = 100 * (1 - value/book["day_start_equity"]) if book["day_start_equity"] else 0
    if dd >= cfg["max_drawdown_pct"] or loss >= cfg["daily_loss_pct"]:
        book["halted"] = True
        book["halt_reason"] = "Maximum drawdown reached" if dd >= cfg["max_drawdown_pct"] else "Daily loss limit reached"
    return missing


def trade_id(run_id, asset, side):
    return f"{run_id}:{asset}:{side}"


def step(book, decisions, quotes, cfg, run_id, at=None, allow_entries=True):
    """Called inside the same SQLite transaction as run completion; retries cannot duplicate fills."""
    at = at or now()
    fee, slip = cfg["fee_bps"]/10000, cfg["slippage_bps"]/10000
    missing = mark(book, quotes, cfg, at)
    actions, blocked = [], []
    by_asset = {d["asset"]: d for d in decisions}
    exited = set()
    for asset, pos in list(book["positions"].items()):
        q = quotes.get(asset)
        if not fresh(q, at):
            blocked.append(asset+": cannot mark or exit on a stale/missing quote")
            continue
        fill = q["bid"]*(1-slip)
        change = 100*(fill/pos["entry_price"]-1)
        age = (at-dt(pos["opened_at"])).total_seconds()/3600
        reason = ("risk_halt" if book["halted"] else "stop_loss" if change <= -cfg["stop_loss_pct"] else
                  "take_profit" if change >= cfg["take_profit_pct"] else "time_exit" if age >= cfg["max_hold_hours"] else
                  "signal_exit" if by_asset.get(asset, {}).get("action") != "paper_candidate" else None)
        if reason:
            proceeds = pos["qty"]*fill
            charge = proceeds*fee
            pnl = proceeds-charge-pos["cost_basis"]
            book["cash"] += proceeds-charge
            book["fees_paid"] += charge
            book["realized_pnl"] += pnl
            action = {"id": trade_id(run_id, asset, "sell"), "asset": asset, "side": "sell", "at": iso(at),
                      "price": fill, "qty": pos["qty"], "fee": charge, "pnl": pnl, "reason": reason}
            actions.append(action)
            del book["positions"][asset]
            exited.add(asset)
    mark(book, quotes, cfg, at)
    for d in sorted(decisions, key=lambda d: d["score"], reverse=True):
        asset = d["asset"]
        if d["action"] != "paper_candidate" or asset in book["positions"] or asset in exited:
            continue
        q = quotes.get(asset)
        if cfg["paused"] or book["halted"] or not allow_entries or missing:
            blocked.append(asset+": entries paused, vetoed, or portfolio quotes incomplete")
            continue
        if not fresh(q, at) or q.get("spread_bps", 10000) > 50 or q.get("volume_24h", 0)*q.get("price", 0) < 1_000_000:
            blocked.append(asset+": quote freshness, spread or liquidity gate failed")
            continue
        equity = book["equity"]
        invested = sum(p["qty"]*p["last_mark"] for p in book["positions"].values())
        budget = min(equity*cfg["position_cap_pct"]/100,
                     max(0, equity*cfg["exposure_cap_pct"]/100-invested),
                     equity*cfg["risk_per_trade_pct"]/100 / ((cfg["stop_loss_pct"]+2*(cfg["fee_bps"]+cfg["slippage_bps"])/100)/100),
                     book["cash"])
        if budget < 5:
            blocked.append(asset+": remaining paper allocation is below $5")
            continue
        fill = q["ask"]*(1+slip)
        notional = budget/(1+fee)
        charge, qty = notional*fee, notional/fill
        book["cash"] -= budget
        book["fees_paid"] += charge
        book["positions"][asset] = {"qty": qty, "entry_price": fill, "cost_basis": budget, "opened_at": iso(at),
                                     "last_mark": q["bid"]*(1-slip)*(1-fee), "run_id": run_id}
        actions.append({"id": trade_id(run_id, asset, "buy"), "asset": asset, "side": "buy", "at": iso(at),
                        "price": fill, "qty": qty, "fee": charge, "reason": "two_strategy_agreement"})
        mark(book, quotes, cfg, at)
    book["trades"].extend(actions)
    # Retain complete trade history; bounded by the service's total-run cap.
    mark(book, quotes, cfg, at)
    book["curve"].append({"at": iso(at), "equity": book["equity"], "quotes_complete": not missing})
    book["curve"] = book["curve"][-3000:]
    return {"trades": actions, "blocked": blocked, "stale_positions": missing, "equity": book["equity"], "halted": book["halted"]}
