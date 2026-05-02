from fastapi import APIRouter
from backend.services.news_service import fetch_gold_news
from backend.database import save_news, get_latest_news
import logging

router = APIRouter(prefix="/api/news", tags=["news"])
logger = logging.getLogger(__name__)


@router.get("")
async def get_news(refresh: bool = False):
    """Retourne les actualités. refresh=true force la mise à jour via Claude."""
    if refresh:
        result = await fetch_gold_news()
        save_news(result["articles"])
        return {"source": "fresh", "articles": result["articles"], "stats": result.get("stats")}

    cached = get_latest_news()
    if cached:
        return {"source": "cache", "articles": cached}

    # Pas de cache → fetch
    result = await fetch_gold_news()
    save_news(result["articles"])
    return {"source": "fresh", "articles": result["articles"], "stats": result.get("stats")}
