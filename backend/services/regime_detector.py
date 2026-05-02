"""
Market Regime Detector.

Identifies the current macro regime and adapts trading strategy accordingly:
  RISK-OFF     : stocks falling, VIX high, gold bullish (safe-haven demand)
  RISK-ON      : stocks rising, VIX low, gold neutral/bearish (risk appetite)
  STAGFLATION  : high inflation + weak growth → gold very bullish
  DEFLATION    : falling prices + recession signals → gold mixed
  QUALITY_FLIGHT: geopolitical crisis → gold very bullish
  NEUTRAL      : mixed / unclear signals
"""
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def detect_regime(
    market: dict,
    macro: dict,
    new_sources: dict,
    fear_greed: dict | None = None,
) -> dict:
    """
    Detect the current market regime from available data.

    Returns:
        regime:      string identifier
        label:       human-readable label
        gold_bias:   BULLISH | BEARISH | NEUTRAL
        description: explanation
        aggression:  how aggressively to trade gold (0.5 = cautious, 1.5 = aggressive)
    """
    corr    = new_sources.get("correlations", {}) if new_sources else {}
    yields  = new_sources.get("yields", {}) if new_sources else {}
    fed_nlp = new_sources.get("fed_nlp", {}) if new_sources else {}

    scores: dict[str, float] = {
        "risk_off":       0.0,
        "risk_on":        0.0,
        "stagflation":    0.0,
        "deflation":      0.0,
        "quality_flight": 0.0,
    }

    signals: list[str] = []

    # ── VIX ──────────────────────────────────────────────────────
    vix_data = corr.get("^VIX", {})
    vix_val  = vix_data.get("current")
    if vix_val is not None:
        if vix_val > 30:
            scores["risk_off"] += 3
            scores["quality_flight"] += 2
            signals.append(f"VIX extrême ({vix_val:.1f}) → panique")
        elif vix_val > 20:
            scores["risk_off"] += 2
            signals.append(f"VIX élevé ({vix_val:.1f}) → stress de marché")
        elif vix_val < 12:
            scores["risk_on"] += 2
            signals.append(f"VIX très bas ({vix_val:.1f}) → complacence")
        else:
            scores["risk_on"] += 1
            signals.append(f"VIX normal ({vix_val:.1f})")

    # ── S&P 500 trend ─────────────────────────────────────────────
    sp500_data = corr.get("^GSPC", {})
    sp500_sig  = sp500_data.get("signal")
    sp500_chg  = sp500_data.get("price_change_pct", 0) or 0
    if sp500_sig == "BULLISH" or sp500_chg > 1:
        scores["risk_on"] += 2
        signals.append("S&P500 haussier → risk-on")
    elif sp500_sig == "BEARISH" or sp500_chg < -1:
        scores["risk_off"] += 2
        signals.append("S&P500 baissier → risk-off")

    # ── DXY ──────────────────────────────────────────────────────
    dxy_data = corr.get("DX-Y.NYB", {})
    dxy_sig  = dxy_data.get("signal")
    if dxy_sig == "BEARISH":   # DXY falling = dollar weak = gold up
        scores["risk_off"] += 1
        scores["stagflation"] += 1
        signals.append("DXY baissier → soutien or")
    elif dxy_sig == "BULLISH":  # DXY rising = dollar strong = gold pressure
        scores["risk_on"] += 1
        signals.append("DXY haussier → pression or")

    # ── Treasury yields ───────────────────────────────────────────
    y10 = yields.get("y10")
    y2  = yields.get("y2")
    inverted = yields.get("inverted", False)
    spread = yields.get("spread_2_10", 0) or 0
    if inverted:
        scores["risk_off"] += 2
        scores["deflation"] += 1
        signals.append("Courbe inversée → signal récession")
    if y10 is not None and y10 > 4.5:
        scores["deflation"] += 1
        signals.append(f"Taux 10Y élevés ({y10:.2f}%) → pression sur or")
    elif y10 is not None and y10 < 3.5:
        scores["stagflation"] += 1
        scores["risk_off"] += 1
        signals.append(f"Taux 10Y bas ({y10:.2f}%) → soutien or")

    # ── Inflation (CPI) ───────────────────────────────────────────
    cpi = macro.get("cpi_yoy") if macro else None
    fed_rate = macro.get("fed_rate") if macro else None
    if cpi is not None:
        if cpi > 4.0:
            scores["stagflation"] += 2
            signals.append(f"CPI élevé ({cpi:.1f}%) → inflation, or haussier")
        elif cpi < 1.5:
            scores["deflation"] += 2
            signals.append(f"CPI bas ({cpi:.1f}%) → déflation, or mixte")
        else:
            signals.append(f"CPI modéré ({cpi:.1f}%)")

    # ── Fed NLP ───────────────────────────────────────────────────
    fed_score = fed_nlp.get("score", 0) or 0
    fed_bias  = fed_nlp.get("bias", "")
    if fed_bias == "DOVISH" or fed_score <= -2:
        scores["stagflation"] += 1
        scores["risk_off"] += 1
        signals.append("Fed dovish → taux en baisse, or haussier")
    elif fed_bias == "HAWKISH" or fed_score >= 2:
        scores["deflation"] += 1
        scores["risk_on"] += 1
        signals.append("Fed hawkish → taux élevés, pression or")

    # ── Fear & Greed ──────────────────────────────────────────────
    if fear_greed:
        fg_val = fear_greed.get("value", 50)
        if fg_val <= 20:
            scores["quality_flight"] += 2
            scores["risk_off"] += 1
            signals.append(f"Fear & Greed extrême ({fg_val}/100) → panique")
        elif fg_val >= 80:
            scores["risk_on"] += 2
            signals.append(f"Fear & Greed extrême greed ({fg_val}/100) → euphorie")

    # ── Determine dominant regime ─────────────────────────────────
    dominant = max(scores, key=lambda k: scores[k])
    dominant_score = scores[dominant]

    # Must exceed threshold to be classified
    if dominant_score < 2:
        dominant = "neutral"

    regime_map = {
        "risk_off": {
            "label":       "Risk-Off",
            "gold_bias":   "BULLISH",
            "description": "Aversion au risque — actions baissières, VIX élevé. Or = valeur refuge. BUY avec confiance.",
            "aggression":  1.3,
            "emoji":       "🔴",
        },
        "risk_on": {
            "label":       "Risk-On",
            "gold_bias":   "BEARISH",
            "description": "Appétit au risque — actions haussières, VIX bas. Or sous pression. SELL prudent.",
            "aggression":  0.7,
            "emoji":       "🟢",
        },
        "stagflation": {
            "label":       "Stagflation",
            "gold_bias":   "BULLISH",
            "description": "Stagflation — inflation haute + croissance faible. Or très haussier. BUY agressif.",
            "aggression":  1.5,
            "emoji":       "🟠",
        },
        "deflation": {
            "label":       "Déflation",
            "gold_bias":   "NEUTRAL",
            "description": "Déflation — taux réels positifs, récession potentielle. Or mixte. Trades sélectifs.",
            "aggression":  0.8,
            "emoji":       "🔵",
        },
        "quality_flight": {
            "label":       "Fuite vers la Qualité",
            "gold_bias":   "BULLISH",
            "description": "Crise géopolitique / panique — fuite vers les actifs sûrs. Or très haussier.",
            "aggression":  1.5,
            "emoji":       "⚠️",
        },
        "neutral": {
            "label":       "Neutre",
            "gold_bias":   "NEUTRAL",
            "description": "Régime mixte / incertain. Trades sélectifs avec gestion du risque renforcée.",
            "aggression":  1.0,
            "emoji":       "⚪",
        },
    }

    info = regime_map[dominant]

    return {
        "regime":      dominant,
        "label":       info["label"],
        "gold_bias":   info["gold_bias"],
        "description": info["description"],
        "aggression":  info["aggression"],
        "emoji":       info["emoji"],
        "scores":      {k: round(v, 1) for k, v in scores.items()},
        "signals":     signals[:6],
        "detected_at": datetime.now(timezone.utc).isoformat(),
    }
