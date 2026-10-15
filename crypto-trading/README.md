# Crypto Nexus — 19-Agent Trading Intelligence

A separate crypto-market analysis project using the same 19-node holographic visual language as Growth Engine.

## Current status
- **UI:** interactive 3D topology and inspectable data-handoff panel.
- **Execution:** handoff packets are illustrative UI simulations, not outputs from 19 live AI calls.
- **Trading:** paper-trading only. No exchange order placement, withdrawals, or private exchange keys.
- **Market feed:** the current visualizer does not yet connect its payload stream to live market feeds or a model backend.
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

## Next engineering milestones
1. Connect a read-only public market-data feed and timestamp every observation.
2. Add a backend API and persist each agent input/output, source, latency, and error.
3. Implement a deterministic paper portfolio with fees, slippage, stop rules, max drawdown, and position limits.
4. Backtest using historical candles without look-ahead bias; report fees, drawdown, Sharpe/Sortino where appropriate, and out-of-sample results.
5. Add the paid model API only after budget approval, with token/cost limits and structured outputs.
6. Consider real exchange execution only after extensive paper trading and explicit separate approval. If ever enabled, use least-privilege trade-only API keys, disable withdrawals, and enforce server-side risk limits.

## Open the visualizer
When the repository's GitHub Pages deployment completes, open `/crypto.html` on the published Pages site.
