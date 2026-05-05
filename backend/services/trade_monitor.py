"""
Automatic trade monitor — checks OPEN trades every 30 s.
Closes at TP1 (WIN) or SL (LOSS) when price crosses the level.
Fires a Telegram notification on close.
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Injected by scheduler after start-up
_send_alert = None

def set_alert_callback(fn):
    global _send_alert
    _send_alert = fn


def _calc_pnl(trade: dict, exit_price: float) -> float:
    """P&L in EUR for a standard lot.
    XAUUSD: 1 lot = 100 oz. lot_size default 0.01 → 1 oz equivalent.
    P&L = (exit - entry) × lot_size × 100   (for BUY)
    """
    entry    = trade.get("entry_price", 0) or 0
    lot      = trade.get("lot_size", 0.01) or 0.01
    direction = trade.get("direction", "BUY")
    if direction == "BUY":
        return round((exit_price - entry) * lot * 100, 2)
    else:
        return round((entry - exit_price) * lot * 100, 2)


async def check_open_trades():
    """Main monitoring coroutine — called every 30 s by the scheduler."""
    try:
        from backend.database import get_trades, update_trade
        from backend.services.market_data import fetch_current_price

        open_trades = [t for t in get_trades(limit=200) if t.get("status") == "OPEN"]
        if not open_trades:
            return

        price_data = await fetch_current_price()
        if not price_data:
            logger.warning("trade_monitor: could not fetch current price")
            return

        price = price_data.get("price")
        if not price:
            return

        for trade in open_trades:
            direction = trade.get("direction")
            entry     = trade.get("entry_price")
            tp1       = trade.get("take_profit_1")
            sl        = trade.get("stop_loss")

            if not entry:
                continue

            hit_tp1  = tp1 and (
                (direction == "BUY"  and price >= tp1) or
                (direction == "SELL" and price <= tp1)
            )
            hit_sl   = sl and (
                (direction == "BUY"  and price <= sl) or
                (direction == "SELL" and price >= sl)
            )

            if hit_tp1:
                pnl = _calc_pnl(trade, tp1)
                update_trade(trade["id"], {
                    "status":     "WIN",
                    "exit_price": tp1,
                    "profit_eur": pnl,
                })
                logger.info(f"Trade #{trade['id']} {direction}: TP1 hit at ${tp1:.2f} → WIN +{pnl}€")
                await _notify_win(trade, tp1, pnl)

            elif hit_sl:
                pnl = _calc_pnl(trade, sl)
                update_trade(trade["id"], {
                    "status":     "LOSS",
                    "exit_price": sl,
                    "profit_eur": pnl,
                })
                logger.info(f"Trade #{trade['id']} {direction}: SL hit at ${sl:.2f} → LOSS {pnl}€")
                await _notify_loss(trade, sl, pnl)

    except Exception as e:
        logger.error(f"check_open_trades error: {e}")


async def _notify_win(trade: dict, exit_price: float, pnl: float):
    if not _send_alert:
        return
    direction = trade.get("direction", "?")
    emoji = "🟢" if direction == "BUY" else "🔴"
    msg = (
        f"✅ *TRADE GAGNANT — TP1 TOUCHÉ !*\n"
        f"{emoji} {direction} XAUUSD\n"
        f"Entrée : ${trade.get('entry_price', '?'):.2f} → Sortie : ${exit_price:.2f}\n"
        f"Gain : *+{pnl}€*\n"
        f"_{datetime.utcnow().strftime('%d/%m %H:%M')} UTC_"
    )
    try:
        await _send_alert(msg)
    except Exception as e:
        logger.warning(f"Telegram WIN notification failed: {e}")


async def _notify_loss(trade: dict, exit_price: float, pnl: float):
    if not _send_alert:
        return
    direction = trade.get("direction", "?")
    emoji = "🟢" if direction == "BUY" else "🔴"
    msg = (
        f"❌ *TRADE PERDANT — SL TOUCHÉ !*\n"
        f"{emoji} {direction} XAUUSD\n"
        f"Entrée : ${trade.get('entry_price', '?'):.2f} → Sortie : ${exit_price:.2f}\n"
        f"Perte : *{pnl}€*\n"
        f"_{datetime.utcnow().strftime('%d/%m %H:%M')} UTC_"
    )
    try:
        await _send_alert(msg)
    except Exception as e:
        logger.warning(f"Telegram LOSS notification failed: {e}")
