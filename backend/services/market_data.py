import asyncio
import httpx
import pandas as pd
import ta
import logging
from datetime import datetime
from backend.config import TWELVE_DATA_API_KEY, TWELVE_DATA_BASE_URL

# ── API call counter ───────────────────────────────────────────────────────
_api_call_count: int = 0
_api_quota_cache: dict = {}
_api_quota_ts: float = 0.0


def increment_api_counter():
    global _api_call_count
    _api_call_count += 1


def get_api_call_count() -> int:
    return _api_call_count

logger = logging.getLogger(__name__)

SYMBOL = "XAU/USD"
YAHOO_SYMBOL = "GC=F"

# Interval mapping: our internal key → yfinance params
_YF_INTERVAL_MAP = {
    "15min": ("15m",  "5d"),
    "1h":    ("1h",   "30d"),
    "4h":    ("1h",   "60d"),   # yfinance has no 4h; use 1h + resample below
    "1day":  ("1d",   "365d"),
    "1week": ("1wk",  "2y"),
}


def _check_twelve_data_error(data: dict, context: str) -> str | None:
    """Returns an error message if Twelve Data returned an API-level error (HTTP 200 with error body)."""
    if data.get("status") == "error":
        msg = data.get("message", "unknown error")
        code = data.get("code", "?")
        return f"Twelve Data [{context}] error {code}: {msg}"
    return None


async def fetch_api_quota() -> dict:
    """Fetch remaining API credits from Twelve Data /api_usage endpoint."""
    global _api_quota_cache, _api_quota_ts
    import time
    now = time.time()
    if _api_quota_cache and (now - _api_quota_ts) < 300:  # cache 5 min
        return _api_quota_cache
    if not TWELVE_DATA_API_KEY:
        return {"error": "No API key configured"}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{TWELVE_DATA_BASE_URL}/api_usage", params={"apikey": TWELVE_DATA_API_KEY})
            r.raise_for_status()
            data = r.json()
        result = {
            "current_usage":   data.get("current_usage", 0),
            "plan_limit":      data.get("plan_limit", 800),
            "plan_daily_limit": data.get("plan_daily_limit", 800),
            "remaining":       max(0, data.get("plan_daily_limit", 800) - data.get("current_usage", 0)),
            "session_calls":   _api_call_count,
            "reset_time":      data.get("timestamp", ""),
        }
        _api_quota_cache = result
        _api_quota_ts    = now
        return result
    except Exception as e:
        logger.warning(f"fetch_api_quota error: {e}")
        return {"error": str(e), "session_calls": _api_call_count}


async def _fetch_current_price_twelve() -> dict | None:
    """Prix actuel via Twelve Data."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{TWELVE_DATA_BASE_URL}/price", params={
                "symbol": SYMBOL,
                "apikey": TWELVE_DATA_API_KEY,
            })
            r.raise_for_status()
            data = r.json()

            increment_api_counter()
            err = _check_twelve_data_error(data, "price")
            if err:
                logger.error(err)
                return None

            price_raw = data.get("price")
            if price_raw is None:
                logger.error(f"_fetch_current_price_twelve: no 'price' field: {data}")
                return None

            price = float(price_raw)
            if price <= 0:
                logger.error(f"_fetch_current_price_twelve: invalid price {price}")
                return None

            return {"price": price, "symbol": SYMBOL, "timestamp": datetime.utcnow().isoformat(), "source": "twelve_data"}
    except Exception as e:
        logger.error(f"_fetch_current_price_twelve error: {e}")
        return None


async def _fetch_ohlc_twelve(interval: str = "1h", outputsize: int = 100) -> list[dict] | None:
    """Données OHLC via Twelve Data."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{TWELVE_DATA_BASE_URL}/time_series", params={
                "symbol": SYMBOL,
                "interval": interval,
                "outputsize": outputsize,
                "apikey": TWELVE_DATA_API_KEY,
            })
            r.raise_for_status()
            data = r.json()

            increment_api_counter()
            err = _check_twelve_data_error(data, f"ohlc/{interval}")
            if err:
                logger.error(err)
                return None

            values = data.get("values")
            if not values:
                logger.error(f"_fetch_ohlc_twelve({interval}): no values: {list(data.keys())}")
                return None

            return [
                {
                    "datetime": v["datetime"],
                    "open":     float(v["open"]),
                    "high":     float(v["high"]),
                    "low":      float(v["low"]),
                    "close":    float(v["close"]),
                    "volume":   float(v.get("volume", 0)),
                }
                for v in values
            ]
    except Exception as e:
        logger.error(f"_fetch_ohlc_twelve({interval}) error: {e}")
        return None


# Track the currently active data source so the router can expose it
_active_source: str = "twelve_data"


async def fetch_current_price() -> dict | None:
    """Prix actuel — Twelve Data avec fallback Yahoo Finance."""
    global _active_source
    result = await _fetch_current_price_twelve()
    if result:
        _active_source = "twelve_data"
        return result
    logger.warning("Twelve Data épuisé → basculement sur Yahoo Finance (price)")
    _active_source = "yahoo_finance"
    return fetch_current_price_yahoo()


async def fetch_ohlc(interval: str = "1h", outputsize: int = 100) -> list[dict] | None:
    """Données OHLC — Twelve Data avec fallback Yahoo Finance. interval: 1min, 5min, 15min, 1h, 4h, 1day."""
    result = await _fetch_ohlc_twelve(interval, outputsize)
    if result:
        return result
    logger.warning(f"Twelve Data épuisé → basculement sur Yahoo Finance (ohlc/{interval})")
    return fetch_ohlc_yahoo(interval, outputsize)


def get_active_source() -> str:
    """Retourne la source de données actuellement utilisée."""
    return _active_source


def fetch_current_price_yahoo() -> dict | None:
    """Prix actuel via yfinance (fallback)."""
    try:
        import yfinance as yf
        ticker = yf.Ticker(YAHOO_SYMBOL)
        info = ticker.fast_info
        price = float(info.last_price)
        if not price or price <= 0:
            raise ValueError(f"Invalid price from Yahoo: {price}")
        logger.info(f"Yahoo Finance price: {price}")
        return {"price": price, "symbol": SYMBOL, "timestamp": datetime.utcnow().isoformat(), "source": "yahoo_finance"}
    except Exception as e:
        logger.error(f"fetch_current_price_yahoo error: {e}")
        return None


def fetch_ohlc_yahoo(interval: str = "1h", outputsize: int = 200) -> list[dict] | None:
    """Données OHLC via yfinance (fallback)."""
    try:
        import yfinance as yf
        yf_interval, period = _YF_INTERVAL_MAP.get(interval, ("1h", "30d"))
        ticker = yf.Ticker(YAHOO_SYMBOL)
        df = ticker.history(period=period, interval=yf_interval, auto_adjust=True)

        if df.empty:
            logger.error(f"fetch_ohlc_yahoo({interval}): empty dataframe")
            return None

        # Resample 1h → 4h when interval is "4h"
        if interval == "4h":
            df = df.resample("4h").agg({
                "Open": "first", "High": "max", "Low": "min",
                "Close": "last", "Volume": "sum",
            }).dropna()

        df = df.tail(outputsize)
        result = []
        for ts, row in df.iterrows():
            result.append({
                "datetime": ts.strftime("%Y-%m-%dT%H:%M:%S"),
                "open":     float(row["Open"]),
                "high":     float(row["High"]),
                "low":      float(row["Low"]),
                "close":    float(row["Close"]),
                "volume":   float(row.get("Volume", 0)),
            })
        logger.info(f"Yahoo Finance OHLC({interval}): {len(result)} candles")
        return result
    except Exception as e:
        logger.error(f"fetch_ohlc_yahoo({interval}) error: {e}")
        return None


def compute_indicators(ohlc: list[dict]) -> dict:
    """Calcule RSI, MACD, EMA, Bollinger Bands, ATR à partir des données OHLC."""
    if not ohlc or len(ohlc) < 30:
        return {}

    df = pd.DataFrame(ohlc)
    df = df.sort_values("datetime").reset_index(drop=True)
    df["close"] = df["close"].astype(float)
    df["high"] = df["high"].astype(float)
    df["low"] = df["low"].astype(float)

    # RSI
    rsi_series = ta.momentum.RSIIndicator(close=df["close"], window=14).rsi()
    rsi_val = float(rsi_series.iloc[-1]) if not rsi_series.empty else None

    # MACD
    macd_obj = ta.trend.MACD(close=df["close"], window_fast=12, window_slow=26, window_sign=9)
    macd_line = macd_obj.macd()
    macd_signal_line = macd_obj.macd_signal()
    macd_hist_line = macd_obj.macd_diff()
    macd_val = float(macd_line.iloc[-1]) if not macd_line.empty else None
    macd_signal_val = float(macd_signal_line.iloc[-1]) if not macd_signal_line.empty else None
    macd_hist_val = float(macd_hist_line.iloc[-1]) if not macd_hist_line.empty else None

    # EMAs
    ema20_series = ta.trend.EMAIndicator(close=df["close"], window=20).ema_indicator()
    ema50_series = ta.trend.EMAIndicator(close=df["close"], window=50).ema_indicator()
    ema200_series = ta.trend.EMAIndicator(close=df["close"], window=200).ema_indicator()

    ema20_val = float(ema20_series.iloc[-1]) if not ema20_series.empty else None
    ema50_val = float(ema50_series.iloc[-1]) if not ema50_series.empty else None
    ema200_clean = ema200_series.dropna()
    ema200_val = float(ema200_clean.iloc[-1]) if len(ema200_clean) > 0 else None

    # Bollinger Bands
    bb_obj = ta.volatility.BollingerBands(close=df["close"], window=20, window_dev=2)
    bb_upper = float(bb_obj.bollinger_hband().iloc[-1])
    bb_lower = float(bb_obj.bollinger_lband().iloc[-1])
    bb_mid = float(bb_obj.bollinger_mavg().iloc[-1])

    # ATR
    atr_series = ta.volatility.AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"], window=14
    ).average_true_range()
    atr_val = float(atr_series.iloc[-1]) if not atr_series.empty else None
    current_price = float(df["close"].iloc[-1])
    atr_pct = (atr_val / current_price * 100) if atr_val else None

    # Tendances
    trend_short = _get_trend(ema20_val, ema50_val)
    trend_medium = _get_trend(ema50_val, ema200_val)

    # Support / résistance (pivots sur 20 bougies)
    supports, resistances = _compute_pivot_levels(df)

    return {
        "price": current_price,
        "open": float(df["open"].iloc[-1]),
        "high": float(df["high"].iloc[-1]),
        "low": float(df["low"].iloc[-1]),
        "volume": float(df["volume"].iloc[-1]) if "volume" in df.columns else 0,
        "rsi": round(rsi_val, 2) if rsi_val is not None else None,
        "macd": round(macd_val, 4) if macd_val is not None else None,
        "macd_signal": round(macd_signal_val, 4) if macd_signal_val is not None else None,
        "macd_histogram": round(macd_hist_val, 4) if macd_hist_val is not None else None,
        "ema20": round(ema20_val, 2) if ema20_val is not None else None,
        "ema50": round(ema50_val, 2) if ema50_val is not None else None,
        "ema200": round(ema200_val, 2) if ema200_val is not None else None,
        "bb_upper": round(bb_upper, 2) if bb_upper is not None else None,
        "bb_lower": round(bb_lower, 2) if bb_lower is not None else None,
        "bb_mid": round(bb_mid, 2) if bb_mid is not None else None,
        "atr": round(atr_val, 2) if atr_val is not None else None,
        "atr_pct": round(atr_pct, 3) if atr_pct is not None else None,
        "trend_short": trend_short,
        "trend_medium": trend_medium,
        "supports": supports,
        "resistances": resistances,
    }


def _get_trend(fast: float | None, slow: float | None) -> str:
    if fast is None or slow is None:
        return "UNKNOWN"
    if fast > slow:
        return "BULLISH"
    elif fast < slow:
        return "BEARISH"
    return "NEUTRAL"


def _compute_pivot_levels(df: pd.DataFrame, window: int = 20) -> tuple[list, list]:
    """Détecte les niveaux de support/résistance par pivots hauts/bas."""
    highs = df["high"].values
    lows = df["low"].values
    supports = []
    resistances = []

    for i in range(window, len(df) - 1):
        # Pivot haut : high local sur `window` bougies
        if highs[i] == max(highs[i - window:i + 1]):
            resistances.append(round(float(highs[i]), 2))
        # Pivot bas : low local
        if lows[i] == min(lows[i - window:i + 1]):
            supports.append(round(float(lows[i]), 2))

    # Garder les 3 niveaux les plus proches du prix actuel
    current = float(df["close"].iloc[-1])
    supports = sorted(set(supports), key=lambda x: abs(x - current))[:3]
    resistances = sorted(set(resistances), key=lambda x: abs(x - current))[:3]
    return sorted(supports), sorted(resistances)


async def get_full_market_data() -> dict:
    """Point d'entrée principal : prix + indicateurs multi-timeframe."""
    price_data, ohlc_15m, ohlc_1h, ohlc_4h, ohlc_1d = await asyncio.gather(
        fetch_current_price(),
        fetch_ohlc("15min", 200),
        fetch_ohlc("1h",    500),
        fetch_ohlc("4h",    100),
        fetch_ohlc("1day",  200),
        return_exceptions=True,
    )

    # Unwrap exceptions
    if isinstance(price_data, Exception): price_data = None
    if isinstance(ohlc_15m,   Exception): ohlc_15m   = None
    if isinstance(ohlc_1h,    Exception): ohlc_1h    = None
    if isinstance(ohlc_4h,    Exception): ohlc_4h    = None
    if isinstance(ohlc_1d,    Exception): ohlc_1d    = None

    indicators = {}
    if ohlc_1h:
        indicators = compute_indicators(ohlc_1h)
    elif price_data:
        indicators["price"] = price_data["price"]

    result = {**indicators}
    if price_data and "price" not in result:
        result["price"] = price_data["price"]

    result["source"]   = price_data.get("source", "twelve_data") if price_data else "unknown"
    result["ohlc_15m"] = ohlc_15m[:100] if ohlc_15m else []
    result["ohlc_1h"]  = ohlc_1h[:100]  if ohlc_1h  else []
    result["ohlc_4h"]  = ohlc_4h[:80]   if ohlc_4h  else []
    result["ohlc_1d"]  = ohlc_1d[:100]  if ohlc_1d  else []

    return result
