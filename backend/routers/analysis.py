from fastapi import APIRouter, BackgroundTasks, HTTPException
from backend.services.ai_analyst import run_analysis
from backend.database import get_latest_analysis, get_recent_analyses
import logging
import time

router = APIRouter(prefix="/api/analysis", tags=["analysis"])
logger = logging.getLogger(__name__)

_composite_cache: dict = {}
_COMPOSITE_TTL = 3600

_running = False


@router.post("/run")
async def trigger_analysis(background_tasks: BackgroundTasks):
    """Lance une nouvelle analyse IA en arrière-plan."""
    global _running
    if _running:
        return {"status": "already_running", "message": "Une analyse est déjà en cours"}
    _running = True
    background_tasks.add_task(_run_and_reset)
    return {"status": "started", "message": "Analyse lancée"}


async def _run_and_reset():
    global _running
    try:
        await run_analysis()
    finally:
        _running = False


@router.post("/run/sync")
async def trigger_analysis_sync():
    """Lance une analyse IA et attend le résultat (peut prendre ~30s)."""
    try:
        result = await run_analysis()
        return result
    except Exception as e:
        logger.error(f"Sync analysis error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/latest")
async def get_latest():
    """Retourne la dernière analyse disponible."""
    analysis = get_latest_analysis()
    if not analysis:
        return {"message": "Aucune analyse disponible. Lancez /api/analysis/run/sync"}
    return analysis


@router.get("/signal-history")
async def get_signal_history(limit: int = 5):
    """Derniers signaux pour l'affichage de l'historique dans le dashboard."""
    return get_recent_analyses(min(limit, 10))


@router.get("/status")
async def get_status():
    """Statut de l'analyse en cours."""
    return {"running": _running}


@router.get("/composite")
async def get_composite_score(refresh: bool = False):
    """Composite 100-point score: correlations, ETF flows, options, yields, Fed NLP."""
    global _composite_cache
    now = time.time()
    if not refresh and _composite_cache.get("ts") and now - _composite_cache["ts"] < _COMPOSITE_TTL:
        return _composite_cache["data"]

    try:
        from backend.services.analysis_engine import build_market_context
        ctx = await build_market_context()
        payload = {
            "composite":   ctx.get("composite", {}),
            "new_sources": ctx.get("new_sources", {}),
            "confluence":  ctx.get("confluence", {}),
        }
        _composite_cache = {"ts": now, "data": payload}
        return payload
    except Exception as e:
        logger.error(f"Composite score endpoint error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
