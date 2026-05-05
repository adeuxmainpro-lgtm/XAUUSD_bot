"""
Pre-AI signal evaluation engine.
RULE: BUY or SELL in 99.9% of cases.
ATTENDRE is reserved ONLY for HIGH-impact macro announcements < 15 minutes away
with an exact confirmed time (has_time=True). No other blocker exists.
"""
import logging

logger = logging.getLogger(__name__)

SIGNAL_STRONG    = "STRONG"      # score > 75  → 1.0% position
SIGNAL_MODERATE  = "MODERATE"    # score 60-75 → 0.75% position
SIGNAL_WEAK      = "WEAK"        # score 40-60 → 0.5% position
SIGNAL_VERY_WEAK = "VERY_WEAK"   # score < 40  → 0.25% position (still directional)
SIGNAL_WAIT      = "WAIT"        # ONLY when HIGH macro < 15min


def evaluate_signal(market: dict, macro: dict, confluence: dict) -> dict:
    """
    Return signal level + direction.
    Direction is ALWAYS BUY or SELL, except when a HIGH-impact macro
    event is less than 15 minutes away.
    """
    score     = confluence.get("score", 0)
    direction = confluence.get("direction", "NEUTRAL")

    # ── ONLY blocker allowed ──────────────────────────────────────
    blocker = _check_macro_blocker(macro)
    if blocker:
        return {
            "signal_level":        SIGNAL_WAIT,
            "confluence_score":    score,
            "direction":           "ATTENDRE",
            "blocking_conditions": [blocker],
            "watch_conditions":    [],
        }

    # ── Determine direction ───────────────────────────────────────
    final_direction = _resolve_direction(direction, market, confluence)

    # ── Signal level purely from score ───────────────────────────
    if score > 75:
        level = SIGNAL_STRONG
    elif score >= 60:
        level = SIGNAL_MODERATE
    elif score >= 40:
        level = SIGNAL_WEAK
    else:
        level = SIGNAL_VERY_WEAK

    return {
        "signal_level":        level,
        "confluence_score":    score,
        "direction":           final_direction,
        "blocking_conditions": [],
        "watch_conditions":    _build_watch(market, confluence, final_direction),
    }


def _check_macro_blocker(macro: dict) -> str | None:
    """Returns a blocker message ONLY if HIGH-impact event < 15 minutes."""
    nxt = macro.get("next_event") if macro else None
    if not nxt:
        return None
    if nxt.get("impact") != "HIGH":
        return None
    if not nxt.get("has_time", False):
        return None
    hours_until = nxt.get("hours_until", 99)
    if hours_until < 0.25:   # < 15 minutes
        title = nxt.get("title", "Annonce macro")
        mins  = max(1, int(hours_until * 60))
        return f"Annonce HIGH impact dans ~{mins}min : {title} — reprendre après publication"
    return None


def _resolve_direction(confluence_dir: str, market: dict, confluence: dict) -> str:
    """
    Resolve a definitive BUY or SELL direction.
    Priority: confluence direction → RSI+MACD tiebreak → BUY default (gold long-term bullish).
    """
    # Confluence is clear
    if confluence_dir in ("BUY", "SELL"):
        return confluence_dir

    # Count bullish vs bearish signals in the confluence signals list
    signals = confluence.get("signals", [])
    bull = sum(1 for s in signals if s.get("direction") in ("BUY", "BULLISH", "bullish"))
    bear = sum(1 for s in signals if s.get("direction") in ("SELL", "BEARISH", "bearish"))

    if bull > bear:
        return "BUY"
    if bear > bull:
        return "SELL"

    # Tiebreak: RSI + MACD
    rsi  = market.get("rsi")
    macd = market.get("macd_histogram") or market.get("macd")
    if rsi is not None:
        if rsi > 50:
            return "BUY"
        if rsi < 50:
            return "SELL"
        # rsi == 50 exactly → use MACD
        if macd is not None:
            if macd > 0:
                return "BUY"
            if macd < 0:
                return "SELL"

    # Default: BUY (gold is in long-term uptrend)
    return "BUY"


def _build_watch(market: dict, confluence: dict, direction: str) -> list[str]:
    """Informational watch conditions — never used as blockers."""
    conds: list[str] = []
    rsi   = market.get("rsi")
    price = market.get("price")

    if rsi is not None:
        if direction == "BUY" and rsi > 70:
            conds.append(f"RSI en surachat ({rsi:.0f}) — surveiller un retracement avant entrée")
        elif direction == "SELL" and rsi < 30:
            conds.append(f"RSI en survente ({rsi:.0f}) — surveiller un rebond avant entrée")

    if price:
        if direction == "BUY":
            resis = sorted(r for r in market.get("resistances", []) if r > price)
            if resis:
                conds.append(f"Prochaine résistance : ${resis[0]:.2f}")
        elif direction == "SELL":
            sups = sorted((s for s in market.get("supports", []) if s < price), reverse=True)
            if sups:
                conds.append(f"Prochain support : ${sups[0]:.2f}")

    return conds[:3]
