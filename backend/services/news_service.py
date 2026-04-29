import json
import logging
from backend.config import CLAUDE_MODEL
from backend.services.rss_service import fetch_all_rss

logger = logging.getLogger(__name__)


async def fetch_gold_news() -> list[dict]:
    """Aggregate news from RSS feeds + Claude web search."""
    import asyncio
    rss_task = fetch_all_rss()
    claude_task = _fetch_claude_news()
    rss_articles, claude_articles = await asyncio.gather(rss_task, claude_task, return_exceptions=True)

    combined: list[dict] = []

    if isinstance(claude_articles, list):
        combined.extend(claude_articles)

    if isinstance(rss_articles, list):
        # Deduplicate by title against claude articles
        existing_titles = {a["title"][:50].lower() for a in combined}
        for a in rss_articles:
            if a["title"][:50].lower() not in existing_titles:
                combined.append(a)
                existing_titles.add(a["title"][:50].lower())

    if not combined:
        return _fallback_news()

    # Sort: calendar events first, then HIGH impact
    combined.sort(key=lambda x: (
        x.get("is_calendar", False),
        x.get("impact") == "HIGH",
        x.get("impact") == "MEDIUM",
    ), reverse=True)

    return combined[:20]


async def _fetch_claude_news() -> list[dict]:
    """Use Claude web_search to find the latest gold news."""
    from backend.services.ai_analyst import _get_client
    try:
        response = await _get_client().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2000,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            messages=[{
                "role": "user",
                "content": (
                    "Search for the 5 most important gold (XAUUSD) news today. "
                    "Include Fed policy, CPI, geopolitical events, USD movements, gold demand. "
                    "Also check for any major X/Twitter posts from @KitcoNewsNOW @Schuldensuehner @MacroAlf @goldbugs. "
                    "Return ONLY a valid JSON array, no other text:\n"
                    '[{"title":"...","summary":"2-3 sentences","impact":"HIGH|MEDIUM|LOW",'
                    '"direction":"BULLISH|BEARISH|NEUTRAL","source":"name","published_at":"date"}]'
                ),
            }],
        )
        text = "".join(b.text for b in response.content if hasattr(b, "text"))
        start = text.find("[")
        end = text.rfind("]") + 1
        if start != -1 and end > start:
            return json.loads(text[start:end])[:5]
    except Exception as e:
        logger.error(f"Claude news fetch error: {e}")
    return []


def _fallback_news() -> list[dict]:
    return [{
        "title": "Service d'actualités temporairement indisponible",
        "summary": "Veuillez réessayer dans quelques minutes.",
        "impact": "LOW",
        "direction": "NEUTRAL",
        "source": "Système",
        "published_at": "",
    }]
