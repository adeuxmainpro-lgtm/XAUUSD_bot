"""
Pre-AI signal evaluation engine.
Computes signal level, blocking conditions and watch conditions
from the confluence score before the LLM runs.
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

SIGNAL_STRONG   = "STRONG"
SIGNAL_MODERATE = "MODERATE"
SIGNAL_WAIT     = "WAIT"

# Confluence thresholds
_T = {SIGNAL_STRONG: 80, SIGNAL_MODERATE: 70, SIGNAL_WAIT: 50}

# Asian thin-liquidity hours (UTC): 21:00-02:00
_ASIAN_THIN_HOURS = set(range(0, 3)) | {21, 22, 23}


def evaluate_signal(market: dict, macro: dict, confluence: dict) -> dict:
    """Return signal level, blocking conditions and watch conditions."""
    score     = confluence.get("score", 0)
    direction = confluence.get("direction", "NEUTRAL")

    blockers = _check_blockers(market, macro, confluence)

    if blockers:
        level = SIGNAL_WAIT
    elif score >= _T[SIGNAL_STRONG]:
        level = SIGNAL_STRONG
    elif score >= _T[SIGNAL_MODERATE]:
        level = SIGNAL_MODERATE
    else:
        level = SIGNAL_WAIT

    watch = _compute_watch(market, confluence) if level == SIGNAL_WAIT else []

    return {
        "signal_level":        level,
        "confluence_score":    score,
        "direction":           direction,
        "blocking_conditions": blockers,
        "watch_conditions":    watch,
    }


def _check_blockers(market: dict, macro: dict, confluence: dict) -> list[str]:
    blockers: list[str] = []

    # 1. HIGH-impact macro event within 4 hours (days_until == 0)
    nxt = macro.get("next_event")
    if nxt and nxt.get("impact") == "HIGH" and nxt.get("days_until", 99) == 0:
        blockers.append(f"Annonce HIGH impact dans les 4h : {nxt.get('title', '?')} — risque de gap")

    # 2. ATR abnormally high (> 0.8% of price)
    atr_pct = market.get("atr_pct")
    if atr_pct and atr_pct > 0.8:
        blockers.append(f"Volatilité ATR excessive ({atr_pct:.2f}%) — risque de stop hunting")

    # 3. Asian thin session (22:00-02:00 UTC) — warning only, not hard block
    utc_hour = datetime.now(timezone.utc).hour
    if utc_hour in _ASIAN_THIN_HOURS:
        blockers.append("Session asiatique creuse — spread élargi, liquidité faible")

    # 4. ≥3 contradictory signals in each direction
    sigs   = confluence.get("signals", [])
    buy_n  = sum(1 for s in sigs if s["direction"] == "BUY")
    sell_n = sum(1 for s in sigs if s["direction"] == "SELL")
    if buy_n >= 3 and sell_n >= 3:
        blockers.append(f"Signaux contradictoires — {buy_n} haussiers vs {sell_n} baissiers")

    return blockers


def _compute_watch(market: dict, confluence: dict) -> list[str]:
    conds: list[str] = []
    score     = confluence.get("score", 0)
    direction = confluence.get("direction", "NEUTRAL")
    price     = market.get("price")
    rsi       = market.get("rsi")
    ts        = market.get("trend_short")

    # RSI condition
    if rsi is not None:
        if direction == "BUY" and 50 < rsi < 70:
            conds.append(f"RSI doit retomber sous 50 (actuellement {rsi:.0f})")
        elif direction == "SELL" and 30 < rsi < 50:
            conds.append(f"RSI doit dépasser 50 (actuellement {rsi:.0f})")

    # Trend condition
    if direction == "BUY" and ts != "BULLISH":
        conds.append("Tendance CT doit confirmer BULLISH (EMA20 doit dépasser EMA50)")
    elif direction == "SELL" and ts != "BEARISH":
        conds.append("Tendance CT doit confirmer BEARISH (EMA20 doit repasser sous EMA50)")

    # Key level condition
    if price:
        if direction == "BUY":
            resis = [r for r in market.get("resistances", []) if r > price]
            if resis:
                near = min(resis)
                conds.append(f"Prix doit casser la résistance ${near:.2f}")
        elif direction == "SELL":
            sups = [s for s in market.get("supports", []) if s < price]
            if sups:
                near = max(sups)
                conds.append(f"Prix doit casser le support ${near:.2f}")

    # Confluence gap
    if score < _T[SIGNAL_MODERATE]:
        conds.append(f"Score de confluence doit atteindre 70% (actuellement {score}%)")

    return conds[:4]
