"""
IG Trading Bot V2 – Hauptschleife
Strategie: RSI Mean Reversion + Bollinger Bands

Ablauf jedes Zyklus:
  1. Login-Status prüfen / erneuern
  2. Offene Positionen laden → Breakeven Stop prüfen
  3. Kerzen laden + Indikatoren berechnen
  4. Signal prüfen
  5. Falls Signal + Bedingungen erfüllt → Position öffnen
"""
import logging
import sys
import time
from datetime import datetime, time as dtime
import pytz

import schedule

from config import Config
from ig_api import IGApi, IGApiError
from notifier import notify_error, notify_stop_updated, notify_trade_closed, notify_trade_opened
from risk_manager import RiskManager
from strategy import (
    Signal,
    candles_to_dataframe,
    check_trailing_stop,
    generate_trade_setup,
    add_indicators,
)

# ------------------------------------------------------------------
# Logging einrichten
# ------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(Config.LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("bot_v2")


# ------------------------------------------------------------------
# Bot-Klasse
# ------------------------------------------------------------------

class TradingBotV2:
    def __init__(self):
        self.api = IGApi()
        self.risk = RiskManager()
        self.epic = Config.TRADING_EPIC
        self.resolution = Config.TRADING_RESOLUTION
        self._logged_in = False
        self._login_attempts = 0
        self._max_login_attempts = 5

    # ------------------------------------------------------------------
    # Session-Management
    # ------------------------------------------------------------------

    def ensure_logged_in(self) -> bool:
        if self._logged_in:
            return True
        if self._login_attempts >= self._max_login_attempts:
            logger.critical("Zu viele fehlgeschlagene Login-Versuche. Bot stoppt.")
            notify_error("Bot V2 gestoppt: Zu viele Login-Fehler.")
            sys.exit(1)
        success = self.api.login()
        if success:
            self._logged_in = True
            self._login_attempts = 0
        else:
            self._login_attempts += 1
            logger.error("Login-Versuch %d/%d fehlgeschlagen.", self._login_attempts, self._max_login_attempts)
        return success

    # ------------------------------------------------------------------
    # Breakeven Stop Management
    # ------------------------------------------------------------------

    def manage_open_positions(self, open_positions: list[dict]) -> None:
        """Prüft und setzt Breakeven Stops für alle offenen Positionen."""
        for raw_pos in open_positions:
            pos = self.risk.extract_position_data(raw_pos)
            if pos["epic"] != self.epic:
                continue

            deal_id = pos["deal_id"]
            direction = pos["direction"]
            entry = pos["entry_price"]
            current_stop = pos["stop_level"]
            current_price = pos["bid"] if direction == "BUY" else pos["offer"]

            if current_price == 0 or entry == 0:
                continue

            candles = self.api.get_candles(self.epic, self.resolution, Config.CANDLE_COUNT)
            df = candles_to_dataframe(candles)
            if df.empty or len(df) < Config.BB_PERIOD + 5:
                continue

            df = add_indicators(df)
            current_atr = float(df.iloc[-2]["atr"])

            new_stop = check_trailing_stop(
                position_direction=direction,
                entry_price=entry,
                current_price=current_price,
                current_stop=current_stop,
                atr=current_atr,
            )

            if new_stop is not None and new_stop != current_stop:
                try:
                    self.api.update_stop_limit(deal_id, stop_level=new_stop)
                    notify_stop_updated(self.epic, current_stop, new_stop)
                except IGApiError as exc:
                    logger.error("Stop-Update fehlgeschlagen: %s", exc)

    # ------------------------------------------------------------------
    # Trade-Ausführung
    # ------------------------------------------------------------------

    def is_trading_hours(self) -> bool:
        """Prüft ob aktuelle Zeit innerhalb der Handelszeiten liegt (Mo-Fr 09:00-17:30 MEZ)."""
        tz = pytz.timezone("Europe/Berlin")
        now = datetime.now(tz)
        if now.weekday() >= 5:  # Samstag=5, Sonntag=6
            return False
        market_open = dtime(9, 30)   # Erste 30 Min (09:00-09:30) meiden – zu volatil
        market_close = dtime(17, 15) # Letzte 15 Min vor Schluss meiden
        return market_open <= now.time() <= market_close

    def try_open_trade(self, open_positions: list[dict]) -> None:
        """Prüft Signal und öffnet ggf. eine neue Position."""
        if not self.is_trading_hours():
            logger.info("Außerhalb der Handelszeiten (Mo-Fr 09:30-17:15). Kein neuer Trade.")
            return

        allowed, reason = self.risk.can_open_new_trade(open_positions, self.epic)
        if not allowed:
            logger.debug("Kein neuer Trade: %s", reason)
            return

        candles = self.api.get_candles(self.epic, self.resolution, Config.CANDLE_COUNT)
        df = candles_to_dataframe(candles)
        if df.empty or len(df) < Config.BB_PERIOD + 10:
            logger.warning("Zu wenige Kerzen (%d). Signal-Analyse übersprungen.", len(df))
            return

        bid, offer = self.api.get_current_price(self.epic)
        if bid == 0 or offer == 0:
            logger.warning("Kein gültiger Preis. Übersprungen.")
            return
        mid_price = (bid + offer) / 2

        df = add_indicators(df)
        last = df.iloc[-1]
        logger.info(
            "Indikatoren: RSI=%.1f | Close=%.1f | BB_low=%.1f | BB_high=%.1f | ATR=%.1f | EMA50=%.1f | Trend=%s",
            last.get("rsi", 0), last.get("close", 0),
            last.get("bb_lower", 0), last.get("bb_upper", 0), last.get("atr", 0),
            last.get("ema200", 0),
            "UP" if last.get("close", 0) > last.get("ema200", 0) else "DOWN",
        )

        setup = generate_trade_setup(df, mid_price)
        if setup is None:
            logger.info("Kein Trade-Signal auf %s.", self.epic)
            return

        valid, reason = self.risk.validate_setup(setup)
        if not valid:
            logger.info("Setup verworfen: %s", reason)
            return

        balance_data = self.api.get_account_balance()
        available = float(balance_data.get("available", 0))
        logger.info("Verfügbares Kapital: %.2f€", available)
        if available <= 0:
            logger.error("Kein verfügbares Kapital (%.2f€). Trade abgebrochen.", available)
            return
        if available < Config.MIN_ACCOUNT_BALANCE:
            logger.warning(
                "Kapital zu niedrig: %.2f€ (Minimum: %.2f€). Trade abgebrochen.",
                available, Config.MIN_ACCOUNT_BALANCE,
            )
            return

        market_details = self.api.get_market_details(self.epic)
        size = self.risk.size_position(setup, available, market_details)

        entry_price = offer if setup.signal == Signal.LONG else bid
        stop_distance = abs(entry_price - setup.stop_loss)
        limit_distance = abs(setup.take_profit - entry_price)

        logger.info(
            "Öffne %s %s | Größe=%.2f | Entry≈%.2f | SL=%.2f | TP=%.2f (BB-Mid) | R/R=%.2f",
            setup.signal.value,
            self.epic,
            size,
            entry_price,
            setup.stop_loss,
            setup.take_profit,
            setup.risk_reward(),
        )

        try:
            confirm = self.api.open_position(
                epic=self.epic,
                direction=setup.signal.value,
                size=size,
                stop_distance=stop_distance,
                limit_distance=limit_distance,
            )

            deal_status = confirm.get("dealStatus", "UNKNOWN")
            if deal_status == "ACCEPTED":
                logger.info("Trade ACCEPTED: dealId=%s", confirm.get("dealId"))
                notify_trade_opened(
                    direction=setup.signal.value,
                    epic=self.epic,
                    size=size,
                    entry=entry_price,
                    stop=setup.stop_loss,
                    target=setup.take_profit,
                    rr=setup.risk_reward(),
                )
            else:
                reason = confirm.get("reason", "UNBEKANNT")
                logger.warning("Trade ABGELEHNT: %s | Grund: %s", deal_status, reason)
                notify_error(f"Trade abgelehnt: {deal_status} – {reason}")

        except IGApiError as exc:
            logger.error("Fehler beim Öffnen der Position: %s", exc)
            notify_error(f"API-Fehler beim Trade: {exc}")

    # ------------------------------------------------------------------
    # Haupt-Zyklusfunktion
    # ------------------------------------------------------------------

    def run_cycle(self) -> None:
        logger.info("--- Zyklus start: %s ---", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

        if not self.ensure_logged_in():
            logger.warning("Zyklus übersprungen: kein Login.")
            return

        try:
            open_positions = self.api.get_open_positions()
            logger.info("Offene Positionen: %d", len(open_positions))

            if open_positions:
                self.manage_open_positions(open_positions)

            self.try_open_trade(open_positions)

        except IGApiError as exc:
            logger.error("API-Fehler im Zyklus: %s", exc)
            if "UNAUTHENTICATED" in str(exc).upper() or "SESSION" in str(exc).upper():
                self._logged_in = False
            notify_error(f"Zyklus-Fehler: {exc}")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Unerwarteter Fehler: %s", exc)
            notify_error(f"Unerwarteter Fehler: {exc}")

        logger.info("--- Zyklus end ---")

    # ------------------------------------------------------------------
    # Start
    # ------------------------------------------------------------------

    def start(self) -> None:
        logger.info("=" * 60)
        logger.info("IG Trading Bot V2 startet")
        logger.info("  Strategie:  RSI Mean Reversion + Bollinger Bands")
        logger.info("  Epic:       %s", self.epic)
        logger.info("  Auflösung: %s", self.resolution)
        logger.info("  BB Periode: %d | StdDev: %.1f", Config.BB_PERIOD, Config.BB_STDDEV)
        logger.info("  RSI Oversold: <%.0f → >%.0f", Config.RSI_OVERSOLD, Config.RSI_OVERSOLD_EXIT)
        logger.info("  RSI Overbought: >%.0f → <%.0f", Config.RSI_OVERBOUGHT, Config.RSI_OVERBOUGHT_EXIT)
        logger.info("  Risiko:     %.1f%% pro Trade", Config.RISK_PER_TRADE_PCT)
        logger.info("  Interval:   %ds", Config.CHECK_INTERVAL_SECONDS)
        logger.info("  Account:    %s (%s)", Config.IG_ACCOUNT_ID, Config.IG_ACCOUNT_TYPE)
        logger.info("=" * 60)

        self.run_cycle()

        schedule.every(Config.CHECK_INTERVAL_SECONDS).seconds.do(self.run_cycle)

        while True:
            schedule.run_pending()
            time.sleep(1)


# ------------------------------------------------------------------
# Entry Point
# ------------------------------------------------------------------

if __name__ == "__main__":
    bot = TradingBotV2()
    bot.start()
