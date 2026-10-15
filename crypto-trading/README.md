# Crypto Nexus — 19-Agent Trading Intelligence

A separate crypto-market analysis project using the same 19-node holographic visual language as Growth Engine.

## Current status
- **UI:** interactive 3D topology and inspectable data-handoff panel.
- **Execution:** handoff packets are illustrative UI simulations, not outputs from 19 live AI calls.
- **Trading:** paper-trading only. No exchange order placement, withdrawals, or private exchange keys.
- **Market feed:** the dashboard reads a public, read-only BTC/USDT 24-hour ticker. The 3D handoff stream remains a demo visualization until connected to the backend's actual handoff events.
- **Not financial advice:** a visual signal or model consensus is not proof of profitability.

## Agent roster
1. Executive Orchestrator
2. Market Data Ingestion
3. Trend & Momentum
4. Volatility Regime
5. Order Book & Liquidity
6. On-chain Intelligence
7. Sentiment Analysis
8. Macro Correlation
9. Technical Analysis
10. Quant Strategy
11. Signal Ensemble
12. Portfolio Allocation
13. Risk Manager
14. Position Sizing
15. Trade Execution Planner
16. Slippage & Fees
17. Backtest & Validation
18. Compliance & Guardrails
19. Final Trade Auditor

## Run the backend

Deploy the `crypto-trading/` folder as a separate web service (for example, on Render):
- Root directory: `crypto-trading`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn api:app --host 0.0.0.0 --port $PORT`
- Health check: `/health`
- Public market analysis: `/api/market?symbol=BTCUSDT&interval=1h`
- Agent roster: `/api/agents`
- Paid 19-agent analysis: `/api/ai-analysis?symbol=BTCUSDT&interval=1h`

The 19-agent endpoint is disabled until `AI_API_KEY` or `ANTHROPIC_API_KEY` is added as a **private server-side environment variable**. One analysis can make up to 19 paid model calls. Do not place keys in the browser, GitHub source, or a public dashboard. The endpoint never places orders.

## Next engineering milestones
1. Connect a read-only public market-data feed and timestamp every observation.
2. Add a backend API and persist each agent input/output, source, latency, and error.
3. Implement a deterministic paper portfolio with fees, slippage, stop rules, max drawdown, and position limits.
4. Backtest using historical candles without look-ahead bias; report fees, drawdown, Sharpe/Sortino where appropriate, and out-of-sample results.
5. Add the paid model API only after budget approval, with token/cost limits and structured outputs.
6. Consider real exchange execution only after extensive paper trading and explicit separate approval. If ever enabled, use least-privilege trade-only API keys, disable withdrawals, and enforce server-side risk limits.

## Open the visualizer
When the repository's GitHub Pages deployment completes, open `/crypto.html` on the published Pages site.
