from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services.ai_analyst import chat
from backend.database import get_chat_history
import logging

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger(__name__)


class ChatRequest(BaseModel):
    message: str


@router.post("")
async def send_message(req: ChatRequest):
    """Envoie un message au bot IA et retourne la réponse."""
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message vide")
    response = await chat(req.message)
    return {"response": response, "message": req.message}


@router.get("/history")
async def get_history(limit: int = 20):
    """Retourne l'historique de conversation."""
    history = get_chat_history(limit=min(limit, 100))
    return {"history": history}
