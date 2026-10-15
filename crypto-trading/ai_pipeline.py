"""Optional 19-call Anthropic agent pipeline for Crypto Nexus.

This pipeline only analyzes public market data and produces a paper-trade proposal.
It has no exchange client and cannot submit orders or withdraw funds.
Each invocation can make up to 19 paid model calls; endpoint is disabled without a key.
"""
from __future__ import annotations
import json, os, urllib.error, urllib.request
from typing import Any
from engine import AGENTS

SYSTEM = """You are one specialist in a crypto market research workflow. Use only the supplied public market snapshot and earlier agent outputs. Never claim to have data that is absent. Treat price patterns as uncertain; do not promise profit. Do not give instructions to place a real exchange order. Your output must be valid JSON with keys: summary (string), findings (array of strings), risks (array of strings), signal (one of LONG_BIAS, DEFENSIVE, NO_TRADE, UNKNOWN), confidence (low, medium, high), evidence_gaps (array of strings), next_actions (array of strings). If evidence is insufficient, prefer NO_TRADE or UNKNOWN."""

def _call(agent: dict[str, str], market: dict[str, Any], prior: list[dict[str, Any]]) -> tuple[dict[str, Any], str]:
    key = os.getenv("AI_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("AI_API_KEY is not configured. Add it as a private hosting environment variable only when ready to fund model usage.")
    model = os.getenv("AI_MODEL", "claude-haiku-4-5")
    user = {
        "agent": agent,
        "market_snapshot": market,
        "prior_handoffs": prior[-5:],
        "instruction": "Perform this specialist role only. Return a concise evidence-based handoff. This is analysis only; no real trading."
    }
    body = {"model": model, "max_tokens": 500, "system": SYSTEM, "messages": [{"role": "user", "content": json.dumps(user)}]}
    req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=json.dumps(body).encode(),
      headers={"content-type":"application/json","x-api-key":key,"anthropic-version":"2023-06-01"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=35) as res:
            response = json.loads(res.read().decode())
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:350]
        raise RuntimeError(f"AI provider HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise RuntimeError(f"AI provider request failed: {exc}") from exc
    raw = "\n".join(x.get("text","") for x in response.get("content",[]) if x.get("type")=="text").strip()
    try: output=json.loads(raw)
    except json.JSONDecodeError as exc: raise RuntimeError(f"{agent['name']} returned invalid JSON") from exc
    required={"summary","findings","risks","signal","confidence","evidence_gaps","next_actions"}
    if not required.issubset(output): raise RuntimeError(f"{agent['name']} omitted required fields")
    if output["signal"] not in {"LONG_BIAS","DEFENSIVE","NO_TRADE","UNKNOWN"}: output["signal"]="UNKNOWN"
    return output, model

def run_crypto_agents(market: dict[str, Any]) -> dict[str, Any]:
    """Run all 19 specialist model calls sequentially, collecting handoff events."""
    results=[]; handoffs=[]
    for index, agent in enumerate(AGENTS):
        output, model = _call(agent, market, results)
        record={"sequence":index+1,"agent_id":agent["id"],"name":agent["name"],"model":model,"output":output}
        results.append(record)
        handoffs.append({
          "transfer_id":f"TX-{index+1:04d}",
          "event":"MARKET_ANALYSIS_HANDOFF" if index else "MARKET_TASK_DISPATCH",
          "source":results[index-1]["name"] if index else "Market Data API",
          "target":agent["name"],
          "payload":{"market":market.get("symbol"),"as_of_ms":market.get("as_of_ms"),"previous_summary":results[index-1]["output"]["summary"] if index else "Analyze supplied market snapshot","signal":output["signal"],"confidence":output["confidence"],"risk_count":len(output["risks"]),"evidence_gap_count":len(output["evidence_gaps"])},
          "status":"completed"
        })
    risk = next((r["output"] for r in results if r["agent_id"]=="risk"), None)
    guard = next((r["output"] for r in results if r["agent_id"]=="guardrails"), None)
    final = results[-1]["output"]
    consensus = [r["output"]["signal"] for r in results if r["output"]["signal"] in {"LONG_BIAS","DEFENSIVE","NO_TRADE"}]
    long_count=consensus.count("LONG_BIAS"); defensive_count=consensus.count("DEFENSIVE")
    proposed="LONG_BIAS" if long_count>=14 else ("DEFENSIVE" if defensive_count>=14 else "NO_TRADE")
    veto = bool((risk and risk["signal"] in {"DEFENSIVE","NO_TRADE","UNKNOWN"}) or (guard and guard["signal"]!="LONG_BIAS"))
    return {
      "status":"completed","mode":"PAPER_ONLY","real_orders_enabled":False,
      "agents_requested":len(AGENTS),"agents_completed":len(results),"model":os.getenv("AI_MODEL","claude-haiku-4-5"),
      "consensus":{"proposed_signal":proposed,"long_bias_votes":long_count,"defensive_votes":defensive_count,"total_classified":len(consensus)},
      "paper_decision":"NO_TRADE" if veto or proposed!="LONG_BIAS" else "PAPER_REVIEW_REQUIRED",
      "risk_veto":veto,"results":results,"handoffs":handoffs,
      "disclaimer":"Model outputs are fallible and not evidence of profitability. No orders were placed. Validate with backtests and paper trading."
    }
