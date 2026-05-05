import logging
from datetime import datetime, date, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from backend.config import (
    ANALYSIS_INTERVAL_MIN,
    PRICE_REFRESH_INTERVAL_MIN,
    NEWS_REFRESH_INTERVAL_MIN,
    VOLATILITY_ALERT_THRESHOLD,
    TELEGRAM_CHAT_ID,
)

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()
_telegram_app = None

# ── Smart notification state ───────────────────────────────────────────────
_last_regime: str = ""
_daily_alert_date: date | None = None
_daily_alert_count: int = 0
_MAX_ALERTS_PER_DAY = 5


def set_telegram_app(app):
    global _telegram_app
    _telegram_app = app


# ─────────────────────────────────────────────────────────────────────────────
# TELEGRAM SEND
# ─────────────────────────────────────────────────────────────────────────────

async def _send_telegram_alert(text: str, enforce_limit: bool = False) -> bool:
    """Send a Telegram message. If enforce_limit=True, respects daily cap."""
    global _daily_alert_date, _daily_alert_count

    if not _telegram_app or not TELEGRAM_CHAT_ID:
        return False

    if enforce_limit:
        today = date.today()
        if _daily_alert_date != today:
            _daily_alert_date  = today
            _daily_alert_count = 0
        if _daily_alert_count >= _MAX_ALERTS_PER_DAY:
            logger.info("Daily alert cap reached — skipping Telegram notification")
            return False
        _daily_alert_count += 1

    try:
        await _telegram_app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="Markdown",
        )
        return True
    except Exception as e:
        logger.error(f"Telegram alert error: {e}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULED JOBS
# ─────────────────────────────────────────────────────────────────────────────

async def _refresh_price():
    try:
        from backend.services.market_data import get_full_market_data
        from backend.database import save_market_snapshot
        data = await get_full_market_data()
        if data:
            save_market_snapshot(data)
            logger.info(f"Price refreshed: ${data.get('price', 'N/A')}")
            atr_pct = data.get("atr_pct", 0) or 0
            if atr_pct > VOLATILITY_ALERT_THRESHOLD:
                await _send_telegram_alert(
                    f"⚠️ *ALERTE VOLATILITÉ XAUUSD*\n"
                    f"ATR: {atr_pct:.3f}% (seuil: {VOLATILITY_ALERT_THRESHOLD}%)\n"
                    f"Prix: ${data.get('price', 'N/A')}",
                    enforce_limit=True,
                )
            await _check_smart_notifications(data)
    except Exception as e:
        logger.error(f"_refresh_price error: {e}")


async def _run_ai_analysis():
    try:
        from backend.services.ai_analyst import run_analysis
        result = await run_analysis()
        direction  = result.get("direction", "WAIT")
        confidence = result.get("confidence", 0)
        confluence = result.get("confluence", {})
        conf_score = confluence.get("score", 0) if confluence else 0
        logger.info(f"Analysis done: {direction} ({confidence}%) confluence={conf_score}%")

        if direction in ("BUY", "SELL") and confidence >= 65:
            entry = result.get("entry", "N/A")
            sl    = result.get("stop_loss", "N/A")
            tp1   = result.get("take_profit_1", "N/A")
            rr    = result.get("risk_reward", "N/A")
            emoji = "🟢" if direction == "BUY" else "🔴"

            patterns_line = ""
            if result.get("detected_patterns"):
                patterns_line = f"\nPatterns: {result['detected_patterns']}"

            trade_score = result.get("trade_score", 0)
            score_line  = f"\nScore SMC/ICT : {trade_score}/100" if trade_score else ""

            await _send_telegram_alert(
                f"{emoji} *SIGNAL XAUUSD : {direction}*\n"
                f"Confiance : {confidence}% | Confluence : {conf_score}%"
                f"{score_line}\n"
                f"Entrée : ${entry}\n"
                f"Stop Loss : ${sl}\n"
                f"TP1 : ${tp1}\n"
                f"R/R : {rr}"
                f"{patterns_line}\n\n"
                f"_{result.get('market_summary', '')}_"
            )
    except Exception as e:
        logger.error(f"_run_ai_analysis error: {e}")


async def _refresh_news():
    try:
        from backend.services.news_service import fetch_gold_news
        from backend.database import save_news
        result  = await fetch_gold_news()
        articles = result["articles"]
        save_news(articles)
        stats   = result.get("stats", {})
        logger.info(
            f"News refreshed: {len(articles)} articles "
            f"(RSS {stats.get('rss_kept','?')}/{stats.get('rss_seen','?')} filtered)"
        )
    except Exception as e:
        logger.error(f"_refresh_news error: {e}")


async def _check_quota():
    """Alert via Telegram if Twelve Data API quota < 100 remaining."""
    try:
        from backend.services.market_data import fetch_api_quota
        quota = await fetch_api_quota()
        remaining = quota.get("remaining")
        if remaining is not None and remaining < 100:
            await _send_telegram_alert(
                f"⚠️ *QUOTA API TWELVE DATA FAIBLE*\n"
                f"Requêtes restantes : *{remaining}* / {quota.get('plan_daily_limit', '?')}\n"
                f"💡 Bascule automatique sur Yahoo Finance activée",
            )
            logger.warning(f"Twelve Data quota low: {remaining} remaining")
    except Exception as e:
        logger.error(f"_check_quota error: {e}")


async def _refresh_cot():
    try:
        from backend.services.cot_service import fetch_cot_gold
        from backend.database import save_cot
        data = await fetch_cot_gold()
        if data and not data.get("error"):
            save_cot(data)
            logger.info(f"COT refreshed: MM net={data.get('mm_net','?')}")
    except Exception as e:
        logger.error(f"_refresh_cot error: {e}")


async def _refresh_sentiment():
    try:
        from backend.services.sentiment_service import fetch_fear_greed
        from backend.database import save_sentiment
        fg = await fetch_fear_greed()
        if fg:
            save_sentiment(fg)
            logger.info(f"Sentiment refreshed: F&G={fg.get('value','?')} ({fg.get('label','?')})")
    except Exception as e:
        logger.error(f"_refresh_sentiment error: {e}")


async def _weekly_ml_report():
    try:
        from backend.services.telegram_service import send_weekly_ml_report
        await send_weekly_ml_report()
    except Exception as e:
        logger.error(f"_weekly_ml_report error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# DAILY BRIEFING  (8h00 UTC)
# ─────────────────────────────────────────────────────────────────────────────

async def _daily_briefing():
    """Send a comprehensive daily XAUUSD briefing at 8h UTC."""
    try:
        from backend.services.market_data import get_full_market_data
        from backend.services.smc_engine import analyze_mtf, detect_kill_zone
        from backend.services.analysis_engine import build_market_context

        now = datetime.now(timezone.utc)
        logger.info("Generating daily briefing…")

        data = await get_full_market_data()
        if not data:
            logger.warning("Daily briefing: no market data")
            return

        price      = data.get("price", 0)
        atr        = data.get("atr", 0) or 0
        supports   = data.get("supports", [])
        resistances = data.get("resistances", [])
        rsi        = data.get("rsi")

        # MTF analysis
        mtf = analyze_mtf(
            data.get("ohlc_15m", []),
            data.get("ohlc_1h",  []),
            data.get("ohlc_4h",  []),
            data.get("ohlc_1d",  []),
        )
        primary_bias  = mtf.get("primary_bias", "NEUTRE")
        aligned_str   = mtf.get("aligned_str", "?")
        bias_emoji    = "🟢" if primary_bias == "BULLISH" else ("🔴" if primary_bias == "BEARISH" else "⚪")

        # Regime (best-effort from last context)
        regime_label = "Inconnu"
        regime_emoji = "⚪"
        try:
            ctx = await build_market_context(data)
            regime = ctx.get("regime", {})
            regime_label = regime.get("label", "Inconnu")
            regime_emoji = regime.get("emoji", "⚪")
        except Exception:
            pass

        # Key levels
        res_str = " / ".join([f"${r}" for r in sorted(resistances, reverse=True)[:3]]) or "N/A"
        sup_str = " / ".join([f"${s}" for s in sorted(supports)[:3]]) or "N/A"

        # OB levels (rough estimate: ±1.5×ATR from price)
        ob_bull = round(price - atr * 1.5, 2) if atr else "N/A"
        ob_bear = round(price + atr * 1.5, 2) if atr else "N/A"

        # Sessions today
        london_open  = "08h00 - 10h00 UTC → meilleure fenêtre"
        ny_open      = "13h30 - 15h30 UTC → deuxième fenêtre"
        london_close = "16h00 - 17h00 UTC → clôture London"

        # Macro keywords from today's news
        macro_line = await _get_macro_events_today()

        # Attention points
        attention: list[str] = []
        if rsi is not None:
            if rsi > 70:
                attention.append(f"⚠️ RSI surachat ({rsi:.0f}) — éviter les BUY")
            elif rsi < 30:
                attention.append(f"⚠️ RSI survente ({rsi:.0f}) — éviter les SELL")
        if atr and atr / price * 100 > 0.8:
            attention.append(f"⚠️ Forte volatilité (ATR {atr:.1f}$) — SL plus large")
        if mtf.get("aligned_count", 0) >= 3:
            attention.append(f"✅ {aligned_str} — forte conviction directionnelle")
        if not attention:
            attention.append("📊 Pas d'alerte particulière — trader avec discipline")

        # Strategy of the day
        if primary_bias == "BULLISH" and mtf.get("aligned_count", 0) >= 3:
            strategy = f"Biais HAUSSIER confirmé sur {aligned_str}. Privilégier les entrées BUY sur les pullbacks en Kill Zone (London/NY)."
        elif primary_bias == "BEARISH" and mtf.get("aligned_count", 0) >= 3:
            strategy = f"Biais BAISSIER confirmé sur {aligned_str}. Privilégier les entrées SELL sur les rebonds en Kill Zone (London/NY)."
        else:
            strategy = "Biais mixte — attendre confirmation d'une direction claire avant d'entrer. Pas de trade en session asiatique."

        msg = (
            f"🌅 *BRIEFING XAUUSD — {now.strftime('%d/%m/%Y')}*\n\n"
            f"💰 *Prix actuel :* ${price:,.2f}\n"
            f"{regime_emoji} *Régime de marché :* {regime_label}\n"
            f"{bias_emoji} *Biais du jour :* {primary_bias} ({aligned_str})\n\n"
            f"📍 *Niveaux clés :*\n"
            f"  - Résistances : {res_str}\n"
            f"  - Supports : {sup_str}\n"
            f"  - OB haussier : ${ob_bull}\n"
            f"  - OB baissier : ${ob_bear}\n\n"
            f"⏰ *Sessions aujourd'hui :*\n"
            f"  - {london_open}\n"
            f"  - {ny_open}\n"
            f"  - {london_close}\n\n"
        )

        if macro_line:
            msg += f"📰 *Événements macro :*\n{macro_line}\n\n"

        msg += "⚠️ *Points d'attention :*\n"
        for pt in attention[:3]:
            msg += f"  {pt}\n"

        msg += f"\n🎯 *Stratégie du jour :* {strategy}\n\n"
        msg += "_XAUUSD Bot · usage éducatif uniquement_"

        await _send_telegram_alert(msg)
        logger.info("Daily briefing sent")

    except Exception as e:
        logger.error(f"_daily_briefing error: {e}")


async def _get_macro_events_today() -> str:
    """Extract macro keywords from today's news headlines."""
    try:
        from backend.database import get_connection
        conn = get_connection()
        cur  = conn.cursor()
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        cur.execute(
            "SELECT title FROM news WHERE published_at LIKE ? AND sentiment IN ('negative','neutral') LIMIT 5",
            (f"{today}%",)
        )
        rows = cur.fetchall()
        conn.close()

        _MACRO_KW = ["CPI", "NFP", "FOMC", "Fed", "inflation", "unemployment",
                     "GDP", "rate", "taux", "emploi", "croissance", "BCE", "ECB",
                     "PPI", "PMI", "ISM", "payroll", "chômage"]

        events: list[str] = []
        for row in rows:
            title = row[0] or ""
            if any(kw.lower() in title.lower() for kw in _MACRO_KW):
                events.append(f"  - {title[:80]}")

        return "\n".join(events[:3]) if events else ""
    except Exception:
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# SMART NOTIFICATIONS
# ─────────────────────────────────────────────────────────────────────────────

async def _check_smart_notifications(market_data: dict):
    """
    Check and fire smart Telegram alerts:
      - Regime change
      - VIX > 25
      - MTF 4/4 aligned
      - RSI extreme (< 20 or > 80) — strong setup opportunity
    Max _MAX_ALERTS_PER_DAY alerts per day.
    """
    global _last_regime

    try:
        from backend.services.smc_engine import analyze_mtf
        from backend.services.analysis_engine import build_market_context

        ctx    = await build_market_context(market_data)
        regime = ctx.get("regime", {})
        mtf    = ctx.get("mtf", {})

        # ── Regime change ─────────────────────────────────────────────────
        current_regime = regime.get("regime", "")
        if current_regime and current_regime != _last_regime and _last_regime:
            old_label = _last_regime
            new_label = regime.get("label", current_regime)
            emoji     = regime.get("emoji", "⚪")
            gold_bias = regime.get("gold_bias", "NEUTRAL")
            bias_txt  = {"BULLISH": "or haussier attendu", "BEARISH": "pression sur or", "NEUTRAL": "or neutre"}.get(gold_bias, "")
            await _send_telegram_alert(
                f"{emoji} *CHANGEMENT DE RÉGIME XAUUSD*\n"
                f"Ancien : {old_label} → Nouveau : *{new_label}*\n"
                f"📊 {regime.get('description', '')}\n"
                f"💡 Implication : {bias_txt}",
                enforce_limit=True,
            )
            logger.info(f"Regime change: {old_label} → {new_label}")
        _last_regime = current_regime

        # ── MTF 4/4 aligned ───────────────────────────────────────────────
        aligned = mtf.get("aligned_count", 0)
        primary = mtf.get("primary_bias", "NEUTRAL")
        if aligned >= 4 and primary != "NEUTRAL":
            emoji = "🟢" if primary == "BULLISH" else "🔴"
            await _send_telegram_alert(
                f"{emoji} *ALIGNEMENT MTF 4/4 XAUUSD*\n"
                f"Tous les timeframes (1D/4H/1H/15M) sont *{primary}*\n"
                f"💡 Signal de haute probabilité — attendre Kill Zone (London/NY)",
                enforce_limit=True,
            )

        # ── RSI extreme opportunity ────────────────────────────────────────
        rsi = market_data.get("rsi")
        price = market_data.get("price", 0)
        if rsi is not None:
            if rsi < 20:
                await _send_telegram_alert(
                    f"📉 *RSI EXTRÊME — SURVENTE XAUUSD*\n"
                    f"RSI : *{rsi:.1f}* (< 20) — territoire de survente extrême\n"
                    f"Prix : ${price:,.2f}\n"
                    f"💡 Rebond haussier possible — attendre confirmation",
                    enforce_limit=True,
                )
            elif rsi > 80:
                await _send_telegram_alert(
                    f"📈 *RSI EXTRÊME — SURACHAT XAUUSD*\n"
                    f"RSI : *{rsi:.1f}* (> 80) — territoire de surachat extrême\n"
                    f"Prix : ${price:,.2f}\n"
                    f"💡 Correction baissière possible — attendre confirmation",
                    enforce_limit=True,
                )

        # ── VIX spike (from correlations if available) ────────────────────
        try:
            new_src = ctx.get("new_sources", {})
            corr    = new_src.get("correlations", {}) if new_src else {}
            vix_val = corr.get("^VIX", {}).get("current")
            if vix_val and vix_val > 25:
                await _send_telegram_alert(
                    f"🚨 *VIX ÉLEVÉ — RISK-OFF SIGNAL*\n"
                    f"VIX : *{vix_val:.1f}* (> 25) — stress de marché détecté\n"
                    f"💡 Or = valeur refuge → biais HAUSSIER attendu",
                    enforce_limit=True,
                )
        except Exception:
            pass

    except Exception as e:
        logger.error(f"_check_smart_notifications error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SCHEDULER SETUP
# ─────────────────────────────────────────────────────────────────────────────

async def _monitor_trades():
    try:
        from backend.services.trade_monitor import check_open_trades
        await check_open_trades()
    except Exception as e:
        logger.error(f"_monitor_trades error: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# INTERACTIVE SIGNAL ALERT (8h05 + 14h00 UTC)
# ─────────────────────────────────────────────────────────────────────────────

async def _send_interactive_signal_alert():
    """
    Run a full analysis. If BUY/SELL with confluence ≥ 60%, send a formatted
    Telegram alert asking OUI/NON and persist it as a pending_signal in the DB.
    """
    if not _telegram_app or not TELEGRAM_CHAT_ID:
        return
    try:
        from backend.services.ai_analyst import run_analysis
        from backend.database import save_pending_signal

        logger.info("Interactive signal alert: running analysis…")
        result = await run_analysis()

        direction      = result.get("direction")
        confluence     = result.get("confluence_score", 0) or 0
        confidence     = result.get("confidence", 0) or 0
        entry          = result.get("entry")
        sl             = result.get("stop_loss")
        tp1            = result.get("take_profit_1")
        tp2            = result.get("take_profit_2")
        rr             = result.get("risk_reward")
        summary        = result.get("market_summary", "")
        signal_level   = result.get("signal_level", "WEAK")

        if direction not in ("BUY", "SELL") or confluence < 60 or not entry:
            logger.info(f"Interactive alert skipped: {direction} confluence={confluence}%")
            return

        emoji = "🟢" if direction == "BUY" else "🔴"
        justif = summary[:200] if summary else "Analyse en cours."

        msg = (
            f"⚡ *SIGNAL XAUUSD — {direction}*\n\n"
            f"📍 Entrée : ${entry:.2f}\n"
            f"🛑 Stop Loss : ${sl:.2f}\n"
            f"🎯 TP1 : ${tp1:.2f} | TP2 : ${tp2:.2f}\n"
            f"📊 R/R : 1:{rr} | Confiance : {confidence}%\n"
            f"📈 Confluence : {confluence}% ({signal_level})\n\n"
            f"💡 _{justif}_\n\n"
            f"Répondez *OUI* pour ouvrir ce trade dans votre journal\n"
            f"Répondez *NON* pour ignorer _(timeout 30min)_"
        )

        # Persist signal for the bot handler to read
        signal_payload = {
            "direction":     direction,
            "entry":         entry,
            "stop_loss":     sl,
            "take_profit_1": tp1,
            "take_profit_2": tp2,
            "risk_reward":   rr,
            "confluence_score": confluence,
            "confidence":    confidence,
            "signal_level":  signal_level,
            "market_summary": summary,
        }
        save_pending_signal(int(TELEGRAM_CHAT_ID), signal_payload, timeout_minutes=30)

        await _send_telegram_alert(msg)
        logger.info(f"Interactive signal sent: {direction} confluence={confluence}%")

    except Exception as e:
        logger.error(f"_send_interactive_signal_alert error: {e}")


def start_scheduler(telegram_app=None):
    if telegram_app:
        set_telegram_app(telegram_app)

    # Wire Telegram alert into trade monitor
    from backend.services.trade_monitor import set_alert_callback
    set_alert_callback(_send_telegram_alert)

    scheduler.add_job(
        _monitor_trades, IntervalTrigger(seconds=30),
        id="monitor_trades", replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        _refresh_price, IntervalTrigger(minutes=PRICE_REFRESH_INTERVAL_MIN),
        id="refresh_price", replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        _run_ai_analysis, IntervalTrigger(minutes=ANALYSIS_INTERVAL_MIN),
        id="ai_analysis", replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        _refresh_news, IntervalTrigger(minutes=NEWS_REFRESH_INTERVAL_MIN),
        id="refresh_news", replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        _refresh_cot, IntervalTrigger(hours=24),
        id="refresh_cot", replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        _refresh_sentiment, IntervalTrigger(hours=4),
        id="refresh_sentiment", replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        _weekly_ml_report, IntervalTrigger(weeks=1),
        id="weekly_ml_report", replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        _check_quota, IntervalTrigger(hours=1),
        id="check_quota", replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        _daily_briefing,
        CronTrigger(hour=8, minute=0, timezone="UTC"),
        id="daily_briefing", replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        _send_interactive_signal_alert,
        CronTrigger(hour=8, minute=5, timezone="UTC"),
        id="interactive_signal_morning", replace_existing=True, max_instances=1,
    )
    scheduler.add_job(
        _send_interactive_signal_alert,
        CronTrigger(hour=14, minute=0, timezone="UTC"),
        id="interactive_signal_afternoon", replace_existing=True, max_instances=1,
    )

    scheduler.start()
    logger.info("Scheduler started (monitor_trades/price/analysis/news/cot/sentiment/ml_report/daily_briefing/interactive_signals).")
