"""
Risikomanagement:
- Positionsgröße: Max. 1% Risiko pro Trade vom verfügbaren Kapital
- Prüft maximale Anzahl offener Positionen
- Verhindert Doppel-Entries auf dasselbe Instrument
"""
import logging
import math
from typing import Optional

from config import Config
from strategy import TradeSetup

logger = logging.getLogger(__name__)


def calculate_position_size(
    account_balance: float,
    stop_distance_points: float,
    point_value: float = 1.0,
    min_size: float = 1.0,
    max_size: float = 100.0,
) -> float:
    """
    Berechnet die optimale Positionsgröße basierend auf Risikobudget.

    Formel: Size = (Balance × Risk%) / (StopDistance × PointValue)

    Args:
        account_balance:      Verfügbares Kapital in Kontowährung
        stop_distance_points: Abstand zum Stop in Punkten (Preis-Einheiten)
        point_value:          Wert eines Punkts in Kontowährung (z.B. 1€ pro Punkt bei DAX)
        min_size:             Minimale Handelsgröße des Instruments
        max_size:             Maximale Handelsgröße pro Trade (Sicherheitsbegrenzung)

    Returns:
        Positionsgröße (abgerundet auf gültige Lotgröße)
    """
    if stop_distance_points <= 0 or account_balance <= 0:
        logger.warning(
            "Ungültige Werte für Positionsgrößenberechnung: "
            "balance=%.2f stop_dist=%.4f",
            account_balance, stop_distance_points,
        )
        return min_size

    risk_amount = account_balance * (Config.RISK_PER_TRADE_PCT / 100.0)
    size = risk_amount / (stop_distance_points * point_value)

    # Abrunden auf min_size-Schritte
    size = math.floor(size / min_size) * min_size
    size = max(min_size, min(size, max_size))

    logger.info(
        "Positionsgröße: %.2f | Balance=%.2f | Risiko=%.2f%% (%.2f€) | "
        "StopDist=%.4f | PointValue=%.4f",
        size,
        account_balance,
        Config.RISK_PER_TRADE_PCT,
        risk_amount,
        stop_distance_points,
        point_value,
    )
    return size


def get_point_value(market_details: dict, currency: str = "EUR") -> float:
    """
    Extrahiert den Punkt-Wert aus den IG Marktdetails.
    Fällt auf 1.0 zurück wenn nicht ermittelbar.
    """
    try:
        dealing_rules = market_details.get("dealingRules", {})
        # IG gibt minDealSize als minimale Lot-Einheit
        min_deal = dealing_rules.get("minDealSize", {})
        min_size = float(min_deal.get("value", 1.0))
        return min_size
    except (KeyError, TypeError, ValueError):
        return 1.0


def get_min_deal_size(market_details: dict) -> float:
    """Gibt die minimale Deal-Größe des Instruments zurück."""
    try:
        dealing_rules = market_details.get("dealingRules", {})
        min_deal = dealing_rules.get("minDealSize", {})
        return float(min_deal.get("value", 1.0))
    except (KeyError, TypeError, ValueError):
        return 1.0


class RiskManager:
    def __init__(self):
        self.max_positions = Config.MAX_OPEN_POSITIONS

    def can_open_new_trade(
        self,
        open_positions: list[dict],
        epic: str,
    ) -> tuple[bool, str]:
        """
        Prüft ob ein neuer Trade eröffnet werden darf.
        Returns: (allowed, reason)
        """
        # Zu viele offene Positionen?
        if len(open_positions) >= self.max_positions:
            reason = f"Max. Positionen erreicht ({len(open_positions)}/{self.max_positions})"
            logger.info("Trade blockiert: %s", reason)
            return False, reason

        # Bereits Position auf diesem Instrument?
        for pos in open_positions:
            pos_epic = pos.get("market", {}).get("epic", "")
            if pos_epic == epic:
                reason = f"Bereits eine Position auf {epic} offen"
                logger.info("Trade blockiert: %s", reason)
                return False, reason

        return True, "OK"

    def validate_setup(self, setup: TradeSetup) -> tuple[bool, str]:
        """
        Validiert ein TradeSetup auf Plausibilität.
        """
        if setup.risk_reward() < 1.5:
            return False, f"R/R zu niedrig: {setup.risk_reward():.2f} (Minimum: 1.5)"

        if setup.atr <= 0:
            return False, "ATR ist 0 oder negativ"

        if setup.stop_distance() <= 0:
            return False, "Stop-Distanz ist 0 oder negativ"

        return True, "OK"

    def size_position(
        self,
        setup: TradeSetup,
        account_balance: float,
        market_details: dict,
    ) -> float:
        """Berechnet die Positionsgröße für das gegebene Setup."""
        min_size = get_min_deal_size(market_details)
        point_value = get_point_value(market_details)

        return calculate_position_size(
            account_balance=account_balance,
            stop_distance_points=setup.stop_distance(),
            point_value=point_value,
            min_size=min_size,
            max_size=min_size * 100,  # max. 100x minimale Lot-Größe
        )

    def extract_position_data(self, position: dict) -> dict:
        """
        Extrahiert relevante Daten aus einer IG-Position.
        Returns dict mit: deal_id, direction, size, entry_price, stop_level, limit_level, epic
        """
        pos = position.get("position", {})
        mkt = position.get("market", {})
        return {
            "deal_id": pos.get("dealId", ""),
            "direction": pos.get("direction", ""),
            "size": float(pos.get("size", 0)),
            "entry_price": float(pos.get("openLevel", 0)),
            "stop_level": float(pos.get("stopLevel") or 0),
            "limit_level": float(pos.get("limitLevel") or 0),
            "epic": mkt.get("epic", ""),
            "instrument_name": mkt.get("instrumentName", ""),
            "bid": float(mkt.get("bid", 0)),
            "offer": float(mkt.get("offer", 0)),
        }
