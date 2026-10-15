# Crypto Nexus — AI-Agent Trading Research & Backtesting

Crypto Nexus is a **paper-only research system**. It evaluates simple benchmark strategies against historical candles and provides a bounded endpoint to test the 19-agent AI pipeline's directional calls on historical snapshots. It does not place exchange orders.

## What is implemented in the repository

- Public, read-only OHLCV candle ingestion from Binance.
- Three transparent benchmark rules: SMA/momentum filter, SMA crossover, and RSI mean reversion.
- Fee/slippage-aware backtests with a chronological 70/30 train/holdout split, next-candle-open execution, no leverage, and metrics including net return, maximum drawdown, closed trades, win rate, profit factor, and a Sharpe-like diagnostic.
- /api/ai-backtest: bounded historical snapshots evaluated by the real 19-call Anthropic agent pipeline. Every sample uses only candles available at that timestamp, then evaluates the consensus signal over a fixed forward horizon.
- API health and key-configuration status.
- Paper-only guardrails. There is no exchange execution client.

**Important deployment status:** these backend files are committed in GitHub, but the API must be deployed to a Python web-service host and configured with a private server-side AI key before live AI-agent tests can run. GitHub Pages alone cannot host this Python API. Do not mistake the visual demo for a running backend.

## API endpoints

- GET /health — service health, 19-agent count, AI-key-configured boolean.
- GET /api/agents — agent roster.
- GET /api/market?symbol=BTCUSDT&interval=1h — current indicator snapshot.
- GET /api/backtest?symbol=BTCUSDT&interval=1h&limit=1000&fee_bps=10&slippage_bps=5 — deterministic strategy benchmarks.
- GET /api/ai-analysis?symbol=BTCUSDT&interval=1h — one current 19-agent analysis run.
- GET /api/ai-backtest?symbol=BTCUSDT&interval=1h&limit=500&samples=3&horizon=6 — historical AI evaluation.

## Deploy the API

A Render blueprint is defined in the repository root render.yaml. Deploy it from Render's Blueprint flow using the repository link below. Review the proposed services carefully before confirming; the blueprint also defines the existing Growth Engine API service. Alternatively, create only a separate web service from this repository with root directory crypto-trading.\n\nUse a Python web service such as Render:
- Root directory: crypto-trading
- Build command: pip install -r requirements.txt
- Start command: uvicorn api:app --host 0.0.0.0 --port $PORT
- Health-check path: /health

The Render blueprint creates a private APP_API_TOKEN automatically to protect paid AI endpoints. Copy that token from the Render service's environment page and paste it into the research UI's token field; the page sends it only as an X-API-Token request header and does not persist it. Add AI_API_KEY or ANTHROPIC_API_KEY as a **private server-side environment variable** only when you are ready to pay for AI calls. Never place the model key in the HTML, browser storage, query string, or GitHub. Choose a model in AI_MODEL if desired. AI endpoints remain disabled until a model key is configured.

## AI test cost and interpretation

Each historical AI sample invokes 19 model calls. The default samples=3 makes **57 model calls**; the maximum samples=10 makes **190 calls**. Model usage may cost money. Start with the deterministic /api/backtest endpoint before enabling paid AI calls.

The AI historical endpoint is a bounded diagnostic, not a production-grade portfolio simulator. It reports the 19-agent consensus signal at selected timestamps and measures a fixed forward horizon after assumed fees/slippage. It does not reconstruct historical news, sentiment, order book, or on-chain feeds, and it does not simulate a continuous overlapping portfolio. AI outputs can vary across runs. A positive result on a small sample is not proof of profitability.

Before considering any live trading, require large out-of-sample tests across multiple assets and market regimes, realistic fee/slippage and spread assumptions, robustness checks, a continuous paper-trading period, and strict server-side risk limits. No private exchange credentials are needed for the current research endpoints. No real orders or withdrawals are supported.

## 19 specialists

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
