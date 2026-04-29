import numpy as np
import pandas as pd
from datetime import datetime


# ─────────────────────────────────────────────────────────────────
# RELIABILITY DATABASES  (fiabilité % selon études statistiques)
# ─────────────────────────────────────────────────────────────────

_C_REL: dict[str, int] = {
    # Single
    "Standard Doji": 50, "Gravestone Doji": 55, "Dragonfly Doji": 58,
    "Long-Legged Doji": 52, "Spinning Top": 48, "High Wave": 50,
    "Doji Star haussier": 58, "Doji Star baissier": 58,
    "Hammer": 60, "Hanging Man": 59, "Inverted Hammer": 57, "Shooting Star": 59,
    "Marubozu haussier": 72, "Marubozu baissier": 72,
    "Belt Hold haussier": 62, "Belt Hold baissier": 62,
    # Two
    "Engulfing haussier": 63, "Engulfing baissier": 63,
    "Harami haussier": 53, "Harami baissier": 53,
    "Harami Cross haussier": 56, "Harami Cross baissier": 56,
    "Piercing Line": 64, "Dark Cloud Cover": 66,
    "Tweezer Top": 55, "Tweezer Bottom": 55,
    "Matching Low": 60, "Matching High": 60,
    "Counterattack Lines haussier": 65, "Counterattack Lines baissier": 65,
    "Homing Pigeon": 60,
    "On-Neck Pattern": 55, "In-Neck Pattern": 55, "Thrusting Pattern": 57,
    "Separating Lines haussier": 60, "Separating Lines baissier": 60,
    "Kicking haussier": 72, "Kicking baissier": 72,
    "Rising Window": 65, "Falling Window": 65,
    "Upside Tasuki Gap": 57, "Downside Tasuki Gap": 57,
    # Three
    "Morning Star": 72, "Evening Star": 72,
    "Morning Doji Star": 76, "Evening Doji Star": 76,
    "Abandoned Baby haussier": 70, "Abandoned Baby baissier": 70,
    "Three White Soldiers": 83, "Three Black Crows": 78,
    "Identical Three Crows": 80,
    "Three Inside Up": 65, "Three Inside Down": 65,
    "Three Outside Up": 68, "Three Outside Down": 68,
    "Two Crows": 65,
    "Three Stars in the South": 65,
    "Tri-Star haussier": 67, "Tri-Star baissier": 67,
    "Upside Gap Three Methods": 60, "Downside Gap Three Methods": 60,
    # Four / Five
    "Rising Three Methods": 70, "Falling Three Methods": 70,
    "Ladder Bottom": 65, "Concealing Baby Swallow": 63,
    "Mat Hold": 72,
    "Breakaway haussier": 63, "Breakaway baissier": 63,
    "Unique Three River Bottom": 65,
    "Stick Sandwich": 62,
    "Deliberation baissier": 60,
}

_CHART_REL: dict[str, int] = {
    "Double Top": 75, "Double Bottom": 78,
    "Triple Top": 80, "Triple Bottom": 82,
    "Head & Shoulders": 83, "Inv. Head & Shoulders": 81,
    "Triangle ascendant": 72, "Triangle descendant": 72, "Triangle symétrique": 65,
    "Formation élargie": 58,
    "Wedge ascendant": 68, "Wedge descendant": 70,
    "Rectangle haussier": 60, "Rectangle baissier": 60, "Rectangle": 58,
    "Flag haussier": 67, "Flag baissier": 67,
    "Pennant haussier": 65, "Pennant baissier": 65,
    "Cup & Handle": 65, "Rounding Bottom (Saucer)": 70,
    "Diamond Top": 68, "Diamond Bottom": 68,
    "Three Drives haussier": 65, "Three Drives baissier": 65,
    "Measured Move haussier": 60, "Measured Move baissier": 60,
}

_HARMONIC_REL: dict[str, int] = {
    "Gartley": 70, "Bat": 75, "Butterfly": 68, "Crab": 72, "Cypher": 70, "Shark": 65,
}

_VSA_REL: dict[str, int] = {
    "Selling Climax": 72, "Buying Climax": 72,
    "Stopping Volume": 68, "No Demand": 65, "No Supply": 65,
    "Up Thrust": 70, "Test du support": 68,
    "End of Rising Market": 67, "End of Falling Market": 67,
}


def _rel(name: str, db: dict, default: int = 55) -> int:
    if name in db:
        return db[name]
    for k, v in db.items():
        if k.lower() in name.lower():
            return v
    return default


def _cp(name: str, ptype: str, desc: str) -> dict:
    return {"name": name, "type": ptype, "reliability": _rel(name, _C_REL), "desc": desc}


def _chart_p(name: str, ptype: str, desc: str,
             target: float | None = None, key_level: float | None = None) -> dict:
    d: dict = {"name": name, "type": ptype, "reliability": _rel(name, _CHART_REL), "desc": desc}
    if target is not None:
        d["target"] = target
    if key_level is not None:
        d["key_level"] = key_level
    return d


# ─────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────

def detect_all_patterns(ohlc: list[dict]) -> dict:
    if not ohlc or len(ohlc) < 10:
        return {"candlestick": {"bullish": [], "bearish": []}, "chart": [],
                "smc": {}, "ict": {}, "harmonic": [], "elliott": {}, "vsa": []}

    df = pd.DataFrame(ohlc).sort_values("datetime").reset_index(drop=True)
    for col in ["open", "high", "low", "close"]:
        df[col] = df[col].astype(float)
    if "volume" in df.columns:
        df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0)

    return {
        "candlestick": detect_candlestick(df),
        "chart":       detect_chart_patterns(df),
        "smc":         detect_smc(df),
        "ict":         detect_ict(df),
        "harmonic":    detect_harmonics(df),
        "elliott":     detect_elliott_wave(df),
        "vsa":         detect_vsa(df),
    }


# ─────────────────────────────────────────────────────────────────
# CANDLESTICK PATTERNS  (65+ patterns)
# ─────────────────────────────────────────────────────────────────

def detect_candlestick(df: pd.DataFrame) -> dict:
    bullish: list[dict] = []
    bearish: list[dict] = []

    if len(df) < 5:
        return {"bullish": bullish, "bearish": bearish}

    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    n = len(c) - 1

    def body(i):       return abs(c[i] - o[i])
    def upper_wick(i): return h[i] - max(c[i], o[i])
    def lower_wick(i): return min(c[i], o[i]) - l[i]
    def rng(i):        return max(h[i] - l[i], 1e-8)
    def bull(i):       return c[i] > o[i]
    def bear(i):       return c[i] < o[i]
    def close_pos(i):  return (c[i] - l[i]) / rng(i)   # 0=low, 1=high
    def avg_body(w=14): return max(np.mean([body(i) for i in range(max(0, n-w), n)]), 1e-8)

    ab = avg_body()

    def bp(name: str, desc: str): bullish.append(_cp(name, "bullish", desc))
    def ep(name: str, desc: str): bearish.append(_cp(name, "bearish", desc))

    # ── SINGLE CANDLE ─────────────────────────────────────────────

    body_ratio = body(n) / rng(n) if rng(n) > 0 else 0
    uw, lw = upper_wick(n), lower_wick(n)

    # Doji group
    if body_ratio <= 0.08:
        if uw > lw * 2.5 and lw < body(n):
            ep("Gravestone Doji", "Tentative haussière repoussée — bearish en uptrend")
        elif lw > uw * 2.5 and uw < body(n):
            bp("Dragonfly Doji", "Pression vendeuse absorbée — bullish en downtrend")
        elif uw > ab * 0.7 and lw > ab * 0.7:
            bp("Long-Legged Doji", "Forte indécision, extrême volatilité — attendre confirmation")
        else:
            if n >= 1 and bear(n - 1):
                bp("Standard Doji", "Indécision après mouvement baissier — potentiel retournement")
            elif n >= 1 and bull(n - 1):
                ep("Standard Doji", "Indécision après mouvement haussier — potentiel retournement")

    # Spinning Top
    if 0.08 < body_ratio < 0.35 and uw > body(n) * 0.8 and lw > body(n) * 0.8:
        if n >= 1 and bear(n - 1):
            bp("Spinning Top", "Indécision avec corps réduit — affaiblissement de la baisse")
        elif n >= 1 and bull(n - 1):
            ep("Spinning Top", "Indécision avec corps réduit — affaiblissement de la hausse")

    # High Wave
    if uw > ab * 1.5 and lw > ab * 1.5 and body_ratio < 0.2:
        bp("High Wave", "Extrême volatilité sans direction — retournement possible")

    # Hammer / Hanging Man
    if body(n) > 0 and lw >= body(n) * 2.0 and uw <= body(n) * 0.4:
        if n >= 3 and c[n - 3] > c[n]:
            bp("Hammer", "Rejet des plus bas, demande émergente — bullish après downtrend")
        else:
            ep("Hanging Man", "Tentative baissière en uptrend — menace sur le stop haussier")

    # Inverted Hammer / Shooting Star
    if body(n) > 0 and uw >= body(n) * 2.0 and lw <= body(n) * 0.4:
        if n >= 1 and bear(n - 1):
            bp("Inverted Hammer", "Tentative haussière en downtrend — confirmation nécessaire")
        elif n >= 1 and bull(n - 1):
            ep("Shooting Star", "Rejet des plus hauts, offre dominante — bearish après uptrend")

    # Marubozu
    if rng(n) > 0 and body_ratio >= 0.92:
        if bull(n):
            bp("Marubozu haussier", "Corps plein sans mèche — force totale, continuation probable")
        else:
            ep("Marubozu baissier", "Corps plein sans mèche — faiblesse totale, continuation probable")

    # Belt Hold
    if n >= 1:
        if bull(n) and lw < body(n) * 0.02 and body(n) > ab:
            bp("Belt Hold haussier", "Ouverture sur les plus bas, récupération totale — bullish")
        elif bear(n) and uw < body(n) * 0.02 and body(n) > ab:
            ep("Belt Hold baissier", "Ouverture sur les plus hauts, chute totale — bearish")

    # Doji Star (gap from previous)
    if n >= 1 and body_ratio <= 0.08:
        if bear(n - 1) and l[n] > h[n - 1]:
            bp("Doji Star haussier", "Doji avec gap haussier — fort signal de retournement")
        elif bull(n - 1) and h[n] < l[n - 1]:
            ep("Doji Star baissier", "Doji avec gap baissier — fort signal de retournement")

    # ── TWO CANDLE ────────────────────────────────────────────────

    if n >= 1:
        # Engulfing
        if bear(n - 1) and bull(n) and o[n] <= c[n - 1] and c[n] >= o[n - 1] and body(n) > body(n - 1):
            bp("Engulfing haussier", "La bougie haussière avale entièrement la précédente — inversion forte")
        if bull(n - 1) and bear(n) and o[n] >= c[n - 1] and c[n] <= o[n - 1] and body(n) > body(n - 1):
            ep("Engulfing baissier", "La bougie baissière avale entièrement la précédente — inversion forte")

        # Harami
        if bear(n - 1) and bull(n) and c[n] < o[n - 1] and o[n] > c[n - 1] and body(n) < body(n - 1) * 0.5:
            bp("Harami haussier", "Bébé dans le ventre baissier — ralentissement de la baisse")
        if bull(n - 1) and bear(n) and c[n] > o[n - 1] and o[n] < c[n - 1] and body(n) < body(n - 1) * 0.5:
            ep("Harami baissier", "Bébé dans le ventre haussier — ralentissement de la hausse")

        # Harami Cross
        doji_n = body(n) <= rng(n) * 0.08
        if doji_n:
            if bear(n - 1) and c[n] < o[n - 1] and o[n] > c[n - 1]:
                bp("Harami Cross haussier", "Doji harami — version plus forte du harami haussier")
            if bull(n - 1) and c[n] > o[n - 1] and o[n] < c[n - 1]:
                ep("Harami Cross baissier", "Doji harami — version plus forte du harami baissier")

        # Piercing Line
        if (bear(n - 1) and bull(n) and o[n] < l[n - 1] and
                c[n] > (o[n - 1] + c[n - 1]) / 2 and c[n] < o[n - 1]):
            bp("Piercing Line", "Perce la moitié de la bougie baissière — rebond potentiel")

        # Dark Cloud Cover
        if (bull(n - 1) and bear(n) and o[n] > h[n - 1] and
                c[n] < (o[n - 1] + c[n - 1]) / 2 and c[n] > o[n - 1]):
            ep("Dark Cloud Cover", "Couvre la moitié de la bougie haussière — retournement baissier")

        # Tweezer
        if bull(n - 1) and bear(n) and abs(h[n] - h[n - 1]) / max(h[n], 1) < 0.002:
            ep("Tweezer Top", "Double plus haut identique = résistance forte, retournement")
        if bear(n - 1) and bull(n) and abs(l[n] - l[n - 1]) / max(abs(l[n]), 1) < 0.002:
            bp("Tweezer Bottom", "Double plus bas identique = support fort, retournement")

        # Matching Low / High
        if bear(n - 1) and bear(n) and abs(c[n] - c[n - 1]) / max(abs(c[n]), 1) < 0.002:
            bp("Matching Low", "Deux clôtures baissières au même niveau = plancher potentiel")
        if bull(n - 1) and bull(n) and abs(c[n] - c[n - 1]) / max(abs(c[n]), 1) < 0.002:
            ep("Matching High", "Deux clôtures haussières au même niveau = plafond potentiel")

        # Counterattack Lines
        if (bear(n - 1) and bull(n) and body(n) > ab and body(n - 1) > ab and
                abs(c[n] - c[n - 1]) / max(abs(c[n - 1]), 1) < 0.003):
            bp("Counterattack Lines haussier", "Même clôture après bougie bearish — retournement haussier")
        if (bull(n - 1) and bear(n) and body(n) > ab and body(n - 1) > ab and
                abs(c[n] - c[n - 1]) / max(abs(c[n - 1]), 1) < 0.003):
            ep("Counterattack Lines baissier", "Même clôture après bougie bullish — retournement baissier")

        # Homing Pigeon
        if (bear(n - 1) and bear(n) and o[n] < o[n - 1] and c[n] > c[n - 1] and
                body(n) < body(n - 1) * 0.6):
            bp("Homing Pigeon", "Petite bougie bearish dans la grande — ralentissement de la baisse")

        # On-Neck Pattern (bearish continuation)
        if (bear(n - 1) and bull(n) and body(n - 1) > ab and
                o[n] < l[n - 1] and abs(c[n] - l[n - 1]) / max(rng(n - 1), 1) < 0.01):
            ep("On-Neck Pattern", "Clôture au niveau du bas précédent — continuation baissière")

        # In-Neck Pattern (bearish continuation)
        if (bear(n - 1) and bull(n) and body(n - 1) > ab and
                o[n] < l[n - 1] and c[n] > l[n - 1] and
                c[n] < c[n - 1] + body(n - 1) * 0.2):
            ep("In-Neck Pattern", "Légère pénétration du corps précédent — continuation baissière")

        # Thrusting Pattern (bearish continuation / weak bullish reversal)
        if (bear(n - 1) and bull(n) and body(n - 1) > ab and
                o[n] < l[n - 1] and c[n] > l[n - 1] and
                c[n] < (o[n - 1] + c[n - 1]) / 2):
            ep("Thrusting Pattern", "Pénètre ~25% du corps précédent — rebond faible, baisse probable")

        # Separating Lines
        if (bull(n - 1) and bull(n) and body(n - 1) > ab and body(n) > ab and
                abs(o[n] - o[n - 1]) / max(o[n - 1], 1) < 0.002):
            bp("Separating Lines haussier", "Même ouverture, corps haussier — continuation haussière forte")
        if (bear(n - 1) and bear(n) and body(n - 1) > ab and body(n) > ab and
                abs(o[n] - o[n - 1]) / max(o[n - 1], 1) < 0.002):
            ep("Separating Lines baissier", "Même ouverture, corps baissier — continuation baissière forte")

        # Kicking (marubozu + gap)
        marubozu_n = body_ratio >= 0.90
        marubozu_n1 = body(n - 1) / max(rng(n - 1), 1e-8) >= 0.90
        if marubozu_n1 and marubozu_n:
            if bear(n - 1) and bull(n) and o[n] > h[n - 1]:
                bp("Kicking haussier", "Gap entre deux marubozu : bear→bull = signal de retournement très fort")
            elif bull(n - 1) and bear(n) and o[n] < l[n - 1]:
                ep("Kicking baissier", "Gap entre deux marubozu : bull→bear = signal de retournement très fort")

        # Rising Window / Falling Window (gaps)
        if l[n] > h[n - 1]:
            bp("Rising Window", f"Gap haussier ${h[n-1]:.2f}→${l[n]:.2f} = support, continuation probable")
        elif h[n] < l[n - 1]:
            ep("Falling Window", f"Gap baissier ${l[n-1]:.2f}→${h[n]:.2f} = résistance, continuation probable")

    # ── THREE CANDLE ──────────────────────────────────────────────

    if n >= 2:
        # Morning Star
        if (bear(n - 2) and body(n - 2) > ab and body(n - 1) <= ab * 0.4 and
                bull(n) and body(n) > ab and c[n] > (o[n - 2] + c[n - 2]) / 2):
            bp("Morning Star", "Étoile du matin — retournement haussier classique en bas de range")

        # Evening Star
        if (bull(n - 2) and body(n - 2) > ab and body(n - 1) <= ab * 0.4 and
                bear(n) and body(n) > ab and c[n] < (o[n - 2] + c[n - 2]) / 2):
            ep("Evening Star", "Étoile du soir — retournement baissier classique en haut de range")

        # Morning Doji Star
        if (bear(n - 2) and body(n - 1) / max(rng(n - 1), 1e-8) <= 0.1 and
                bull(n) and c[n] > (o[n - 2] + c[n - 2]) / 2):
            bp("Morning Doji Star", "Doji étoile du matin — version plus forte, très fiable")

        # Evening Doji Star
        if (bull(n - 2) and body(n - 1) / max(rng(n - 1), 1e-8) <= 0.1 and
                bear(n) and c[n] < (o[n - 2] + c[n - 2]) / 2):
            ep("Evening Doji Star", "Doji étoile du soir — version plus forte, très fiable")

        # Abandoned Baby
        if (bear(n - 2) and body(n - 2) > ab and
                body(n - 1) / max(rng(n - 1), 1e-8) <= 0.1 and
                h[n - 1] < l[n - 2] and bull(n) and l[n] > h[n - 1]):
            bp("Abandoned Baby haussier", "Doji avec gaps des deux côtés — retournement haussier rare et fort")
        if (bull(n - 2) and body(n - 2) > ab and
                body(n - 1) / max(rng(n - 1), 1e-8) <= 0.1 and
                l[n - 1] > h[n - 2] and bear(n) and h[n] < l[n - 1]):
            ep("Abandoned Baby baissier", "Doji avec gaps des deux côtés — retournement baissier rare et fort")

        # Three White Soldiers
        if (bull(n - 2) and bull(n - 1) and bull(n) and
                c[n] > c[n - 1] > c[n - 2] and o[n] > o[n - 1] > o[n - 2] and
                body(n) > ab * 0.7 and body(n - 1) > ab * 0.7):
            bp("Three White Soldiers", "Trois bougies haussières progressives — tendance haussière bien établie")

        # Three Black Crows
        if (bear(n - 2) and bear(n - 1) and bear(n) and
                c[n] < c[n - 1] < c[n - 2] and o[n] < o[n - 1] < o[n - 2] and
                body(n) > ab * 0.7 and body(n - 1) > ab * 0.7):
            ep("Three Black Crows", "Trois bougies baissières progressives — tendance baissière bien établie")

        # Identical Three Crows (opens inside previous body)
        if (bear(n - 2) and bear(n - 1) and bear(n) and
                c[n] < c[n - 1] < c[n - 2] and
                c[n - 1] <= o[n] <= o[n - 2] and c[n - 2] <= o[n - 1] <= o[n - 3 if n >= 3 else 0] and
                body(n) > ab * 0.7 and body(n - 1) > ab * 0.7):
            ep("Identical Three Crows", "Trois corbeaux identiques — signal baissier très fort et rare")

        # Two Crows (bearish reversal: bull, gap-up bear, engulfing bear)
        if n >= 2:
            if (bull(n - 2) and body(n - 2) > ab and
                    bear(n - 1) and o[n - 1] > c[n - 2] and
                    bear(n) and o[n] >= o[n - 1] and c[n] > c[n - 2] and c[n] < c[n - 1]):
                ep("Two Crows", "Deux corbeaux — dégradation progressive de la tendance haussière")

        # Three Inside Up
        if (bear(n - 2) and
                bull(n - 1) and body(n - 1) < body(n - 2) and
                c[n - 1] < o[n - 2] and o[n - 1] > c[n - 2] and
                bull(n) and c[n] > o[n - 2]):
            bp("Three Inside Up", "Harami + confirmation haussière — retournement validé")

        # Three Inside Down
        if (bull(n - 2) and
                bear(n - 1) and body(n - 1) < body(n - 2) and
                c[n - 1] > o[n - 2] and o[n - 1] < c[n - 2] and
                bear(n) and c[n] < o[n - 2]):
            ep("Three Inside Down", "Harami + confirmation baissière — retournement validé")

        # Three Outside Up
        if (bear(n - 2) and
                bull(n - 1) and o[n - 1] <= c[n - 2] and c[n - 1] >= o[n - 2] and
                body(n - 1) > body(n - 2) and
                bull(n) and c[n] > c[n - 1]):
            bp("Three Outside Up", "Engulfing + confirmation — retournement haussier fort")

        # Three Outside Down
        if (bull(n - 2) and
                bear(n - 1) and o[n - 1] >= c[n - 2] and c[n - 1] <= o[n - 2] and
                body(n - 1) > body(n - 2) and
                bear(n) and c[n] < c[n - 1]):
            ep("Three Outside Down", "Engulfing + confirmation — retournement baissier fort")

        # Three Stars in the South (3 doji-like small candles)
        doji2 = body(n - 2) / max(rng(n - 2), 1e-8) <= 0.15
        doji1 = body(n - 1) / max(rng(n - 1), 1e-8) <= 0.15
        doji0 = body_ratio <= 0.15
        if doji2 and doji1 and doji0 and bear(n - 2) and bear(n - 1) and bear(n):
            if rng(n) < rng(n - 1) < rng(n - 2):
                bp("Three Stars in the South", "Ralentissement progressif de la baisse — retournement probable")

        # Tri-Star
        if doji2 and doji1 and doji0:
            if c[n - 2] > c[n - 1] and c[n] > c[n - 1]:
                bp("Tri-Star haussier", "Trois doji en V — retournement rare et très fiable")
            elif c[n - 2] < c[n - 1] and c[n] < c[n - 1]:
                ep("Tri-Star baissier", "Trois doji en Λ — retournement rare et très fiable")

        # Upside Gap Three Methods (bull cont.)
        if (bull(n - 2) and body(n - 2) > ab and
                l[n - 1] > h[n - 2] and  # gap up
                bear(n - 1) and
                bull(n) and o[n] > c[n - 1] and c[n] > c[n - 2]):
            bp("Upside Gap Three Methods", "Gap haussier + retour partiel + confirmation — continuation bullish")

        # Downside Gap Three Methods (bear cont.)
        if (bear(n - 2) and body(n - 2) > ab and
                h[n - 1] < l[n - 2] and  # gap down
                bull(n - 1) and
                bear(n) and o[n] < c[n - 1] and c[n] < c[n - 2]):
            ep("Downside Gap Three Methods", "Gap baissier + retour partiel + confirmation — continuation bearish")

        # Upside Tasuki Gap (bull continuation)
        if n >= 2:
            if (bull(n - 2) and bull(n - 1) and
                    l[n - 1] > h[n - 2] and  # gap between -2 and -1
                    bear(n) and o[n] > l[n - 1] and c[n] > h[n - 2] and c[n] < l[n - 1]):
                bp("Upside Tasuki Gap", "Gap haussier partiellement comblé par une bougie bearish — continuation haussière")

            # Downside Tasuki Gap (bear continuation)
            if (bear(n - 2) and bear(n - 1) and
                    h[n - 1] < l[n - 2] and  # gap between -2 and -1
                    bull(n) and o[n] < h[n - 1] and c[n] < l[n - 2] and c[n] > h[n - 1]):
                ep("Downside Tasuki Gap", "Gap baissier partiellement comblé par une bougie bullish — continuation baissière")

    # ── FOUR / FIVE CANDLE ────────────────────────────────────────

    if n >= 4:
        # Rising Three Methods (5-candle bull continuation)
        if (bull(n - 4) and body(n - 4) > ab and
                bear(n - 3) and bear(n - 2) and bear(n - 1) and
                c[n - 3] > c[n - 4] * 0.97 and c[n - 1] > l[n - 4] and
                bull(n) and c[n] > c[n - 4]):
            bp("Rising Three Methods", "Pause baissière sur 3 bougies dans uptrend — continuation haussière forte")

        # Falling Three Methods (5-candle bear continuation)
        if (bear(n - 4) and body(n - 4) > ab and
                bull(n - 3) and bull(n - 2) and bull(n - 1) and
                c[n - 3] < c[n - 4] * 1.03 and c[n - 1] < h[n - 4] and
                bear(n) and c[n] < c[n - 4]):
            ep("Falling Three Methods", "Pause haussière sur 3 bougies dans downtrend — continuation baissière forte")

        # Mat Hold (5-candle bullish continuation)
        if (bull(n - 4) and body(n - 4) > ab * 1.2 and
                bear(n - 3) and bear(n - 2) and bear(n - 1) and
                l[n - 3] > l[n - 4] and c[n - 1] > l[n - 4] and
                bull(n) and c[n] > h[n - 4]):
            bp("Mat Hold", "5 bougies — continuation haussière après pause (variante Rising Three Methods)")

        # Ladder Bottom (5-candle bullish reversal)
        if (bear(n - 4) and bear(n - 3) and bear(n - 2) and
                c[n - 4] > c[n - 3] > c[n - 2] and
                bull(n - 1) and upper_wick(n - 1) > body(n - 1) and
                bull(n) and c[n] > o[n - 4]):
            bp("Ladder Bottom", "Escalier baissier puis inversion — fin de downtrend confirmée")

        # Concealing Baby Swallow (4-candle bullish reversal)
        if n >= 3:
            if (bear(n - 3) and bear(n - 2) and
                    upper_wick(n - 3) < body(n - 3) * 0.05 and
                    upper_wick(n - 2) < body(n - 2) * 0.05 and
                    bear(n - 1) and h[n - 1] > h[n - 2] and
                    bear(n) and o[n] > h[n - 1] and h[n] > h[n - 1] and c[n] < l[n - 1]):
                bp("Concealing Baby Swallow", "4 bougies bearish + englobement — forte inversion haussière")

        # Breakaway (5-candle reversal)
        if n >= 4:
            # Bullish breakaway
            if (bear(n - 4) and body(n - 4) > ab and
                    bear(n - 3) and l[n - 3] < l[n - 4] and
                    bear(n - 2) and bear(n - 1) and
                    bull(n) and c[n] > c[n - 3] and o[n] < c[n - 1]):
                bp("Breakaway haussier", "5 bougies — gap haussier qui comble 4 bougies bearish")
            # Bearish breakaway
            if (bull(n - 4) and body(n - 4) > ab and
                    bull(n - 3) and h[n - 3] > h[n - 4] and
                    bull(n - 2) and bull(n - 1) and
                    bear(n) and c[n] < c[n - 3] and o[n] > c[n - 1]):
                ep("Breakaway baissier", "5 bougies — gap baissier qui comble 4 bougies bullish")

        # Stick Sandwich (3 candles: bear, bull, bear at same close)
        if n >= 2:
            if (bear(n - 2) and bull(n - 1) and bear(n) and
                    abs(c[n] - c[n - 2]) / max(abs(c[n - 2]), 1) < 0.003 and
                    o[n - 1] < c[n - 2] and c[n - 1] > o[n - 2]):
                bp("Stick Sandwich", "Deux bougies bearish encadrent une haussière — support potentiel")

        # Unique Three River Bottom
        if n >= 2:
            if (bear(n - 2) and body(n - 2) > ab and
                    bear(n - 1) and lower_wick(n - 1) > body(n - 1) * 2 and l[n - 1] < l[n - 2] and
                    bull(n) and body(n) < ab * 0.5 and c[n] < c[n - 2]):
                bp("Unique Three River Bottom", "Fond à trois rivières — retournement haussier rare")

        # Deliberation (bearish reversal after 3 bulls)
        if n >= 2:
            if (bull(n - 2) and bull(n - 1) and bull(n) and
                    body(n - 2) > ab and body(n - 1) > ab and body(n) < ab * 0.5 and
                    c[n] > c[n - 1] > c[n - 2] and
                    upper_wick(n) > body(n)):
                ep("Deliberation baissier", "Hésitation après 3 hausses — ralentissement, vente possible")

    return {"bullish": bullish, "bearish": bearish}


# ─────────────────────────────────────────────────────────────────
# CHART PATTERNS
# ─────────────────────────────────────────────────────────────────

def detect_chart_patterns(df: pd.DataFrame) -> list[dict]:
    patterns: list[dict] = []
    if len(df) < 30:
        return patterns

    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    n = len(c)
    w = min(80, n)
    rh, rl, rc = h[-w:], l[-w:], c[-w:]

    peaks   = _peaks(rh, order=4)
    troughs = _troughs(rl, order=4)

    # ── Double Top ────────────────────────────────────────────────
    if len(peaks) >= 2:
        p1, p2 = peaks[-2], peaks[-1]
        if abs(rh[p1] - rh[p2]) / rh[p1] < 0.007 and p2 - p1 >= 5:
            neckline = min(rl[p1:p2 + 1])
            target   = neckline - (rh[p1] - neckline)
            patterns.append(_chart_p("Double Top", "bearish",
                f"Double sommet — neckline ${neckline:.2f}, objectif ${target:.2f}",
                target=round(target, 2), key_level=round(neckline, 2)))

    # ── Double Bottom ─────────────────────────────────────────────
    if len(troughs) >= 2:
        t1, t2 = troughs[-2], troughs[-1]
        if abs(rl[t1] - rl[t2]) / max(abs(rl[t1]), 1) < 0.007 and t2 - t1 >= 5:
            neckline = max(rh[t1:t2 + 1])
            target   = neckline + (neckline - rl[t1])
            patterns.append(_chart_p("Double Bottom", "bullish",
                f"Double fond — neckline ${neckline:.2f}, objectif ${target:.2f}",
                target=round(target, 2), key_level=round(neckline, 2)))

    # ── Triple Top ────────────────────────────────────────────────
    if len(peaks) >= 3:
        p1, p2, p3 = peaks[-3], peaks[-2], peaks[-1]
        if (abs(rh[p1] - rh[p2]) / rh[p1] < 0.008 and
                abs(rh[p2] - rh[p3]) / rh[p2] < 0.008 and
                p2 - p1 >= 5 and p3 - p2 >= 5):
            neckline = min(rl[p1:p3 + 1])
            target   = neckline - (rh[p2] - neckline)
            patterns.append(_chart_p("Triple Top", "bearish",
                f"Triple sommet — neckline ${neckline:.2f}, objectif ${target:.2f}",
                target=round(target, 2), key_level=round(neckline, 2)))

    # ── Triple Bottom ─────────────────────────────────────────────
    if len(troughs) >= 3:
        t1, t2, t3 = troughs[-3], troughs[-2], troughs[-1]
        if (abs(rl[t1] - rl[t2]) / max(abs(rl[t1]), 1) < 0.008 and
                abs(rl[t2] - rl[t3]) / max(abs(rl[t2]), 1) < 0.008 and
                t2 - t1 >= 5 and t3 - t2 >= 5):
            neckline = max(rh[t1:t3 + 1])
            target   = neckline + (neckline - rl[t2])
            patterns.append(_chart_p("Triple Bottom", "bullish",
                f"Triple fond — neckline ${neckline:.2f}, objectif ${target:.2f}",
                target=round(target, 2), key_level=round(neckline, 2)))

    # ── Head & Shoulders ──────────────────────────────────────────
    if len(peaks) >= 3:
        p1, p2, p3 = peaks[-3], peaks[-2], peaks[-1]
        if (rh[p2] > rh[p1] and rh[p2] > rh[p3] and
                abs(rh[p1] - rh[p3]) / rh[p1] < 0.018):
            neckline = (min(rl[p1:p2 + 1]) + min(rl[p2:p3 + 1])) / 2
            target   = neckline - (rh[p2] - neckline)
            patterns.append(_chart_p("Head & Shoulders", "bearish",
                f"H&S — neckline ${neckline:.2f}, objectif ${target:.2f}",
                target=round(target, 2), key_level=round(neckline, 2)))

    # ── Inverse Head & Shoulders ──────────────────────────────────
    if len(troughs) >= 3:
        t1, t2, t3 = troughs[-3], troughs[-2], troughs[-1]
        if (rl[t2] < rl[t1] and rl[t2] < rl[t3] and
                abs(rl[t1] - rl[t3]) / max(abs(rl[t1]), 1) < 0.018):
            neckline = (max(rh[t1:t2 + 1]) + max(rh[t2:t3 + 1])) / 2
            target   = neckline + (neckline - rl[t2])
            patterns.append(_chart_p("Inv. Head & Shoulders", "bullish",
                f"Inv. H&S — neckline ${neckline:.2f}, objectif ${target:.2f}",
                target=round(target, 2), key_level=round(neckline, 2)))

    # ── Triangles ─────────────────────────────────────────────────
    if len(peaks) >= 2 and len(troughs) >= 2:
        p1, p2 = peaks[-2], peaks[-1]
        t1, t2 = troughs[-2], troughs[-1]
        high_diff = rh[p2] - rh[p1]
        low_diff  = rl[t2] - rl[t1]
        if abs(high_diff) < rh[p1] * 0.004 and low_diff > 0:
            patterns.append(_chart_p("Triangle ascendant", "bullish",
                f"Résistance plate ${rh[p2]:.2f} + plus bas croissants — cassure haussière probable",
                key_level=round(rh[p2], 2)))
        elif abs(low_diff) < abs(rl[t1]) * 0.004 and high_diff < 0:
            patterns.append(_chart_p("Triangle descendant", "bearish",
                f"Support plat ${rl[t2]:.2f} + plus hauts décroissants — cassure baissière probable",
                key_level=round(rl[t2], 2)))
        elif high_diff < 0 and low_diff > 0:
            patterns.append(_chart_p("Triangle symétrique", "neutral",
                "Compression symétrique — cassure dans le sens de la tendance dominante attendue"))
        elif high_diff > 0 and low_diff < 0 and abs(high_diff) > rh[p1] * 0.008:
            patterns.append(_chart_p("Formation élargie", "neutral",
                "Broadening formation — volatilité croissante, indécision du marché"))

    # ── Wedges ────────────────────────────────────────────────────
    if len(peaks) >= 2 and len(troughs) >= 2:
        p1, p2 = peaks[-2], peaks[-1]
        t1, t2 = troughs[-2], troughs[-1]
        hp = p2 - p1 if p2 > p1 else 1
        ht = t2 - t1 if t2 > t1 else 1
        high_slope = (rh[p2] - rh[p1]) / hp
        low_slope  = (rl[t2] - rl[t1]) / ht
        # Rising Wedge: both sloping up but lows rise faster → bearish
        if high_slope > 0 and low_slope > 0 and low_slope > high_slope * 1.15:
            patterns.append(_chart_p("Wedge ascendant", "bearish",
                "Rising Wedge — lignes convergentes en hausse → retournement baissier probable"))
        # Falling Wedge: both sloping down but highs fall faster → bullish
        elif high_slope < 0 and low_slope < 0 and high_slope < low_slope * 1.15:
            patterns.append(_chart_p("Wedge descendant", "bullish",
                "Falling Wedge — lignes convergentes en baisse → retournement haussier probable"))

    # ── Rectangle ─────────────────────────────────────────────────
    if len(peaks) >= 2 and len(troughs) >= 2:
        p1, p2 = peaks[-2], peaks[-1]
        t1, t2 = troughs[-2], troughs[-1]
        high_sim = abs(rh[p1] - rh[p2]) / max(rh[p1], 1) < 0.005
        low_sim  = abs(rl[t1] - rl[t2]) / max(abs(rl[t1]), 1) < 0.005
        if high_sim and low_sim and p2 - p1 >= 6 and t2 - t1 >= 6:
            resistance = (rh[p1] + rh[p2]) / 2
            support    = (rl[t1] + rl[t2]) / 2
            spread_r   = (resistance - support) / max(resistance, 1)
            if spread_r > 0.002:
                price_pos = (rc[-1] - support) / max(resistance - support, 1e-8)
                if price_pos < 0.3:
                    patterns.append(_chart_p("Rectangle haussier", "bullish",
                        f"Range horizontal — prix au support ${support:.2f}, objectif résistance ${resistance:.2f}",
                        key_level=round(resistance, 2)))
                elif price_pos > 0.7:
                    patterns.append(_chart_p("Rectangle baissier", "bearish",
                        f"Range horizontal — prix à la résistance ${resistance:.2f}, objectif support ${support:.2f}",
                        key_level=round(support, 2)))

    # ── Flag / Pennant ────────────────────────────────────────────
    if n >= 25:
        impulse = rc[-25:-10]
        consol  = rc[-10:]
        imp_range = max(impulse) - min(impulse)
        con_range = max(consol) - min(consol)
        imp_move  = impulse[-1] - impulse[0]
        if con_range < imp_range * 0.4 and abs(imp_move) > imp_range * 0.6:
            # Pennant if very narrow consolidation
            name = ("Pennant" if con_range < imp_range * 0.2 else "Flag")
            if imp_move > 0:
                patterns.append(_chart_p(f"{name} haussier", "bullish",
                    "Consolidation post-impulsion haussière — continuation probable"))
            else:
                patterns.append(_chart_p(f"{name} baissier", "bearish",
                    "Consolidation post-impulsion baissière — continuation probable"))

    # ── Cup & Handle ──────────────────────────────────────────────
    if len(rc) >= 40:
        cup    = rc[-40:-5]
        handle = rc[-10:]
        cup_low_idx = int(np.argmin(cup))
        if (cup_low_idx > 5 and cup_low_idx < len(cup) - 5 and
                cup[0] > cup[cup_low_idx] and cup[-1] > cup[cup_low_idx] and
                abs(cup[0] - cup[-1]) / max(cup[0], 1) < 0.035 and
                min(handle) > cup[cup_low_idx] and max(handle) < cup[-1]):
            patterns.append(_chart_p("Cup & Handle", "bullish",
                f"Coupe et anse — signal si cassure ${cup[-1]:.2f}",
                key_level=round(cup[-1], 2)))

    # ── Rounding Bottom ───────────────────────────────────────────
    if len(rc) >= 40:
        seg = rc[-40:]
        mid = len(seg) // 2
        left_avg  = np.mean(seg[:10])
        mid_avg   = np.mean(seg[mid - 5:mid + 5])
        right_avg = np.mean(seg[-10:])
        if mid_avg < left_avg * 0.99 and mid_avg < right_avg * 0.99 and right_avg > left_avg * 0.995:
            patterns.append(_chart_p("Rounding Bottom (Saucer)", "bullish",
                "Fond arrondi — accumulation progressive, signal haussier de retournement"))

    # ── Diamond Top ───────────────────────────────────────────────
    if len(peaks) >= 4 and len(troughs) >= 4:
        early_peaks   = peaks[:-2]
        late_peaks    = peaks[-2:]
        early_troughs = troughs[:-2]
        late_troughs  = troughs[-2:]
        if early_peaks and late_peaks and early_troughs and late_troughs:
            early_range = rh[early_peaks[-1]] - rl[early_troughs[-1]]
            late_range  = rh[late_peaks[-1]]  - rl[late_troughs[-1]]
            if early_range > 0 and late_range < early_range * 0.7:
                patterns.append(_chart_p("Diamond Top", "bearish",
                    "Diamond Top — contraction après expansion. Retournement baissier."))

    # ── Three Drives ──────────────────────────────────────────────
    if len(peaks) >= 3:
        p1, p2, p3 = peaks[-3], peaks[-2], peaks[-1]
        d12 = rh[p2] - rh[p1]
        d23 = rh[p3] - rh[p2]
        if d12 > 0 and d23 > 0 and abs(d23 - d12) / d12 < 0.18:
            patterns.append(_chart_p("Three Drives haussier", "bearish",
                f"Trois poussées égales vers ${rh[p3]:.2f} — épuisement haussier"))
    if len(troughs) >= 3:
        t1, t2, t3 = troughs[-3], troughs[-2], troughs[-1]
        d12 = rl[t1] - rl[t2]
        d23 = rl[t2] - rl[t3]
        if d12 > 0 and d23 > 0 and abs(d23 - d12) / d12 < 0.18:
            patterns.append(_chart_p("Three Drives baissier", "bullish",
                f"Trois poussées baissières égales vers ${rl[t3]:.2f} — épuisement baissier"))

    # ── Measured Move ─────────────────────────────────────────────
    if len(peaks) >= 1 and len(troughs) >= 2:
        if troughs[-2] < peaks[-1] and peaks[-1] < troughs[-1]:
            leg1   = rh[peaks[-1]] - rl[troughs[-2]]
            leg2   = rl[troughs[-1]] - rl[troughs[-2]]
            if leg1 > 0 and abs(leg2 - leg1) / leg1 < 0.2:
                target = rc[-1] + leg1
                patterns.append(_chart_p("Measured Move haussier", "bullish",
                    f"Measured Move — objectif de continuation ${target:.2f}",
                    target=round(target, 2)))

    return patterns


# ─────────────────────────────────────────────────────────────────
# HARMONIC PATTERNS
# ─────────────────────────────────────────────────────────────────

def detect_harmonics(df: pd.DataFrame) -> list[dict]:
    results: list[dict] = []
    if len(df) < 30:
        return results

    h = df["high"].values
    l = df["low"].values

    peaks   = _peaks(h, order=3)
    troughs = _troughs(l, order=3)
    swings  = _alternating_swings(h, l, peaks, troughs)

    if len(swings) < 5:
        return results

    def fib(val, target, tol=0.10):
        return abs(val - target) / max(target, 1e-8) <= tol

    def fib_range(val, lo, hi, tol=0.10):
        return lo * (1 - tol) <= val <= hi * (1 + tol)

    for start in range(max(0, len(swings) - 8), len(swings) - 4):
        seg = swings[start:start + 5]
        X, A, B, C, D = seg

        is_bull = (X[2] == 'low'  and A[2] == 'high' and B[2] == 'low'  and C[2] == 'high' and D[2] == 'low')
        is_bear = (X[2] == 'high' and A[2] == 'low'  and B[2] == 'high' and C[2] == 'low'  and D[2] == 'high')
        if not (is_bull or is_bear):
            continue

        ptype = "bullish" if is_bull else "bearish"
        xa = abs(A[1] - X[1])
        ab = abs(B[1] - A[1])
        bc = abs(C[1] - B[1])
        cd = abs(D[1] - C[1])
        xd = abs(D[1] - X[1])
        xc = abs(C[1] - X[1])

        if xa == 0 or ab == 0 or bc == 0 or cd == 0:
            continue

        ab_xa  = ab / xa
        bc_ab  = bc / ab
        cd_bc  = cd / bc
        xd_xa  = xd / xa

        matched = None

        # Gartley: AB=0.618·XA, BC=0.382–0.886·AB, CD=1.272–1.618·BC, XD=0.786·XA
        if (fib(ab_xa, 0.618) and fib_range(bc_ab, 0.382, 0.886) and
                fib_range(cd_bc, 1.272, 1.618) and fib(xd_xa, 0.786)):
            matched = ("Gartley", 70, "Retracement 78.6% de XA — PRZ haute probabilité")

        # Bat: AB=0.382–0.500·XA, CD=1.618–2.618·BC, XD=0.886·XA
        elif (fib_range(ab_xa, 0.382, 0.500) and fib_range(bc_ab, 0.382, 0.886) and
              fib_range(cd_bc, 1.618, 2.618) and fib(xd_xa, 0.886)):
            matched = ("Bat", 75, "Retracement 88.6% de XA — signal d'entrée très fiable")

        # Butterfly: AB=0.786·XA, CD=1.618–2.618·BC, XD=1.272–1.618·XA
        elif (fib(ab_xa, 0.786) and fib_range(bc_ab, 0.382, 0.886) and
              fib_range(cd_bc, 1.618, 2.618) and fib_range(xd_xa, 1.272, 1.618)):
            matched = ("Butterfly", 68, "Extension 127.2–161.8% de XA — inversion externe")

        # Crab: AB=0.382–0.618·XA, CD=2.618–3.618·BC, XD=1.618·XA
        elif (fib_range(ab_xa, 0.382, 0.618) and fib_range(bc_ab, 0.382, 0.886) and
              fib_range(cd_bc, 2.618, 3.618) and fib(xd_xa, 1.618)):
            matched = ("Crab", 72, "Extension 161.8% de XA — inversion la plus extrême")

        # Cypher: AB=0.382–0.618·XA, XC=1.272–1.414·XA, XD=0.786·XC
        elif (xc > 0 and fib_range(ab_xa, 0.382, 0.618) and
              fib_range(xc / xa, 1.272, 1.414) and fib(xd / xc, 0.786)):
            matched = ("Cypher", 70, "Retracement 78.6% de XC — structure asymétrique fiable")

        # Shark: AB=0.886–1.13·XA, CD/AB=1.618–2.24
        elif fib_range(ab_xa, 0.886, 1.130) and fib_range(cd / ab, 1.618, 2.240):
            matched = ("Shark", 65, "Pattern 5-0 intermédiaire — inversion potentielle")

        if matched:
            name_base, rel, base_desc = matched
            label = f"{name_base} {'haussier' if is_bull else 'baissier'}"
            results.append({
                "name":        label,
                "type":        ptype,
                "reliability": rel,
                "prz":         round(D[1], 2),
                "d_level":     round(D[1], 2),
                "desc":        f"{name_base} {ptype} — PRZ ${D[1]:.2f}. {base_desc}",
                "ratios": {
                    "AB/XA": round(ab_xa, 3),
                    "BC/AB": round(bc_ab, 3),
                    "CD/BC": round(cd_bc, 3),
                    "XD/XA": round(xd_xa, 3),
                },
            })

    return results


# ─────────────────────────────────────────────────────────────────
# ELLIOTT WAVE
# ─────────────────────────────────────────────────────────────────

def detect_elliott_wave(df: pd.DataFrame) -> dict:
    if len(df) < 40:
        return {}

    h = df["high"].values
    l = df["low"].values
    c = df["close"].values

    peaks   = _peaks(h, order=4)
    troughs = _troughs(l, order=4)
    swings  = _alternating_swings(h, l, peaks, troughs)

    if len(swings) < 6:
        return {}

    # 5-wave impulse
    for direction in ("up", "down"):
        expected = (["low", "high", "low", "high", "low", "high"]
                    if direction == "up"
                    else ["high", "low", "high", "low", "high", "low"])
        for start in range(max(0, len(swings) - 10), len(swings) - 5):
            seg = swings[start:start + 6]
            if [s[2] for s in seg] != expected:
                continue
            p = [s[1] for s in seg]

            w1 = abs(p[1] - p[0])
            w2 = abs(p[2] - p[1])
            w3 = abs(p[3] - p[2])
            w4 = abs(p[4] - p[3])
            w5 = abs(p[5] - p[4])

            if direction == "up":
                rule1 = p[2] > p[0]
                rule2 = not (w3 < w1 and w3 < w5)
                rule3 = p[4] > p[1]
            else:
                rule1 = p[2] < p[0]
                rule2 = not (w3 < w1 and w3 < w5)
                rule3 = p[4] < p[1]

            if rule1 and rule2 and rule3:
                # Deduce current wave position
                last_sw = swings[-1]
                complete = last_sw[0] == seg[-1][0]
                if complete:
                    wave_pos = "5 — complète → correction A-B-C probable"
                    bias = "bearish" if direction == "up" else "bullish"
                else:
                    remaining = len(seg) - 1 - seg.index(last_sw) if last_sw in seg else "?"
                    wave_pos = f"en cours"
                    bias = "bullish" if direction == "up" else "bearish"

                # Extension analysis
                w3_strongest = w3 >= w1 and w3 >= w5
                extension    = "étendue" if w3 > w1 * 1.618 else "normale"

                return {
                    "type":       "impulse",
                    "direction":  "bullish" if direction == "up" else "bearish",
                    "bias":       bias,
                    "reliability": 65,
                    "wave_count": "1-2-3-4-5",
                    "current_wave": wave_pos,
                    "wave_prices": [round(p_, 2) for p_ in p],
                    "w3_extension": extension,
                    "desc": (
                        f"Vagues 1-2-3-4-5 {'haussières' if direction=='up' else 'baissières'} — "
                        f"vague 3 {extension} ({'la plus forte' if w3_strongest else 'attention: règle vague 3'}), "
                        f"position: {wave_pos}"
                    ),
                }

    # ABC correction
    if len(swings) >= 3:
        for start in range(max(0, len(swings) - 5), len(swings) - 2):
            seg = swings[start:start + 3]
            A, B, C_ = seg
            a_leg = abs(B[1] - A[1])
            b_leg = abs(C_[1] - B[1])
            if a_leg == 0:
                continue
            b_ratio = b_leg / a_leg

            if A[2] == 'high' and B[2] == 'low' and C_[2] == 'high' and b_ratio < 1.0:
                c_target = B[1] - a_leg
                c_ext    = "normal" if b_ratio > 0.5 else "profond"
                return {
                    "type":        "correction",
                    "direction":   "bearish",
                    "bias":        "bearish",
                    "reliability": 60,
                    "wave_count":  "A-B-C",
                    "current_wave": f"C — cible ${c_target:.2f}",
                    "desc": f"Correction A-B-C baissière ({c_ext}), B={b_ratio:.1%} de A — cible vague C ${c_target:.2f}",
                }
            elif A[2] == 'low' and B[2] == 'high' and C_[2] == 'low' and b_ratio < 1.0:
                c_target = B[1] + a_leg
                c_ext    = "normal" if b_ratio > 0.5 else "profond"
                return {
                    "type":        "correction",
                    "direction":   "bullish",
                    "bias":        "bullish",
                    "reliability": 60,
                    "wave_count":  "A-B-C",
                    "current_wave": f"C — cible ${c_target:.2f}",
                    "desc": f"Correction A-B-C haussière ({c_ext}), B={b_ratio:.1%} de A — cible vague C ${c_target:.2f}",
                }

    return {}


# ─────────────────────────────────────────────────────────────────
# VSA — Volume Spread Analysis
# ─────────────────────────────────────────────────────────────────

def detect_vsa(df: pd.DataFrame) -> list[dict]:
    results: list[dict] = []
    if "volume" not in df.columns or len(df) < 15:
        return results

    vol = df["volume"].values.astype(float)
    if vol.max() <= 0:
        return results

    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    n = len(c) - 1

    lookback    = min(20, n)
    avg_vol     = np.mean(vol[max(0, n - lookback):n]) or 1.0
    avg_spread  = np.mean(h[max(0, n - lookback):n] - l[max(0, n - lookback):n]) or 1e-8

    def spread(i):     return h[i] - l[i]
    def close_pos(i):  return (c[i] - l[i]) / max(spread(i), 1e-8)
    def bull(i):       return c[i] > o[i]
    def bear(i):       return c[i] < o[i]

    sv    = vol[n]
    sp    = spread(n)
    cp    = close_pos(n)
    v_hi  = sv > avg_vol * 2.0
    v_mid = sv > avg_vol * 1.4
    v_lo  = sv < avg_vol * 0.6
    sp_wi = sp > avg_spread * 1.6
    sp_na = sp < avg_spread * 0.7

    def vp(name, ptype, desc):
        results.append({"name": name, "type": ptype,
                         "reliability": _rel(name, _VSA_REL), "desc": desc})

    # Selling Climax: high vol, wide spread DOWN bar, close in upper half
    if v_hi and sp_wi and bear(n) and cp > 0.5:
        vp("Selling Climax", "bullish",
           f"Vente climatique — volume {sv/avg_vol:.1f}x normal, large bougie baissière mais clôture haute. Demande absorbant l'offre.")

    # Buying Climax: high vol, wide spread UP bar, close in lower half
    elif v_hi and sp_wi and bull(n) and cp < 0.5:
        vp("Buying Climax", "bearish",
           f"Achat climatique — volume {sv/avg_vol:.1f}x normal, large bougie haussière mais clôture basse. Offre absorbant la demande.")

    # Up Thrust: high vol, wide spread UP then close in lower third
    elif v_mid and sp_wi and bull(n) and cp < 0.33:
        vp("Up Thrust", "bearish",
           "Up Thrust — forte montée rejetée, clôture en bas de bougie. Signal de faiblesse/distribution.")

    # Stopping Volume: very high vol, narrow spread DOWN → supply absorbed
    elif v_hi and sp_na and bear(n):
        vp("Stopping Volume", "bullish",
           f"Volume d'arrêt — {sv/avg_vol:.1f}x volume normal sur bougie étroite bearish. L'offre est absorbée, rebond possible.")

    # No Demand: low vol, narrow up bar, close in lower half
    elif v_lo and sp_na and bull(n) and cp < 0.5:
        vp("No Demand", "bearish",
           "Absence de demande — hausse sans volume. Faiblesse haussière masquée, risque de retournement.")

    # No Supply: low vol, narrow down bar, close in upper half
    elif v_lo and sp_na and bear(n) and cp > 0.5:
        vp("No Supply", "bullish",
           "Absence d'offre — baisse sans volume. Les vendeurs se retirent, potentiel rebond.")

    # Test of Support: low vol, bear bar, close near high
    elif v_lo and bear(n) and cp > 0.65 and n >= 1:
        vp("Test du support", "bullish",
           "Test du support — faible volume sur bougie baissière clôturant haut. L'offre est absente à ce niveau.")

    # End of Rising Market: price up 5 candles but volume declining
    if n >= 5:
        rc = c[n - 5:n + 1]
        rv = vol[n - 5:n + 1]
        if rv.std() > 0 and rc[-1] > rc[0]:
            slope = np.polyfit(range(6), rv, 1)[0]
            if slope < -avg_vol * 0.04:
                vp("End of Rising Market", "bearish",
                   "Fin de marché haussier — prix monte mais volume décline. Divergence baissière (distribution silencieuse).")

    # End of Falling Market: price down but volume declining
    if n >= 5:
        rc = c[n - 5:n + 1]
        rv = vol[n - 5:n + 1]
        if rv.std() > 0 and rc[-1] < rc[0]:
            slope = np.polyfit(range(6), rv, 1)[0]
            if slope < -avg_vol * 0.04:
                vp("End of Falling Market", "bullish",
                   "Fin de marché baissier — prix descend mais volume décline. Divergence haussière (accumulation silencieuse).")

    return results


# ─────────────────────────────────────────────────────────────────
# SMC — Smart Money Concepts
# ─────────────────────────────────────────────────────────────────

def detect_smc(df: pd.DataFrame) -> dict:
    result: dict = {"order_blocks": [], "fvg": [], "bos": [], "choch": [], "liquidity": []}
    if len(df) < 15:
        return result

    o = df["open"].values
    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    n = len(c)
    w = min(40, n)

    prev_h = max(h[-(w + 1):-4]) if n > w + 4 else max(h)
    prev_l = min(l[-(w + 1):-4]) if n > w + 4 else min(l)
    last   = c[-1]

    if last > prev_h:
        result["bos"].append(f"BOS haussier (cassure résistance ${prev_h:.2f})")
    elif last < prev_l:
        result["bos"].append(f"BOS baissier (cassure support ${prev_l:.2f})")

    if n >= 10:
        local_lows  = _troughs(l[-20:], order=3)
        local_highs = _peaks(h[-20:],   order=3)
        if len(local_lows) >= 2 and len(local_highs) >= 2:
            if (l[-20:][local_lows[-1]] < l[-20:][local_lows[-2]] and
                    last > h[-20:][local_highs[-1]]):
                result["choch"].append("CHoCH haussier (changement de caractère)")
            elif (h[-20:][local_highs[-1]] < h[-20:][local_highs[-2]] and
                    last < l[-20:][local_lows[-1]]):
                result["choch"].append("CHoCH baissier (changement de caractère)")

    # FVG
    for i in range(2, min(10, n)):
        idx = n - i
        if idx < 2:
            break
        if h[idx - 2] < l[idx]:
            gap = l[idx] - h[idx - 2]
            if gap >= 0.2:
                result["fvg"].append({"type": "bullish", "top": round(l[idx], 2),
                                      "bottom": round(h[idx - 2], 2),
                                      "mid": round((l[idx] + h[idx - 2]) / 2, 2),
                                      "size": round(gap, 2)})
                break
        elif l[idx - 2] > h[idx]:
            gap = l[idx - 2] - h[idx]
            if gap >= 0.2:
                result["fvg"].append({"type": "bearish", "top": round(l[idx - 2], 2),
                                      "bottom": round(h[idx], 2),
                                      "mid": round((l[idx - 2] + h[idx]) / 2, 2),
                                      "size": round(gap, 2)})
                break

    # Order Blocks
    for i in range(3, min(30, n)):
        idx = n - i
        if idx < 1:
            break
        if c[idx] < o[idx] and idx + 2 < n and c[idx + 1] > o[idx + 1] and c[idx + 2] > o[idx + 2]:
            result["order_blocks"].append({
                "type": "bullish",
                "high": round(max(o[idx], c[idx]), 2),
                "low":  round(min(o[idx], c[idx]), 2),
                "desc": f"OB haussier ${min(o[idx],c[idx]):.2f}–${max(o[idx],c[idx]):.2f}",
                "reliability": 65,
            })
            break

    for i in range(3, min(30, n)):
        idx = n - i
        if idx < 1:
            break
        if c[idx] > o[idx] and idx + 2 < n and c[idx + 1] < o[idx + 1] and c[idx + 2] < o[idx + 2]:
            result["order_blocks"].append({
                "type": "bearish",
                "high": round(max(o[idx], c[idx]), 2),
                "low":  round(min(o[idx], c[idx]), 2),
                "desc": f"OB baissier ${min(o[idx],c[idx]):.2f}–${max(o[idx],c[idx]):.2f}",
                "reliability": 65,
            })
            break

    # Liquidity
    recent_highs = _peaks(h[-w:],   order=5)
    recent_lows  = _troughs(l[-w:], order=5)
    if len(recent_highs) >= 2:
        eq   = h[-w:][recent_highs[-1]]
        prev = h[-w:][recent_highs[-2]]
        if abs(eq - prev) / max(eq, 1) < 0.004:
            result["liquidity"].append({"type": "sell_side", "level": round(eq, 2),
                                        "desc": f"Liquidité sell-side ${eq:.2f}"})
    if len(recent_lows) >= 2:
        eq   = l[-w:][recent_lows[-1]]
        prev = l[-w:][recent_lows[-2]]
        if abs(eq - prev) / max(abs(eq), 1) < 0.004:
            result["liquidity"].append({"type": "buy_side", "level": round(eq, 2),
                                        "desc": f"Liquidité buy-side ${eq:.2f}"})

    return result


# ─────────────────────────────────────────────────────────────────
# ICT — Inner Circle Trader concepts
# ─────────────────────────────────────────────────────────────────

def detect_ict(df: pd.DataFrame) -> dict:
    result: dict = {"kill_zones": [], "ote": None, "breaker_blocks": [], "mitigation_blocks": []}
    if len(df) < 10:
        return result

    h = df["high"].values
    l = df["low"].values
    c = df["close"].values
    o = df["open"].values
    n = len(c)

    utc_h = datetime.utcnow().hour
    if   2 <= utc_h <= 5:   result["kill_zones"].append("Asian Kill Zone (02h–05h UTC)")
    elif 7 <= utc_h <= 10:  result["kill_zones"].append("London Kill Zone (07h–10h UTC) — forte liquidité")
    elif 12 <= utc_h <= 15: result["kill_zones"].append("New York Kill Zone (12h–15h UTC) — forte liquidité")
    elif 19 <= utc_h <= 21: result["kill_zones"].append("Tokyo Kill Zone (19h–21h UTC)")

    w       = min(30, n)
    swing_h = max(h[-w:])
    swing_l = min(l[-w:])
    move    = swing_h - swing_l
    if move > 0:
        ote_low  = swing_h - 0.786 * move
        ote_high = swing_h - 0.618 * move
        price    = c[-1]
        if ote_low <= price <= ote_high:
            result["ote"] = {
                "zone_high": round(ote_high, 2),
                "zone_low":  round(ote_low, 2),
                "current":   round(price, 2),
                "reliability": 65,
                "desc": f"Zone OTE Fibonacci 61.8–78.6% ({ote_low:.2f}–{ote_high:.2f}) — entrée ICT idéale",
            }

    # Breaker Blocks
    for i in range(4, min(20, n)):
        idx = n - i
        if idx < 2:
            break
        if (c[idx] > o[idx] and idx + 2 < n and
                c[idx + 1] < o[idx + 1] and c[-1] > max(o[idx], c[idx])):
            result["breaker_blocks"].append({
                "type":  "bullish",
                "level": round(max(o[idx], c[idx]), 2),
                "reliability": 67,
                "desc":  f"Breaker Block haussier ${max(o[idx],c[idx]):.2f} — ancien OB baissier mitigé",
            })
            break

    for i in range(4, min(20, n)):
        idx = n - i
        if idx < 2:
            break
        if (c[idx] < o[idx] and idx + 2 < n and
                c[idx + 1] > o[idx + 1] and c[-1] < min(o[idx], c[idx])):
            result["breaker_blocks"].append({
                "type":  "bearish",
                "level": round(min(o[idx], c[idx]), 2),
                "reliability": 67,
                "desc":  f"Breaker Block baissier ${min(o[idx],c[idx]):.2f} — ancien OB haussier mitigé",
            })
            break

    return result


# ─────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────

def _peaks(arr: np.ndarray, order: int = 5) -> list[int]:
    return [i for i in range(order, len(arr) - order)
            if arr[i] == arr[i - order:i + order + 1].max()]


def _troughs(arr: np.ndarray, order: int = 5) -> list[int]:
    return [i for i in range(order, len(arr) - order)
            if arr[i] == arr[i - order:i + order + 1].min()]


def _alternating_swings(h: np.ndarray, l: np.ndarray,
                        peaks: list[int], troughs: list[int]) -> list[tuple]:
    combined = [(idx, h[idx], 'high') for idx in peaks] + \
               [(idx, l[idx], 'low')  for idx in troughs]
    combined.sort(key=lambda x: x[0])
    if not combined:
        return []
    result = [combined[0]]
    for sw in combined[1:]:
        if sw[2] != result[-1][2]:
            result.append(sw)
        elif sw[2] == 'high' and sw[1] > result[-1][1]:
            result[-1] = sw
        elif sw[2] == 'low' and sw[1] < result[-1][1]:
            result[-1] = sw
    return result
