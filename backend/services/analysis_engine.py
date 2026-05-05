import logging
import asyncio
from backend.services.market_data import get_full_market_data
from backend.services.macro_data import get_macro_context
from backend.services.pattern_service import detect_all_patterns
from backend.services.sentiment_service import fetch_fear_greed, compute_confluence, compute_composite_score
from backend.services.signal_engine import evaluate_signal
from backend.services.new_sources_service import fetch_all_new_sources
from backend.services.smc_engine import (
    analyze_mtf, detect_kill_zone, detect_liquidity_sweep,
    detect_wyckoff_phase, detect_rsi_divergence, compute_trade_score,
)
from backend.services.regime_detector import detect_regime
from backend.database import get_latest_news, get_latest_cot, get_latest_sentiment, get_closed_trades_for_learning
from backend.services.forex_factory_service import fetch_high_impact_events, is_high_impact_imminent

logger = logging.getLogger(__name__)


def _compute_ema(closes: list[float], period: int) -> float | None:
    if len(closes) < period:
        return None
    k = 2.0 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return ema


async def build_market_context() -> dict:
    """Assemble full market context: price, macro, news, patterns, COT, sentiment, trade history."""
    market, macro, fg, new_sources, ff_events, ff_imminent = await asyncio.gather(
        get_full_market_data(),
        get_macro_context(),
        fetch_fear_greed(),
        fetch_all_new_sources(),
        fetch_high_impact_events(),
        is_high_impact_imminent(hours=2),
        return_exceptions=True,
    )

    if isinstance(market, Exception):
        logger.error(f"Market data error: {market}")
        market = {}
    if isinstance(macro, Exception):
        logger.error(f"Macro data error: {macro}")
        macro = {}
    if isinstance(fg, Exception):
        logger.error(f"Fear & Greed error: {fg}")
        fg = None
    if isinstance(new_sources, Exception):
        logger.warning(f"New sources error: {new_sources}")
        new_sources = {}
    if isinstance(ff_events, Exception):
        logger.warning(f"Forex Factory error: {ff_events}")
        ff_events = []
    if isinstance(ff_imminent, Exception):
        ff_imminent = None

    # Patterns from 1h OHLC
    patterns: dict = {}
    ohlc_1h  = market.get("ohlc_1h",  [])
    ohlc_15m = market.get("ohlc_15m", [])
    ohlc_4h  = market.get("ohlc_4h",  [])
    ohlc_1d  = market.get("ohlc_1d",  [])

    if ohlc_1h:
        try:
            patterns = detect_all_patterns(ohlc_1h)
        except Exception as e:
            logger.error(f"Pattern detection error: {e}")

    # COT from cache (refreshed by scheduler weekly)
    cot = get_latest_cot()

    # News from cache (needed before confluence to include sentiment in signal count)
    news = get_latest_news()

    # Confluence score (includes news sentiment + ETF flows in the count)
    fg_clean = fg if not isinstance(fg, Exception) else None
    confluence = compute_confluence(
        market, patterns, cot, fg_clean,
        news=news, new_sources=new_sources,
    )

    # Pre-AI signal evaluation (blocking conditions, signal level, watch list)
    signal_eval = evaluate_signal(market, macro if not isinstance(macro, Exception) else {}, confluence)

    # Composite 100-point score
    try:
        composite = compute_composite_score(market, patterns, cot, fg_clean, news, new_sources)
    except Exception as e:
        logger.warning(f"Composite score error: {e}")
        composite = {}

    # ── SMC/ICT strategy engine ───────────────────────────────────
    try:
        mtf = analyze_mtf(ohlc_15m, ohlc_1h, ohlc_4h, ohlc_1d)
    except Exception as e:
        logger.warning(f"MTF analysis error: {e}")
        mtf = {"biases": {}, "primary_bias": "NEUTRAL", "aligned_count": 0,
               "aligned_str": "N/A", "bias_4h": "NEUTRAL", "bias_1d": "NEUTRAL"}

    kill_zone = detect_kill_zone()

    try:
        liquidity_sweep = detect_liquidity_sweep(ohlc_1h)
    except Exception as e:
        logger.warning(f"Liquidity sweep error: {e}")
        liquidity_sweep = {"detected": False, "type": None, "direction": None, "level": None, "desc": ""}

    try:
        wyckoff = detect_wyckoff_phase(ohlc_1h)
    except Exception as e:
        logger.warning(f"Wyckoff error: {e}")
        wyckoff = {"phase": "Unknown", "desc": "", "trading_bias": "NEUTRAL"}

    try:
        rsi_divergence = detect_rsi_divergence(ohlc_1h)
    except Exception as e:
        logger.warning(f"RSI divergence error: {e}")
        rsi_divergence = {"detected": False, "type": None, "direction": None, "desc": ""}

    try:
        trade_score_obj = compute_trade_score(
            mtf, kill_zone, liquidity_sweep, patterns, rsi_divergence, market,
        )
    except Exception as e:
        logger.warning(f"Trade score error: {e}")
        trade_score_obj = {"score": 0, "conditions": {}, "details": [], "tradeable": False,
                           "signal_level": "WEAK", "label": "N/A", "position_pct": 0.0}

    # Market regime detection
    try:
        regime = detect_regime(
            market,
            macro if not isinstance(macro, Exception) else {},
            new_sources,
            fg_clean,
        )
    except Exception as e:
        logger.warning(f"Regime detection error: {e}")
        regime = {"regime": "neutral", "label": "Neutre", "gold_bias": "NEUTRAL",
                  "description": "", "aggression": 1.0, "emoji": "⚪", "signals": []}

    # Trade learning data
    past_trades = get_closed_trades_for_learning(30)

    # EMA200 multi-timeframe filter
    _price = market.get("price")
    _closes_4h = [c["close"] for c in ohlc_4h if c.get("close")]
    _closes_1h = [c["close"] for c in ohlc_1h if c.get("close")]
    _ema200_4h = _compute_ema(_closes_4h, 200)
    _ema200_1h = _compute_ema(_closes_1h, 200)
    ema200_filter = {
        "ema200_4h": round(_ema200_4h, 2) if _ema200_4h else None,
        "ema200_1h": round(_ema200_1h, 2) if _ema200_1h else None,
        "above_4h":  (_price > _ema200_4h) if (_price and _ema200_4h) else None,
        "above_1h":  (_price > _ema200_1h) if (_price and _ema200_1h) else None,
    }

    return {
        "market":          market,
        "macro":           macro,
        "news":            news,
        "patterns":        patterns,
        "cot":             cot,
        "fear_greed":      fg_clean,
        "confluence":      confluence,
        "signal_eval":     signal_eval,
        "new_sources":     new_sources,
        "composite":       composite,
        "past_trades":     past_trades,
        "ema200_filter":   ema200_filter,
        # SMC/ICT engine outputs
        "mtf":             mtf,
        "kill_zone":       kill_zone,
        "liquidity_sweep": liquidity_sweep,
        "wyckoff":         wyckoff,
        "rsi_divergence":  rsi_divergence,
        "trade_score_obj": trade_score_obj,
        "regime":          regime,
        # Economic calendar
        "ff_events":       ff_events,
        "ff_imminent":     ff_imminent,
    }


def format_context_for_prompt(ctx: dict) -> str:
    """Format full context as readable text for Claude."""
    m = ctx.get("market", {})
    macro = ctx.get("macro", {})
    news = ctx.get("news", [])
    patterns = ctx.get("patterns", {})
    cot = ctx.get("cot")
    fg = ctx.get("fear_greed")
    confluence = ctx.get("confluence", {})
    signal_eval = ctx.get("signal_eval", {})
    past_trades = ctx.get("past_trades", [])

    mtf             = ctx.get("mtf", {})
    kill_zone       = ctx.get("kill_zone", {})
    liquidity_sweep = ctx.get("liquidity_sweep", {})
    wyckoff         = ctx.get("wyckoff", {})
    rsi_divergence  = ctx.get("rsi_divergence", {})
    trade_score_obj = ctx.get("trade_score_obj", {})
    regime          = ctx.get("regime", {})

    lines = ["=== DONNÉES DE MARCHÉ XAUUSD ==="]

    price = m.get("price")
    if price:
        lines.append(f"Prix actuel : ${price:.2f}")
        lines.append(f"Open: ${m.get('open','N/A')}  High: ${m.get('high','N/A')}  Low: ${m.get('low','N/A')}")

    lines.append("\n--- INDICATEURS TECHNIQUES ---")
    if m.get("rsi") is not None:
        rsi = m["rsi"]
        interp = "suracheté" if rsi > 70 else ("survendu" if rsi < 30 else "neutre")
        lines.append(f"RSI(14): {rsi:.1f} ({interp})")

    if m.get("macd") is not None:
        hist = m.get("macd_histogram", 0) or 0
        lines.append(f"MACD: {m['macd']:.4f} | Signal: {m.get('macd_signal','N/A')} | Histo: {'▲' if hist>0 else '▼'} {hist:.4f}")

    for ema in ["ema20", "ema50", "ema200"]:
        if m.get(ema) and price:
            diff = (price - m[ema]) / m[ema] * 100
            lines.append(f"{ema.upper()}: ${m[ema]:.2f} (prix {'au-dessus +' if diff>0 else 'en-dessous '}{abs(diff):.2f}%)")

    if m.get("bb_upper"):
        lines.append(f"Bollinger : sup=${m['bb_upper']:.2f} | mid=${m['bb_mid']:.2f} | inf=${m['bb_lower']:.2f}")

    if m.get("atr"):
        lines.append(f"ATR(14): ${m['atr']:.2f} ({m.get('atr_pct',0):.3f}% du prix)")

    lines.append(f"\nTendance CT (EMA20/50): {m.get('trend_short','N/A')}")
    lines.append(f"Tendance MT (EMA50/200): {m.get('trend_medium','N/A')}")

    if m.get("supports"):
        lines.append(f"Supports: {m['supports']}")
    if m.get("resistances"):
        lines.append(f"Résistances: {m['resistances']}")

    # ── Patterns ──
    cs = patterns.get("candlestick", {})
    chart_pats = patterns.get("chart", [])
    smc = patterns.get("smc", {})
    ict = patterns.get("ict", {})

    if cs.get("bullish") or cs.get("bearish"):
        lines.append("\n--- PATTERNS CHANDELIERS ---")
        if cs.get("bullish"):
            names = [p.get("name") if isinstance(p, dict) else p for p in cs["bullish"]]
            lines.append(f"Haussiers: {', '.join(names)}")
        if cs.get("bearish"):
            names = [p.get("name") if isinstance(p, dict) else p for p in cs["bearish"]]
            lines.append(f"Baissiers: {', '.join(names)}")

    if chart_pats:
        lines.append("\n--- PATTERNS CHARTISTES ---")
        for p in chart_pats:
            lines.append(f"• {p.get('name')} ({p.get('type','')}) — {p.get('desc','')}")

    smc_items = []
    for ob in smc.get("order_blocks", []):
        smc_items.append(ob.get("desc", ""))
    for fvg in smc.get("fvg", []):
        smc_items.append(f"FVG {fvg.get('type','')}: ${fvg.get('bottom','')}–${fvg.get('top','')}")
    for bos in smc.get("bos", []):
        smc_items.append(bos)
    for choch in smc.get("choch", []):
        smc_items.append(choch)
    for liq in smc.get("liquidity", []):
        smc_items.append(liq.get("desc", ""))
    if smc_items:
        lines.append("\n--- SMC / ICT ---")
        for s in smc_items:
            lines.append(f"• {s}")
    if ict.get("kill_zones"):
        lines.append(f"• {' | '.join(ict['kill_zones'])}")
    if ict.get("ote"):
        lines.append(f"• {ict['ote']['desc']}")
    for bb in ict.get("breaker_blocks", []):
        lines.append(f"• {bb.get('desc','')}")

    # ── Confluence ──
    if confluence:
        lines.append(f"\n--- SCORE DE CONFLUENCE ---")
        lines.append(f"Direction: {confluence.get('direction')} | Score: {confluence.get('score')}% ({confluence.get('buy_weight')} BUY vs {confluence.get('sell_weight')} SELL)")
        for sig in confluence.get("signals", [])[:8]:
            lines.append(f"  {'▲' if sig['direction']=='BUY' else '▼'} [{sig['weight']}] {sig['label']}")

    # ── Pre-AI signal evaluation ──
    if signal_eval:
        lvl   = signal_eval.get("signal_level", "WAIT")
        score = signal_eval.get("confluence_score", 0)
        lines.append(f"\n--- ÉVALUATION PRÉ-ANALYSE ---")
        lines.append(f"Niveau de signal : {lvl} (confluence {score}%)")
        lvl_map = {
            "STRONG":   "✅ SIGNAL FORT — confluence ≥ 75%, BUY/SELL recommandé avec confiance élevée",
            "MODERATE": "⚡ SIGNAL MODÉRÉ — confluence 60-74%, BUY/SELL avec prudence",
            "WEAK":     "〰 SIGNAL FAIBLE — confluence 45-59%, BUY/SELL avec position réduite 0.5%",
            "WAIT":     "⏳ ATTENDRE — annonce HIGH impact dans moins de 30 minutes",
        }
        lines.append(lvl_map.get(lvl, f"Signal niveau {lvl}"))
        for b in signal_eval.get("blocking_conditions", []):
            lines.append(f"  ⛔ BLOQUANT: {b}")
        if signal_eval.get("watch_conditions"):
            lines.append("Conditions à surveiller :")
            for w in signal_eval["watch_conditions"]:
                lines.append(f"  → {w}")

    # ── Macro ──
    lines.append("\n=== CONTEXTE MACRO ===")
    if macro.get("fed_rate") is not None:
        lines.append(f"Taux FED: {macro['fed_rate']:.2f}%")
    if macro.get("cpi_yoy") is not None:
        lines.append(f"CPI YoY: {macro['cpi_yoy']:.2f}%")
    if macro.get("nfp_change_k") is not None:
        lines.append(f"NFP: +{macro['nfp_change_k']:.0f}K emplois")
    if macro.get("dxy") is not None:
        lines.append(f"DXY: {macro['dxy']:.3f}")
    if macro.get("us10y") is not None:
        us10y = macro["us10y"]
        real_yield_note = "↑ pression baissière sur l'or" if us10y > 4.5 else ("↓ soutien à l'or" if us10y < 3.5 else "neutre")
        lines.append(f"Taux 10Y US (DGS10): {us10y:.3f}% — {real_yield_note}")
    if macro.get("dxy_fred") is not None:
        lines.append(f"Dollar Index large (DTWEXBGS/FRED): {macro['dxy_fred']:.2f}")

    # ── Forex Factory Economic Calendar ──
    ff_events  = ctx.get("ff_events", [])
    ff_imminent = ctx.get("ff_imminent")

    if ff_imminent:
        ev = ff_imminent
        lines.append(f"\n⛔ ALERTE CALENDRIER — ÉVÉNEMENT HIGH IMPACT IMMINENT :")
        lines.append(f"  {ev['title']} dans {ev['hours_until']:.1f}h ({ev.get('time','?')} UTC)")
        lines.append(f"  → RÈGLE : NE PAS OUVRIR DE TRADE — attendre la publication et la digestion")

    upcoming_2h = [e for e in ff_events if 0 < e.get("hours_until", 99) <= 2]
    upcoming_24h = [e for e in ff_events if 2 < e.get("hours_until", 99) <= 24]

    if upcoming_2h or upcoming_24h:
        lines.append("\n--- CALENDRIER ÉCONOMIQUE HIGH IMPACT (USD) ---")
        for e in upcoming_2h:
            lines.append(f"  ⚠️ DANS {e['hours_until']:.1f}H : {e['title']} ({e.get('time','?')} UTC)")
        for e in upcoming_24h[:4]:
            lines.append(f"  📅 Dans {e['hours_until']:.0f}h : {e['title']} ({e.get('time','?')} UTC)")

    # ── COT ──
    if cot and not cot.get("error"):
        lines.append(f"\n--- COT REPORT (semaine du {cot.get('report_date','?')}) ---")
        lines.append(f"Managed Money net: {cot.get('mm_net',0):+,} ({cot.get('mm_sentiment','?')})")
        if cot.get("mm_net_change") is not None:
            lines.append(f"Variation hebdo MM: {cot.get('mm_net_change',0):+,}")
        lines.append(f"Spéculateurs non-commerciaux net: {cot.get('noncomm_net',0):+,}")
        if cot.get("contrarian_note"):
            lines.append(f"⚠️ {cot['contrarian_note']}")

    # ── Fear & Greed ──
    if fg:
        lines.append(f"\n--- SENTIMENT DE MARCHÉ ---")
        lines.append(f"Fear & Greed: {fg.get('value',0)}/100 ({fg.get('label','?')}) → {fg.get('gold_note','')}")

    # ── News & Calendar ──
    calendar = [n for n in news if n.get("is_calendar")]
    regular_news = [n for n in news if not n.get("is_calendar")]

    if calendar:
        lines.append("\n=== CALENDRIER ÉCONOMIQUE (cette semaine) ===")
        for ev in calendar[:5]:
            lines.append(f"📅 {ev.get('title','').replace('[CALENDRIER] ','')} — {ev.get('summary','')}")

    if regular_news:
        lines.append("\n=== ACTUALITÉS RÉCENTES ===")
        impact_icon = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
        for n in regular_news[:6]:
            icon = impact_icon.get(n.get("impact",""), "⚪")
            lines.append(f"{icon} [{n.get('impact','?')}] {n.get('title','')} ({n.get('source','')})")
            if n.get("summary"):
                lines.append(f"   {n.get('summary','')[:200]}")

    # ── Composite Score ──
    composite = ctx.get("composite", {})
    new_sources = ctx.get("new_sources", {})
    if composite:
        score = composite.get("score", 50)
        direction = composite.get("direction", "?")
        label = composite.get("label", "")
        lines.append(f"\n=== SCORE COMPOSITE (0-100) ===")
        lines.append(f"Score global: {score}/100 → {direction} — {label}")
        lines.append(f"(>60 = BUY, <40 = SELL, 40-60 = signal faible)")
        cats = composite.get("categories", {})
        for cat, data in cats.items():
            lines.append(f"  {cat}: {data.get('score')}/{data.get('max')} ({data.get('direction')})")

    # ── SMC/ICT Strategy Engine ──
    if mtf:
        lines.append("\n=== STRATÉGIE SMC/ICT — ANALYSE MULTI-TIMEFRAME ===")
        bias_4h = mtf.get("bias_4h", "NEUTRAL")
        bias_1d = mtf.get("bias_1d", "NEUTRAL")
        lines.append(f"Biais primaire (4H) : {bias_4h} | Biais long terme (1J) : {bias_1d}")
        lines.append(f"Alignement MTF : {mtf.get('aligned_str', 'N/A')}")
        biases = mtf.get("biases", {})
        for tf, b in biases.items():
            lines.append(f"  {tf:3s}: {b.get('bias','?'):8s}  ({b.get('detail','')})")

    if kill_zone:
        kz_name = kill_zone.get("name", "?")
        kz_active = kill_zone.get("active", False)
        kz_tradeable = kill_zone.get("tradeable", False)
        status = "✅ ACTIVE" if kz_active and kz_tradeable else ("⚠️ EVITER" if kz_active else "❌ Hors session")
        lines.append(f"\nSESSION ACTIVE : {kz_name} — {status}")

    if liquidity_sweep.get("detected"):
        lines.append(f"\nLIQUIDITY SWEEP : {liquidity_sweep.get('desc', '')}")
        lines.append(f"  → Signal attendu : {liquidity_sweep.get('direction', '?')}")
    else:
        lines.append(f"\nLIQUIDITY SWEEP : Aucun sweep récent détecté")

    if wyckoff:
        lines.append(f"\nPHASE WYCKOFF : {wyckoff.get('phase', '?')}")
        lines.append(f"  {wyckoff.get('desc', '')}")

    if rsi_divergence.get("detected"):
        lines.append(f"\nDIVERGENCE RSI : {rsi_divergence.get('desc', '')}")
    else:
        lines.append(f"\nDIVERGENCE RSI : Aucune divergence détectée")

    if trade_score_obj:
        score = trade_score_obj.get("score", 0)
        label = trade_score_obj.get("label", "")
        tradeable = trade_score_obj.get("tradeable", False)
        lines.append(f"\nSCORE TRADE SMC/ICT : {score}/100 — {label}")
        lines.append(f"Trade actionnable : {'✅ OUI (score ≥ 70)' if tradeable else '❌ NON (score < 70)'}")
        for d in trade_score_obj.get("details", []):
            lines.append(f"  {d}")

    # ── EMA200 Multi-Timeframe Filter ──
    ema200_filter = ctx.get("ema200_filter", {})
    e4h = ema200_filter.get("ema200_4h")
    e1h = ema200_filter.get("ema200_1h")
    a4h = ema200_filter.get("above_4h")
    a1h = ema200_filter.get("above_1h")
    if e4h or e1h:
        lines.append(f"\n--- FILTRE EMA200 MULTI-TIMEFRAME ---")
        if e4h:
            lines.append(f"EMA200 4H : ${e4h:.2f} → {'HAUSSIER ✅' if a4h else 'BAISSIER ❌'} (prix {'au-dessus' if a4h else 'en-dessous'})")
        if e1h:
            lines.append(f"EMA200 1H : ${e1h:.2f} → {'HAUSSIER ✅' if a1h else 'BAISSIER ❌'} (prix {'au-dessus' if a1h else 'en-dessous'})")
        if a4h is not None and a1h is not None:
            if a4h == a1h:
                lines.append(f"✅ Confirmation EMA200 : les 2 TF d'accord → {'BUY' if a4h else 'SELL'}")
            else:
                lines.append(f"⚠️ Divergence EMA200 : 4H et 1H ne s'accordent pas — signal affaibli")

    # ── Market Regime ──
    if regime:
        r_label = regime.get("label", "?")
        r_emoji = regime.get("emoji", "")
        r_bias  = regime.get("gold_bias", "NEUTRAL")
        r_agg   = regime.get("aggression", 1.0)
        lines.append(f"\n=== RÉGIME DE MARCHÉ : {r_emoji} {r_label} ===")
        lines.append(f"Biais or: {r_bias} | Agressivité suggérée: ×{r_agg}")
        lines.append(f"{regime.get('description', '')}")
        for s in regime.get("signals", [])[:4]:
            lines.append(f"  • {s}")

    lines.append("\n⚡ RÈGLE ABSOLUE SMC/ICT :")
    lines.append("  1. Ne trader QUE dans le sens du biais 4H")
    lines.append("  2. Score trade ≥ 70 obligatoire pour BUY/SELL")
    lines.append("  3. Kill zone active (London Open 8h-10h UTC ou NY Open 13h30-15h30 UTC)")
    lines.append("  4. Si score < 70 → direction ATTENDRE même si confluence technique élevée")

    # ── New Intelligence Sources ──
    corr = new_sources.get("correlations", {})
    if corr:
        lines.append("\n--- CORRÉLATIONS 30J (vs GC=F) ---")
        sym_labels = {"^GSPC": "S&P500", "BTC-USD": "BTC", "CL=F": "WTI", "^VIX": "VIX", "TLT": "TLT", "DX-Y.NYB": "DXY"}
        for sym, d in corr.items():
            label = sym_labels.get(sym, sym)
            lines.append(f"  {label}: corr={d.get('correlation_30d',0):+.3f} → {d.get('signal','?')}")

    etf = new_sources.get("etf_flows", {})
    if etf:
        lines.append("\n--- FLUX ETF OR ---")
        for ticker, d in etf.items():
            lines.append(f"  {ticker}: {d.get('price_change_pct',0):+.2f}% vol×{d.get('volume_vs_avg',1):.1f} → {d.get('signal','?')}")

    opts = new_sources.get("options", {})
    if opts:
        lines.append(f"\n--- OPTIONS GLD P/C RATIO ---")
        lines.append(f"  P/C={opts.get('put_call_ratio','?')} → {opts.get('signal','?')} ({opts.get('note','')})")

    yields = new_sources.get("yields", {})
    if yields:
        lines.append(f"\n--- COURBE DES TAUX TREASURY ---")
        lines.append(f"  2Y={yields.get('y2','?')}% | 10Y={yields.get('y10','?')}% | Spread 2s10s={yields.get('spread_2_10',0):+.3f}%")
        lines.append(f"  Inversion: {'OUI → refuge or' if yields.get('inverted') else 'NON'} → {yields.get('signal','?')}")

    fed = new_sources.get("fed_nlp", {})
    if fed:
        lines.append(f"\n--- FED DISCOURS NLP ---")
        lines.append(f"  Score: {fed.get('score',0):+d}/±5 | Biais: {fed.get('bias','?')} → {fed.get('gold_signal','?')} pour l'or")
        if fed.get("summary"):
            lines.append(f"  Résumé: {fed['summary']}")

    # ── Trade learning ──
    if past_trades:
        wins   = [t for t in past_trades if t["status"] == "WIN"]
        losses = [t for t in past_trades if t["status"] == "LOSS"]
        wr     = round(len(wins) / len(past_trades) * 100)

        lines.append(f"\n=== APPRENTISSAGE — HISTORIQUE TRADES ({len(past_trades)} récents) ===")
        lines.append(f"Bilan : {len(wins)} WIN / {len(losses)} LOSS — Win rate {wr}%")

        buy_trades  = [t for t in past_trades if t.get("direction") == "BUY"]
        sell_trades = [t for t in past_trades if t.get("direction") == "SELL"]
        buy_wr = sell_wr = None
        if buy_trades:
            buy_wr = round(len([t for t in buy_trades  if t["status"] == "WIN"]) / len(buy_trades)  * 100)
            lines.append(f"Win rate BUY  : {buy_wr}% ({len(buy_trades)} trades)")
        if sell_trades:
            sell_wr = round(len([t for t in sell_trades if t["status"] == "WIN"]) / len(sell_trades) * 100)
            lines.append(f"Win rate SELL : {sell_wr}% ({len(sell_trades)} trades)")

        # Individual last 10 trades
        lines.append("\nDerniers trades :")
        for t in past_trades[:10]:
            ep      = t.get("entry_price")
            xp      = t.get("exit_price")
            pl      = t.get("profit_eur") or 0
            rsi     = t.get("rsi_at_entry")
            trend   = t.get("trend_at_entry") or "?"
            pl_str  = f"+€{pl:.0f}" if pl >= 0 else f"-€{abs(pl):.0f}"
            ep_str  = f"${ep:.2f}" if ep else "?"
            xp_str  = f"${xp:.2f}" if xp else "?"
            rsi_str = f" RSI={rsi:.0f}" if rsi else ""
            lines.append(f"  {t.get('status','?'):4s} {t.get('direction','?'):4s} {ep_str}→{xp_str} {pl_str}{rsi_str} [{trend}]")

        # RSI range analysis
        win_rsi  = [t["rsi_at_entry"] for t in wins   if t.get("rsi_at_entry")]
        loss_rsi = [t["rsi_at_entry"] for t in losses if t.get("rsi_at_entry")]
        if win_rsi:
            avg_win_rsi  = round(sum(win_rsi) / len(win_rsi))
            rsi_ok = len([r for r in win_rsi if 40 <= r <= 60])
            lines.append(f"RSI moyen des WIN  : {avg_win_rsi} ({rsi_ok}/{len(win_rsi)} entre 40-60)")
        if loss_rsi:
            avg_loss_rsi = round(sum(loss_rsi) / len(loss_rsi))
            rsi_ext = len([r for r in loss_rsi if r < 30 or r > 70])
            lines.append(f"RSI moyen des LOSS : {avg_loss_rsi} ({rsi_ext}/{len(loss_rsi)} en zone extrême)")

        # EMA alignment at win vs loss
        win_trend = [t.get("trend_at_entry") for t in wins if t.get("trend_at_entry")]
        if win_trend:
            bull_w = win_trend.count("BULLISH")
            lines.append(f"EMA alignment WIN : {bull_w}/{len(win_trend)} BULLISH, {len(win_trend)-bull_w}/{len(win_trend)} BEARISH")

        # Consecutive losses streak (recent, same direction)
        consec_loss = 0
        consec_dir  = None
        for t in past_trades:
            if t["status"] == "LOSS":
                if consec_dir is None:
                    consec_dir = t.get("direction")
                if t.get("direction") == consec_dir:
                    consec_loss += 1
                else:
                    break
            else:
                break

        # Natural language summary for Claude
        notes = []
        if consec_loss >= 2:
            notes.append(f"{consec_loss} LOSS consécutifs en {consec_dir} — éviter {consec_dir}")
        if buy_wr is not None and sell_wr is not None:
            if buy_wr > sell_wr + 20:
                notes.append(f"BUY plus performant ({buy_wr}% vs {sell_wr}%)")
            elif sell_wr > buy_wr + 20:
                notes.append(f"SELL plus performant ({sell_wr}% vs {buy_wr}%)")
        if win_rsi and len([r for r in win_rsi if 40 <= r <= 60]) / len(win_rsi) > 0.6:
            notes.append("WIN arrivent majoritairement avec RSI 40-60")
        if loss_rsi and len([r for r in loss_rsi if r < 30 or r > 70]) / len(loss_rsi) > 0.5:
            notes.append("LOSS surviennent souvent en zone RSI extrême (<30 ou >70)")

        if notes:
            lines.append("⚡ ADAPTATION : " + " | ".join(notes))
        else:
            lines.append(f"→ Aucun biais marqué sur les {len(past_trades)} derniers trades")

    return "\n".join(lines)
