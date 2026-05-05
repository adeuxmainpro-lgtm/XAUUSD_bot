import sys
import os
import logging
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from telegram import Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

logger = logging.getLogger(__name__)

# Ensemble des chat_id ayant activé les alertes
_alert_subscribers: set[int] = set()


def _fmt_price(v):
    return f"${v:.2f}" if v is not None else "—"


def _fmt_pct(v):
    return f"{v}%" if v is not None else "—"


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "🏅 *XAUUSD Trading Bot* — Bienvenue !\n\n"
        "Commandes disponibles :\n"
        "• /analyse — Analyse complète XAUUSD\n"
        "• /patterns — Patterns techniques détectés\n"
        "• /sentiment — Fear & Greed + COT Report\n"
        "• /news — Actualités RSS + IA\n"
        "• /risk `[bankroll]` — Calcul position\n"
        "• /chat `[question]` — Question à l'IA\n"
        "• /alerte — Activer/désactiver les alertes\n"
        "• /status — Statut du marché\n\n"
        "_⚠️ Usage éducatif uniquement — pas de conseil financier_"
    )
    await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def cmd_analyse(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Analyse en cours... (~30s)", parse_mode=ParseMode.MARKDOWN)
    try:
        from backend.services.ai_analyst import run_analysis
        result = await run_analysis()
        text = _format_analysis(result)
        await msg.edit_text(text, parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"cmd_analyse error: {e}")
        await msg.edit_text(f"❌ Erreur lors de l'analyse : {e}")


def _format_analysis(r: dict) -> str:
    direction = r.get("direction", "?")
    emojis = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡", "WAIT": "🔵", "NO_TRADE": "⚫"}
    emoji = emojis.get(direction, "❓")

    lines = [
        f"{emoji} *XAUUSD : {direction}*",
        f"Confiance : {r.get('confidence', 0)}% | {r.get('timeframe', '—')}",
    ]

    if r.get("entry"):
        lines += [
            "",
            f"📍 Entrée : {_fmt_price(r.get('entry'))}",
            f"🛑 Stop Loss : {_fmt_price(r.get('stop_loss'))}",
            f"🎯 TP1 : {_fmt_price(r.get('take_profit_1'))}",
            f"🎯 TP2 : {_fmt_price(r.get('take_profit_2'))}",
            f"📊 R/R : 1:{r.get('risk_reward', '—')}",
        ]

    if r.get("dangerous_period"):
        lines += ["", f"⚠️ *Période risquée :* {r.get('dangerous_reason', '')}"]

    if r.get("market_summary"):
        lines += ["", f"_{r['market_summary']}_"]

    if r.get("main_arguments"):
        lines.append("\n✅ *Arguments :*")
        for arg in r["main_arguments"][:3]:
            lines.append(f"  • {arg}")

    if r.get("main_risks"):
        lines.append("\n⚠️ *Risques :*")
        for risk in r["main_risks"][:2]:
            lines.append(f"  • {risk}")

    return "\n".join(lines)


async def cmd_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📰 Récupération des actualités...")
    try:
        from backend.database import get_latest_news
        from backend.services.news_service import fetch_gold_news
        from backend.database import save_news

        articles = get_latest_news()
        if not articles:
            articles = await fetch_gold_news()
            save_news(articles)

        if not articles:
            await msg.edit_text("Aucune actualité disponible.")
            return

        impact_emoji = {"HIGH": "🔴", "MEDIUM": "🟡", "LOW": "🟢"}
        dir_emoji = {"BULLISH": "▲", "BEARISH": "▼", "NEUTRAL": "→"}

        lines = ["📰 *Actualités XAUUSD du jour :*\n"]
        for a in articles[:5]:
            ie = impact_emoji.get(a.get("impact", ""), "⚪")
            de = dir_emoji.get(a.get("direction", ""), "→")
            lines.append(f"{ie}{de} *{a.get('title', '')}*")
            if a.get("summary"):
                lines.append(f"_{a['summary'][:150]}..._" if len(a.get("summary", "")) > 150 else f"_{a.get('summary', '')}_")
            lines.append("")

        await msg.edit_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"cmd_news error: {e}")
        await msg.edit_text(f"❌ Erreur : {e}")


async def cmd_risk(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text(
            "Usage : `/risk [bankroll] [risque]`\n"
            "Exemples :\n"
            "  `/risk 1000` — bankroll 1000€, risque normal\n"
            "  `/risk 5000 low` — bankroll 5000€, risque faible\n"
            "  `/risk 2000 aggressive`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    try:
        bankroll = float(args[0])
        risk_level = args[1] if len(args) > 1 else "normal"
        if risk_level not in ("low", "normal", "aggressive"):
            risk_level = "normal"

        from backend.database import get_latest_analysis
        from backend.services.risk_manager import calculate_position

        analysis = get_latest_analysis()
        if not analysis or not analysis.get("entry"):
            await update.message.reply_text(
                "❌ Aucune analyse avec entrée disponible.\nLancez d'abord /analyse"
            )
            return

        entry = analysis["entry"]
        sl = analysis.get("stop_loss")
        if not sl:
            await update.message.reply_text("❌ Stop loss non défini dans l'analyse.")
            return

        result = calculate_position(
            bankroll_eur=bankroll,
            risk_level=risk_level,
            stop_loss_pips=abs(entry - sl),
            entry_price=entry,
            take_profit_1=analysis.get("take_profit_1"),
            take_profit_2=analysis.get("take_profit_2"),
        )

        text = (
            f"💰 *Calcul de position XAUUSD*\n\n"
            f"Bankroll : €{bankroll} | Risque : {risk_level} ({result['risk_pct']}%)\n"
            f"Capital risqué : *€{result['amount_risked_eur']}*\n\n"
            f"📊 *Taille de position :*\n"
            f"  • Standard : {result['lot_size_standard']} lots\n"
            f"  • Mini : {result['lot_size_mini']} lots\n"
            f"  • Micro : {result['lot_size_micro']} lots\n\n"
            f"📍 Entrée : ${entry:.2f}\n"
            f"🛑 Stop Loss : ${sl:.2f} (distance : ${abs(entry-sl):.2f})\n"
            f"⚖️ Levier : {result['leverage_used']}x\n"
            f"💸 Perte max : €{result['max_loss_eur']}\n"
        )
        if result.get("tp1_profit_eur"):
            text += f"🎯 Gain TP1 : €{result['tp1_profit_eur']}\n"
        if result.get("risk_reward"):
            text += f"📈 R/R : 1:{result['risk_reward']}"

        await update.message.reply_text(text, parse_mode=ParseMode.MARKDOWN)

    except ValueError:
        await update.message.reply_text("❌ Bankroll invalide. Exemple : `/risk 1000`", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"cmd_risk error: {e}")
        await update.message.reply_text(f"❌ Erreur : {e}")


async def cmd_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    question = " ".join(context.args) if context.args else ""
    if not question:
        await update.message.reply_text(
            "Usage : `/chat [votre question]`\n"
            "Exemple : `/chat Pourquoi tu recommandes d'acheter ?`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    msg = await update.message.reply_text("🤔 Analyse en cours...")
    try:
        from backend.services.ai_analyst import chat
        answer = await chat(question)
        # Telegram limite à 4096 caractères
        if len(answer) > 4000:
            answer = answer[:4000] + "...\n_(réponse tronquée)_"
        await msg.edit_text(f"🤖 {answer}", parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"cmd_chat error: {e}")
        await msg.edit_text(f"❌ Erreur : {e}")


async def cmd_alerte(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if chat_id in _alert_subscribers:
        _alert_subscribers.discard(chat_id)
        await update.message.reply_text("🔕 Alertes automatiques *désactivées*.", parse_mode=ParseMode.MARKDOWN)
    else:
        _alert_subscribers.add(chat_id)
        await update.message.reply_text(
            "🔔 Alertes automatiques *activées* !\n"
            "Vous recevrez les signaux BUY/SELL (confiance ≥ 65%) et les alertes de volatilité.",
            parse_mode=ParseMode.MARKDOWN,
        )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        from backend.database import get_latest_snapshot, get_latest_analysis
        snap = get_latest_snapshot()
        analysis = get_latest_analysis()

        lines = ["📊 *Statut XAUUSD*\n"]

        if snap:
            trend_emoji = {"BULLISH": "📈", "BEARISH": "📉", "NEUTRAL": "➡️"}.get(snap.get("trend_short"), "❓")
            lines += [
                f"💰 Prix : ${snap.get('price', 0):.2f}",
                f"📉 RSI : {snap.get('rsi', '—')}",
                f"{trend_emoji} Tendance CT : {snap.get('trend_short', '—')}",
                f"➡️ Tendance MT : {snap.get('trend_medium', '—')}",
                f"⚡ ATR% : {snap.get('atr', '—')}",
            ]
        else:
            lines.append("_Aucun snapshot disponible_")

        if analysis:
            dir_emoji = {"BUY": "🟢", "SELL": "🔴", "HOLD": "🟡", "WAIT": "🔵"}.get(analysis.get("direction"), "❓")
            lines += [
                "",
                f"🎯 *Dernière recommandation :* {dir_emoji} {analysis.get('direction', '—')}",
                f"Confiance : {analysis.get('confidence', 0)}%",
            ]

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        await update.message.reply_text(f"❌ Erreur : {e}")


async def cmd_patterns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Détection des patterns en cours...")
    try:
        from backend.services.market_data import fetch_ohlc
        from backend.services.pattern_service import detect_all_patterns

        ohlc = await fetch_ohlc("1h", 100)
        if not ohlc:
            await msg.edit_text("❌ Données OHLC indisponibles.")
            return

        p = detect_all_patterns(ohlc)
        cs = p.get("candlestick", {})
        chart = p.get("chart", [])
        smc = p.get("smc", {})
        ict = p.get("ict", {})

        lines = ["📊 *Patterns XAUUSD (1h)*\n"]

        if cs.get("bullish"):
            lines.append(f"🟢 *Chandeliers haussiers :* {', '.join(cs['bullish'])}")
        if cs.get("bearish"):
            lines.append(f"🔴 *Chandeliers baissiers :* {', '.join(cs['bearish'])}")

        if chart:
            lines.append("\n📈 *Patterns chartistes :*")
            for cp in chart:
                emoji = "🟢" if cp.get("type") == "bullish" else "🔴" if cp.get("type") == "bearish" else "🟡"
                lines.append(f"{emoji} {cp.get('name')} — {cp.get('desc','')}")

        bos = smc.get("bos", [])
        obs = smc.get("order_blocks", [])
        fvgs = smc.get("fvg", [])
        if bos or obs or fvgs:
            lines.append("\n🧠 *SMC :*")
            for b in bos: lines.append(f"• {b}")
            for ob in obs: lines.append(f"• {ob.get('desc','')}")
            for fvg in fvgs: lines.append(f"• FVG {fvg.get('type','')} ${fvg.get('bottom','')}–${fvg.get('top','')}")

        kz = ict.get("kill_zones", [])
        ote = ict.get("ote")
        if kz or ote:
            lines.append("\n⚡ *ICT :*")
            for kzone in kz: lines.append(f"• {kzone}")
            if ote: lines.append(f"• {ote.get('desc','')}")

        if len(lines) == 1:
            lines.append("_Aucun pattern significatif détecté._")

        await msg.edit_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"cmd_patterns error: {e}")
        await msg.edit_text(f"❌ Erreur : {e}")


async def cmd_sentiment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("📡 Récupération du sentiment...")
    try:
        from backend.services.sentiment_service import fetch_fear_greed
        from backend.database import get_latest_cot

        fg = await fetch_fear_greed()
        cot = get_latest_cot()

        lines = ["📡 *Sentiment de Marché XAUUSD*\n"]

        if fg:
            impl_emoji = {"BULLISH": "🟢", "BEARISH": "🔴", "NEUTRAL": "🟡"}.get(fg.get("gold_implication",""), "⚪")
            lines += [
                f"😱 *Fear & Greed Index :* {fg.get('value',0)}/100",
                f"Label : {fg.get('label','?')}",
                f"Impact or : {impl_emoji} {fg.get('gold_implication','?')}",
                f"_{fg.get('gold_note','')}_",
            ]

        if cot and not cot.get("error"):
            mm_emoji = "🟢" if cot.get("mm_sentiment") == "BULLISH" else "🔴"
            lines += [
                "",
                f"📋 *COT Report ({cot.get('report_date','?')}) :*",
                f"Managed Money net : {mm_emoji} {cot.get('mm_net',0):+,}",
            ]
            if cot.get("mm_net_change") is not None:
                lines.append(f"Variation hebdo : {cot.get('mm_net_change',0):+,}")
            if cot.get("contrarian_note"):
                lines.append(f"⚠️ {cot['contrarian_note']}")

        await msg.edit_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
    except Exception as e:
        logger.error(f"cmd_sentiment error: {e}")
        await msg.edit_text(f"❌ Erreur : {e}")


# ─────────────────────────────────────────────────────────────────────────────
# INTERACTIVE SIGNAL RESPONSE HANDLER  (OUI / NON)
# ─────────────────────────────────────────────────────────────────────────────

async def handle_signal_response(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Handles free-text OUI/NON replies to an interactive trading signal.
    Ignores all other text so normal conversation isn't disrupted.
    """
    if not update.message or not update.message.text:
        return

    chat_id = update.effective_chat.id
    text    = update.message.text.strip().lower()

    if text not in ("oui", "non", "yes", "no"):
        return  # not a signal response — ignore

    try:
        from backend.database import get_pending_signal, mark_signal_handled, save_trade

        pending = get_pending_signal(chat_id)

        if not pending:
            await update.message.reply_text(
                "ℹ️ Aucun signal en attente (expiré ou déjà traité).",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        signal_id = pending["id"]

        if text in ("oui", "yes"):
            # Create the trade in the journal
            today = datetime.utcnow().strftime("%Y-%m-%d")
            trade_data = {
                "trade_date":      today,
                "direction":       pending.get("direction", "BUY"),
                "entry_price":     pending.get("entry"),
                "stop_loss":       pending.get("stop_loss"),
                "take_profit_1":   pending.get("take_profit_1"),
                "take_profit_2":   pending.get("take_profit_2"),
                "status":          "OPEN",
                "profit_eur":      0,
                "lot_size":        0.01,
                "confluence_score": pending.get("confluence_score"),
                "notes":           f"Ouvert via alerte Telegram — confiance {pending.get('confidence',0)}%",
            }
            trade_id = save_trade(trade_data)
            mark_signal_handled(signal_id)

            direction = pending.get("direction", "?")
            entry     = pending.get("entry", 0)
            sl        = pending.get("stop_loss", 0)
            tp1       = pending.get("take_profit_1", 0)
            emoji     = "🟢" if direction == "BUY" else "🔴"

            await update.message.reply_text(
                f"✅ *Trade ouvert dans votre journal !*\n\n"
                f"{emoji} {direction} XAUUSD — Trade #{trade_id}\n"
                f"📍 Entrée : ${entry:.2f}\n"
                f"🛑 SL : ${sl:.2f} | 🎯 TP1 : ${tp1:.2f}\n\n"
                f"_Le suivi automatique vérifie le prix toutes les 30s._",
                parse_mode=ParseMode.MARKDOWN,
            )
            logger.info(f"Trade #{trade_id} created via Telegram OUI response (chat_id={chat_id})")

        else:  # non / no
            mark_signal_handled(signal_id)
            await update.message.reply_text(
                "⏭️ *Signal ignoré.*\nProchain signal à 14h00 UTC.",
                parse_mode=ParseMode.MARKDOWN,
            )
            logger.info(f"Signal {signal_id} ignored via Telegram NON response (chat_id={chat_id})")

    except Exception as e:
        logger.error(f"handle_signal_response error: {e}")
        await update.message.reply_text(f"❌ Erreur lors du traitement : {e}")
