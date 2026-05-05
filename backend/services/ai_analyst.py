import json
import logging
import httpx
from anthropic import AsyncAnthropic
from backend.config import ANTHROPIC_API_KEY, CLAUDE_MODEL
from backend.services.analysis_engine import build_market_context, format_context_for_prompt
from backend.services.telegram_service import send_strong_signal
from backend.database import save_analysis, save_chat_message, get_chat_history, get_consecutive_losses

logger = logging.getLogger(__name__)
_client: AsyncAnthropic | None = None


def _get_client() -> AsyncAnthropic:
    global _client
    if _client is None:
        # Provide our own httpx.AsyncClient to avoid the 'proxies' argument
        # that older anthropic SDK versions pass and httpx>=0.28 no longer accepts.
        _client = AsyncAnthropic(
            api_key=ANTHROPIC_API_KEY,
            http_client=httpx.AsyncClient(
                timeout=httpx.Timeout(120.0, connect=10.0),
            ),
        )
    return _client


SYSTEM_PROMPT = """Tu es un trader institutionnel expert XAUUSD (Or/Dollar) avec 20 ans d'expérience.
Tu appliques la stratégie SMC/ICT professionnelle avec un win rate cible > 60%.

━━━ RÈGLE NON NÉGOCIABLE ━━━

Tu DOIS retourner BUY ou SELL dans 99.9% des cas.
ATTENDRE = INTERDIT sauf si une annonce macro HIGH impact arrive dans moins de 15 minutes avec heure exacte confirmée.
Retourner ATTENDRE sans annonce imminente = ERREUR CRITIQUE.
Retourner WAIT ou NO_TRADE = ERREUR CRITIQUE.
Même avec 0 données ou un signal très faible → choisis toujours BUY ou SELL.
En cas de doute absolu → BUY (l'or est en tendance haussière long terme depuis 20 ans).

━━━ MÉTHODOLOGIE SMC/ICT ━━━

HIÉRARCHIE DES TIMEFRAMES :
1. 1J  → biais directionnel long terme (contexte macro)
2. 4H  → biais primaire (direction préférée)
3. 1H  → structure d'entrée (OB, FVG, patterns)
4. 15M → entrée précise et confirmation finale

PHASES WYCKOFF → STRATÉGIE :
  Mark Up       → trader les pullbacks haussiers sur OB/FVG (BUY)
  Mark Down     → trader les rebonds baissiers sur OB/FVG (SELL)
  Accumulation  → préparer des BUY sur les tests du support
  Distribution  → préparer des SELL sur les tests de résistance

CALCUL SL/TP PROFESSIONNEL :
SELL :
  SL  = swing high récent + ATR × 0.5 (jamais sur un chiffre rond)
  TP1 = prochain support significatif / swing low
  TP2 = objectif mesuré, MINIMUM = distance SL × 2

BUY :
  SL  = swing low récent − ATR × 0.5 (jamais sur un chiffre rond)
  TP1 = prochaine résistance significative / swing high
  TP2 = objectif mesuré symétrique, MINIMUM = distance SL × 2

NIVEAUX DE SIGNAL (position sizing) :
  Score > 75  → STRONG   → 1.0% du capital
  Score 60-75 → MODERATE → 0.75% du capital
  Score 40-60 → WEAK     → 0.5% du capital
  Score < 40  → VERY_WEAK → 0.25% du capital (toujours BUY ou SELL)

GESTION DU RISQUE :
  - Sortie partielle : 50% à TP1 → SL au break-even → 50% jusqu'à TP2
  - Si 2 pertes consécutives → mode conservateur (0.5%)
  - SL jamais sur un nombre rond

CORRÉLATIONS MACRO :
  - DXY haussier → or baissier | DXY baissier → or haussier
  - VIX > 20 → refuge or | Taux réels négatifs → or haussier
  - Fed dovish → or haussier | Fed hawkish → or baissier

Format de réponse : JSON valide uniquement pour les recommandations.
Pour les questions ouvertes : réponse concise en français."""

RECOMMENDATION_PROMPT_TEMPLATE = """Analyse le contexte de marché suivant et fournis une recommandation SMC/ICT pour XAUUSD.

{context}

━━━ PROCESSUS DE DÉCISION ━━━

ÉTAPE 1 — Direction (OBLIGATOIRE : BUY ou SELL) :
  Compte les signaux haussiers vs baissiers dans le contexte.
  Plus de haussiers → BUY | Plus de baissiers → SELL.
  Égalité → RSI > 50 = BUY, RSI < 50 = SELL, RSI = 50 → MACD positif = BUY, négatif = SELL.
  Doute absolu → BUY (tendance haussière long terme).
  ATTENDRE UNIQUEMENT si annonce macro HIGH dans moins de 15min avec heure confirmée dans le contexte.

ÉTAPE 2 — Calculer les niveaux précis :
  Utilise ATR, OB, FVG, supports/résistances du contexte.
  SL jamais sur un nombre rond ($X00.00 ou $X50.00) — décaler de $2-$5.
  TP2 minimum = distance_SL × 2.

NIVEAUX DE SIGNAL (signal_level) — basé sur le score confluence :
  Score > 75  → "STRONG"    (1.0% du capital)
  Score 60-75 → "MODERATE"  (0.75% du capital)
  Score 40-60 → "WEAK"      (0.5% du capital)
  Score < 40  → "VERY_WEAK" (0.25% du capital — toujours BUY ou SELL)

SORTIE PARTIELLE (obligatoire, à décrire dans partial_exit) :
  Fermer 50% à TP1 → SL au break-even → Laisser 50% courir jusqu'à TP2.

━━━ FORMAT JSON (répondre UNIQUEMENT avec ce JSON, sans texte avant/après) ━━━
{{
  "direction":        "BUY | SELL | ATTENDRE",
  "signal_level":     "STRONG | MODERATE | WEAK | VERY_WEAK | WAIT",
  "entry":            3300.50,
  "stop_loss":        3315.00,
  "take_profit_1":    3275.00,
  "take_profit_2":    3245.00,
  "risk_reward":      2.3,
  "confidence":       75,
  "confluence_score": 72,
  "timeframe":        "intraday | swing | scalping",
  "partial_exit":     "Fermer 50% à TP1 ($X). SL au BE ($Y). 50% jusqu'à TP2 ($Z).",
  "main_arguments":   ["argument SMC/ICT précis 1", "argument 2", "argument 3"],
  "main_risks":       ["risque 1", "risque 2"],
  "key_patterns":     ["pattern ou signal clé 1", "pattern 2"],
  "watch_conditions": ["condition à surveiller 1", "condition 2"],
  "alternative_scenario": "Scénario si biais invalide",
  "market_summary":   "Résumé SMC/ICT en 2-3 phrases",
  "no_trade_reason":  null,
  "dangerous_period": false,
  "dangerous_reason": null,
  "trade_learning_note": null,
  "wyckoff_note":     "Phase Wyckoff et implication pour le trade"
}}

Contraintes JSON ABSOLUES :
- direction : BUY ou SELL dans 99.9% des cas — ATTENDRE uniquement si annonce HIGH < 15min confirmée
- Si tu veux écrire ATTENDRE sans annonce imminente dans le contexte → écris BUY à la place
- entry : prix actuel ±0.02% (BUY légèrement en-dessous, SELL légèrement au-dessus)
- stop_loss : calculé depuis niveaux techniques, pas sur un nombre rond
- TP2 OBLIGATOIREMENT ≥ distance_SL × 2
- partial_exit : décrire les 3 étapes avec prix réels
- confidence : STRONG≥70, MODERATE 50-69, WEAK/VERY_WEAK 30-49
- entry/SL/TP/risk_reward : null uniquement si direction = ATTENDRE
- dangerous_period : true si annonce macro HIGH dans moins de 15min avec heure confirmée
"""


async def run_analysis() -> dict:
    """Full analysis with patterns, COT, sentiment, confluence and trade learning."""
    try:
        ctx = await build_market_context()
        context_text = format_context_for_prompt(ctx)

        response = await _get_client().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1800,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": RECOMMENDATION_PROMPT_TEMPLATE.format(context=context_text),
            }],
        )

        raw_text = response.content[0].text.strip()
        start = raw_text.find("{")
        end = raw_text.rfind("}") + 1

        if start != -1 and end > start:
            rec = json.loads(raw_text[start:end])
            rec["context_snapshot"] = {
                "price":        ctx["market"].get("price"),
                "rsi":          ctx["market"].get("rsi"),
                "trend_short":  ctx["market"].get("trend_short"),
                "trend_medium": ctx["market"].get("trend_medium"),
                "dxy":          ctx["macro"].get("dxy") if isinstance(ctx.get("macro"), dict) else None,
                "fed_rate":     ctx["macro"].get("fed_rate") if isinstance(ctx.get("macro"), dict) else None,
                "confluence":   ctx.get("confluence"),
                "signal_eval":  ctx.get("signal_eval"),
                "fear_greed":   ctx.get("fear_greed"),
            }
            rec["detected_patterns"] = _summarize_patterns(ctx.get("patterns", {}))
            # Merge pre-computed watch conditions if LLM didn't provide any
            if not rec.get("watch_conditions"):
                rec["watch_conditions"] = ctx.get("signal_eval", {}).get("watch_conditions", [])

            # Confluence detail string from sentiment engine
            confluence = ctx.get("confluence", {})
            rec["confluence_detail"] = confluence.get("detail_str", "")

            # Post-processing: pin entry to current price (never use a stale price)
            current_price = ctx["market"].get("price")
            direction = rec.get("direction")
            if current_price and direction in ("BUY", "SELL") and rec.get("entry") is not None:
                # BUY: enter at or slightly below current price (small limit buffer)
                # SELL: enter at or slightly above current price
                if direction == "BUY":
                    corrected_entry = round(current_price * 0.9998, 2)
                else:
                    corrected_entry = round(current_price * 1.0002, 2)

                old_entry = rec["entry"]
                rec["entry"] = corrected_entry

                # Recalculate R/R with the corrected entry (SL/TP levels stay as-is)
                sl  = rec.get("stop_loss")
                tp2 = rec.get("take_profit_2") or rec.get("take_profit_1")
                if sl and tp2:
                    try:
                        if direction == "BUY":
                            sl_dist = corrected_entry - sl
                            tp_dist = tp2 - corrected_entry
                        else:
                            sl_dist = sl - corrected_entry
                            tp_dist = corrected_entry - tp2
                        if sl_dist > 0 and tp_dist > 0:
                            rec["risk_reward"] = round(tp_dist / sl_dist, 2)
                    except Exception:
                        pass

                if abs(old_entry - corrected_entry) > 1.0:
                    logger.info(f"Entry corrected {direction}: ${old_entry} → ${corrected_entry} (market: ${current_price})")

            # Post-processing: merge pre-computed SMC/ICT engine fields
            kill_zone       = ctx.get("kill_zone", {})
            mtf             = ctx.get("mtf", {})
            wyckoff         = ctx.get("wyckoff", {})
            rsi_divergence  = ctx.get("rsi_divergence", {})
            liquidity_sweep = ctx.get("liquidity_sweep", {})
            trade_score_obj = ctx.get("trade_score_obj", {})

            rec["session_active"]   = kill_zone.get("name", "")
            rec["session_badge"]    = kill_zone.get("color", "red")
            rec["session_tradeable"] = kill_zone.get("tradeable", False)
            rec["mtf"]              = mtf
            rec["wyckoff"]          = wyckoff
            rec["rsi_divergence"]   = rsi_divergence
            rec["liquidity_sweep"]  = liquidity_sweep
            rec["trade_score_obj"]  = trade_score_obj
            rec["trade_score"]      = trade_score_obj.get("score", 0)
            rec["regime"]           = ctx.get("regime", {})

            # Post-processing: force BUY/SELL if AI returned ATTENDRE without valid macro blocker
            ai_direction = rec.get("direction")
            macro_blocker_active = (
                rec.get("dangerous_period", False)
                or ctx.get("signal_eval", {}).get("signal_level") == "WAIT"
            )
            if ai_direction in ("ATTENDRE", "WAIT", "NO_TRADE", None) and not macro_blocker_active:
                forced = _force_direction_from_context(ctx)
                logger.info(f"ATTENDRE override: AI said '{ai_direction}' with no macro blocker → forced {forced}")
                rec["direction"] = forced
                rec["no_trade_reason"] = None
                # Generate ATR-based levels if entry is null
                if rec.get("entry") is None:
                    price = ctx["market"].get("price")
                    atr   = ctx["market"].get("atr") or (price * 0.005 if price else 10)
                    if price:
                        if forced == "BUY":
                            entry = round(price * 0.9998, 2)
                            rec["entry"]         = entry
                            rec["stop_loss"]     = round(entry - atr * 1.5, 2)
                            rec["take_profit_1"] = round(entry + atr * 1.5, 2)
                            rec["take_profit_2"] = round(entry + atr * 3.0, 2)
                        else:
                            entry = round(price * 1.0002, 2)
                            rec["entry"]         = entry
                            rec["stop_loss"]     = round(entry + atr * 1.5, 2)
                            rec["take_profit_1"] = round(entry - atr * 1.5, 2)
                            rec["take_profit_2"] = round(entry - atr * 3.0, 2)
                        rec["risk_reward"] = 2.0
                # Restore signal level from pre-computed engine if AI left it as WAIT
                if rec.get("signal_level") in ("WAIT", None):
                    rec["signal_level"] = ctx.get("signal_eval", {}).get("signal_level", "WEAK")

            # Post-processing: compute gain estimate and weekly projection
            _compute_gain_estimate(rec)

            # Post-processing: ATR > 0.6% → 50% position reduction
            atr_pct = ctx["market"].get("atr_pct")
            rec["position_reduction"] = atr_pct is not None and atr_pct > 0.6

            # Post-processing: consecutive losses → conservative mode + 4-tier position sizing
            consec_losses = get_consecutive_losses()
            sig_level = rec.get("signal_level", "WEAK")
            base_risk = (
                1.0   if sig_level == "STRONG"    else
                0.75  if sig_level == "MODERATE"  else
                0.5   if sig_level == "WEAK"       else
                0.25  # VERY_WEAK
            )
            if consec_losses >= 2:
                rec["recommended_risk_pct"] = min(base_risk, 0.5)
                rec["conservative_mode"] = True
                rec["conservative_reason"] = f"{consec_losses} pertes consécutives — mode conservateur activé"
            else:
                rec["recommended_risk_pct"] = base_risk
                rec["conservative_mode"] = False
                rec["conservative_reason"] = None
            rec["weak_signal"] = sig_level in ("WEAK", "VERY_WEAK")

            save_analysis(rec)

            # Telegram alert for STRONG signals
            if rec.get("signal_level") == "STRONG" and rec.get("direction") in ("BUY", "SELL"):
                price = ctx["market"].get("price")
                try:
                    await send_strong_signal(rec.get("direction", "?"), rec.get("confluence_score", 0), price)
                except Exception as tg_err:
                    logger.warning(f"Telegram alert failed (non-critical): {tg_err}")

            return rec
        else:
            logger.error(f"JSON not found in response: {raw_text}")
            return _fallback_analysis()

    except Exception as e:
        logger.error(f"run_analysis error: {e}")
        return _fallback_analysis()


async def chat(user_message: str) -> str:
    """Conversational mode with full market context."""
    try:
        ctx = await build_market_context()
        context_text = format_context_for_prompt(ctx)
        history = get_chat_history(limit=10)

        messages = [{"role": m["role"], "content": m["content"]} for m in history]
        messages.append({
            "role": "user",
            "content": f"Contexte marché actuel :\n{context_text}\n\nQuestion : {user_message}",
        })

        response = await _get_client().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=1000,
            system=SYSTEM_PROMPT,
            messages=messages,
        )

        answer = response.content[0].text.strip()
        save_chat_message("user", user_message)
        save_chat_message("assistant", answer)
        return answer

    except Exception as e:
        logger.error(f"chat error: {e}")
        return "Désolé, une erreur s'est produite. Veuillez réessayer."


def _compute_gain_estimate(rec: dict) -> None:
    """Compute gain/loss estimates for a standard 1000€ bankroll at 1% risk.
    Partial-exit model: 50% closed at TP1, SL moved to BE, 50% runs to TP2.
    Adds 'gain_estimate' and 'weekly_projection' keys in-place.
    """
    direction = rec.get("direction")
    if direction not in ("BUY", "SELL"):
        return
    entry = rec.get("entry")
    sl    = rec.get("stop_loss")
    tp1   = rec.get("take_profit_1")
    tp2   = rec.get("take_profit_2")
    if not (entry and sl and tp1):
        return

    sl_dist  = abs(entry - sl)
    tp1_dist = abs(tp1 - entry)
    tp2_dist = abs(tp2 - entry) if tp2 else tp1_dist * 2

    if sl_dist <= 0:
        return

    # Standard reference: 1000€ bankroll, 1% risk → 10€ at risk
    BANKROLL = 1000
    RISK_PCT = 0.01
    risk_eur = BANKROLL * RISK_PCT  # 10€

    rr_tp1 = tp1_dist / sl_dist
    rr_tp2 = tp2_dist / sl_dist

    # Full position at TP1 / TP2
    gain_tp1_full = round(risk_eur * rr_tp1, 1)
    gain_tp2_full = round(risk_eur * rr_tp2, 1)

    # Partial exit: 50% closed at TP1, 50% runs to TP2 (no more risk after BE)
    # If TP1 hit: lock +gain_tp1_full×0.5 from first half
    # If TP2 hit: lock +gain_tp2_full×0.5 from second half
    # If stop hit before TP1: lose full risk_eur
    gain_partial_both  = round(gain_tp1_full * 0.5 + gain_tp2_full * 0.5, 1)
    gain_partial_tp1only = round(gain_tp1_full * 0.5, 1)  # TP2 missed, SL at BE

    # Weekly/monthly projection (60% win rate, 5 trades/week, partial exit model)
    WIN_RATE    = 0.60
    TRADES_WEEK = 5
    # Expected gain per trade using partial model:
    #   P(TP1 hit) = WIN_RATE, of which assume 70% also reach TP2
    p_both  = WIN_RATE * 0.70
    p_tp1   = WIN_RATE * 0.30
    p_loss  = 1 - WIN_RATE
    ev_per_trade = (p_both * gain_partial_both
                    + p_tp1 * gain_partial_tp1only
                    - p_loss * risk_eur)
    weekly_eur = round(ev_per_trade * TRADES_WEEK, 1)
    weekly_pct = round(weekly_eur / BANKROLL * 100, 2)
    monthly_pct = round(weekly_pct * 4.3, 1)

    rec["gain_estimate"] = {
        "bankroll_example":    BANKROLL,
        "risk_eur":            risk_eur,
        "gain_tp1_eur":        gain_tp1_full,
        "gain_tp2_eur":        gain_tp2_full,
        "gain_partial_eur":    gain_partial_both,
        "rr_tp1":              round(rr_tp1, 2),
        "rr_tp2":              round(rr_tp2, 2),
    }
    rec["weekly_projection"] = {
        "trades_per_week":     TRADES_WEEK,
        "win_rate_pct":        int(WIN_RATE * 100),
        "weekly_gain_eur":     weekly_eur,
        "weekly_gain_pct":     weekly_pct,
        "monthly_gain_pct":    monthly_pct,
    }


def _summarize_patterns(patterns: dict) -> list[str]:
    """Flatten all detected patterns into a readable list."""
    summary = []
    cs = patterns.get("candlestick", {})
    for p in cs.get("bullish", []):
        summary.append(p.get("name") if isinstance(p, dict) else p)
    for p in cs.get("bearish", []):
        summary.append(p.get("name") if isinstance(p, dict) else p)
    for p in patterns.get("chart", []):
        summary.append(p.get("name", ""))
    for ob in patterns.get("smc", {}).get("order_blocks", []):
        summary.append(ob.get("desc", ""))
    for bos in patterns.get("smc", {}).get("bos", []):
        summary.append(bos)
    ote = patterns.get("ict", {}).get("ote")
    if ote:
        summary.append("OTE Zone")
    return [s for s in summary if s]


def _force_direction_from_context(ctx: dict) -> str:
    """Resolve BUY or SELL from market context. Never returns ATTENDRE."""
    confluence = ctx.get("confluence", {})
    signals    = confluence.get("signals", [])
    bull = sum(1 for s in signals if s.get("direction") in ("BUY", "BULLISH", "bullish"))
    bear = sum(1 for s in signals if s.get("direction") in ("SELL", "BEARISH", "bearish"))

    if bull > bear:
        return "BUY"
    if bear > bull:
        return "SELL"

    market = ctx.get("market", {})
    rsi    = market.get("rsi")
    macd   = market.get("macd_histogram") or market.get("macd")

    if rsi is not None:
        if rsi > 50:
            return "BUY"
        if rsi < 50:
            return "SELL"
        if macd is not None:
            if macd > 0:
                return "BUY"
            if macd < 0:
                return "SELL"

    return "BUY"


def _fallback_analysis() -> dict:
    return {
        "direction": "BUY",
        "signal_level": "WEAK",
        "entry": None,
        "stop_loss": None,
        "take_profit_1": None,
        "take_profit_2": None,
        "risk_reward": None,
        "confidence": 0,
        "confluence_score": 0,
        "timeframe": "intraday",
        "main_arguments": ["Service d'analyse temporairement indisponible"],
        "main_risks": ["Vérifiez votre connexion et vos clés API"],
        "key_patterns": [],
        "alternative_scenario": "N/A",
        "market_summary": "Analyse indisponible. Veuillez relancer l'analyse.",
        "dangerous_period": False,
        "dangerous_reason": None,
        "trade_learning_note": None,
        "error": True,
    }
