"""
Professional SMC/ICT trading strategy engine.
Provides: MTF bias analysis, kill zones, liquidity sweeps, Wyckoff phase,
RSI divergence detection, and a 0-100 trade quality score.
"""
import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import ta

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _peaks(arr: np.ndarray, order: int = 3) -> list[int]:
    return [i for i in range(order, len(arr) - order)
            if arr[i] == arr[i - order:i + order + 1].max()]


def _troughs(arr: np.ndarray, order: int = 3) -> list[int]:
    return [i for i in range(order, len(arr) - order)
            if arr[i] == arr[i - order:i + order + 1].min()]


def _df(ohlc: list[dict]) -> pd.DataFrame | None:
    if not ohlc or len(ohlc) < 20:
        return None
    df = pd.DataFrame(ohlc).sort_values("datetime").reset_index(drop=True)
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# MTF ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def _bias_for_tf(ohlc: list[dict]) -> dict:
    """Compute directional bias for one timeframe using EMA trend + swing structure."""
    df = _df(ohlc)
    if df is None:
        return {"bias": "NEUTRAL", "detail": "Données insuffisantes"}

    c = df["close"].values.astype(float)
    h = df["high"].values.astype(float)
    l = df["low"].values.astype(float)

    # EMA trend
    ema20_s = ta.trend.EMAIndicator(pd.Series(c), window=20).ema_indicator().values
    ema50_s = ta.trend.EMAIndicator(pd.Series(c), window=50).ema_indicator().values

    ema20_v = float(ema20_s[-1]) if not np.isnan(ema20_s[-1]) else None
    ema50_v = float(ema50_s[-1]) if not np.isnan(ema50_s[-1]) else None

    if ema20_v is not None and ema50_v is not None:
        ema_bull = ema20_v > ema50_v
        ema_desc = f"EMA20({'>' if ema_bull else '<'})EMA50"
    else:
        ema_bull = None
        ema_desc = "EMA N/A"

    # Swing structure
    w = min(40, len(c))
    rh = h[-w:]
    rl = l[-w:]
    peaks   = _peaks(rh, order=3)
    troughs = _troughs(rl, order=3)

    swing_bull: bool | None = None
    sw_desc = "structure mixte"
    if len(peaks) >= 2 and len(troughs) >= 2:
        hh = bool(rh[peaks[-1]] > rh[peaks[-2]])
        lh = bool(rh[peaks[-1]] < rh[peaks[-2]])
        hl = bool(rl[troughs[-1]] > rl[troughs[-2]])
        ll = bool(rl[troughs[-1]] < rl[troughs[-2]])
        if hh and hl:
            swing_bull = True
            sw_desc = "HH+HL"
        elif lh and ll:
            swing_bull = False
            sw_desc = "LH+LL"

    # Weighted score: swing=2, ema=1
    score = 0
    if swing_bull is True:   score += 2
    elif swing_bull is False: score -= 2
    if ema_bull is True:     score += 1
    elif ema_bull is False:  score -= 1

    if score >= 2:
        bias = "BULLISH"
    elif score <= -2:
        bias = "BEARISH"
    else:
        bias = "NEUTRAL"

    return {"bias": bias, "detail": f"{ema_desc}, {sw_desc}"}


def analyze_mtf(
    ohlc_15m: list[dict],
    ohlc_1h:  list[dict],
    ohlc_4h:  list[dict],
    ohlc_1d:  list[dict],
) -> dict:
    """
    Multi-timeframe analysis across 4 timeframes.
    Primary bias = 4H. 3/4 alignment required for strong signal.
    """
    b15m = _bias_for_tf(ohlc_15m)
    b1h  = _bias_for_tf(ohlc_1h)
    b4h  = _bias_for_tf(ohlc_4h)
    b1d  = _bias_for_tf(ohlc_1d)

    biases = {"1D": b1d, "4H": b4h, "1H": b1h, "15M": b15m}

    # 4H is the primary trading direction
    primary_bias = b4h["bias"] if b4h["bias"] != "NEUTRAL" else b1h["bias"]

    directions = [v["bias"] for v in biases.values() if v["bias"] != "NEUTRAL"]
    bull_count = directions.count("BULLISH")
    bear_count = directions.count("BEARISH")

    # Count alignment with the primary bias
    if primary_bias == "BULLISH":
        aligned_count = bull_count
    elif primary_bias == "BEARISH":
        aligned_count = bear_count
    else:
        aligned_count = 0

    return {
        "biases":         biases,
        "primary_bias":   primary_bias,
        "bull_count":     bull_count,
        "bear_count":     bear_count,
        "aligned_count":  aligned_count,
        "aligned_str":    f"{aligned_count}/4 TF alignés",
        "bias_4h":        b4h["bias"],
        "bias_1d":        b1d["bias"],
    }


# ─────────────────────────────────────────────────────────────────────────────
# KILL ZONE
# ─────────────────────────────────────────────────────────────────────────────

_SESSIONS = [
    # (id, label, start_utc, end_utc, quality, color)
    ("london_open",   "London Open",      8.0,   10.0,  "best",  "green"),
    ("ny_open",       "New York Open",    13.5,  15.5,  "best",  "green"),
    ("london_close",  "London Close",     16.0,  17.0,  "good",  "yellow"),
    ("asian",         "Session Asiatique", 0.0,   7.0,  "avoid", "red"),
]


def detect_kill_zone() -> dict:
    """
    Identifies the current ICT kill zone.
    Returns session info with active flag and quality rating.
    """
    now = datetime.now(timezone.utc)
    t = now.hour + now.minute / 60.0

    for sid, name, start, end, quality, color in _SESSIONS:
        if start <= t < end:
            return {
                "id":      sid,
                "name":    name,
                "quality": quality,
                "color":   color,
                "active":  True,
                "tradeable": quality != "avoid",
            }

    return {
        "id":      "off_hours",
        "name":    "Hors session",
        "quality": "avoid",
        "color":   "red",
        "active":  False,
        "tradeable": False,
    }


# ─────────────────────────────────────────────────────────────────────────────
# LIQUIDITY SWEEP
# ─────────────────────────────────────────────────────────────────────────────

def detect_liquidity_sweep(ohlc: list[dict]) -> dict:
    """
    Detects recent liquidity sweeps on the last candles.
    A bearish sweep: wick above swing high then closed below it → SELL.
    A bullish sweep: wick below swing low then closed above it → BUY.
    """
    df = _df(ohlc)
    if df is None:
        return {"detected": False, "type": None, "direction": None, "level": None, "desc": ""}

    h = df["high"].values.astype(float)
    l = df["low"].values.astype(float)
    c = df["close"].values.astype(float)
    n = len(c)

    if n < 20:
        return {"detected": False, "type": None, "direction": None, "level": None, "desc": ""}

    # Reference window for swing levels (candles -35 to -5)
    ref_end   = max(n - 5, 15)
    ref_start = max(ref_end - 30, 0)
    ref_h = h[ref_start:ref_end]
    ref_l = l[ref_start:ref_end]

    swing_high = float(np.max(ref_h))
    swing_low  = float(np.min(ref_l))

    # Check last 5 candles for sweep
    for i in range(n - 5, n):
        # Bearish sweep: wick above swing high, close below
        if h[i] > swing_high and c[i] < swing_high:
            return {
                "detected":  True,
                "type":      "bearish_sweep",
                "direction": "SELL",
                "level":     round(swing_high, 2),
                "desc":      f"Sweep baissier — wick au-dessus de ${swing_high:.2f} puis rejet",
            }
        # Bullish sweep: wick below swing low, close above
        if l[i] < swing_low and c[i] > swing_low:
            return {
                "detected":  True,
                "type":      "bullish_sweep",
                "direction": "BUY",
                "level":     round(swing_low, 2),
                "desc":      f"Sweep haussier — wick sous ${swing_low:.2f} puis rejet",
            }

    return {
        "detected":  False,
        "type":      None,
        "direction": None,
        "level":     None,
        "desc":      "Aucun liquidity sweep récent",
    }


# ─────────────────────────────────────────────────────────────────────────────
# WYCKOFF PHASE
# ─────────────────────────────────────────────────────────────────────────────

def detect_wyckoff_phase(ohlc: list[dict]) -> dict:
    """
    Identifies the Wyckoff market phase using price structure and EMAs.
    Phases: Mark Up, Mark Down, Accumulation, Distribution, Range.
    """
    df = _df(ohlc)
    if df is None:
        return {"phase": "Unknown", "desc": "Données insuffisantes", "trading_bias": "NEUTRAL"}

    c = df["close"].values.astype(float)
    h = df["high"].values.astype(float)
    l = df["low"].values.astype(float)
    n = len(c)

    w = min(60, n)
    recent_c = c[-w:]
    recent_h = h[-w:]
    recent_l = l[-w:]

    # EMA slope
    ema20 = ta.trend.EMAIndicator(pd.Series(c), window=20).ema_indicator().values
    ema50 = ta.trend.EMAIndicator(pd.Series(c), window=50).ema_indicator().values

    ema20_rising = float(ema20[-1]) > float(ema20[-5]) if not np.isnan(ema20[-1]) and not np.isnan(ema20[-5]) else None
    ema50_rising = float(ema50[-1]) > float(ema50[-10]) if not np.isnan(ema50[-1]) and not np.isnan(ema50[-10]) else None

    # Swing structure in recent window
    peaks   = _peaks(recent_h, order=4)
    troughs = _troughs(recent_l, order=4)

    hh = hl = lh = ll = False
    if len(peaks) >= 2:
        hh = bool(recent_h[peaks[-1]] > recent_h[peaks[-2]])
        lh = not hh
    if len(troughs) >= 2:
        hl = bool(recent_l[troughs[-1]] > recent_l[troughs[-2]])
        ll = not hl

    # Range detection: small price movement relative to ATR
    atr_approx = float(np.mean(recent_h - recent_l))
    price_range = float(np.max(recent_h) - np.min(recent_l))
    is_ranging = price_range < atr_approx * 6

    current = float(c[-1])
    range_mid = (float(np.max(recent_h)) + float(np.min(recent_l))) / 2

    if hh and hl and ema20_rising and ema50_rising:
        phase        = "Mark Up"
        desc         = "Phase Mark Up — tendance haussière (HH+HL+EMAs croissantes) · Trader les pullbacks BUY"
        trading_bias = "BULLISH"
    elif lh and ll and ema20_rising is False and ema50_rising is False:
        phase        = "Mark Down"
        desc         = "Phase Mark Down — tendance baissière (LH+LL+EMAs décroissantes) · Trader les rebonds SELL"
        trading_bias = "BEARISH"
    elif is_ranging and current < range_mid:
        phase        = "Accumulation"
        desc         = "Phase Accumulation — range en bas de range · Préparer des BUY sur les tests du support"
        trading_bias = "BULLISH"
    elif is_ranging and current > range_mid:
        phase        = "Distribution"
        desc         = "Phase Distribution — range en haut de range · Préparer des SELL sur les tests de résistance"
        trading_bias = "BEARISH"
    else:
        phase        = "Transition"
        desc         = "Phase Transition — structure incertaine · Attendre une direction claire"
        trading_bias = "NEUTRAL"

    return {"phase": phase, "desc": desc, "trading_bias": trading_bias}


# ─────────────────────────────────────────────────────────────────────────────
# RSI DIVERGENCE
# ─────────────────────────────────────────────────────────────────────────────

def detect_rsi_divergence(ohlc: list[dict]) -> dict:
    """
    Detects RSI divergences.
    Bearish: price HH + RSI LH → SELL signal.
    Bullish: price LL + RSI HL → BUY signal.
    """
    df = _df(ohlc)
    if df is None or len(df) < 30:
        return {"detected": False, "type": None, "direction": None, "desc": ""}

    c = df["close"].values.astype(float)
    h = df["high"].values.astype(float)
    l = df["low"].values.astype(float)

    rsi_vals = ta.momentum.RSIIndicator(pd.Series(c), window=14).rsi().values

    w = min(50, len(c))
    rh  = h[-w:]
    rl  = l[-w:]
    rsi = rsi_vals[-w:]

    price_peaks   = _peaks(rh, order=4)
    price_troughs = _troughs(rl, order=4)

    # Bearish divergence: price HH but RSI LH (last 2 peaks)
    if len(price_peaks) >= 2:
        p1, p2 = price_peaks[-2], price_peaks[-1]
        if rh[p2] > rh[p1] and not np.isnan(rsi[p1]) and not np.isnan(rsi[p2]) and rsi[p2] < rsi[p1]:
            strength = "forte" if abs(rsi[p2] - rsi[p1]) > 8 else "modérée"
            return {
                "detected":  True,
                "type":      "bearish",
                "direction": "SELL",
                "strength":  strength,
                "desc":      (f"Divergence RSI baissière {strength} — "
                              f"prix HH (${rh[p2]:.2f}>${rh[p1]:.2f}) "
                              f"mais RSI LH ({rsi[p2]:.1f}<{rsi[p1]:.1f})"),
            }

    # Bullish divergence: price LL but RSI HL (last 2 troughs)
    if len(price_troughs) >= 2:
        t1, t2 = price_troughs[-2], price_troughs[-1]
        if rl[t2] < rl[t1] and not np.isnan(rsi[t1]) and not np.isnan(rsi[t2]) and rsi[t2] > rsi[t1]:
            strength = "forte" if abs(rsi[t2] - rsi[t1]) > 8 else "modérée"
            return {
                "detected":  True,
                "type":      "bullish",
                "direction": "BUY",
                "strength":  strength,
                "desc":      (f"Divergence RSI haussière {strength} — "
                              f"prix LL (${rl[t2]:.2f}<${rl[t1]:.2f}) "
                              f"mais RSI HL ({rsi[t2]:.1f}>{rsi[t1]:.1f})"),
            }

    return {"detected": False, "type": None, "direction": None, "desc": "Aucune divergence RSI"}


# ─────────────────────────────────────────────────────────────────────────────
# TRADE SCORE  (0-100)
# ─────────────────────────────────────────────────────────────────────────────

def compute_trade_score(
    mtf:             dict,
    kill_zone:       dict,
    liquidity_sweep: dict,
    patterns:        dict,
    rsi_divergence:  dict,
    market:          dict,
) -> dict:
    """
    Professional trade quality score (0-100).

    Scoring:
      MTF ≥ 3/4 aligned  : +30 pts
      MTF = 2/4 aligned   : +15 pts
      Kill zone active    : +20 pts
      Liquidity sweep     : +20 pts
      OB + FVG present    : +15 pts  (OB or FVG only: +8)
      RSI divergence      : +15 pts

    Signal level:
      ≥90 → VERY_STRONG (1.5% position)
      80-89 → STRONG (1.0%)
      70-79 → MODERATE (0.5%)
      <70  → WEAK (no trade)
    """
    score = 0
    conditions: dict[str, bool] = {}
    details: list[str] = []

    # 1. MTF alignment (30 pts)
    aligned = mtf.get("aligned_count", 0)
    if aligned >= 3:
        score += 30
        conditions["mtf_alignment"] = True
        details.append(f"✅ MTF {aligned}/4 alignés (+30)")
    elif aligned == 2:
        score += 15
        conditions["mtf_alignment"] = False
        details.append(f"⚡ MTF {aligned}/4 alignés (+15)")
    else:
        conditions["mtf_alignment"] = False
        details.append(f"❌ MTF {aligned}/4 alignés (+0)")

    # 2. Kill zone (20 pts)
    kz_ok = kill_zone.get("tradeable", False)
    if kz_ok:
        score += 20
        conditions["kill_zone_active"] = True
        details.append(f"✅ {kill_zone.get('name', '?')} (+20)")
    else:
        conditions["kill_zone_active"] = False
        details.append(f"❌ {kill_zone.get('name', 'Hors session')} (+0)")

    # 3. Liquidity sweep (20 pts)
    sweep_ok = liquidity_sweep.get("detected", False)
    if sweep_ok:
        score += 20
        conditions["liquidity_sweep"] = True
        details.append(f"✅ {liquidity_sweep.get('desc', 'Sweep confirmé')} (+20)")
    else:
        conditions["liquidity_sweep"] = False
        details.append(f"❌ Aucun liquidity sweep (+0)")

    # 4. OB + FVG in trade direction (15 pts)
    primary_bias = mtf.get("primary_bias", "NEUTRAL")
    smc = patterns.get("smc", {})

    def _side(obj, key: str) -> str:
        return obj.get("type", "") if isinstance(obj, dict) else ""

    has_ob_dir  = any(_side(ob, "type") == ("bullish" if primary_bias == "BULLISH" else "bearish")
                      for ob in smc.get("order_blocks", []))
    has_fvg_dir = any(_side(fvg, "type") == ("bullish" if primary_bias == "BULLISH" else "bearish")
                      for fvg in smc.get("fvg", []))

    if has_ob_dir and has_fvg_dir:
        score += 15
        conditions["ob_fvg"] = True
        details.append("✅ OB + FVG confirmés dans la direction (+15)")
    elif has_ob_dir or has_fvg_dir:
        score += 8
        conditions["ob_fvg"] = False
        details.append("⚡ OB ou FVG partiel (+8)")
    else:
        conditions["ob_fvg"] = False
        details.append("❌ Aucun OB/FVG dans la direction (+0)")

    # 5. RSI divergence (15 pts)
    div_ok = rsi_divergence.get("detected", False)
    if div_ok:
        score += 15
        conditions["rsi_divergence"] = True
        details.append(f"✅ {rsi_divergence.get('desc', 'Divergence RSI')} (+15)")
    else:
        conditions["rsi_divergence"] = False
        details.append("❌ Aucune divergence RSI (+0)")

    # RSI not extreme
    rsi = market.get("rsi")
    conditions["rsi_ok"] = rsi is None or (20 < rsi < 80)

    # Score thresholds
    if score >= 90:
        signal_level = "VERY_STRONG"
        position_pct = 1.5
        label = "Signal très fort — 1.5% du capital"
    elif score >= 80:
        signal_level = "STRONG"
        position_pct = 1.0
        label = "Signal fort — 1% du capital"
    elif score >= 70:
        signal_level = "MODERATE"
        position_pct = 0.5
        label = "Signal modéré — 0.5% du capital"
    else:
        signal_level = "WEAK"
        position_pct = 0.0
        label = f"Score insuffisant ({score}/100) — pas de trade"

    return {
        "score":        score,
        "conditions":   conditions,
        "details":      details,
        "signal_level": signal_level,
        "position_pct": position_pct,
        "label":        label,
        "tradeable":    score >= 70,
        "primary_bias": primary_bias,
    }
