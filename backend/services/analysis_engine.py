import logging
import asyncio
from backend.services.market_data import get_full_market_data
from backend.services.macro_data import get_macro_context
from backend.services.pattern_service import detect_all_patterns
from backend.services.sentiment_service import fetch_fear_greed, compute_confluence
from backend.services.signal_engine import evaluate_signal
from backend.database import get_latest_news, get_latest_cot, get_latest_sentiment, get_closed_trades_for_learning

logger = logging.getLogger(__name__)


async def build_market_context() -> dict:
    """Assemble full market context: price, macro, news, patterns, COT, sentiment, trade history."""
    market, macro, fg = await asyncio.gather(
        get_full_market_data(),
        get_macro_context(),
        fetch_fear_greed(),
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

    # Patterns from 1h OHLC
    patterns: dict = {}
    ohlc_1h = market.get("ohlc_1h", [])
    if ohlc_1h:
        try:
            patterns = detect_all_patterns(ohlc_1h)
        except Exception as e:
            logger.error(f"Pattern detection error: {e}")

    # COT from cache (refreshed by scheduler weekly)
    cot = get_latest_cot()

    # Confluence score
    confluence = compute_confluence(market, patterns, cot, fg if not isinstance(fg, Exception) else None)

    # Pre-AI signal evaluation (blocking conditions, signal level, watch list)
    signal_eval = evaluate_signal(market, macro if not isinstance(macro, Exception) else {}, confluence)

    # News from cache
    news = get_latest_news()

    # Trade learning data
    past_trades = get_closed_trades_for_learning(30)

    return {
        "market":      market,
        "macro":       macro,
        "news":        news,
        "patterns":    patterns,
        "cot":         cot,
        "fear_greed":  fg if not isinstance(fg, Exception) else None,
        "confluence":  confluence,
        "signal_eval": signal_eval,
        "past_trades": past_trades,
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
            "STRONG":   "✅ SIGNAL FORT — confluence ≥ 80%, trade recommandé avec confiance élevée",
            "MODERATE": "⚡ SIGNAL MODÉRÉ — confluence 70-79%, trade possible avec prudence",
            "WAIT":     "⏳ ATTENDRE — confluence < 70% ou conditions bloquantes, ne pas trader",
        }
        lines.append(lvl_map.get(lvl, ""))
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

    # ── Trade learning ──
    if past_trades:
        wins = [t for t in past_trades if t["status"] == "WIN"]
        losses = [t for t in past_trades if t["status"] == "LOSS"]
        lines.append(f"\n=== HISTORIQUE DE TES TRADES (apprentissage) ===")
        lines.append(f"Derniers {len(past_trades)} trades: {len(wins)} gagnants / {len(losses)} perdants")

        if past_trades:
            wr = round(len(wins)/len(past_trades)*100)
            lines.append(f"Win rate global: {wr}%")

        buy_trades = [t for t in past_trades if t["direction"] == "BUY"]
        sell_trades = [t for t in past_trades if t["direction"] == "SELL"]
        if buy_trades:
            buy_wr = round(len([t for t in buy_trades if t["status"]=="WIN"]) / len(buy_trades) * 100)
            lines.append(f"Win rate BUY: {buy_wr}% ({len(buy_trades)} trades)")
        if sell_trades:
            sell_wr = round(len([t for t in sell_trades if t["status"]=="WIN"]) / len(sell_trades) * 100)
            lines.append(f"Win rate SELL: {sell_wr}% ({len(sell_trades)} trades)")

        # RSI patterns at loss
        loss_rsi = [t["rsi_at_entry"] for t in losses if t.get("rsi_at_entry")]
        if loss_rsi:
            avg_loss_rsi = sum(loss_rsi) / len(loss_rsi)
            lines.append(f"RSI moyen lors des pertes: {avg_loss_rsi:.0f}")
            if avg_loss_rsi > 65:
                lines.append("⚠️ Historique: les trades en zone survendu/suracheté ont tendance à perdre")

        # Recent losses details
        for t in losses[:3]:
            lines.append(f"  Perte récente: {t['direction']} entrée ${t.get('entry_price','?')} RSI={t.get('rsi_at_entry','?')} tendance={t.get('trend_at_entry','?')}")

    return "\n".join(lines)
