from fastapi import APIRouter, HTTPException
from backend.services.market_data import (
    get_full_market_data, fetch_ohlc, fetch_current_price,
    get_active_source, fetch_api_quota,
)
from backend.database import get_latest_snapshot, save_market_snapshot
import logging
import time

router = APIRouter(prefix="/api/market", tags=["market"])
logger = logging.getLogger(__name__)

_live_cache: dict = {}
_live_cache_ts: float = 0.0
_LIVE_TTL = 1.0


@router.get("/price")
async def get_price():
    """Prix actuel et indicateurs principaux."""
    data = await get_full_market_data()
    price = data.get("price") if data else None
    if not price or price <= 0:
        raise HTTPException(
            status_code=503,
            detail="Prix indisponible — clé API Twelve Data invalide, quota épuisé, ou service indisponible"
        )
    save_market_snapshot(data)
    return {
        "price": data.get("price"),
        "open": data.get("open"),
        "high": data.get("high"),
        "low": data.get("low"),
        "change_pct": _compute_change(data.get("price"), data.get("open")),
        "rsi": data.get("rsi"),
        "macd": data.get("macd"),
        "macd_signal": data.get("macd_signal"),
        "macd_histogram": data.get("macd_histogram"),
        "ema20": data.get("ema20"),
        "ema50": data.get("ema50"),
        "ema200": data.get("ema200"),
        "trend_short": data.get("trend_short"),
        "trend_medium": data.get("trend_medium"),
        "atr": data.get("atr"),
        "atr_pct": data.get("atr_pct"),
        "bb_upper": data.get("bb_upper"),
        "bb_mid": data.get("bb_mid"),
        "bb_lower": data.get("bb_lower"),
        "supports": data.get("supports", []),
        "resistances": data.get("resistances", []),
        "source": data.get("source", "twelve_data"),
    }


@router.get("/price/live")
async def get_live_price():
    """Prix actuel seul, optimisé pour les appels fréquents. Cache 1s."""
    global _live_cache, _live_cache_ts
    now = time.time()
    if _live_cache and (now - _live_cache_ts) < _LIVE_TTL:
        return _live_cache

    price_data = await fetch_current_price()
    if not price_data:
        if _live_cache:
            return _live_cache
        raise HTTPException(status_code=503, detail="Price unavailable")

    snapshot = get_latest_snapshot()
    open_price = snapshot.get("open") if snapshot else None

    result = {
        "price":      price_data["price"],
        "change_pct": _compute_change(price_data["price"], open_price),
        "timestamp":  price_data["timestamp"],
    }
    _live_cache    = result
    _live_cache_ts = now
    return result


@router.get("/ohlc/{interval}")
async def get_ohlc(interval: str = "1h", outputsize: int = 100):
    """Données OHLC. interval: 1min, 5min, 15min, 1h, 4h, 1day."""
    valid_intervals = ["1min", "5min", "15min", "30min", "1h", "4h", "1day", "1week"]
    if interval not in valid_intervals:
        raise HTTPException(status_code=400, detail=f"Invalid interval. Use: {valid_intervals}")
    data = await fetch_ohlc(interval, min(outputsize, 500))
    if not data:
        raise HTTPException(status_code=503, detail="OHLC data unavailable — Twelve Data et Yahoo Finance ont tous les deux échoué")
    return {"interval": interval, "data": data, "source": get_active_source()}


@router.get("/indicators")
async def get_indicators():
    """Tous les indicateurs techniques du snapshot le plus récent."""
    snapshot = get_latest_snapshot()
    if not snapshot:
        data = await get_full_market_data()
        return data
    return snapshot


@router.get("/quota")
async def get_quota():
    """Twelve Data API quota/usage info."""
    return await fetch_api_quota()


def _compute_change(current: float | None, open_: float | None) -> float | None:
    if current and open_ and open_ != 0:
        return round((current - open_) / open_ * 100, 3)
    return None
