from fastapi import APIRouter
from backend.services.macro_data import get_enriched_macro

router = APIRouter(prefix="/api/macro", tags=["macro"])


@router.get("/context")
async def macro_context():
    return await get_enriched_macro()
