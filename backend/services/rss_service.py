import httpx
import logging
import xml.etree.ElementTree as ET
from datetime import datetime

logger = logging.getLogger(__name__)

RSS_FEEDS = [
    {"name": "Kitco", "url": "https://www.kitco.com/rss/kitco-news.rss"},
    {"name": "FXStreet", "url": "https://www.fxstreet.com/rss/news"},
    {"name": "ForexLive", "url": "https://www.forexlive.com/feed/news"},
    {"name": "MarketWatch", "url": "https://feeds.content.dowjones.io/public/rss/mw_marketpulse"},
    {"name": "Reuters Business", "url": "https://feeds.reuters.com/reuters/businessNews"},
    {"name": "Investing.com Gold", "url": "https://www.investing.com/rss/news_25.rss"},
    {"name": "Forex Factory Calendar", "url": "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"},
]

GOLD_KEYWORDS = [
    "gold", "xau", "fed", "federal reserve", "dollar", "inflation", "cpi", "fomc",
    "treasury", "yield", "rate hike", "rate cut", "precious metal", "commodity",
    "safe haven", "geopolit", "silver", "dxy", "jerome powell", "nfp", "payroll",
    "gdp", "recession", "tariff", "china", "war", "crisis",
]

CALENDAR_KEYWORDS = ["nfp", "payroll", "cpi", "gdp", "fomc", "powell", "fed", "pce", "pmi", "retail sales"]


async def _fetch_feed(url: str, name: str) -> list[dict]:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; TradingBot/1.0)"}
        async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=headers) as client:
            r = await client.get(url)
            r.raise_for_status()
            return _parse_xml(r.content, name)
    except Exception as e:
        logger.warning(f"RSS {name}: {e}")
        return []


def _parse_xml(content: bytes, source: str) -> list[dict]:
    articles = []
    try:
        root = ET.fromstring(content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # Forex Factory calendar format
        if root.tag == "weeklyevents" or root.find("event") is not None:
            return _parse_forex_factory(root)

        # Standard RSS
        items = root.findall(".//item")
        if not items:
            # Atom feed
            items = root.findall(".//atom:entry", ns) or root.findall(".//{http://www.w3.org/2005/Atom}entry")

        for item in items[:15]:
            title = (
                _text(item, "title") or
                _text(item, "{http://www.w3.org/2005/Atom}title") or ""
            ).strip()
            desc = (
                _text(item, "description") or
                _text(item, "{http://www.w3.org/2005/Atom}summary") or
                _text(item, "{http://www.w3.org/2005/Atom}content") or ""
            ).strip()
            pub = _text(item, "pubDate") or _text(item, "{http://www.w3.org/2005/Atom}updated") or ""

            combined = (title + " " + desc).lower()
            if any(kw in combined for kw in GOLD_KEYWORDS):
                articles.append({
                    "title": title[:200],
                    "summary": _strip_html(desc)[:400],
                    "source": source,
                    "published_at": pub,
                    "impact": _infer_impact(combined),
                    "direction": _infer_direction(combined),
                })
    except ET.ParseError as e:
        logger.warning(f"XML parse {source}: {e}")
    return articles


def _parse_forex_factory(root: ET.Element) -> list[dict]:
    """Parse Forex Factory economic calendar XML."""
    events = []
    for ev in root.findall("event"):
        title = _text(ev, "title") or ""
        country = _text(ev, "country") or ""
        impact = (_text(ev, "impact") or "").upper()
        date_str = _text(ev, "date") or ""
        forecast = _text(ev, "forecast") or "N/A"
        previous = _text(ev, "previous") or "N/A"

        if country != "USD":
            continue
        if impact not in ("High", "Medium", "HIGH", "MEDIUM"):
            continue

        title_lower = title.lower()
        if not any(kw in title_lower for kw in CALENDAR_KEYWORDS + ["employment", "trade balance", "consumer"]):
            continue

        events.append({
            "title": f"[CALENDRIER] {title}",
            "summary": f"Impact: {impact} | Prévision: {forecast} | Précédent: {previous}",
            "source": "Forex Factory",
            "published_at": date_str,
            "impact": "HIGH" if impact in ("High", "HIGH") else "MEDIUM",
            "direction": "NEUTRAL",
            "is_calendar": True,
        })
    return events[:10]


def _text(el: ET.Element, tag: str) -> str | None:
    child = el.find(tag)
    return child.text if child is not None else None


def _strip_html(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", " ", text).strip()


def _infer_impact(text: str) -> str:
    high_words = ["fomc", "nfp", "payroll", "cpi", "fed decision", "rate", "gdp", "war", "crisis", "emergency"]
    if any(w in text for w in high_words):
        return "HIGH"
    medium_words = ["inflation", "pmi", "trade", "retail", "gold demand", "china"]
    if any(w in text for w in medium_words):
        return "MEDIUM"
    return "LOW"


def _infer_direction(text: str) -> str:
    bullish = ["rises", "surges", "gains", "buy", "bullish", "higher", "climbs", "rally", "support", "demand", "safe haven"]
    bearish = ["falls", "drops", "sell", "bearish", "lower", "declines", "pressure", "weak"]
    bull_count = sum(1 for w in bullish if w in text)
    bear_count = sum(1 for w in bearish if w in text)
    if bull_count > bear_count:
        return "BULLISH"
    if bear_count > bull_count:
        return "BEARISH"
    return "NEUTRAL"


async def fetch_all_rss() -> list[dict]:
    import asyncio
    tasks = [_fetch_feed(f["url"], f["name"]) for f in RSS_FEEDS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_articles: list[dict] = []
    for r in results:
        if isinstance(r, list):
            all_articles.extend(r)

    # Deduplicate by title prefix
    seen: set[str] = set()
    unique: list[dict] = []
    for a in all_articles:
        key = a["title"][:60].lower()
        if key not in seen:
            seen.add(key)
            unique.append(a)

    # Calendar events first, then HIGH, MEDIUM, LOW
    priority = {"is_calendar": 3, "HIGH": 2, "MEDIUM": 1, "LOW": 0}
    unique.sort(key=lambda x: (x.get("is_calendar", False), x.get("impact", "LOW") == "HIGH", x.get("impact", "LOW") == "MEDIUM"), reverse=True)

    return unique[:25]


async def fetch_economic_calendar() -> list[dict]:
    """Return only calendar events for the week."""
    articles = await _fetch_feed("https://nfs.faireconomy.media/ff_calendar_thisweek.xml", "Forex Factory")
    return [a for a in articles if a.get("is_calendar")]
