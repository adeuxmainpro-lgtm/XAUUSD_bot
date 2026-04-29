import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
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


def set_telegram_app(app):
    global _telegram_app
    _telegram_app = app


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
                    f"Prix: ${data.get('price', 'N/A')}"
                )
    except Exception as e:
        logger.error(f"_refresh_price error: {e}")


async def _run_ai_analysis():
    try:
        from backend.services.ai_analyst import run_analysis
        result = await run_analysis()
        direction = result.get("direction", "WAIT")
        confidence = result.get("confidence", 0)
        confluence = result.get("confluence", {})
        conf_score = confluence.get("score", 0) if confluence else 0
        logger.info(f"Analysis done: {direction} ({confidence}%) confluence={conf_score}%")

        if direction in ("BUY", "SELL") and confidence >= 65:
            entry = result.get("entry", "N/A")
            sl = result.get("stop_loss", "N/A")
            tp1 = result.get("take_profit_1", "N/A")
            rr = result.get("risk_reward", "N/A")
            emoji = "🟢" if direction == "BUY" else "🔴"

            patterns_line = ""
            if result.get("detected_patterns"):
                patterns_line = f"\nPatterns: {result['detected_patterns']}"

            await _send_telegram_alert(
                f"{emoji} *SIGNAL XAUUSD : {direction}*\n"
                f"Confiance : {confidence}% | Confluence : {conf_score}%\n"
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
        articles = await fetch_gold_news()
        save_news(articles)
        logger.info(f"News refreshed: {len(articles)} articles")
    except Exception as e:
        logger.error(f"_refresh_news error: {e}")


async def _refresh_cot():
    """Refresh COT data (weekly, published every Friday by CFTC)."""
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


async def _send_telegram_alert(text: str):
    if not _telegram_app or not TELEGRAM_CHAT_ID:
        return
    try:
        await _telegram_app.bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=text,
            parse_mode="Markdown",
        )
    except Exception as e:
        logger.error(f"Telegram alert error: {e}")


def start_scheduler(telegram_app=None):
    if telegram_app:
        set_telegram_app(telegram_app)

    scheduler.add_job(_refresh_price, IntervalTrigger(minutes=PRICE_REFRESH_INTERVAL_MIN),
                      id="refresh_price", replace_existing=True, max_instances=1)
    scheduler.add_job(_run_ai_analysis, IntervalTrigger(minutes=ANALYSIS_INTERVAL_MIN),
                      id="ai_analysis", replace_existing=True, max_instances=1)
    scheduler.add_job(_refresh_news, IntervalTrigger(minutes=NEWS_REFRESH_INTERVAL_MIN),
                      id="refresh_news", replace_existing=True, max_instances=1)
    scheduler.add_job(_refresh_cot, IntervalTrigger(hours=24),
                      id="refresh_cot", replace_existing=True, max_instances=1)
    scheduler.add_job(_refresh_sentiment, IntervalTrigger(hours=4),
                      id="refresh_sentiment", replace_existing=True, max_instances=1)

    scheduler.start()
    logger.info("Scheduler started (price/analysis/news/cot/sentiment).")
