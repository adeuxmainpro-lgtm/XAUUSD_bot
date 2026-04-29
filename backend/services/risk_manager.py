from backend.config import RISK_LEVELS, GOLD_CONTRACT_SIZE
import logging

logger = logging.getLogger(__name__)

EUR_TO_USD = 1.08  # Taux approximatif EUR/USD (sera mis à jour si disponible)


def calculate_position(
    bankroll_eur: float,
    risk_level: str,
    stop_loss_pips: float,
    entry_price: float,
    take_profit_1: float | None = None,
    take_profit_2: float | None = None,
) -> dict:
    """
    Calcule le dimensionnement de position pour XAUUSD.

    Pour l'or : 1 pip = $0.01, 1 lot standard = 100 oz
    Valeur d'1 pip pour 1 lot = 100 * 0.01 = $1
    Mais en pratique, le spread est en $, donc :
    - Stop loss en $ par oz = stop_loss_pips * 0.1 (si pip = 0.1$)
    - On utilise stop_loss_pips comme distance en USD/oz directement
    """
    risk_pct = RISK_LEVELS.get(risk_level, RISK_LEVELS["normal"])

    # Montant risqué en EUR et USD
    amount_risked_eur = bankroll_eur * risk_pct
    amount_risked_usd = amount_risked_eur * EUR_TO_USD

    # Pour XAUUSD : stop loss en USD (distance en $/oz)
    # 1 lot standard = 100 oz → valeur pip = 100 * pip_value
    stop_loss_usd_per_oz = stop_loss_pips  # on considère que c'est déjà en $/oz

    if stop_loss_usd_per_oz <= 0:
        return {"error": "Stop loss must be > 0"}

    # Taille de position en lots
    lot_size_usd = amount_risked_usd / (stop_loss_usd_per_oz * GOLD_CONTRACT_SIZE)

    # Catégoriser : standard / mini / micro
    lots_standard = lot_size_usd
    lots_mini = lots_standard * 10
    lots_micro = lots_standard * 100

    # Levier (approximatif, basé sur une marge 1:100)
    position_value_usd = lots_standard * GOLD_CONTRACT_SIZE * entry_price
    leverage_used = position_value_usd / (bankroll_eur * EUR_TO_USD) if bankroll_eur > 0 else 0

    # Perte max si SL touché
    max_loss_usd = amount_risked_usd
    max_loss_eur = amount_risked_eur

    # TP en euros
    tp1_profit_eur = None
    tp2_profit_eur = None
    rr_ratio = None

    if take_profit_1 and entry_price:
        tp1_distance = abs(take_profit_1 - entry_price)
        tp1_profit_usd = tp1_distance * lots_standard * GOLD_CONTRACT_SIZE
        tp1_profit_eur = tp1_profit_usd / EUR_TO_USD
        rr_ratio = round(tp1_distance / stop_loss_usd_per_oz, 2) if stop_loss_usd_per_oz else None

    if take_profit_2 and entry_price:
        tp2_distance = abs(take_profit_2 - entry_price)
        tp2_profit_usd = tp2_distance * lots_standard * GOLD_CONTRACT_SIZE
        tp2_profit_eur = tp2_profit_usd / EUR_TO_USD

    return {
        "bankroll_eur": bankroll_eur,
        "risk_level": risk_level,
        "risk_pct": risk_pct * 100,
        "amount_risked_eur": round(amount_risked_eur, 2),
        "amount_risked_usd": round(amount_risked_usd, 2),
        "stop_loss_distance_usd": stop_loss_usd_per_oz,
        "lot_size_standard": round(lots_standard, 3),
        "lot_size_mini": round(lots_mini, 2),
        "lot_size_micro": round(lots_micro, 1),
        "position_value_usd": round(position_value_usd, 2),
        "leverage_used": round(leverage_used, 1),
        "max_loss_usd": round(max_loss_usd, 2),
        "max_loss_eur": round(max_loss_eur, 2),
        "tp1_profit_eur": round(tp1_profit_eur, 2) if tp1_profit_eur else None,
        "tp2_profit_eur": round(tp2_profit_eur, 2) if tp2_profit_eur else None,
        "risk_reward": rr_ratio,
        "entry_price": entry_price,
        "take_profit_1": take_profit_1,
        "take_profit_2": take_profit_2,
    }
