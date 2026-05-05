from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from backend.services.risk_manager import calculate_position
from backend.database import get_latest_analysis
import logging

router = APIRouter(prefix="/api/risk", tags=["risk"])
logger = logging.getLogger(__name__)


class RiskRequest(BaseModel):
    bankroll_eur: float = Field(..., gt=0, description="Capital en euros")
    risk_level: str = Field("normal", description="low | normal | aggressive (ignoré si risk_pct fourni)")
    risk_pct: float | None = Field(None, gt=0, le=100, description="Risque libre en % (ex: 1.5). Prioritaire sur risk_level.")
    stop_loss_pips: float = Field(..., gt=0, description="Distance stop loss en USD/oz")
    entry_price: float = Field(..., gt=0, description="Prix d'entrée en USD")
    take_profit_1: float | None = Field(None, description="TP1 en USD")
    take_profit_2: float | None = Field(None, description="TP2 en USD")


@router.post("/calculate")
async def calculate_risk(req: RiskRequest):
    """Calcule le dimensionnement de position."""
    result = calculate_position(
        bankroll_eur=req.bankroll_eur,
        risk_level=req.risk_level,
        risk_pct_override=req.risk_pct,
        stop_loss_pips=req.stop_loss_pips,
        entry_price=req.entry_price,
        take_profit_1=req.take_profit_1,
        take_profit_2=req.take_profit_2,
    )
    return result


@router.get("/from-analysis")
async def risk_from_analysis(bankroll_eur: float, risk_level: str = "normal"):
    """Calcule le risque à partir de la dernière analyse."""
    analysis = get_latest_analysis()
    if not analysis or not analysis.get("entry"):
        raise HTTPException(status_code=404, detail="Aucune analyse avec entrée disponible")

    entry = analysis["entry"]
    sl = analysis.get("stop_loss")
    tp1 = analysis.get("take_profit_1")
    tp2 = analysis.get("take_profit_2")

    if not sl:
        raise HTTPException(status_code=400, detail="Stop loss non défini dans l'analyse")

    sl_distance = abs(entry - sl)

    result = calculate_position(
        bankroll_eur=bankroll_eur,
        risk_level=risk_level,
        stop_loss_pips=sl_distance,
        entry_price=entry,
        take_profit_1=tp1,
        take_profit_2=tp2,
    )
    result["analysis_direction"] = analysis.get("direction")
    result["analysis_confidence"] = analysis.get("confidence")
    return result
