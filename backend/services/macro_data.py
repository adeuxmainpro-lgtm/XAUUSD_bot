import httpx
import logging
import asyncio
from datetime import datetime, timezone, timedelta
import xml.etree.ElementTree as ET

from backend.config import FRED_API_KEY, FRED_BASE_URL, TWELVE_DATA_API_KEY, TWELVE_DATA_BASE_URL

logger = logging.getLogger(__name__)

_macro_cache: dict = {}
_CACHE_TTL_SECONDS = 4 * 3600


async def _fred_series_latest(series_id: str) -> float | None:
    """Récupère la dernière valeur d'une série FRED."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{FRED_BASE_URL}/series/observations", params={
                "series_id": series_id,
                "api_key": FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 1,
            })
            r.raise_for_status()
            obs = r.json().get("observations", [])
            if obs and obs[0]["value"] != ".":
                return float(obs[0]["value"])
    except Exception as e:
        logger.error(f"FRED {series_id} error: {e}")
    return None


async def _fred_series_last_n(series_id: str, n: int) -> list[float]:
    """Récupère les n dernières valeurs d'une série FRED (ordre décroissant = récent en premier)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{FRED_BASE_URL}/series/observations", params={
                "series_id": series_id,
                "api_key": FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": n,
            })
            r.raise_for_status()
            obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
            return [float(o["value"]) for o in obs]
    except Exception as e:
        logger.error(f"FRED {series_id} last {n} error: {e}")
    return []


def _detect_trend(values: list[float], threshold: float = 0.05) -> str:
    """Détecte la tendance depuis une liste [récent, ..., ancien]."""
    if len(values) < 2:
        return "stable"
    delta = values[0] - values[-1]
    if delta > threshold:
        return "hausse"
    elif delta < -threshold:
        return "baisse"
    return "stable"


async def fetch_fed_rate() -> float | None:
    return await _fred_series_latest("FEDFUNDS")


async def fetch_us10y() -> float | None:
    """10-year US Treasury yield (DGS10) from FRED — daily series."""
    return await _fred_series_latest("DGS10")


async def fetch_dxy_fred() -> float | None:
    """Trade-weighted US Dollar Index broad (DTWEXBGS) from FRED — weekly series."""
    return await _fred_series_latest("DTWEXBGS")


async def fetch_cpi() -> float | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{FRED_BASE_URL}/series/observations", params={
                "series_id": "CPIAUCSL",
                "api_key": FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 13,
            })
            r.raise_for_status()
            obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
            if len(obs) >= 13:
                latest = float(obs[0]["value"])
                year_ago = float(obs[12]["value"])
                return round((latest - year_ago) / year_ago * 100, 2)
    except Exception as e:
        logger.error(f"CPI fetch error: {e}")
    return None


async def fetch_nfp() -> float | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{FRED_BASE_URL}/series/observations", params={
                "series_id": "PAYEMS",
                "api_key": FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 2,
            })
            r.raise_for_status()
            obs = [o for o in r.json().get("observations", []) if o["value"] != "."]
            if len(obs) >= 2:
                return round(float(obs[0]["value"]) - float(obs[1]["value"]), 0)
    except Exception as e:
        logger.error(f"NFP fetch error: {e}")
    return None


async def fetch_dxy() -> float | None:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{TWELVE_DATA_BASE_URL}/price", params={
                "symbol": "DX/Y",
                "apikey": TWELVE_DATA_API_KEY,
            })
            r.raise_for_status()
            data = r.json()
            if "price" in data:
                return round(float(data["price"]), 3)
    except Exception as e:
        logger.error(f"DXY fetch error: {e}")
    return None


async def _fetch_dxy_history() -> list[float]:
    """Récupère les 7 derniers cours journaliers DXY pour calculer la tendance."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{TWELVE_DATA_BASE_URL}/time_series", params={
                "symbol": "DX/Y",
                "interval": "1day",
                "outputsize": 7,
                "apikey": TWELVE_DATA_API_KEY,
            })
            r.raise_for_status()
            values = r.json().get("values", [])
            return [float(v["close"]) for v in values if "close" in v]
    except Exception as e:
        logger.error(f"DXY history fetch error: {e}")
    return []


async def _fetch_next_macro_event() -> dict | None:
    """Récupère le prochain événement haute importance USD depuis Forex Factory."""
    ff_url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
    try:
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as client:
            r = await client.get(ff_url)
            r.raise_for_status()
            root = ET.fromstring(r.text)

        now = datetime.now(timezone.utc)
        candidates = []

        for event in root.findall(".//event"):
            country = (event.findtext("country") or "").strip()
            impact = (event.findtext("impact") or "").strip()
            title = (event.findtext("title") or "").strip()
            date_str = (event.findtext("date") or "").strip()
            time_str = (event.findtext("time") or "").strip()

            if country != "USD" or impact not in ("High", "Medium") or not title or not date_str:
                continue

            # Parse date — Forex Factory uses MM-DD-YYYY
            event_dt = None
            for fmt in ("%m-%d-%Y", "%Y-%m-%d", "%m/%d/%Y"):
                try:
                    event_dt = datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
                    break
                except ValueError:
                    continue

            if event_dt is None:
                continue

            # Try to incorporate time if available
            if time_str and time_str not in ("Tentative", "All Day", ""):
                try:
                    t = datetime.strptime(time_str, "%H:%M")
                    event_dt = event_dt.replace(hour=t.hour, minute=t.minute)
                except ValueError:
                    pass

            if event_dt >= now:
                days_until = (event_dt.date() - now.date()).days
                hours_until = max(0.0, (event_dt - now).total_seconds() / 3600)
                has_time = bool(time_str and time_str not in ("Tentative", "All Day", ""))
                candidates.append({
                    "title": title,
                    "date": event_dt.strftime("%Y-%m-%d"),
                    "days_until": days_until,
                    "hours_until": round(hours_until, 2),
                    "has_time": has_time,
                    "impact": impact.upper(),
                })

        if not candidates:
            return None

        candidates.sort(key=lambda x: x["days_until"])
        event = candidates[0]
        days = event["days_until"]
        event["countdown"] = "aujourd'hui" if days == 0 else "demain" if days == 1 else f"dans {days} jours"
        return event

    except Exception as e:
        logger.error(f"Forex Factory calendar error: {e}")
    return None


def _generate_gold_summary(
    fed_trend: str,
    fed_rate: float | None,
    cpi_trend: str,
    cpi_yoy: float | None,
    dxy_trend: str,
    dxy: float | None,
) -> str:
    parts = []

    # Dollar / FED
    if dxy_trend == "baisse" or fed_trend == "baisse":
        if dxy_trend == "baisse" and fed_trend == "baisse":
            parts.append("Le recul du dollar et des taux directeurs crée un contexte favorable à l'or.")
        elif dxy_trend == "baisse":
            parts.append("Le repli du dollar (DXY en baisse) soutient mécaniquement l'or via leur corrélation inverse.")
        else:
            parts.append("Le pivot accommodant de la FED allège la pression sur l'or lié au coût d'opportunité.")
    elif dxy_trend == "hausse" and fed_trend == "hausse":
        parts.append("Le dollar fort et les taux en hausse exercent une double pression baissière sur l'or.")
    elif dxy_trend == "hausse":
        parts.append("Le renforcement du dollar (DXY en hausse) pèse sur l'or via leur corrélation inverse.")
    elif fed_trend == "hausse":
        parts.append("La hausse des taux directeurs accroît le coût d'opportunité de l'or.")
    else:
        parts.append("Le contexte dollar et taux reste neutre pour l'or à court terme.")

    # Inflation
    if cpi_yoy is not None:
        if cpi_trend == "hausse" and cpi_yoy > 3.0:
            parts.append(f"L'inflation CPI en progression ({cpi_yoy}% YoY) renforce l'attrait de l'or comme couverture.")
        elif cpi_trend == "baisse" and cpi_yoy < 3.0:
            parts.append(f"Le recul de l'inflation vers {cpi_yoy}% YoY réduit la prime de refuge, mais les incertitudes géopolitiques restent un soutien structurel.")
        elif cpi_yoy > 3.0:
            parts.append(f"L'inflation persistante à {cpi_yoy}% YoY maintient l'or comme valeur refuge privilégiée.")
        else:
            parts.append(f"L'inflation maîtrisée à {cpi_yoy}% YoY limite la demande de couverture, mais la demande physique soutient les cours.")
    else:
        parts.append("En l'absence de données CPI récentes, le consensus de marché reste déterminant pour l'or.")

    return " ".join(parts)


async def get_macro_context() -> dict:
    """Agrège toutes les données macro (Fed rate, CPI, NFP, DXY, DGS10, DTWEXBGS)."""
    results = await asyncio.gather(
        fetch_fed_rate(),
        fetch_cpi(),
        fetch_nfp(),
        fetch_dxy(),
        fetch_us10y(),
        fetch_dxy_fred(),
        return_exceptions=True,
    )

    def safe(val):
        return val if not isinstance(val, Exception) else None

    return {
        "fed_rate":     safe(results[0]),
        "cpi_yoy":      safe(results[1]),
        "nfp_change_k": safe(results[2]),
        "dxy":          safe(results[3]),
        "us10y":        safe(results[4]),   # DGS10 — 10-year Treasury yield
        "dxy_fred":     safe(results[5]),   # DTWEXBGS — broad dollar index
    }


async def get_enriched_macro() -> dict:
    """Agrège les données macro avec tendances, prochain événement et résumé or."""
    global _macro_cache
    now_ts = datetime.now(timezone.utc).timestamp()
    if _macro_cache.get("ts") and now_ts - _macro_cache["ts"] < _CACHE_TTL_SECONDS:
        return _macro_cache["data"]

    results = await asyncio.gather(
        _fred_series_last_n("FEDFUNDS", 3),
        _fred_series_last_n("CPIAUCSL", 14),
        fetch_nfp(),
        fetch_dxy(),
        _fetch_dxy_history(),
        _fetch_next_macro_event(),
        fetch_us10y(),
        fetch_dxy_fred(),
        return_exceptions=True,
    )

    def safe(val):
        return None if isinstance(val, Exception) else val

    fed_values = safe(results[0]) or []
    cpi_values = safe(results[1]) or []
    nfp = safe(results[2])
    dxy = safe(results[3])
    dxy_history = safe(results[4]) or []
    next_event = safe(results[5])
    us10y = safe(results[6])
    dxy_fred = safe(results[7])

    # FED
    fed_rate = fed_values[0] if fed_values else None
    fed_trend = _detect_trend(fed_values, threshold=0.1)

    # CPI YoY + trend
    cpi_yoy = None
    cpi_trend = "stable"
    if len(cpi_values) >= 13:
        latest = cpi_values[0]
        year_ago = cpi_values[12]
        cpi_yoy = round((latest - year_ago) / year_ago * 100, 2)
        if len(cpi_values) >= 14:
            prev = cpi_values[1]
            prev_year_ago = cpi_values[13]
            prev_yoy = (prev - prev_year_ago) / prev_year_ago * 100
            cpi_trend = _detect_trend([cpi_yoy, prev_yoy], threshold=0.1)

    # DXY trend (dxy_history[0] = most recent)
    dxy_trend = _detect_trend(dxy_history, threshold=0.3) if len(dxy_history) >= 2 else "stable"

    gold_summary = _generate_gold_summary(fed_trend, fed_rate, cpi_trend, cpi_yoy, dxy_trend, dxy)

    data = {
        "fed_rate":     fed_rate,
        "fed_trend":    fed_trend,
        "cpi_yoy":      cpi_yoy,
        "cpi_trend":    cpi_trend,
        "nfp_change_k": nfp,
        "dxy":          dxy,
        "dxy_trend":    dxy_trend,
        "us10y":        us10y,    # 10-year Treasury yield (DGS10)
        "dxy_fred":     dxy_fred, # Broad dollar index (DTWEXBGS)
        "next_event":   next_event,
        "gold_summary": gold_summary,
    }

    _macro_cache = {"ts": now_ts, "data": data}
    return data
