import json
import logging
from backend.config import CLAUDE_MODEL
from backend.services.rss_service import fetch_all_rss

logger = logging.getLogger(__name__)

# Cheaper model for batch sentiment classification (fast, low cost)
_SENTIMENT_MODEL = "claude-haiku-4-5-20251001"


async def fetch_gold_news() -> dict:
    """Aggregate news from RSS feeds + Claude web search + batch sentiment analysis.
    Returns {"articles": [...], "stats": {...}}."""
    import asyncio
    rss_task    = fetch_all_rss()
    claude_task = _fetch_claude_news()
    rss_result, claude_articles = await asyncio.gather(rss_task, claude_task, return_exceptions=True)

    combined: list[dict] = []
    rss_stats: dict = {}

    # Claude web search results (already gold-specific by query)
    claude_count = 0
    if isinstance(claude_articles, list):
        combined.extend(claude_articles)
        claude_count = len(claude_articles)

    # RSS results (already title-filtered by rss_service)
    if isinstance(rss_result, tuple):
        rss_articles, rss_stats = rss_result
        existing_titles = {a["title"][:50].lower() for a in combined}
        for a in rss_articles:
            if a["title"][:50].lower() not in existing_titles:
                combined.append(a)
                existing_titles.add(a["title"][:50].lower())

    total_before_sentiment = len(combined)

    if not combined:
        return {"articles": _fallback_news(), "stats": {"total_fetched": 0, "total_kept": 0, "claude_articles": 0}}

    # Batch AI sentiment analysis (Haiku, 1 call for all articles)
    try:
        combined = await _batch_sentiment_analysis(combined)
    except Exception as e:
        logger.warning(f"Batch sentiment skipped (non-critical): {e}")

    # Sort: calendar first, then HIGH impact, then reliability
    combined.sort(key=lambda x: (
        x.get("is_calendar", False),
        x.get("impact") == "HIGH",
        x.get("impact") == "MEDIUM",
        x.get("reliability", 3),
    ), reverse=True)

    articles = combined[:30]

    stats = {
        "rss_seen":        rss_stats.get("rss_total_seen", 0),
        "rss_kept":        rss_stats.get("rss_total_kept", 0),
        "rss_after_dedup": rss_stats.get("rss_after_dedup", 0),
        "claude_articles": claude_count,
        "total_kept":      total_before_sentiment,
        "final_count":     len(articles),
    }
    logger.info(
        f"News pipeline: RSS {stats['rss_kept']}/{stats['rss_seen']} passed filter · "
        f"Claude +{stats['claude_articles']} · Total {stats['total_kept']} → {stats['final_count']} articles"
    )
    return {"articles": articles, "stats": stats}


async def _fetch_claude_news() -> list[dict]:
    """Use Claude web_search covering all key gold/macro topics."""
    from backend.services.ai_analyst import _get_client
    try:
        response = await _get_client().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2500,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{
                "role": "user",
                "content": (
                    "Search for the latest gold (XAUUSD) market intelligence today. Cover ALL of these topics:\n"
                    "1. XAUUSD gold price analysis today\n"
                    "2. gold market news today\n"
                    "3. Federal Reserve gold impact\n"
                    "4. DXY dollar index today\n"
                    "5. gold sentiment traders today\n"
                    "6. gold price prediction analysts\n\n"
                    "Return the 8 most impactful results as a valid JSON array ONLY (no text before or after):\n"
                    '[{"title":"...","summary":"2-3 sentences","impact":"HIGH|MEDIUM|LOW",'
                    '"direction":"BULLISH|BEARISH|NEUTRAL","source":"site name","published_at":"today"}]'
                ),
            }],
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        start = text.find("[")
        end   = text.rfind("]") + 1
        if start != -1 and end > start:
            articles = json.loads(text[start:end])
            for a in articles:
                a.setdefault("reliability", 4)
            return articles[:8]
    except Exception as e:
        logger.error(f"Claude news fetch error: {e}")
    return []


async def _batch_sentiment_analysis(articles: list[dict]) -> list[dict]:
    """Classify bullish/bearish/neutral for each article using Haiku (one API call)."""
    from backend.services.ai_analyst import _get_client

    # Only analyze non-calendar articles
    to_analyze = [(i, a) for i, a in enumerate(articles) if not a.get("is_calendar")]
    if not to_analyze:
        return articles

    # Build prompt with numbered titles
    titles_text = "\n".join(
        f"{idx + 1}. [{a.get('source', '?')}] {a['title']}"
        for idx, (_, a) in enumerate(to_analyze)
    )

    response = await _get_client().messages.create(
        model=_SENTIMENT_MODEL,
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": (
                "Pour chaque titre ci-dessous, évalue l'impact DIRECT sur le prix de l'or (XAU/USD) UNIQUEMENT.\n\n"
                "Règles d'évaluation pour l'or :\n"
                "- BULLISH : dollar faible, Fed dovish/baisses de taux, hausse des risques géopolitiques, "
                "inflation élevée, VIX élevé, fuite vers les refuges, demande d'or en hausse\n"
                "- BEARISH : dollar fort, Fed hawkish/hausses de taux, taux réels en hausse, "
                "risk-on, pression sur l'or, sorties ETF or\n"
                "- NEUTRAL : article sur l'or sans direction claire, ou impact indirect non déterminant\n\n"
                "IMPORTANT : si l'article ne concerne pas directement l'or ou les facteurs macro qui l'influencent, "
                "réponds NEUTRAL.\n\n"
                f"{titles_text}\n\n"
                'Réponds UNIQUEMENT avec ce JSON : {"sentiments": ["BULLISH", "NEUTRAL", ...]}'
            ),
        }],
    )

    text = response.content[0].text.strip()
    start = text.find("{")
    end   = text.rfind("}") + 1
    if start == -1 or end <= start:
        return articles

    data = json.loads(text[start:end])
    sentiments = data.get("sentiments", [])

    result = list(articles)
    for idx, (orig_idx, _) in enumerate(to_analyze):
        if idx < len(sentiments) and sentiments[idx] in ("BULLISH", "BEARISH", "NEUTRAL"):
            result[orig_idx] = {**result[orig_idx], "direction": sentiments[idx]}

    return result


def _fallback_news() -> list[dict]:
    return [{
        "title":        "Service d'actualités temporairement indisponible",
        "summary":      "Veuillez réessayer dans quelques minutes.",
        "impact":       "LOW",
        "direction":    "NEUTRAL",
        "source":       "Système",
        "published_at": "",
        "reliability":  3,
    }]
