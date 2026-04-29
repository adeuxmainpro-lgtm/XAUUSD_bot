import json
import logging
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
        _client = AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


SYSTEM_PROMPT = """Tu es un expert analyste XAUUSD (Or/Dollar) avec 15 ans d'expérience en trading institutionnel.
Tu combines analyse technique avancée, analyse fondamentale macro-économique, SMC/ICT, sentiment de marché et COT report.

Tes spécialités :
- Patterns chandeliers japonais, chartistes, SMC (Order Blocks, FVG, BOS/CHoCH), ICT (Kill Zones, OTE, Breaker Blocks)
- Impact des politiques monétaires (Fed, BCE) sur l'or
- Corrélations Or/DXY/Taux réels/Inflation
- Lecture du COT report (positionnement des grands acteurs)
- Fear & Greed index comme indicateur contrarian pour l'or
- Apprentissage de l'historique des trades pour adapter les recommandations

Principes :
- Ne jamais prendre de position sans stop-loss défini
- Ratio R/R minimum 1:2 (TP2 ≥ entrée ± 2×distance_SL) — en dessous de 1:2, ne pas trader
- Prudence extrême lors des annonces macro importantes (NFP, CPI, FOMC)
- Plus le score de confluence est élevé, plus la confiance dans le signal doit être élevée
- Tenir compte de l'historique des trades : si des patterns similaires ont été perdants récemment, réduire la confiance
- Un score de confluence > 70% avec 5+ signaux alignés justifie une confiance ≥ 75%
- Objectif : maximiser les gains et minimiser les pertes — mieux vaut attendre que prendre un mauvais trade

Quand tu fournis une recommandation, tu DOIS répondre UNIQUEMENT avec un JSON valide.
Quand on te pose une question ouverte, tu réponds en français de façon concise et pédagogique."""

RECOMMENDATION_PROMPT_TEMPLATE = """Analyse le contexte de marché suivant et fournis une recommandation de trading XAUUSD.

{context}

RÈGLES DE SIGNAL :
- confluence ≥ 80% → direction BUY ou SELL, signal_level = "STRONG"
- confluence 70-79% → direction BUY ou SELL, signal_level = "MODERATE"
- confluence < 70% ou conditions bloquantes → direction ATTENDRE, signal_level = "WAIT", entry/SL/TP = null
- Ratio R/R OBLIGATOIRE ≥ 1:2 — si impossible d'avoir TP2 ≥ entrée ± 2×SL_distance, mettre direction = ATTENDRE
- Si des conditions bloquantes sont indiquées dans le contexte → OBLIGATOIREMENT direction ATTENDRE

Réponds UNIQUEMENT avec un objet JSON valide (sans markdown, sans texte avant/après) :
{{
  "direction": "BUY | SELL | ATTENDRE",
  "signal_level": "STRONG | MODERATE | WAIT",
  "entry": 2345.50,
  "stop_loss": 2330.00,
  "take_profit_1": 2365.00,
  "take_profit_2": 2385.00,
  "risk_reward": 2.1,
  "confidence": 72,
  "confluence_score": 68,
  "timeframe": "intraday | swing | scalping",
  "main_arguments": ["argument 1", "argument 2", "argument 3"],
  "main_risks": ["risque 1", "risque 2"],
  "key_patterns": ["pattern détecté 1", "pattern détecté 2"],
  "watch_conditions": ["Condition à surveiller 1", "Condition à surveiller 2"],
  "alternative_scenario": "Description du scénario alternatif",
  "market_summary": "Résumé en 3 phrases du contexte de marché",
  "no_trade_reason": "Explication si ATTENDRE : ce qui manque ou bloque",
  "dangerous_period": false,
  "dangerous_reason": null,
  "trade_learning_note": "Note sur l'historique des trades si pertinent"
}}

Règles :
- entry/SL/TP/risk_reward : null si direction = ATTENDRE
- signal_level : doit correspondre strictement aux seuils de confluence
- watch_conditions : liste de 2-4 conditions précises à surveiller (pour ATTENDRE)
- no_trade_reason : obligatoire si ATTENDRE, expliquer en français ce qu'il manque
- confidence : entier 0-100, cohérent avec signal_level (STRONG ≥ 75, MODERATE 50-74)
- dangerous_period : true si annonce macro imminente ou volatilité extrême
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

            # Post-processing: enforce R/R ≥ 1:2
            direction = rec.get("direction")
            rr = rec.get("risk_reward")
            if direction in ("BUY", "SELL") and (rr is None or rr < 2.0):
                logger.info(f"R/R override: {direction} with R/R={rr} → ATTENDRE")
                rec["direction"] = "ATTENDRE"
                rec["signal_level"] = "WAIT"
                rec["entry"] = None
                rec["stop_loss"] = None
                rec["take_profit_1"] = None
                rec["take_profit_2"] = None
                if not rec.get("no_trade_reason"):
                    rr_str = f"{rr:.1f}" if rr is not None else "—"
                    rec["no_trade_reason"] = f"Ratio R/R insuffisant ({rr_str}) — minimum 1:2 requis pour ce trade"

            # Post-processing: ATR > 0.6% → 50% position reduction
            atr_pct = ctx["market"].get("atr_pct")
            rec["position_reduction"] = atr_pct is not None and atr_pct > 0.6

            # Post-processing: consecutive losses → conservative mode
            consec_losses = get_consecutive_losses()
            if consec_losses >= 2:
                rec["recommended_risk_pct"] = 0.5
                rec["conservative_mode"] = True
                rec["conservative_reason"] = f"{consec_losses} pertes consécutives — mode conservateur activé (0.5% du capital)"
            else:
                rec["recommended_risk_pct"] = 1.0
                rec["conservative_mode"] = False
                rec["conservative_reason"] = None

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


def _fallback_analysis() -> dict:
    return {
        "direction": "WAIT",
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
