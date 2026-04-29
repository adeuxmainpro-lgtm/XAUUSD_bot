import httpx
import logging
import json

logger = logging.getLogger(__name__)

# CFTC public OData API - Gold futures (COMEX)
CFTC_API = "https://publicreporting.cftc.gov/api/odata/v1/HistoricalViewOiByContractAndTrader"


async def fetch_cot_gold() -> dict | None:
    """Fetch latest COT data for gold from CFTC public API."""
    try:
        params = {
            "$filter": "Commodity_Name eq 'GOLD'",
            "$top": "2",
            "$orderby": "Report_Date_as_YYYY_MM_DD desc",
        }
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(CFTC_API, params=params)
            r.raise_for_status()
            rows = r.json().get("value", [])

        if not rows:
            return _fallback_cot()

        row = rows[0]
        prev = rows[1] if len(rows) > 1 else None

        noncomm_long = int(row.get("NonComm_Positions_Long_All", 0) or 0)
        noncomm_short = int(row.get("NonComm_Positions_Short_All", 0) or 0)
        comm_long = int(row.get("Comm_Positions_Long_All", 0) or 0)
        comm_short = int(row.get("Comm_Positions_Short_All", 0) or 0)
        mm_long = int(row.get("M_Money_Positions_Long_All", 0) or 0)
        mm_short = int(row.get("M_Money_Positions_Short_All", 0) or 0)
        nonrept_long = int(row.get("NonRept_Positions_Long_All", 0) or 0)
        nonrept_short = int(row.get("NonRept_Positions_Short_All", 0) or 0)

        noncomm_net = noncomm_long - noncomm_short
        mm_net = mm_long - mm_short

        # Week-over-week change
        wow_mm_net = None
        if prev:
            prev_mm_long = int(prev.get("M_Money_Positions_Long_All", 0) or 0)
            prev_mm_short = int(prev.get("M_Money_Positions_Short_All", 0) or 0)
            wow_mm_net = mm_net - (prev_mm_long - prev_mm_short)

        spec_sentiment = "BULLISH" if noncomm_net > 0 else "BEARISH"
        mm_sentiment = "BULLISH" if mm_net > 0 else "BEARISH"

        # Extreme positioning (contrarian signal when very stretched)
        total_oi = noncomm_long + noncomm_short
        long_ratio = noncomm_long / total_oi if total_oi > 0 else 0.5
        contrarian_note = None
        if long_ratio > 0.75:
            contrarian_note = "Positionnement spéculatif extrême LONG → risque retournement"
        elif long_ratio < 0.25:
            contrarian_note = "Positionnement spéculatif extrême SHORT → risque retournement"

        return {
            "report_date": row.get("Report_Date_as_YYYY_MM_DD", ""),
            "noncomm_long": noncomm_long,
            "noncomm_short": noncomm_short,
            "noncomm_net": noncomm_net,
            "mm_long": mm_long,
            "mm_short": mm_short,
            "mm_net": mm_net,
            "mm_net_change": wow_mm_net,
            "comm_net": comm_long - comm_short,
            "nonrept_net": nonrept_long - nonrept_short,
            "spec_sentiment": spec_sentiment,
            "mm_sentiment": mm_sentiment,
            "long_ratio_pct": round(long_ratio * 100, 1),
            "contrarian_note": contrarian_note,
        }
    except Exception as e:
        logger.error(f"COT fetch error: {e}")
        return _fallback_cot()


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
