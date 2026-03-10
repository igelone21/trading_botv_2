"""
Telegram-Benachrichtigungen (optional).
Wenn TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID gesetzt sind, werden Alerts gesendet.
"""
import logging

import requests

from config import Config

logger = logging.getLogger(__name__)


def send_telegram(message: str) -> bool:
    """Sendet eine Telegram-Nachricht. Gibt True zurück bei Erfolg."""
    token = Config.TELEGRAM_BOT_TOKEN
    chat_id = Config.TELEGRAM_CHAT_ID
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={"chat_id": chat_id, "text": message, "parse_mode": "Markdown"},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except requests.RequestException as exc:
        logger.warning("Telegram-Fehler: %s", exc)
        return False


def notify_trade_opened(direction: str, epic: str, size: float, entry: float,
                         stop: float, target: float, rr: float) -> None:
    msg = (
        f"🟢 *Trade geöffnet*\n"
        f"Instrument: `{epic}`\n"
        f"Richtung: *{direction}*\n"
        f"Größe: {size}\n"
        f"Entry: {entry:.2f}\n"
        f"Stop Loss: {stop:.2f}\n"
        f"Take Profit: {target:.2f}\n"
        f"R/R: {rr:.2f}"
    )
    send_telegram(msg)


def notify_trade_closed(epic: str, direction: str, pnl_description: str) -> None:
    msg = (
        f"🔴 *Trade geschlossen*\n"
        f"Instrument: `{epic}`\n"
        f"Richtung: {direction}\n"
        f"{pnl_description}"
    )
    send_telegram(msg)


def notify_stop_updated(epic: str, old_stop: float, new_stop: float) -> None:
    msg = (
        f"🔁 *Stop aktualisiert*\n"
        f"Instrument: `{epic}`\n"
        f"Alt: {old_stop:.2f} → Neu: {new_stop:.2f}"
    )
    send_telegram(msg)


def notify_error(message: str) -> None:
    msg = f"⚠️ *Bot-Fehler*\n{message}"
    send_telegram(msg)
