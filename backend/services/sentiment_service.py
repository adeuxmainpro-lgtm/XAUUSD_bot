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


def compute_confluence(
    market: dict,
    patterns: dict,
    cot: dict | None,
    fg: dict | None,
    news: list | None = None,
    new_sources: dict | None = None,
) -> dict:
    """Aggregate all signals into a confluence score with direction vote.

    RSI interpretation: momentum/trend-confirmation (not contrarian).
      RSI < 40 = bearish territory, RSI > 60 = bullish territory.
    Each indicator, pattern, news sentiment, and ETF flow contributes exactly
    1 to the buy_count / sell_count shown in detail_str.
    """
    signals: list[dict] = []
    buy_w = 0
    sell_w = 0
    buy_count = 0
    sell_count = 0

    # Track dominant direction per category for triple-alignment bonus
    _cat_bull: dict[str, float] = {}
    _cat_bear: dict[str, float] = {}

    def add(label: str, direction: str, weight: int, category: str = ""):
        nonlocal buy_w, sell_w, buy_count, sell_count
        signals.append({"label": label, "direction": direction, "weight": weight})
        if direction == "BUY":
            buy_w += weight
            buy_count += 1
            _cat_bull[category] = _cat_bull.get(category, 0) + weight
        else:
            sell_w += weight
            sell_count += 1
            _cat_bear[category] = _cat_bear.get(category, 0) + weight

    # ── RSI — momentum/trend-confirmation (low RSI = bearish, high RSI = bullish) ──
    rsi = market.get("rsi")
    if rsi is not None:
        if rsi < 30:
            add(f"RSI momentum baissier fort ({rsi:.0f})", "SELL", 2, "indicator")
        elif rsi < 40:
            add(f"RSI territoire baissier ({rsi:.0f})", "SELL", 1, "indicator")
        elif rsi > 70:
            add(f"RSI momentum haussier fort ({rsi:.0f})", "BUY", 2, "indicator")
        elif rsi > 60:
            add(f"RSI territoire haussier ({rsi:.0f})", "BUY", 1, "indicator")

    # ── MACD ──
    hist = market.get("macd_histogram")
    macd = market.get("macd")
    sig  = market.get("macd_signal")
    if hist is not None and macd is not None and sig is not None:
        if hist > 0 and macd > sig:
            add("MACD croisement haussier", "BUY", 2, "indicator")
        elif hist < 0 and macd < sig:
            add("MACD croisement baissier", "SELL", 2, "indicator")

    # ── EMA alignment — counts as 1 signal for the full triple alignment ──
    ts = market.get("trend_short")   # EMA20 vs EMA50
    tm = market.get("trend_medium")  # EMA50 vs EMA200
    if ts == "BEARISH" and tm == "BEARISH":
        add("EMA20 < EMA50 < EMA200 — tendance baissière triple", "SELL", 4, "indicator")
    elif ts == "BULLISH" and tm == "BULLISH":
        add("EMA20 > EMA50 > EMA200 — tendance haussière triple", "BUY", 4, "indicator")
    elif ts == "BEARISH":
        add("EMA20 < EMA50 — tendance CT baissière", "SELL", 2, "indicator")
    elif ts == "BULLISH":
        add("EMA20 > EMA50 — tendance CT haussière", "BUY", 2, "indicator")
    if ts != tm:  # mixed: add the medium-term separately when they disagree
        if tm == "BEARISH":
            add("EMA50 < EMA200 — tendance MT baissière", "SELL", 2, "indicator")
        elif tm == "BULLISH":
            add("EMA50 > EMA200 — tendance MT haussière", "BUY", 2, "indicator")

    # ── Bollinger Bands ──
    price  = market.get("price")
    bb_low = market.get("bb_lower")
    bb_high = market.get("bb_upper")
    if price and bb_low and bb_high:
        band_range = bb_high - bb_low
        if band_range > 0:
            if price <= bb_low + band_range * 0.05:
                add("Prix sur bande inférieure BB", "BUY", 2, "indicator")
            elif price >= bb_high - band_range * 0.05:
                add("Prix sur bande supérieure BB", "SELL", 2, "indicator")

    # ── Candlestick patterns — 1 signal each ──
    for p in patterns.get("candlestick", {}).get("bullish", []):
        name = p.get("name") if isinstance(p, dict) else p
        rel  = p.get("reliability", 60) if isinstance(p, dict) else 60
        add(f"Chandelier haussier: {name} ({rel}%)", "BUY", 3 if rel >= 75 else 2, "pattern")
    for p in patterns.get("candlestick", {}).get("bearish", []):
        name = p.get("name") if isinstance(p, dict) else p
        rel  = p.get("reliability", 60) if isinstance(p, dict) else 60
        add(f"Chandelier baissier: {name} ({rel}%)", "SELL", 3 if rel >= 75 else 2, "pattern")

    # ── Chart patterns — 1 signal each ──
    for p in patterns.get("chart", []):
        if p.get("type") == "bullish":
            add(f"Pattern chartiste haussier: {p['name']}", "BUY", 3, "pattern")
        elif p.get("type") == "bearish":
            add(f"Pattern chartiste baissier: {p['name']}", "SELL", 3, "pattern")

    # ── SMC / ICT ──
    for ob in patterns.get("smc", {}).get("order_blocks", []):
        if ob.get("type") == "bullish":
            add("Order Block haussier", "BUY", 2, "pattern")
        elif ob.get("type") == "bearish":
            add("Order Block baissier", "SELL", 2, "pattern")
    for fvg in patterns.get("smc", {}).get("fvg", []):
        if fvg.get("type") == "bullish":
            add("FVG haussier", "BUY", 1, "pattern")
        elif fvg.get("type") == "bearish":
            add("FVG baissier", "SELL", 1, "pattern")
    for bos in patterns.get("smc", {}).get("bos", []):
        if "haussier" in bos.lower():
            add(bos, "BUY", 2, "pattern")
        elif "baissier" in bos.lower():
            add(bos, "SELL", 2, "pattern")
    for bb_ in patterns.get("ict", {}).get("breaker_blocks", []):
        desc = bb_.get("desc", "").lower() if isinstance(bb_, dict) else str(bb_).lower()
        if "haussier" in desc or "bullish" in desc:
            add(f"Breaker Block haussier", "BUY", 2, "pattern")
        elif "baissier" in desc or "bearish" in desc:
            add(f"Breaker Block baissier", "SELL", 2, "pattern")
    ote = patterns.get("ict", {}).get("ote")
    if ote:
        ote_dir = "BUY" if (ts == "BULLISH" and tm == "BULLISH") else "SELL"
        add(f"Zone OTE ({ote.get('zone_low', '')}-{ote.get('zone_high', '')})", ote_dir, 2, "pattern")

    # ── COT ──
    if cot and not cot.get("error"):
        mm_sent   = cot.get("mm_sentiment")
        mm_change = cot.get("mm_net_change")
        if mm_sent == "BULLISH":
            w = 4 if (mm_change and mm_change > 5000) else 3
            add(f"COT MM nets longs{f' +{mm_change:,}' if mm_change else ''}", "BUY", w, "macro")
        elif mm_sent == "BEARISH":
            w = 4 if (mm_change and mm_change < -5000) else 3
            add(f"COT MM nets courts{f' {mm_change:,}' if mm_change else ''}", "SELL", w, "macro")

    # ── Fear & Greed — contrarian for gold ──
    if fg:
        fgi = fg.get("gold_implication")
        if fgi == "BULLISH":
            add(f"Fear & Greed {fg['value']}/100 ({fg['label']}) — refuge or", "BUY", 1, "macro")
        elif fgi == "BEARISH":
            add(f"Fear & Greed {fg['value']}/100 ({fg['label']}) — pression sur l'or", "SELL", 1, "macro")

    # ── News sentiment — 1 aggregated signal ──
    if news:
        non_cal = [n for n in news if not n.get("is_calendar")]
        bear_n  = sum(1 for n in non_cal if n.get("direction") == "BEARISH")
        bull_n  = sum(1 for n in non_cal if n.get("direction") == "BULLISH")
        if bear_n > bull_n:
            add(f"Sentiment news baissier ({bear_n}/{len(non_cal)} BEARISH)", "SELL", 1, "news")
        elif bull_n > bear_n:
            add(f"Sentiment news haussier ({bull_n}/{len(non_cal)} BULLISH)", "BUY", 1, "news")

    # ── ETF flows — 1 aggregated signal ──
    if new_sources:
        etf = new_sources.get("etf_flows", {})
        if etf:
            bear_etf = sum(1 for d in etf.values() if d.get("signal") == "BEARISH")
            bull_etf = sum(1 for d in etf.values() if d.get("signal") == "BULLISH")
            if bear_etf > bull_etf:
                add(f"Flux ETF or négatifs ({bear_etf} ETF baissier)", "SELL", 1, "macro")
            elif bull_etf > bear_etf:
                add(f"Flux ETF or positifs ({bull_etf} ETF haussier)", "BUY", 1, "macro")

    # ── Triple alignment bonus ──
    cats_all = set(_cat_bull.keys()) | set(_cat_bear.keys())
    _cat_dominant: dict[str, str] = {
        c: ("BUY" if _cat_bull.get(c, 0) >= _cat_bear.get(c, 0) else "SELL")
        for c in cats_all
    }
    cats_to_align = {"pattern", "indicator", "macro"}
    if cats_to_align.issubset(cats_all):
        dirs = [_cat_dominant[c] for c in cats_to_align]
        if len(set(dirs)) == 1:
            add("Alignement triple : patterns + indicateurs + macro", dirs[0], 3)

    total_count = buy_count + sell_count
    if total_count == 0:
        direction = "NEUTRAL"
        score = 50
    elif buy_count >= sell_count:
        direction = "BUY"
        score = round(buy_count / total_count * 100)
    else:
        direction = "SELL"
        score = round(sell_count / total_count * 100)

    detail_str = f"{buy_count} haussier{'s' if buy_count != 1 else ''} / {sell_count} baissier{'s' if sell_count != 1 else ''}"

    return {
        "direction":    direction,
        "score":        score,
        "buy_weight":   buy_w,
        "sell_weight":  sell_w,
        "buy_count":    buy_count,
        "sell_count":   sell_count,
        "signal_count": len(signals),
        "detail_str":   detail_str,
        "signals":      signals,
    }


def compute_composite_score(
    market: dict,
    patterns: dict,
    cot: dict | None,
    fg: dict | None,
    news: list[dict] | None,
    new_sources: dict | None,
) -> dict:
    """
    Composite 0-100 score across 6 categories.
    50 = neutral, >60 = BUY, <40 = SELL.
    Categories:
      technical     max 25 pts
      patterns      max 20 pts
      macro         max 20 pts (Fed NLP, Treasury, DXY correlation)
      institutional max 20 pts (COT, ETF flows, options)
      retail        max 10 pts (Fear & Greed contrarian)
      news          max  5 pts
    """

    # --- helpers ---
    CAT_MAX = {"technical": 25, "patterns": 20, "macro": 20, "institutional": 20, "retail": 10, "news": 5}

    cats: dict[str, dict] = {k: {"bull": 0.0, "bear": 0.0, "signals": []} for k in CAT_MAX}

    def add(cat: str, direction: str, weight: float, label: str):
        cats[cat]["signals"].append({"label": label, "direction": direction, "weight": weight})
        if direction == "BUY":
            cats[cat]["bull"] += weight
        else:
            cats[cat]["bear"] += weight

    # ── TECHNICAL (25 pts) ───────────────────────────────────────
    rsi = market.get("rsi")
    if rsi is not None:
        if rsi < 30:   add("technical", "BUY",  3, f"RSI survendu ({rsi:.0f})")
        elif rsi < 40: add("technical", "BUY",  1, f"RSI bas ({rsi:.0f})")
        elif rsi > 70: add("technical", "SELL", 3, f"RSI suracheté ({rsi:.0f})")
        elif rsi > 60: add("technical", "SELL", 1, f"RSI élevé ({rsi:.0f})")

    hist = market.get("macd_histogram")
    macd = market.get("macd"); sig = market.get("macd_signal")
    if hist is not None and macd is not None and sig is not None:
        if hist > 0 and macd > sig: add("technical", "BUY",  2, "MACD croisement haussier")
        elif hist < 0 and macd < sig: add("technical", "SELL", 2, "MACD croisement baissier")

    ts = market.get("trend_short"); tm = market.get("trend_medium")
    if ts == "BULLISH":  add("technical", "BUY",  2, "EMA20>50 haussier")
    elif ts == "BEARISH": add("technical", "SELL", 2, "EMA20<50 baissier")
    if tm == "BULLISH":  add("technical", "BUY",  3, "EMA50>200 tendance MT haussière")
    elif tm == "BEARISH": add("technical", "SELL", 3, "EMA50<200 tendance MT baissière")

    price = market.get("price")
    bb_low = market.get("bb_lower"); bb_high = market.get("bb_upper")
    if price and bb_low and bb_high:
        br = bb_high - bb_low
        if br > 0:
            if price <= bb_low + br * 0.05:   add("technical", "BUY",  2, "Prix sur BB inférieure")
            elif price >= bb_high - br * 0.05: add("technical", "SELL", 2, "Prix sur BB supérieure")

    atr_pct = market.get("atr_pct")
    if atr_pct and atr_pct > 0.8: add("technical", "SELL", 1, f"Volatilité ATR élevée ({atr_pct:.2f}%)")

    # ── PATTERNS (20 pts) ────────────────────────────────────────
    for p in patterns.get("candlestick", {}).get("bullish", []):
        name = p.get("name") if isinstance(p, dict) else p
        rel  = p.get("reliability", 60) if isinstance(p, dict) else 60
        add("patterns", "BUY",  3 if rel >= 75 else 2, f"Chandelier haussier: {name}")
    for p in patterns.get("candlestick", {}).get("bearish", []):
        name = p.get("name") if isinstance(p, dict) else p
        rel  = p.get("reliability", 60) if isinstance(p, dict) else 60
        add("patterns", "SELL", 3 if rel >= 75 else 2, f"Chandelier baissier: {name}")
    for p in patterns.get("chart", []):
        if p.get("type") == "bullish":  add("patterns", "BUY",  3, f"Chart: {p['name']}")
        elif p.get("type") == "bearish": add("patterns", "SELL", 3, f"Chart: {p['name']}")
    for ob in patterns.get("smc", {}).get("order_blocks", []):
        if ob.get("type") == "bullish":  add("patterns", "BUY",  2, "Order Block haussier")
        elif ob.get("type") == "bearish": add("patterns", "SELL", 2, "Order Block baissier")
    for bos in patterns.get("smc", {}).get("bos", []):
        if "haussier" in bos.lower(): add("patterns", "BUY",  2, bos)
        elif "baissier" in bos.lower(): add("patterns", "SELL", 2, bos)
    ote = patterns.get("ict", {}).get("ote")
    if ote:
        d = "BUY" if (ts == "BULLISH" or tm == "BULLISH") else "SELL"
        add("patterns", d, 3, f"Zone OTE {ote.get('zone_low','')}–{ote.get('zone_high','')}")

    # ── MACRO (20 pts) ───────────────────────────────────────────
    ns = new_sources or {}

    # DXY correlation (key = "DX-Y.NYB" from yfinance)
    corr = ns.get("correlations", {})
    dxy_sig = corr.get("DX-Y.NYB", {}).get("signal")
    if dxy_sig == "BULLISH":  add("macro", "BUY",  3, f"DXY corrélation baissière (or favorisé)")
    elif dxy_sig == "BEARISH": add("macro", "SELL", 3, f"DXY corrélation haussière (or pénalisé)")

    # VIX (key = "^VIX" from yfinance; risk-off = gold bullish)
    vix_data = corr.get("^VIX", {})
    vix_sig = vix_data.get("signal")
    vix_val = vix_data.get("current")
    if vix_val and vix_val > 20:  add("macro", "BUY",  2, f"VIX élevé ({vix_val:.1f}) → refuge or")
    elif vix_sig == "BEARISH":    add("macro", "SELL", 1, f"VIX bas → risk-on, pression sur l'or")

    # Treasury yields
    yields = ns.get("yields", {})
    yields_sig = yields.get("signal")
    if yields_sig == "BULLISH":   add("macro", "BUY",  3, f"Courbe inversée → refuge obligataire + or")
    elif yields_sig == "BEARISH": add("macro", "SELL", 3, f"Taux longs élevés → pression sur l'or")

    # Fed NLP
    fed = ns.get("fed_nlp", {})
    fed_sig = fed.get("gold_signal")
    fed_score = fed.get("score", 0)
    if fed_sig == "BULLISH":   add("macro", "BUY",  3 if abs(fed_score) >= 3 else 2, f"Fed dovish (score {fed_score}) → or haussier")
    elif fed_sig == "BEARISH": add("macro", "SELL", 3 if abs(fed_score) >= 3 else 2, f"Fed hawkish (score {fed_score}) → or baissier")

    # WTI (key = "CL=F" from yfinance; inflation proxy)
    wti_sig = corr.get("CL=F", {}).get("signal")
    if wti_sig == "BULLISH": add("macro", "BUY",  1, "WTI corrélé à l'or → inflation proxy")

    # ── INSTITUTIONAL (20 pts) ───────────────────────────────────
    # COT Managed Money
    if cot and not cot.get("error"):
        mm_sent = cot.get("mm_sentiment")
        mm_chg  = cot.get("mm_net_change")
        mm_net  = cot.get("mm_net", 0) or 0
        # Extreme contrarian signal
        if mm_net > 200000:
            add("institutional", "SELL", 4, f"COT MM suracheté ({mm_net:,}) → contrarian baissier")
        elif mm_net < 50000:
            add("institutional", "BUY",  4, f"COT MM survendu ({mm_net:,}) → contrarian haussier")
        elif mm_sent == "BULLISH":
            w = 4 if (mm_chg and mm_chg > 5000) else 3
            add("institutional", "BUY",  w, f"COT MM nets longs{' +'+str(mm_chg) if mm_chg else ''}")
        elif mm_sent == "BEARISH":
            w = 4 if (mm_chg and mm_chg < -5000) else 3
            add("institutional", "SELL", w, f"COT MM nets courts{' '+str(mm_chg) if mm_chg else ''}")
        # Commercials (hedgers = contrarian)
        comm_net = cot.get("comm_net", 0) or 0
        if comm_net > 0:   add("institutional", "SELL", 2, f"Commerciaux net long (hedge producteurs)")
        elif comm_net < 0: add("institutional", "BUY",  2, f"Commerciaux net short (couverture acheteurs)")

    # ETF flows
    etf = ns.get("etf_flows", {})
    for ticker, etf_data in etf.items():
        s = etf_data.get("signal")
        pct = etf_data.get("price_change_pct", 0)
        if s == "BULLISH":   add("institutional", "BUY",  2, f"ETF {ticker} entrées (+{pct:.2f}%)")
        elif s == "BEARISH": add("institutional", "SELL", 2, f"ETF {ticker} sorties ({pct:.2f}%)")

    # Options P/C ratio (contrarian)
    opts = ns.get("options", {})
    pc   = opts.get("put_call_ratio")
    opts_sig = opts.get("signal")
    if opts_sig == "BULLISH" and pc:   add("institutional", "BUY",  3, f"Options GLD P/C élevé ({pc:.2f}) → contrarian haussier")
    elif opts_sig == "BEARISH" and pc: add("institutional", "SELL", 3, f"Options GLD P/C bas ({pc:.2f}) → contrarian baissier")

    # ── RETAIL (10 pts) ──────────────────────────────────────────
    if fg:
        fgi = fg.get("gold_implication")
        v   = fg.get("value", 50)
        if fgi == "BULLISH":
            w = 3 if v <= 25 else 2
            add("retail", "BUY",  w, f"Fear & Greed {v}/100 — {fg.get('gold_note','')}")
        elif fgi == "BEARISH":
            w = 3 if v >= 75 else 2
            add("retail", "SELL", w, f"Fear & Greed {v}/100 — {fg.get('gold_note','')}")

    # ── NEWS (5 pts) ─────────────────────────────────────────────
    if news:
        non_cal = [n for n in news if not n.get("is_calendar")]
        bull_n  = sum(1 for n in non_cal if n.get("direction") == "BULLISH")
        bear_n  = sum(1 for n in non_cal if n.get("direction") == "BEARISH")
        if bull_n > bear_n:   add("news", "BUY",  min(bull_n, 3), f"Actualités haussières ({bull_n}/{len(non_cal)})")
        elif bear_n > bull_n: add("news", "SELL", min(bear_n, 3), f"Actualités baissières ({bear_n}/{len(non_cal)})")

    # ── COMPUTE SCORES ───────────────────────────────────────────
    def _cat_score(bull_w: float, bear_w: float, max_pts: int) -> int:
        total = bull_w + bear_w
        if total == 0:
            return max_pts // 2
        return round((bull_w / total) * max_pts)

    cat_results = {}
    total_score = 0
    for cat_name, cat_data in cats.items():
        max_pts = CAT_MAX[cat_name]
        bull_w  = cat_data["bull"]
        bear_w  = cat_data["bear"]
        score   = _cat_score(bull_w, bear_w, max_pts)
        pct_bull = bull_w / (bull_w + bear_w) if (bull_w + bear_w) > 0 else 0.5
        direction = "BUY" if pct_bull > 0.62 else ("SELL" if pct_bull < 0.38 else "NEUTRAL")
        cat_results[cat_name] = {
            "score":     score,
            "max":       max_pts,
            "direction": direction,
            "signals":   cat_data["signals"],
        }
        total_score += score

    # Direction from composite
    if total_score > 60:
        direction = "BUY"
        label     = "Signal fort haussier" if total_score > 75 else "Signal modéré haussier"
    elif total_score < 40:
        direction = "SELL"
        label     = "Signal fort baissier" if total_score < 25 else "Signal modéré baissier"
    else:
        # Weak zone: use dominant signal from signals list to break tie
        all_bull = sum(c["bull"] for c in cats.values())
        all_bear = sum(c["bear"] for c in cats.values())
        direction = "BUY" if all_bull >= all_bear else "SELL"
        label     = "Signal faible — position réduite"

    return {
        "score":      total_score,
        "direction":  direction,
        "label":      label,
        "categories": cat_results,
    }
