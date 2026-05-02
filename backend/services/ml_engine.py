"""
Machine Learning Engine — Trade Outcome Analysis & Weight Adaptation.

Analyzes closed trades to identify:
  - Win rates by RSI bucket, trend, direction, confluence range
  - Best/worst performing conditions
  - Suggests weight adjustments for confluence scoring

Weight adjustments are stored in a JSON file and read by sentiment_service
on each confluence computation.
"""
import json
import logging
import math
from pathlib import Path
from datetime import datetime, timezone

from backend.database import get_connection

logger = logging.getLogger(__name__)

WEIGHTS_FILE = Path(__file__).parent.parent / "ml_weights.json"

# Default weights (multipliers applied to base confluence weights)
_DEFAULT_WEIGHTS: dict = {
    "rsi_high":       1.0,   # RSI > 60 bullish signals
    "rsi_low":        1.0,   # RSI < 40 bearish signals
    "macd":           1.0,
    "ema_triple":     1.0,
    "bollinger":      1.0,
    "pattern_candle": 1.0,
    "pattern_chart":  1.0,
    "smc_ob":         1.0,
    "smc_fvg":        1.0,
    "smc_bos":        1.0,
    "cot":            1.0,
    "fear_greed":     1.0,
    "news_sentiment": 1.0,
    "etf_flows":      1.0,
}

_MIN_WEIGHT = 0.3
_MAX_WEIGHT = 2.0
_MIN_TRADES_FOR_ADJUSTMENT = 5


def load_weights() -> dict:
    """Load ML weight multipliers from file (or return defaults)."""
    try:
        if WEIGHTS_FILE.exists():
            with open(WEIGHTS_FILE) as f:
                data = json.load(f)
            # Merge with defaults to handle new keys
            merged = {**_DEFAULT_WEIGHTS, **data}
            return merged
    except Exception as e:
        logger.warning(f"Could not load ml_weights.json: {e}")
    return dict(_DEFAULT_WEIGHTS)


def save_weights(weights: dict):
    """Persist weight multipliers to JSON file."""
    try:
        with open(WEIGHTS_FILE, "w") as f:
            json.dump(weights, f, indent=2)
        logger.info("ML weights saved to ml_weights.json")
    except Exception as e:
        logger.error(f"Could not save ml_weights.json: {e}")


def _get_all_closed_trades(limit: int = 200) -> list[dict]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT direction, entry_price, exit_price, status, profit_eur,
               rsi_at_entry, trend_at_entry, confluence_score, patterns_at_entry,
               trade_date, session_at_entry, trade_score, wyckoff_phase
        FROM trades WHERE status IN ('WIN','LOSS','BE')
        ORDER BY trade_date DESC LIMIT ?
    """, (limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    for r in rows:
        try:
            r["patterns_at_entry"] = json.loads(r.get("patterns_at_entry") or "[]")
        except Exception:
            r["patterns_at_entry"] = []
    return rows


def _win_rate_for(trades: list[dict]) -> float | None:
    closed = [t for t in trades if t["status"] in ("WIN", "LOSS")]
    if not closed:
        return None
    return round(len([t for t in closed if t["status"] == "WIN"]) / len(closed) * 100, 1)


def _rsi_bucket(rsi: float | None) -> str:
    if rsi is None:
        return "unknown"
    if rsi < 30:   return "extreme_low"
    if rsi < 40:   return "low"
    if rsi < 50:   return "below_mid"
    if rsi < 60:   return "above_mid"
    if rsi < 70:   return "high"
    return "extreme_high"


def _confluence_bucket(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score < 45:   return "<45%"
    if score < 55:   return "45-55%"
    if score < 65:   return "55-65%"
    if score < 75:   return "65-75%"
    return "≥75%"


def analyze_trade_performance(limit: int = 100) -> dict:
    """
    Full trade outcome analysis.
    Returns win rates by multiple dimensions + suggested weight adjustments.
    """
    trades = _get_all_closed_trades(limit)
    closed = [t for t in trades if t["status"] in ("WIN", "LOSS")]

    if len(closed) < 3:
        return {
            "error": f"Historique insuffisant ({len(closed)} trades fermés < 3 requis)",
            "total_trades": len(closed),
        }

    wins   = [t for t in closed if t["status"] == "WIN"]
    losses = [t for t in closed if t["status"] == "LOSS"]
    global_wr = round(len(wins) / len(closed) * 100, 1)

    # ── By direction ──
    by_direction: dict = {}
    for d in ("BUY", "SELL"):
        sub = [t for t in closed if t.get("direction") == d]
        wr = _win_rate_for(sub)
        if wr is not None:
            by_direction[d] = {"win_rate": wr, "count": len(sub)}

    # ── By RSI bucket ──
    by_rsi: dict = {}
    for t in closed:
        b = _rsi_bucket(t.get("rsi_at_entry"))
        by_rsi.setdefault(b, []).append(t)
    by_rsi_wr = {b: {"win_rate": _win_rate_for(v), "count": len(v)}
                 for b, v in by_rsi.items() if _win_rate_for(v) is not None}

    # ── By confluence score ──
    by_conf: dict = {}
    for t in closed:
        b = _confluence_bucket(t.get("confluence_score"))
        by_conf.setdefault(b, []).append(t)
    by_conf_wr = {b: {"win_rate": _win_rate_for(v), "count": len(v)}
                  for b, v in by_conf.items() if _win_rate_for(v) is not None}

    # ── By trend at entry ──
    by_trend: dict = {}
    for t in closed:
        trend = t.get("trend_at_entry") or "UNKNOWN"
        by_trend.setdefault(trend, []).append(t)
    by_trend_wr = {b: {"win_rate": _win_rate_for(v), "count": len(v)}
                   for b, v in by_trend.items() if _win_rate_for(v) is not None}

    # ── By session ──
    by_session: dict = {}
    for t in closed:
        sess = t.get("session_at_entry") or "Inconnu"
        by_session.setdefault(sess, []).append(t)
    by_session_wr = {b: {"win_rate": _win_rate_for(v), "count": len(v)}
                     for b, v in by_session.items() if _win_rate_for(v) is not None}

    # ── By Wyckoff phase ──
    by_wyckoff: dict = {}
    for t in closed:
        phase = t.get("wyckoff_phase") or "Inconnu"
        by_wyckoff.setdefault(phase, []).append(t)
    by_wyckoff_wr = {b: {"win_rate": _win_rate_for(v), "count": len(v)}
                     for b, v in by_wyckoff.items() if _win_rate_for(v) is not None}

    # ── P&L metrics ──
    gross_profit = sum(t["profit_eur"] or 0 for t in wins)
    gross_loss   = abs(sum(t["profit_eur"] or 0 for t in losses))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else None
    avg_win   = round(gross_profit / len(wins),   2) if wins   else 0
    avg_loss  = round(gross_loss   / len(losses), 2) if losses else 0

    # ── Weight adjustment suggestions ──
    weight_adjustments = _compute_weight_adjustments(
        global_wr, by_rsi_wr, by_conf_wr, by_trend_wr
    )

    return {
        "generated_at":      datetime.now(timezone.utc).isoformat(),
        "total_trades":      len(closed),
        "wins":              len(wins),
        "losses":            len(losses),
        "win_rate":          global_wr,
        "profit_factor":     profit_factor,
        "avg_win_eur":       avg_win,
        "avg_loss_eur":      avg_loss,
        "by_direction":      by_direction,
        "by_rsi":            by_rsi_wr,
        "by_confluence":     by_conf_wr,
        "by_trend":          by_trend_wr,
        "by_session":        by_session_wr,
        "by_wyckoff":        by_wyckoff_wr,
        "weight_adjustments": weight_adjustments,
    }


def _compute_weight_adjustments(
    global_wr: float,
    by_rsi: dict,
    by_conf: dict,
    by_trend: dict,
) -> dict:
    """
    Suggest weight multiplier changes based on observed win rates.
    Win rate > 70% on ≥5 trades → increase weight by 30%.
    Win rate < 40% on ≥5 trades → decrease weight by 30%.
    """
    current = load_weights()
    adjusted = dict(current)
    changes: list[str] = []

    def _adjust(key: str, win_rate: float, count: int, label: str):
        if count < _MIN_TRADES_FOR_ADJUSTMENT:
            return
        old = adjusted.get(key, 1.0)
        if win_rate > 70:
            new = min(old * 1.30, _MAX_WEIGHT)
            if abs(new - old) > 0.05:
                adjusted[key] = round(new, 2)
                changes.append(f"{label}: {win_rate:.0f}% WR → poids {old:.2f}→{new:.2f} (+30%)")
        elif win_rate < 40:
            new = max(old * 0.70, _MIN_WEIGHT)
            if abs(new - old) > 0.05:
                adjusted[key] = round(new, 2)
                changes.append(f"{label}: {win_rate:.0f}% WR → poids {old:.2f}→{new:.2f} (-30%)")

    # RSI buckets
    for bucket, data in by_rsi.items():
        wr = data.get("win_rate") or 0
        cnt = data.get("count", 0)
        if bucket in ("low", "extreme_low"):
            _adjust("rsi_low", wr, cnt, f"RSI bas ({bucket})")
        elif bucket in ("high", "extreme_high"):
            _adjust("rsi_high", wr, cnt, f"RSI haut ({bucket})")

    # Confluence buckets
    for bucket, data in by_conf.items():
        wr = data.get("win_rate") or 0
        cnt = data.get("count", 0)
        if bucket == "≥75%":
            _adjust("macd", wr, cnt, "Score confluence ≥75%")

    if adjusted != current:
        save_weights(adjusted)
        logger.info(f"ML weights updated: {len(changes)} changes")

    return {"applied": adjusted, "changes": changes}


def apply_ml_weights(signals: list[dict]) -> list[dict]:
    """
    Apply ML weight multipliers to a list of confluence signals.
    Each signal: {"label": str, "direction": str, "weight": int}
    """
    weights = load_weights()

    _LABEL_MAP = {
        "RSI territoire haussier":   "rsi_high",
        "RSI momentum haussier":     "rsi_high",
        "RSI territoire baissier":   "rsi_low",
        "RSI momentum baissier":     "rsi_low",
        "MACD":                      "macd",
        "EMA20 > EMA50 > EMA200":   "ema_triple",
        "EMA20 < EMA50 < EMA200":   "ema_triple",
        "Bollinger":                 "bollinger",
        "Chandelier":               "pattern_candle",
        "Pattern chartiste":        "pattern_chart",
        "Order Block":               "smc_ob",
        "FVG":                       "smc_fvg",
        "BOS":                       "smc_bos",
        "CHoCH":                     "smc_bos",
        "COT":                       "cot",
        "Fear & Greed":              "fear_greed",
        "Sentiment news":            "news_sentiment",
        "Flux ETF":                  "etf_flows",
    }

    adjusted = []
    for sig in signals:
        label = sig.get("label", "")
        mult  = 1.0
        for keyword, wkey in _LABEL_MAP.items():
            if keyword.lower() in label.lower():
                mult = weights.get(wkey, 1.0)
                break
        new_weight = max(0.1, sig.get("weight", 1) * mult)
        adjusted.append({**sig, "weight": round(new_weight, 2)})

    return adjusted


def build_weekly_report() -> str:
    """Build a Telegram-ready weekly ML performance report."""
    data = analyze_trade_performance(50)

    if "error" in data:
        return f"📊 *Rapport ML Hebdomadaire*\n⚠️ {data['error']}"

    lines = [
        "📊 *Rapport ML Hebdomadaire — XAUUSD Bot*",
        f"📅 {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M UTC')}",
        "",
        f"📈 Win Rate global : *{data['win_rate']}%* ({data['wins']}W / {data['losses']}L)",
        f"💰 Profit Factor : {data.get('profit_factor') or 'N/A'}",
        f"🎯 Gain moyen : +{data['avg_win_eur']}€ | Perte moyenne : -{data['avg_loss_eur']}€",
    ]

    if data.get("by_direction"):
        lines.append("\n📌 *Par direction :*")
        for d, s in data["by_direction"].items():
            lines.append(f"  {d}: {s['win_rate']}% ({s['count']} trades)")

    if data.get("by_session"):
        lines.append("\n🕐 *Par session :*")
        for s, v in sorted(data["by_session"].items(), key=lambda x: x[1]["win_rate"], reverse=True):
            lines.append(f"  {s}: {v['win_rate']}% ({v['count']} trades)")

    if data.get("by_wyckoff"):
        lines.append("\n📊 *Par phase Wyckoff :*")
        for p, v in sorted(data["by_wyckoff"].items(), key=lambda x: x[1]["win_rate"], reverse=True):
            lines.append(f"  {p}: {v['win_rate']}% ({v['count']} trades)")

    changes = data.get("weight_adjustments", {}).get("changes", [])
    if changes:
        lines.append("\n🤖 *Ajustements de poids ML :*")
        for c in changes[:5]:
            lines.append(f"  • {c}")

    lines.append("\n_XAUUSD Bot · usage éducatif uniquement_")
    return "\n".join(lines)
