import httpx
import logging

logger = logging.getLogger(__name__)


async def fetch_fear_greed() -> dict | None:
    """Fear & Greed index (alternative.me) as market risk-appetite proxy.
    For gold: extreme fear → bullish (safe-haven demand), extreme greed → bearish.
    """
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://api.alternative.me/fng/?limit=2")
            r.raise_for_status()
            entries = r.json()["data"]

        current = entries[0]
        value = int(current["value"])
        label = current["value_classification"]

        prev_value = int(entries[1]["value"]) if len(entries) > 1 else value
        change = value - prev_value

        if value <= 25:
            gold_implication = "BULLISH"
            gold_note = "Panique extrême → demande refuge pour l'or"
        elif value <= 45:
            gold_implication = "BULLISH"
            gold_note = "Peur → appétit pour l'or en hausse"
        elif value <= 55:
            gold_implication = "NEUTRAL"
            gold_note = "Sentiment neutre"
        elif value <= 75:
            gold_implication = "BEARISH"
            gold_note = "Cupidité → réduction des positions refuge"
        else:
            gold_implication = "BEARISH"
            gold_note = "Cupidité extrême → risque rotation hors or"

        return {
            "value": value,
            "label": label,
            "change_1d": change,
            "gold_implication": gold_implication,
            "gold_note": gold_note,
        }
    except Exception as e:
        logger.error(f"Fear & Greed fetch error: {e}")
        return None


def compute_confluence(market: dict, patterns: dict, cot: dict | None, fg: dict | None) -> dict:
    """Aggregate all signals into a confluence score with direction vote."""
    signals: list[dict] = []
    buy_w = 0
    sell_w = 0
    buy_count = 0
    sell_count = 0

    # Track categories for triple alignment bonus
    _cat_dirs: dict[str, str] = {}  # category → dominant direction

    def add(label: str, direction: str, weight: int, category: str = ""):
        nonlocal buy_w, sell_w, buy_count, sell_count
        signals.append({"label": label, "direction": direction, "weight": weight})
        if direction == "BUY":
            buy_w += weight
            buy_count += 1
        else:
            sell_w += weight
            sell_count += 1
        if category:
            _cat_dirs[category] = direction

    # --- RSI ---
    rsi = market.get("rsi")
    if rsi is not None:
        if rsi < 30:
            add(f"RSI survendu ({rsi:.0f})", "BUY", 3, "indicator")
        elif rsi < 40:
            add(f"RSI bas ({rsi:.0f})", "BUY", 1, "indicator")
        elif rsi > 70:
            add(f"RSI suracheté ({rsi:.0f})", "SELL", 3, "indicator")
        elif rsi > 60:
            add(f"RSI élevé ({rsi:.0f})", "SELL", 1, "indicator")

    # --- MACD ---
    hist = market.get("macd_histogram")
    macd = market.get("macd")
    sig = market.get("macd_signal")
    if hist is not None:
        if hist > 0 and macd is not None and sig is not None and macd > sig:
            add("MACD croisement haussier", "BUY", 2, "indicator")
        elif hist < 0 and macd is not None and sig is not None and macd < sig:
            add("MACD croisement baissier", "SELL", 2, "indicator")

    # --- EMA trend ---
    ts = market.get("trend_short")
    tm = market.get("trend_medium")
    if ts == "BULLISH":
        add("Tendance CT haussière (EMA20>50)", "BUY", 2, "indicator")
    elif ts == "BEARISH":
        add("Tendance CT baissière (EMA20<50)", "SELL", 2, "indicator")
    if tm == "BULLISH":
        add("Tendance MT haussière (EMA50>200)", "BUY", 3, "indicator")
    elif tm == "BEARISH":
        add("Tendance MT baissière (EMA50<200)", "SELL", 3, "indicator")

    # --- Bollinger Bands ---
    price = market.get("price")
    bb_low = market.get("bb_lower")
    bb_high = market.get("bb_upper")
    if price and bb_low and bb_high:
        band_range = bb_high - bb_low
        if band_range > 0:
            if price <= bb_low + band_range * 0.05:
                add("Prix sur bande inférieure BB", "BUY", 2, "indicator")
            elif price >= bb_high - band_range * 0.05:
                add("Prix sur bande supérieure BB", "SELL", 2, "indicator")

    # --- Candlestick patterns ---
    for p in patterns.get("candlestick", {}).get("bullish", []):
        name = p.get("name") if isinstance(p, dict) else p
        rel  = p.get("reliability", 60) if isinstance(p, dict) else 60
        w    = 3 if rel >= 75 else 2
        add(f"Pattern chandelier haussier: {name} (fiabilité {rel}%)", "BUY", w, "pattern")
    for p in patterns.get("candlestick", {}).get("bearish", []):
        name = p.get("name") if isinstance(p, dict) else p
        rel  = p.get("reliability", 60) if isinstance(p, dict) else 60
        w    = 3 if rel >= 75 else 2
        add(f"Pattern chandelier baissier: {name} (fiabilité {rel}%)", "SELL", w, "pattern")

    # --- Chart patterns ---
    for p in patterns.get("chart", []):
        if p.get("type") == "bullish":
            add(f"Pattern chartiste: {p['name']}", "BUY", 3, "pattern")
        elif p.get("type") == "bearish":
            add(f"Pattern chartiste: {p['name']}", "SELL", 3, "pattern")

    # --- SMC ---
    for ob in patterns.get("smc", {}).get("order_blocks", []):
        if ob.get("type") == "bullish":
            add("Order Block haussier détecté", "BUY", 2, "pattern")
        elif ob.get("type") == "bearish":
            add("Order Block baissier détecté", "SELL", 2, "pattern")
    for fvg in patterns.get("smc", {}).get("fvg", []):
        if fvg.get("type") == "bullish":
            add("FVG haussier (imbalance)", "BUY", 1)
        elif fvg.get("type") == "bearish":
            add("FVG baissier (imbalance)", "SELL", 1)
    for bos in patterns.get("smc", {}).get("bos", []):
        if "haussier" in bos.lower():
            add(bos, "BUY", 2)
        elif "baissier" in bos.lower():
            add(bos, "SELL", 2)

    # --- ICT OTE ---
    ote = patterns.get("ict", {}).get("ote")
    if ote:
        if ts == "BULLISH" or tm == "BULLISH":
            add(f"Prix en zone OTE ({ote['zone_low']}-{ote['zone_high']})", "BUY", 3)
        else:
            add(f"Prix en zone OTE ({ote['zone_low']}-{ote['zone_high']})", "SELL", 3)

    # --- COT ---
    if cot and not cot.get("error"):
        mm_sent = cot.get("mm_sentiment")
        mm_change = cot.get("mm_net_change")
        if mm_sent == "BULLISH":
            w = 3
            label = "COT Managed Money nets longs sur l'or"
            if mm_change and mm_change > 5000:
                label += f" (+{mm_change:,} contrats cette semaine)"
                w = 4
            add(label, "BUY", w, "macro")
        elif mm_sent == "BEARISH":
            w = 3
            label = "COT Managed Money nets courts sur l'or"
            if mm_change and mm_change < -5000:
                label += f" ({mm_change:,} contrats cette semaine)"
                w = 4
            add(label, "SELL", w, "macro")

    # --- Fear & Greed ---
    if fg:
        if fg["gold_implication"] == "BULLISH":
            add(f"Fear & Greed: {fg['label']} ({fg['value']}) → {fg['gold_note']}", "BUY", 1, "macro")
        elif fg["gold_implication"] == "BEARISH":
            add(f"Fear & Greed: {fg['label']} ({fg['value']}) → {fg['gold_note']}", "SELL", 1, "macro")

    # --- Triple alignment bonus: pattern + indicator + macro all agree ---
    cats_aligned = {"pattern", "indicator", "macro"}
    if cats_aligned.issubset(_cat_dirs.keys()):
        dirs = [_cat_dirs[c] for c in cats_aligned]
        if len(set(dirs)) == 1:  # all three point same direction
            bonus_dir = dirs[0]
            add("Alignement triple : patterns + indicateurs + macro", bonus_dir, 3)

    total = buy_w + sell_w
    if total == 0:
        direction = "NEUTRAL"
        score = 50
    elif buy_w >= sell_w:
        direction = "BUY"
        score = round(buy_w / total * 100)
    else:
        direction = "SELL"
        score = round(sell_w / total * 100)

    detail_str = f"{buy_count} haussier{'s' if buy_count != 1 else ''} / {sell_count} baissier{'s' if sell_count != 1 else ''}"

    return {
        "direction": direction,
        "score": score,
        "buy_weight": buy_w,
        "sell_weight": sell_w,
        "buy_count": buy_count,
        "sell_count": sell_count,
        "signal_count": len(signals),
        "detail_str": detail_str,
        "signals": signals,
    }
