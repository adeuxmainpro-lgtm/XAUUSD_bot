import httpx
import logging
import xml.etree.ElementTree as ET
from datetime import datetime

logger = logging.getLogger(__name__)

# reliability: 1-5 (Kitco/Reuters/FXStreet = 5, Google News = 4, Investing/SeekingAlpha = 3, Reddit/YouTube = 2)
RSS_FEEDS = [
    {"name": "Kitco",               "url": "https://www.kitco.com/rss/kitco-news.rss",                                                             "reliability": 5},
    {"name": "FXStreet",            "url": "https://www.fxstreet.com/rss/news",                                                                     "reliability": 5},
    {"name": "Reuters Business",    "url": "https://feeds.reuters.com/reuters/businessNews",                                                         "reliability": 5},
    {"name": "Forex Factory",       "url": "https://nfs.faireconomy.media/ff_calendar_thisweek.xml",                                                 "reliability": 5},
    {"name": "Google News Gold",    "url": "https://news.google.com/rss/search?q=gold+price+XAUUSD&hl=en&gl=US&ceid=US:en",                         "reliability": 4},
    {"name": "MarketWatch",         "url": "https://feeds.content.dowjones.io/public/rss/mw_marketpulse",                                           "reliability": 4},
    {"name": "ForexLive",           "url": "https://www.forexlive.com/feed/news",                                                                    "reliability": 3},
    {"name": "Investing.com Gold",  "url": "https://www.investing.com/rss/news_25.rss",                                                              "reliability": 3},
    {"name": "Seeking Alpha GLD",   "url": "https://seekingalpha.com/api/sa/combined/GLD.xml",                                                       "reliability": 3},
    {"name": "Reddit Forex",        "url": "https://www.reddit.com/r/Forex/search.rss?q=gold+XAUUSD&sort=new",                                      "reliability": 2},
    {"name": "Reddit Gold",         "url": "https://www.reddit.com/r/Gold/search.rss?q=price&sort=new",                                             "reliability": 2},
    {"name": "YouTube Trading",     "url": "https://www.youtube.com/feeds/videos.xml?channel_id=UCRQiAB2a6B6XTXDgLLZkFwA",                          "reliability": 2},
]

# Title must contain at least one of these — ensures the article is actually about gold/XAU
GOLD_TITLE_KEYWORDS = [
    "gold", "xau", "xauusd", "xau/usd", "precious metal", "bullion",
]

# Body context keywords — used for impact/direction inference (after title passes)
GOLD_BODY_KEYWORDS = [
    "gold", "xau", "xauusd", "precious metal", "bullion",
    "federal reserve", "fed rate", "powell", "fomc", "interest rate",
    "rate hike", "rate cut", "inflation", "cpi", "dxy", "dollar index",
    "dollar strength", "dollar weakness", "treasury yield", "real yield",
    "nfp", "payroll", "gdp", "pce", "safe haven",
]

CALENDAR_KEYWORDS = ["nfp", "payroll", "cpi", "gdp", "fomc", "powell", "fed", "pce", "pmi", "retail sales"]


async def _fetch_feed(url: str, name: str, reliability: int = 3) -> tuple[list[dict], dict]:
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; GoldTradingBot/1.0; +https://github.com/trading)"}
        async with httpx.AsyncClient(timeout=12, follow_redirects=True, headers=headers) as client:
            r = await client.get(url)
            r.raise_for_status()
            return _parse_xml(r.content, name, reliability)
    except Exception as e:
        logger.warning(f"RSS {name}: {e}")
        return [], {"total_seen": 0, "total_kept": 0}


def _parse_xml(content: bytes, source: str, reliability: int = 3) -> tuple[list[dict], dict]:
    """Returns (articles, stats) where stats = {total_seen, total_kept}."""
    articles = []
    stats = {"total_seen": 0, "total_kept": 0}
    try:
        root = ET.fromstring(content)
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        # Forex Factory calendar format
        if root.tag == "weeklyevents" or root.find("event") is not None:
            cal = _parse_forex_factory(root, reliability)
            return cal, {"total_seen": len(cal), "total_kept": len(cal)}

        # YouTube / Atom feed
        items = root.findall(".//item")
        if not items:
            items = (
                root.findall(".//atom:entry", ns) or
                root.findall(".//{http://www.w3.org/2005/Atom}entry")
            )

        for item in items[:15]:
            title = (
                _text(item, "title") or
                _text(item, "{http://www.w3.org/2005/Atom}title") or
                _text(item, "media:title") or ""
            ).strip()
            desc = (
                _text(item, "description") or
                _text(item, "{http://www.w3.org/2005/Atom}summary") or
                _text(item, "{http://www.w3.org/2005/Atom}content") or
                _text(item, "{http://search.yahoo.com/mrss/}description") or ""
            ).strip()
            pub = (
                _text(item, "pubDate") or
                _text(item, "{http://www.w3.org/2005/Atom}updated") or
                _text(item, "{http://www.w3.org/2005/Atom}published") or ""
            )

            if not title:
                continue

            stats["total_seen"] += 1
            title_lower = title.lower()
            combined    = (title_lower + " " + desc.lower())

            # STRICT: title must explicitly mention gold/XAU to be relevant
            if not any(kw in title_lower for kw in GOLD_TITLE_KEYWORDS):
                continue

            stats["total_kept"] += 1
            articles.append({
                "title":        title[:200],
                "summary":      _strip_html(desc)[:400],
                "source":       source,
                "published_at": pub,
                "impact":       _infer_impact(combined),
                "direction":    _infer_direction(combined),
                "reliability":  reliability,
            })
    except ET.ParseError as e:
        logger.warning(f"XML parse {source}: {e}")
    return articles, stats


def _parse_forex_factory(root: ET.Element, reliability: int = 5) -> list[dict]:
    events = []
    for ev in root.findall("event"):
        title   = _text(ev, "title") or ""
        country = _text(ev, "country") or ""
        impact  = (_text(ev, "impact") or "").upper()
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
            "title":        f"[CALENDRIER] {title}",
            "summary":      f"Impact: {impact} | Prévision: {forecast} | Précédent: {previous}",
            "source":       "Forex Factory",
            "published_at": date_str,
            "impact":       "HIGH" if impact in ("High", "HIGH") else "MEDIUM",
            "direction":    "NEUTRAL",
            "reliability":  reliability,
            "is_calendar":  True,
        })
    return events[:10]


def _text(el: ET.Element, tag: str) -> str | None:
    child = el.find(tag)
    return child.text if child is not None else None


def _strip_html(text: str) -> str:
    import re
    return re.sub(r"<[^>]+>", " ", text).strip()


def _infer_impact(text: str) -> str:
    high_words = ["fomc", "nfp", "payroll", "cpi", "fed decision", "rate decision", "gdp", "interest rate", "emergency"]
    if any(w in text for w in high_words):
        return "HIGH"
    medium_words = ["inflation", "pmi", "gold demand", "dxy", "dollar index", "powell", "federal reserve"]
    if any(w in text for w in medium_words):
        return "MEDIUM"
    return "LOW"


def _infer_direction(text: str) -> str:
    # Gold-specific bullish signals (good for gold price)
    bullish = [
        "gold rises", "gold surges", "gold gains", "gold rallies", "gold climbs",
        "gold higher", "gold up", "gold demand", "gold bullish", "gold support",
        "bullish gold", "buy gold", "gold safe haven",
        "dollar weak", "dollar falls", "dollar lower", "dxy drops",
        "rate cut", "dovish", "fed cut", "yields fall", "yields lower",
    ]
    # Gold-specific bearish signals (bad for gold price)
    bearish = [
        "gold falls", "gold drops", "gold lower", "gold declines", "gold retreats",
        "gold slides", "gold pressure", "gold bearish", "sell gold", "gold weak",
        "dollar strong", "dollar rises", "dollar higher", "dxy rises", "dxy up",
        "rate hike", "hawkish", "fed hike", "yields rise", "yields higher",
    ]
    bull_count = sum(1 for w in bullish if w in text)
    bear_count = sum(1 for w in bearish if w in text)
    if bull_count > bear_count:
        return "BULLISH"
    if bear_count > bull_count:
        return "BEARISH"
    return "NEUTRAL"


async def fetch_all_rss() -> tuple[list[dict], dict]:
    """Returns (articles, stats) where stats tracks how many items passed the gold filter."""
    import asyncio
    tasks = [_fetch_feed(f["url"], f["name"], f.get("reliability", 3)) for f in RSS_FEEDS]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_articles: list[dict] = []
    total_seen  = 0
    total_kept  = 0

    for r in results:
        if isinstance(r, tuple) and len(r) == 2:
            articles, s = r
            all_articles.extend(articles)
            total_seen += s.get("total_seen", 0)
            total_kept += s.get("total_kept", 0)

    logger.info(f"RSS filter: {total_kept}/{total_seen} articles passed gold-relevance filter")

    # Deduplicate by title prefix
    seen: set[str] = set()
    unique: list[dict] = []
    for a in all_articles:
        key = a["title"][:60].lower()
        if key not in seen:
            seen.add(key)
            unique.append(a)

    # Calendar events first, then HIGH/MEDIUM/LOW, then by reliability
    unique.sort(key=lambda x: (
        x.get("is_calendar", False),
        x.get("impact", "LOW") == "HIGH",
        x.get("impact", "LOW") == "MEDIUM",
        x.get("reliability", 3),
    ), reverse=True)

    stats = {
        "rss_total_seen": total_seen,
        "rss_total_kept": total_kept,
        "rss_after_dedup": len(unique),
    }
    return unique[:40], stats


async def fetch_economic_calendar() -> list[dict]:
    articles, _ = await _fetch_feed("https://nfs.faireconomy.media/ff_calendar_thisweek.xml", "Forex Factory", 5)
    return [a for a in articles if a.get("is_calendar")]
