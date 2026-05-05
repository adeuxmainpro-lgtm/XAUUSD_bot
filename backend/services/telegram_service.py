"""
Telegram alert service for strong trading signals.
Rate-limited to 1 alert per 4 hours to prevent spam.
"""
import httpx
import logging
from datetime import datetime, timezone, timedelta
from backend.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = logging.getLogger(__name__)

_COOLDOWN_HOURS = 4
_last_alert_sent: datetime | None = None
_last_bankroll_alert: dict = {}


async def _send_text(text: str) -> bool:
    """Low-level: send any text to Telegram."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
            )
            r.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        return False


async def send_weekly_ml_report() -> bool:
    """Send the weekly ML performance report to Telegram."""
    try:
        from backend.services.ml_engine import build_weekly_report
        text = build_weekly_report()
        sent = await _send_text(text)
        if sent:
            logger.info("Telegram weekly ML report sent")
        return sent
    except Exception as e:
        logger.error(f"send_weekly_ml_report error: {e}")
        return False


async def check_bankroll_alerts(bankroll: dict) -> None:
    """Fire a Telegram alert when bankroll crosses -10% (warning) or +10% (celebration)."""
    global _last_bankroll_alert
    now     = datetime.now(timezone.utc)
    initial = bankroll.get("initial", 1000)
    current = bankroll.get("current", initial)
    pct     = bankroll.get("pct", 0)

    if pct <= -10:
        last = _last_bankroll_alert.get("warning")
        if last is None or (now - last) > timedelta(hours=6):
            text = (
                f"⚠️ *ALERTE BANKROLL*\n"
                f"Bankroll actuelle : *{current:.2f}€* ({pct:+.1f}%)\n"
                f"Bankroll initiale : {initial:.2f}€\n"
                f"Vous avez perdu plus de 10% — réduisez le lot size."
            )
            if await _send_text(text):
                _last_bankroll_alert["warning"] = now

    elif pct >= 10:
        last = _last_bankroll_alert.get("celebration")
        if last is None or (now - last) > timedelta(hours=12):
            text = (
                f"🎉 *BANKROLL EN HAUSSE !*\n"
                f"Bankroll actuelle : *{current:.2f}€* ({pct:+.1f}%)\n"
                f"Bankroll initiale : {initial:.2f}€\n"
                f"Excellent travail !"
            )
            if await _send_text(text):
                _last_bankroll_alert["celebration"] = now


async def send_strong_signal(direction: str, confluence_score: int, price: float | None) -> bool:
    """Send a Telegram alert for a STRONG signal. Returns True if sent."""
    global _last_alert_sent

    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.debug("Telegram not configured — skipping alert")
        return False

    now = datetime.now(timezone.utc)
    if _last_alert_sent is not None:
        elapsed = now - _last_alert_sent
        if elapsed < timedelta(hours=_COOLDOWN_HOURS):
            remaining_min = int((_COOLDOWN_HOURS * 3600 - elapsed.total_seconds()) / 60)
            logger.info(f"Telegram cooldown active — {remaining_min}min restantes")
            return False

    price_str = f"${price:.2f}" if price else "N/A"
    text = (
        f"⚡ *SIGNAL FORT détecté*\n"
        f"📈 Direction : *{direction}* XAUUSD\n"
        f"📊 Confluence : *{confluence_score}%*\n"
        f"💰 Prix : {price_str}\n"
        f"🕐 {now.strftime('%H:%M UTC')}\n"
        f"_XAUUSD Bot — usage éducatif uniquement_"
    )

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "Markdown"},
            )
            r.raise_for_status()
        _last_alert_sent = now
        logger.info(f"Telegram STRONG signal sent: {direction} confluence={confluence_score}%")
        return True
    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        return False
