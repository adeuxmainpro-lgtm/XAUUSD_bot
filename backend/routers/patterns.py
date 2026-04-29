from fastapi import APIRouter, Query
from backend.services.market_data import fetch_ohlc
from backend.services.pattern_service import detect_all_patterns

router = APIRouter(prefix="/api/patterns", tags=["patterns"])


@router.get("")
async def get_patterns(interval: str = Query(default="1h")):
    ohlc = await fetch_ohlc(interval, outputsize=100)
    if not ohlc:
        return {"error": "Données OHLC indisponibles", "interval": interval}
    patterns = detect_all_patterns(ohlc)
    patterns["interval"] = interval
    patterns["candles_analyzed"] = len(ohlc)
    return patterns
