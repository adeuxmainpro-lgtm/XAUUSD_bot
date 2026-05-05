"""
forex_factory_service.py
Fetches the Forex Factory economic calendar via the public XML feed
(https://nfs.faireconomy.media/ff_calendar_thisweek.xml).

Returns HIGH-impact USD events, filtered to the key gold-moving releases:
NFP, CPI, FOMC, ISM, PPI, PCE, Unemployment, Retail Sales, GDP.

Provides:
  - fetch_high_impact_events()  -> list[dict]  (cached 1h)
  - get_upcoming_events(hours)  -> list[dict]  events in the next N hours
  - is_high_impact_imminent(hours) -> dict | None  first imminent event or None
"""

import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta

import httpx

logger = logging.getLogger(__name__)

_FF_XML_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"

_HIGH_IMPACT_KEYWORDS = {
    "NFP", "CPI", "FOMC", "ISM", "PPI", "PCE",
    "UNEMPLOYMENT", "NON-FARM", "NONFARM",
    "RETAIL SALES", "GDP", "FEDERAL RESERVE",
    "INTEREST RATE", "INFLATION",
}

_cache: dict = {}
_CACHE_TTL = 3600  # 1h


def _keyword_match(title: str) -> bool:
    t = title.upper()
    return any(kw in t for kw in _HIGH_IMPACT_KEYWORDS)


def _parse_event_dt(date_str: str, time_str: str) -> datetime | None:
    """Parse a Forex Factory event date+time into a UTC datetime."""
    event_dt = None
    for fmt in ("%m-%d-%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            event_dt = datetime.strptime(date_str, fmt).replace(tzinfo=timezone.utc)
            break
        except ValueError:
            continue
    if event_dt is None:
        return None

    if time_str and time_str not in ("Tentative", "All Day", ""):
        for tfmt in ("%I:%M%p", "%H:%M", "%I%p"):
            try:
                t = datetime.strptime(time_str.strip(), tfmt)
                event_dt = event_dt.replace(hour=t.hour, minute=t.minute)
                break
            except ValueError:
                continue

    return event_dt


async def fetch_high_impact_events() -> list[dict]:
    """
    Return HIGH-impact USD events for the current week, filtered to
    gold-relevant releases (NFP, CPI, FOMC, ISM, PPI, PCE…).
    Cached 1h.
    """
    now_ts = datetime.now(timezone.utc).timestamp()
    cached = _cache.get("events")
    if cached and now_ts - cached["ts"] < _CACHE_TTL:
        return cached["data"]

    events: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=15, headers={"User-Agent": "Mozilla/5.0"}) as client:
            r = await client.get(_FF_XML_URL)
            r.raise_for_status()
            root = ET.fromstring(r.text)

        now = datetime.now(timezone.utc)

        for ev in root.findall(".//event"):
            country = (ev.findtext("country") or "").strip()
            impact  = (ev.findtext("impact")  or "").strip()
            title   = (ev.findtext("title")   or "").strip()
            date_str = (ev.findtext("date")   or "").strip()
            time_str = (ev.findtext("time")   or "").strip()

            # Only USD + High impact + keyword-matching titles
            if country != "USD":
                continue
            if impact.lower() != "high":
                continue
            if not _keyword_match(title):
                continue

            event_dt = _parse_event_dt(date_str, time_str)
            if event_dt is None:
                continue

            hours_until = (event_dt - now).total_seconds() / 3600
            has_time = bool(time_str and time_str not in ("Tentative", "All Day", ""))

            events.append({
                "title":       title,
                "date":        date_str,
                "time":        time_str,
                "impact":      "HIGH",
                "dt":          event_dt.isoformat(),
                "hours_until": round(hours_until, 2),
                "has_time":    has_time,
                "imminent":    0 < hours_until <= 2,
                "passed":      hours_until <= 0,
            })

        events.sort(key=lambda x: x["hours_until"])

    except Exception as e:
        logger.error(f"Forex Factory calendar error: {e}")

    _cache["events"] = {"ts": now_ts, "data": events}
    return events


async def get_upcoming_events(hours: float = 2.0) -> list[dict]:
    """Return HIGH-impact events scheduled within the next `hours` hours."""
    all_events = await fetch_high_impact_events()
    return [e for e in all_events if 0 < e["hours_until"] <= hours]


async def is_high_impact_imminent(hours: float = 2.0) -> dict | None:
    """
    Return the soonest upcoming HIGH-impact event within `hours`, or None.
    Used by the analysis engine to flag dangerous_period.
    """
    upcoming = await get_upcoming_events(hours)
    return upcoming[0] if upcoming else None
