from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.database import (
    save_trade, update_trade, delete_trade,
    get_trades, get_trade_by_id, get_trade_stats,
    get_closed_trades_for_learning,
)

router = APIRouter(prefix="/api/journal", tags=["journal"])


class TradeCreate(BaseModel):
    trade_date: str
    direction: str
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    exit_price: Optional[float] = None
    status: str = "OPEN"
    profit_eur: float = 0.0
    lot_size: float = 0.01
    notes: Optional[str] = None
    rsi_at_entry: Optional[float] = None
    trend_at_entry: Optional[str] = None
    confluence_score: Optional[int] = None


class TradeUpdate(BaseModel):
    trade_date: Optional[str] = None
    direction: Optional[str] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    exit_price: Optional[float] = None
    status: Optional[str] = None
    profit_eur: Optional[float] = None
    lot_size: Optional[float] = None
    notes: Optional[str] = None
    rsi_at_entry: Optional[float] = None
    trend_at_entry: Optional[str] = None
    confluence_score: Optional[int] = None


@router.get("/trades")
def list_trades(limit: int = 100):
    return get_trades(limit)


@router.post("/trades", status_code=201)
def create_trade(trade: TradeCreate):
    trade_id = save_trade(trade.model_dump())
    t = get_trade_by_id(trade_id)
    return t


@router.get("/trades/{trade_id}")
def get_trade(trade_id: int):
    t = get_trade_by_id(trade_id)
    if not t:
        raise HTTPException(status_code=404, detail="Trade non trouvé")
    return t


@router.put("/trades/{trade_id}")
def edit_trade(trade_id: int, trade: TradeUpdate):
    if not get_trade_by_id(trade_id):
        raise HTTPException(status_code=404, detail="Trade non trouvé")
    update_trade(trade_id, {k: v for k, v in trade.model_dump().items() if v is not None})
    return get_trade_by_id(trade_id)


@router.delete("/trades/{trade_id}", status_code=204)
def remove_trade(trade_id: int):
    if not get_trade_by_id(trade_id):
        raise HTTPException(status_code=404, detail="Trade non trouvé")
    delete_trade(trade_id)


@router.get("/stats")
def journal_stats():
    return get_trade_stats()


@router.post("/trades/{trade_id}/analyze")
async def analyze_trade_with_ai(trade_id: int):
    """Ask Claude to analyze a losing trade and identify the error pattern."""
    trade = get_trade_by_id(trade_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade non trouvé")

    from backend.services.ai_analyst import _get_client
    from backend.config import CLAUDE_MODEL

    direction = trade["direction"]
    entry = trade["entry_price"]
    sl = trade.get("stop_loss")
    exit_p = trade.get("exit_price")
    pnl = trade.get("profit_eur", 0)
    rsi = trade.get("rsi_at_entry")
    trend = trade.get("trend_at_entry")
    conf = trade.get("confluence_score")
    status = trade.get("status")
    notes = trade.get("notes", "")

    prompt = f"""Analyse ce trade XAUUSD et identifie les erreurs commises :

Trade : {direction} | Entrée: ${entry} | SL: ${sl} | Sortie: ${exit_p}
Résultat : {status} | P&L: {pnl}€
RSI à l'entrée : {rsi} | Tendance : {trend} | Score confluence : {conf}
Notes du trader : {notes or 'aucune'}

Fournis une analyse structurée :
1. Erreur principale identifiée
2. Contexte de marché défavorable (si détectable)
3. Ce qui aurait dû déclencher l'abstention
4. Règle à appliquer pour éviter ce type de trade à l'avenir
Réponds en français, de façon concise et actionnable."""

    try:
        response = await _get_client().messages.create(
            model=CLAUDE_MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        return {"analysis": response.content[0].text.strip(), "trade_id": trade_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
