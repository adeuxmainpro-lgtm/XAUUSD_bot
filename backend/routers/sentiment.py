from fastapi import APIRouter, BackgroundTasks
from backend.database import get_latest_cot, get_latest_sentiment, save_cot, save_sentiment
from backend.services.cot_service import fetch_cot_gold
from backend.services.sentiment_service import fetch_fear_greed

router = APIRouter(prefix="/api/sentiment", tags=["sentiment"])


@router.get("")
async def get_sentiment(refresh: bool = False):
    fg = get_latest_sentiment() if not refresh else None
    cot = get_latest_cot() if not refresh else None

    if not fg or refresh:
        fg = await fetch_fear_greed()
        if fg:
            save_sentiment(fg)

    if not cot or refresh:
        cot = await fetch_cot_gold()
        if cot:
            save_cot(cot)

    return {"fear_greed": fg, "cot": cot}


@router.get("/cot")
async def get_cot(refresh: bool = False):
    cot = get_latest_cot() if not refresh else None
    if not cot:
        cot = await fetch_cot_gold()
        if cot:
            save_cot(cot)
    return cot or {}


@router.get("/fear-greed")
async def get_fear_greed(refresh: bool = False):
    fg = get_latest_sentiment() if not refresh else None
    if not fg:
        fg = await fetch_fear_greed()
        if fg:
            save_sentiment(fg)
    return fg or {}
