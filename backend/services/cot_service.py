import csv
import io
import httpx
import logging
import json
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Primary: CFTC disaggregated CSV (no auth required, updated every Friday)
_CFTC_CSV_URL = "https://www.cftc.gov/dea/newcot/c_disagg.txt"
# Fallback: CFTC public OData API
_CFTC_API = "https://publicreporting.cftc.gov/api/odata/v1/HistoricalViewOiByContractAndTrader"

_cot_cache: dict = {}
_COT_CACHE_TTL = 6 * 3600  # 6h — data is weekly, refresh is generous


async def _fetch_cot_csv() -> dict | None:
    """Parse the CFTC disaggregated CSV file and extract Gold (COMEX) positions."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(_CFTC_CSV_URL, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()

        reader = csv.DictReader(io.StringIO(r.text))
        gold_rows = []
        for row in reader:
            name = row.get("Market_and_Exchange_Names", "").strip().upper()
            if "GOLD" in name and "COMEX" in name:
                gold_rows.append(row)
            if len(gold_rows) >= 2:
                break  # only need latest + previous

        if not gold_rows:
            logger.warning("COT CSV: no GOLD-COMEX row found")
            return None

        def _int(row, key):
            try:
                return int(row.get(key, 0) or 0)
            except (ValueError, TypeError):
                return 0

        row  = gold_rows[0]
        prev = gold_rows[1] if len(gold_rows) > 1 else None

        mm_long  = _int(row, "M_Money_Positions_Long_All")
        mm_short = _int(row, "M_Money_Positions_Short_All")
        prod_long  = _int(row, "Prod_Merc_Positions_Long_All")
        prod_short = _int(row, "Prod_Merc_Positions_Short_All")
        swap_long  = _int(row, "Swap__Positions_Long_All_")
        swap_short = _int(row, "Swap__Positions_Short_All")
        other_long  = _int(row, "Other_Rept_Positions_Long_All")
        other_short = _int(row, "Other_Rept_Positions_Short_All")
        nonrept_long  = _int(row, "NonRept_Positions_Long_All")
        nonrept_short = _int(row, "NonRept_Positions_Short_All")

        mm_net = mm_long - mm_short
        prod_net = prod_long - prod_short

        wow_mm_net = None
        if prev:
            prev_mm_long  = _int(prev, "M_Money_Positions_Long_All")
            prev_mm_short = _int(prev, "M_Money_Positions_Short_All")
            wow_mm_net = mm_net - (prev_mm_long - prev_mm_short)

        report_date = row.get("Report_Date_as_YYYY_MM_DD", "").strip()

        total_mm = mm_long + mm_short
        long_ratio = mm_long / total_mm if total_mm > 0 else 0.5
        contrarian_note = None
        if long_ratio > 0.75:
            contrarian_note = "Money Managers extrêmement LONG → risque retournement baissier"
        elif long_ratio < 0.25:
            contrarian_note = "Money Managers extrêmement SHORT → risque retournement haussier"

        return {
            "report_date": report_date,
            "noncomm_long":  mm_long,
            "noncomm_short": mm_short,
            "noncomm_net":   mm_net,
            "mm_long":  mm_long,
            "mm_short": mm_short,
            "mm_net":   mm_net,
            "mm_net_change": wow_mm_net,
            "comm_net":    prod_net,
            "nonrept_net": nonrept_long - nonrept_short,
            "spec_sentiment": "BULLISH" if mm_net > 0 else "BEARISH",
            "mm_sentiment":   "BULLISH" if mm_net > 0 else "BEARISH",
            "long_ratio_pct": round(long_ratio * 100, 1),
            "contrarian_note": contrarian_note,
            "source": "csv",
        }
    except Exception as e:
        logger.error(f"COT CSV fetch error: {e}")
        return None


async def fetch_cot_gold() -> dict | None:
    """Fetch latest COT data for gold. Primary: CFTC CSV. Fallback: OData API."""
    # Check in-memory cache first
    now_ts = datetime.now(timezone.utc).timestamp()
    if _cot_cache.get("ts") and now_ts - _cot_cache["ts"] < _COT_CACHE_TTL:
        return _cot_cache["data"]

    # Try CSV first (more reliable, no auth needed)
    data = await _fetch_cot_csv()

    # Fallback to OData API if CSV fails
    if data is None:
        data = await _fetch_cot_odata()

    if data is None:
        return _fallback_cot()

    _cot_cache["ts"] = now_ts
    _cot_cache["data"] = data
    return data


async def _fetch_cot_odata() -> dict | None:
    """Fallback: CFTC OData API (legacy disaggregated endpoint)."""
    try:
        params = {
            "$filter": "Commodity_Name eq 'GOLD'",
            "$top": "2",
            "$orderby": "Report_Date_as_YYYY_MM_DD desc",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(_CFTC_API, params=params)
            r.raise_for_status()
            rows = r.json().get("value", [])

        if not rows:
            return None

        row  = rows[0]
        prev = rows[1] if len(rows) > 1 else None

        mm_long  = int(row.get("M_Money_Positions_Long_All",  0) or 0)
        mm_short = int(row.get("M_Money_Positions_Short_All", 0) or 0)
        comm_long  = int(row.get("Comm_Positions_Long_All",  0) or 0)
        comm_short = int(row.get("Comm_Positions_Short_All", 0) or 0)
        nonrept_long  = int(row.get("NonRept_Positions_Long_All",  0) or 0)
        nonrept_short = int(row.get("NonRept_Positions_Short_All", 0) or 0)

        mm_net = mm_long - mm_short
        wow_mm_net = None
        if prev:
            prev_mm_long  = int(prev.get("M_Money_Positions_Long_All",  0) or 0)
            prev_mm_short = int(prev.get("M_Money_Positions_Short_All", 0) or 0)
            wow_mm_net = mm_net - (prev_mm_long - prev_mm_short)

        total_mm  = mm_long + mm_short
        long_ratio = mm_long / total_mm if total_mm > 0 else 0.5
        contrarian_note = None
        if long_ratio > 0.75:
            contrarian_note = "Positionnement spéculatif extrême LONG → risque retournement"
        elif long_ratio < 0.25:
            contrarian_note = "Positionnement spéculatif extrême SHORT → risque retournement"

        return {
            "report_date":     row.get("Report_Date_as_YYYY_MM_DD", ""),
            "noncomm_long":    mm_long,
            "noncomm_short":   mm_short,
            "noncomm_net":     mm_net,
            "mm_long":         mm_long,
            "mm_short":        mm_short,
            "mm_net":          mm_net,
            "mm_net_change":   wow_mm_net,
            "comm_net":        comm_long - comm_short,
            "nonrept_net":     nonrept_long - nonrept_short,
            "spec_sentiment":  "BULLISH" if mm_net > 0 else "BEARISH",
            "mm_sentiment":    "BULLISH" if mm_net > 0 else "BEARISH",
            "long_ratio_pct":  round(long_ratio * 100, 1),
            "contrarian_note": contrarian_note,
            "source":          "odata",
        }
    except Exception as e:
        logger.error(f"COT OData fetch error: {e}")
        return None


def _fallback_cot() -> dict:
    """Return minimal structure when CFTC API is unavailable."""
    return {
        "report_date": None,
        "noncomm_net": None,
        "mm_net": None,
        "mm_net_change": None,
        "comm_net": None,
        "spec_sentiment": "UNKNOWN",
        "mm_sentiment": "UNKNOWN",
        "long_ratio_pct": None,
        "contrarian_note": None,
        "error": True,
    }
