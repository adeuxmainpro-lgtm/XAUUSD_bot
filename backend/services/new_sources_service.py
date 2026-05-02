"""
new_sources_service.py
Additional market intelligence for XAUUSD analysis.

Sources:
  - Correlation matrix (GC=F vs ^GSPC, BTC-USD, CL=F, ^VIX, TLT, DX-Y.NYB)
  - ETF flows (GLD, IAU)
  - Options sentiment (GLD put/call ratio)
  - Treasury yield curve (^IRX, ^TNX, ^TYX)
  - Fed speeches NLP via Claude Haiku

All yfinance calls are dispatched via asyncio.to_thread() to avoid blocking.
All failures are silent: functions return {} or None.
Each source type has an independent in-memory TTL cache.
"""

import asyncio
import json
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory TTL cache
# ---------------------------------------------------------------------------

_cache: dict[str, dict[str, Any]] = {}


def _cache_get(key: str) -> dict | None:
    """Return cached value if still fresh, else None."""
    entry = _cache.get(key)
    if entry is None:
        return None
    now = datetime.now(timezone.utc).timestamp()
    if now - entry["ts"] > entry["ttl"]:
        return None
    return entry["data"]


def _cache_set(key: str, data: dict, ttl: int) -> None:
    _cache[key] = {
        "ts": datetime.now(timezone.utc).timestamp(),
        "ttl": ttl,
        "data": data,
    }


# ---------------------------------------------------------------------------
# fetch_correlations
# ---------------------------------------------------------------------------

_CORRELATION_SYMBOLS = ["^GSPC", "BTC-USD", "CL=F", "^VIX", "TLT", "DX-Y.NYB"]
_CORRELATION_TTL = 3600


def _sync_fetch_correlations() -> dict:
    """Synchronous yfinance call — must be run via asyncio.to_thread."""
    import yfinance as yf  # imported here to avoid import-time side effects
    import pandas as pd

    tickers = ["GC=F"] + _CORRELATION_SYMBOLS
    raw = yf.download(tickers, period="60d", interval="1d", auto_adjust=True, progress=False)

    # yfinance returns MultiIndex columns: (field, symbol)
    if isinstance(raw.columns, pd.MultiIndex):
        close = raw["Close"]
    else:
        close = raw[["Close"]]

    gold_col = "GC=F"
    if gold_col not in close.columns:
        return {}

    gold_close = close[gold_col].dropna()

    results: dict[str, Any] = {}
    for sym in _CORRELATION_SYMBOLS:
        if sym not in close.columns:
            continue
        asset_close = close[sym].dropna()

        combined = pd.concat([gold_close, asset_close], axis=1).dropna()
        combined.columns = ["gold", "asset"]
        last30 = combined.tail(30)

        if len(last30) < 10:
            continue

        corr_matrix = last30.corr()
        corr = float(corr_matrix.loc["gold", "asset"])
        current = float(asset_close.iloc[-1])

        # Signal interpretation
        if sym == "^VIX":
            signal = "BULLISH" if corr > 0.3 else ("BEARISH" if corr < -0.3 else "NEUTRAL")
        elif sym == "DX-Y.NYB":
            signal = "BULLISH" if corr < -0.3 else ("BEARISH" if corr > 0.3 else "NEUTRAL")
        elif sym == "CL=F":
            signal = "BULLISH" if corr > 0.3 else "NEUTRAL"
        elif sym == "TLT":
            signal = "BULLISH" if corr > 0.3 else "NEUTRAL"
        else:
            # ^GSPC and BTC-USD: context only
            signal = "NEUTRAL"

        results[sym] = {
            "symbol": sym,
            "correlation_30d": round(corr, 4),
            "current": round(current, 4),
            "signal": signal,
        }

    return results


async def fetch_correlations() -> dict:
    """Return 30-day Pearson correlations of key assets with gold (GC=F)."""
    cached = _cache_get("correlations")
    if cached is not None:
        return cached

    try:
        data = await asyncio.to_thread(_sync_fetch_correlations)
        if data:
            _cache_set("correlations", data, _CORRELATION_TTL)
        return data
    except Exception as e:
        logger.warning(f"fetch_correlations error: {e}")
        return {}


# ---------------------------------------------------------------------------
# fetch_etf_flows
# ---------------------------------------------------------------------------

_ETF_SYMBOLS = ["GLD", "IAU"]
_ETF_TTL = 3600


def _sync_fetch_etf_flows() -> dict:
    """Synchronous yfinance call — must be run via asyncio.to_thread."""
    import yfinance as yf

    results: dict[str, Any] = {}

    for ticker in _ETF_SYMBOLS:
        try:
            hist = yf.Ticker(ticker).history(period="5d", interval="1d", auto_adjust=True)
            if hist is None or len(hist) < 2:
                continue

            hist = hist.dropna(subset=["Close", "Volume"])
            if len(hist) < 2:
                continue

            price_today = float(hist["Close"].iloc[-1])
            price_yesterday = float(hist["Close"].iloc[-2])
            price_change_pct = (price_today - price_yesterday) / price_yesterday * 100

            volume_today = float(hist["Volume"].iloc[-1])
            avg_volume = float(hist["Volume"].mean())
            volume_vs_avg = volume_today / avg_volume if avg_volume > 0 else 1.0

            if price_change_pct > 0.2 and volume_today > avg_volume:
                signal = "BULLISH"
            elif price_change_pct < -0.2 and volume_today > avg_volume:
                signal = "BEARISH"
            else:
                signal = "NEUTRAL"

            results[ticker] = {
                "price": round(price_today, 4),
                "price_change_pct": round(price_change_pct, 4),
                "volume_vs_avg": round(volume_vs_avg, 4),
                "signal": signal,
            }
        except Exception as e:
            logger.warning(f"fetch_etf_flows [{ticker}] error: {e}")

    return results


async def fetch_etf_flows() -> dict:
    """Return price and volume flow data for GLD and IAU gold ETFs."""
    cached = _cache_get("etf_flows")
    if cached is not None:
        return cached

    try:
        data = await asyncio.to_thread(_sync_fetch_etf_flows)
        if data:
            _cache_set("etf_flows", data, _ETF_TTL)
        return data
    except Exception as e:
        logger.warning(f"fetch_etf_flows error: {e}")
        return {}


# ---------------------------------------------------------------------------
# fetch_options_sentiment
# ---------------------------------------------------------------------------

_OPTIONS_TTL = 14400


def _sync_fetch_options_sentiment() -> dict:
    """Synchronous yfinance call — must be run via asyncio.to_thread."""
    import yfinance as yf

    gld = yf.Ticker("GLD")
    expirations = gld.options
    if not expirations:
        return {}

    nearest_expiry = expirations[0]
    chain = gld.option_chain(nearest_expiry)

    calls = chain.calls
    puts = chain.puts

    if calls is None or puts is None or calls.empty or puts.empty:
        return {}

    call_oi = int(calls["openInterest"].fillna(0).sum())
    put_oi = int(puts["openInterest"].fillna(0).sum())

    if call_oi == 0:
        return {}

    put_call_ratio = put_oi / call_oi

    if put_call_ratio > 1.0:
        signal = "BULLISH"
        note = "High put OI suggests hedging activity — contrarian bullish signal for gold."
    elif put_call_ratio < 0.7:
        signal = "BEARISH"
        note = "Low put/call ratio indicates call-heavy positioning — contrarian bearish signal."
    else:
        signal = "NEUTRAL"
        note = "Balanced put/call ratio — no directional bias detected."

    return {
        "put_call_ratio": round(put_call_ratio, 4),
        "call_oi": call_oi,
        "put_oi": put_oi,
        "signal": signal,
        "note": note,
    }


async def fetch_options_sentiment() -> dict:
    """Return GLD options put/call ratio and contrarian sentiment signal."""
    cached = _cache_get("options")
    if cached is not None:
        return cached

    try:
        data = await asyncio.to_thread(_sync_fetch_options_sentiment)
        if data:
            _cache_set("options", data, _OPTIONS_TTL)
        return data
    except Exception as e:
        logger.warning(f"fetch_options_sentiment error: {e}")
        return {}


# ---------------------------------------------------------------------------
# fetch_treasury_yields
# ---------------------------------------------------------------------------

_YIELD_SYMBOLS = {"^IRX": "y2", "^TNX": "y10", "^TYX": "y30"}
_YIELDS_TTL = 3600


def _sync_fetch_treasury_yields() -> dict:
    """Synchronous yfinance call — must be run via asyncio.to_thread."""
    import yfinance as yf

    values: dict[str, float] = {}

    for sym, label in _YIELD_SYMBOLS.items():
        try:
            hist = yf.Ticker(sym).history(period="5d", interval="1d", auto_adjust=True)
            if hist is None or hist.empty:
                continue
            last_close = float(hist["Close"].dropna().iloc[-1])
            values[label] = round(last_close, 4)
        except Exception as e:
            logger.warning(f"fetch_treasury_yields [{sym}] error: {e}")

    if "y2" not in values or "y10" not in values:
        return {}

    y2 = values["y2"]
    y10 = values["y10"]
    y30 = values.get("y30")

    spread_2_10 = round(y2 - y10, 4)
    inverted = spread_2_10 > 0  # 2Y > 10Y means inverted curve

    if inverted:
        signal = "BULLISH"
    elif y10 > 4.5:
        signal = "BEARISH"
    else:
        signal = "NEUTRAL"

    result: dict[str, Any] = {
        "y2": y2,
        "y10": y10,
        "spread_2_10": spread_2_10,
        "inverted": inverted,
        "signal": signal,
    }
    if y30 is not None:
        result["y30"] = y30

    return result


async def fetch_treasury_yields() -> dict:
    """Return treasury yield curve data and gold signal based on inversion / level."""
    cached = _cache_get("yields")
    if cached is not None:
        return cached

    try:
        data = await asyncio.to_thread(_sync_fetch_treasury_yields)
        if data:
            _cache_set("yields", data, _YIELDS_TTL)
        return data
    except Exception as e:
        logger.warning(f"fetch_treasury_yields error: {e}")
        return {}


# ---------------------------------------------------------------------------
# fetch_fed_speeches_nlp
# ---------------------------------------------------------------------------

_FED_RSS_URL = "https://www.federalreserve.gov/feeds/speeches.xml"
_FED_NLP_TTL = 86400
_HAIKU_MODEL = "claude-haiku-4-5-20251001"

_FED_NLP_PROMPT = (
    "Analyse le ton hawkish (hausses taux, mauvais pour l'or) vs dovish (baisses taux, bon pour l'or) "
    "de ces derniers discours Fed. Score de -5 (très hawkish) à +5 (très dovish). "
    'JSON uniquement: {"score": 2, "bias": "HAWKISH|DOVISH|NEUTRAL", "summary": "1 phrase"}'
)


async def _fetch_fed_rss_speeches() -> list[dict]:
    """Fetch and parse the last 3 speeches from the Fed RSS feed."""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(_FED_RSS_URL, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            content = r.content
    except Exception as e:
        logger.warning(f"Fed RSS fetch error: {e}")
        return []

    speeches: list[dict] = []
    try:
        root = ET.fromstring(content)
        items = root.findall(".//item")
        for item in items[:3]:
            title = (item.findtext("title") or "").strip()
            desc = (item.findtext("description") or "").strip()
            speeches.append({"title": title, "description": desc[:500]})
    except ET.ParseError as e:
        logger.warning(f"Fed RSS parse error: {e}")

    return speeches


async def fetch_fed_speeches_nlp() -> dict:
    """Analyze the hawkish/dovish tone of recent Fed speeches via Claude Haiku."""
    cached = _cache_get("fed_speeches")
    if cached is not None:
        return cached

    try:
        from backend.services.ai_analyst import _get_client  # lazy import

        speeches = await _fetch_fed_rss_speeches()
        if not speeches:
            return {}

        speech_text = "\n\n".join(
            f"Titre: {s['title']}\n{s['description']}" for s in speeches
        )

        client = _get_client()
        response = await client.messages.create(
            model=_HAIKU_MODEL,
            max_tokens=256,
            messages=[{
                "role": "user",
                "content": f"{speech_text}\n\n{_FED_NLP_PROMPT}",
            }],
        )

        raw_text = response.content[0].text.strip()
        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1

        if start == -1 or end <= start:
            logger.warning("Fed NLP: JSON not found in Haiku response")
            return {}

        parsed = json.loads(raw_text[start:end])
        score = int(parsed.get("score", 0))
        bias = str(parsed.get("bias", "NEUTRAL"))
        summary = str(parsed.get("summary", ""))

        if score >= 1:
            gold_signal = "BULLISH"
        elif score <= -1:
            gold_signal = "BEARISH"
        else:
            gold_signal = "NEUTRAL"

        data: dict[str, Any] = {
            "score": score,
            "bias": bias,
            "gold_signal": gold_signal,
            "summary": summary,
            "speeches": [s["title"] for s in speeches],
        }

        _cache_set("fed_speeches", data, _FED_NLP_TTL)
        return data

    except Exception as e:
        logger.warning(f"fetch_fed_speeches_nlp error: {e}")
        return {}


# ---------------------------------------------------------------------------
# fetch_all_new_sources
# ---------------------------------------------------------------------------

async def fetch_all_new_sources() -> dict:
    """Run all 5 intelligence sources in parallel and aggregate results."""
    results = await asyncio.gather(
        fetch_correlations(),
        fetch_etf_flows(),
        fetch_options_sentiment(),
        fetch_treasury_yields(),
        fetch_fed_speeches_nlp(),
        return_exceptions=True,
    )

    def _safe(val: Any) -> dict:
        if isinstance(val, Exception):
            logger.warning(f"fetch_all_new_sources: individual source failed: {val}")
            return {}
        if isinstance(val, dict):
            return val
        return {}

    return {
        "correlations": _safe(results[0]),
        "etf_flows":    _safe(results[1]),
        "options":      _safe(results[2]),
        "yields":       _safe(results[3]),
        "fed_nlp":      _safe(results[4]),
        "timestamp":    datetime.now(timezone.utc).isoformat(),
    }
