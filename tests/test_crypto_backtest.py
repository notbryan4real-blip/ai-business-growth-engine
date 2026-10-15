from pathlib import Path
import math
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "crypto-trading"))
from backtest import run_backtest


def synthetic_candles(n=800):
    rows=[]
    for i in range(n):
        # Deterministic mixed trend keeps the test independent of network data.
        close=100 + 0.025*i + 8*math.sin(i/13) + 2*math.sin(i/4)
        open_price=close*(1 + 0.001*math.sin(i))
        rows.append({
            "open_time": i*3600000,
            "open": open_price,
            "high": max(open_price,close)*1.01,
            "low": min(open_price,close)*0.99,
            "close": close,
            "volume": 1000.0,
            "close_time": (i+1)*3600000-1,
        })
    return rows


def test_backtest_returns_holdout_and_cost_assumptions():
    result=run_backtest(synthetic_candles(), initial_cash=1000, fee_bps=10, slippage_bps=5)
    assert result["mode"] == "HISTORICAL_BACKTEST_PAPER_ONLY"
    assert result["candles"] == 800
    assert result["holdout_candles"] >= 160
    assert result["assumptions"]["fee_bps_per_side"] == 10
    assert result["assumptions"]["slippage_bps_per_side"] == 5
    assert set(result["full_period_results"]) == {"sma_momentum", "sma_cross", "rsi_reversion"}
    assert set(result["holdout_results"]) == {"sma_momentum", "sma_cross", "rsi_reversion"}
    for stats in result["full_period_results"].values():
        assert "net_return_pct" in stats
        assert "max_drawdown_pct" in stats
        assert stats["max_drawdown_pct"] >= 0


def test_backtest_rejects_too_few_candles():
    try:
        run_backtest(synthetic_candles(100))
    except ValueError as exc:
        assert "160" in str(exc)
    else:
        raise AssertionError("Expected insufficient-history validation")
