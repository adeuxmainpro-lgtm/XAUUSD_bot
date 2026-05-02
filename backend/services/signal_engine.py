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
SIGNAL_WEAK     = "WEAK"
SIGNAL_WAIT     = "WAIT"

# Confluence thresholds
_T = {SIGNAL_STRONG: 75, SIGNAL_MODERATE: 60, SIGNAL_WEAK: 45}


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
    elif score >= _T[SIGNAL_WEAK]:
        level = SIGNAL_WEAK
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

    # SEUL bloquant : annonce HIGH impact dans moins de 30 minutes avec heure connue
    nxt = macro.get("next_event")
    if nxt and nxt.get("impact") == "HIGH":
        hours_until = nxt.get("hours_until", 99)
        has_time    = nxt.get("has_time", False)
        if has_time and hours_until < 0.5:
            blockers.append(f"Annonce HIGH impact dans moins de 30min : {nxt.get('title', '?')} — attendre la publication")

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
    if score < _T[SIGNAL_WEAK]:
        conds.append(f"Score de confluence doit atteindre 45% (actuellement {score}%)")

    return conds[:4]
