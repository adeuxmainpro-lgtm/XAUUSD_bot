"""
Performance analytics router.
Provides win rate stats by session, pattern, regime, Wyckoff phase,
plus Sharpe ratio, profit factor, and backtesting results.
"""
import logging
from fastapi import APIRouter, BackgroundTasks
from datetime import datetime, timezone

from backend.services.ml_engine import analyze_trade_performance
from backend.services.backtest_engine import run_backtest

router = APIRouter()
logger = logging.getLogger(__name__)

# Simple in-memory cache (1h TTL for backtest, 10min for performance)
_perf_cache:    dict | None = None
_perf_ts:       datetime | None = None
_backtest_cache: dict | None = None
_backtest_ts:    datetime | None = None

_PERF_TTL_MIN      = 10
_BACKTEST_TTL_MIN  = 120


@router.get("/api/performance")
async def get_performance():
    """Returns live trade performance analytics (ML analysis)."""
    global _perf_cache, _perf_ts

    now = datetime.now(timezone.utc)
    if (_perf_cache is not None and _perf_ts is not None
            and (now - _perf_ts).total_seconds() < _PERF_TTL_MIN * 60):
        return _perf_cache

    try:
        data = analyze_trade_performance(100)
        _perf_cache = data
        _perf_ts    = now
        return data
    except Exception as e:
        logger.error(f"Performance endpoint error: {e}")
        return {"error": str(e)}


@router.get("/api/performance/backtest")
async def get_backtest(years: int = 5):
    """Returns backtesting results (cached 2h)."""
    global _backtest_cache, _backtest_ts

    now = datetime.now(timezone.utc)
    if (_backtest_cache is not None and _backtest_ts is not None
            and (now - _backtest_ts).total_seconds() < _BACKTEST_TTL_MIN * 60):
        return _backtest_cache

    try:
        logger.info(f"Running backtest ({years}y)…")
        data = run_backtest(years)
        _backtest_cache = data
        _backtest_ts    = now
        return data
    except Exception as e:
        logger.error(f"Backtest endpoint error: {e}")
        return {"error": str(e)}
