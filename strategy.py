"""
Strategie: RSI Mean Reversion + Bollinger Bands

Logik:
  LONG:  RSI erholt sich von Überverkauft (< 30 → > 35) UND Preis nahe/unter unterem BB
  SHORT: RSI fällt von Überkauft (> 70 → < 65) UND Preis nahe/über oberem BB

Ziel:    Rückkehr zum Bollinger-Mittelpunkt (BB-Mitte = 20-SMA)
Stop:    1.5 × ATR(14) unter/über Einstieg
Breakeven: Stop auf Entry wenn Profit ≥ 1.0 × ATR
"""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Optional

import numpy as np
import pandas as pd

from config import Config

logger = logging.getLogger(__name__)


class Signal(Enum):
    LONG = "BUY"
    SHORT = "SELL"
    NONE = "NONE"


@dataclass
class TradeSetup:
    signal: Signal
    entry_price: float
    stop_loss: float
    take_profit: float
    atr: float
    rsi: float
    bb_upper: float
    bb_lower: float
    bb_mid: float

    def stop_distance(self) -> float:
        return abs(self.entry_price - self.stop_loss)

    def target_distance(self) -> float:
        return abs(self.take_profit - self.entry_price)

    def risk_reward(self) -> float:
        if self.stop_distance() == 0:
            return 0.0
        return self.target_distance() / self.stop_distance()


def candles_to_dataframe(candles: list[dict]) -> pd.DataFrame:
    """Konvertiert IG-Kerzen-API-Antwort in einen DataFrame."""
    rows = []
    for c in candles:
        try:
            rows.append(
                {
                    "time": c.get("snapshotTime", ""),
                    "open": float(c["openPrice"]["bid"]),
                    "high": float(c["highPrice"]["bid"]),
                    "low": float(c["lowPrice"]["bid"]),
                    "close": float(c["closePrice"]["bid"]),
                    "volume": float(c.get("lastTradedVolume", 0) or 0),
                }
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Kerze übersprungen wegen Parsing-Fehler: %s", exc)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
    return df


def _rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def _bollinger_bands(series: pd.Series, period: int, num_std: float) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Gibt (upper, mid, lower) zurück."""
    mid = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    high = df["high"]
    low = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Fügt RSI, Bollinger Bands und ATR zum DataFrame hinzu."""
    df = df.copy()
    df["rsi"] = _rsi(df["close"], Config.RSI_PERIOD)
    bb_upper, bb_mid, bb_lower = _bollinger_bands(df["close"], Config.BB_PERIOD, Config.BB_STDDEV)
    df["bb_upper"] = bb_upper
    df["bb_mid"] = bb_mid
    df["bb_lower"] = bb_lower
    df["atr"] = _atr(df, Config.ATR_PERIOD)
    return df


def detect_signal(df: pd.DataFrame) -> Optional[Signal]:
    """
    Erkennt RSI Mean Reversion Signal.

    LONG:  RSI war unter RSI_OVERSOLD (vorherige Kerze) und ist jetzt über RSI_OVERSOLD_EXIT
           UND Preis ist unter oder nahe unterem Bollinger Band (innerhalb 0.5 × ATR)

    SHORT: RSI war über RSI_OVERBOUGHT (vorherige Kerze) und ist jetzt unter RSI_OVERBOUGHT_EXIT
           UND Preis ist über oder nahe oberem Bollinger Band (innerhalb 0.5 × ATR)
    """
    if len(df) < Config.BB_PERIOD + 5:
        return None

    # -3: zwei Kerzen zurück, -2: letzte abgeschlossene, -1: laufende Kerze
    prev = df.iloc[-3]
    curr = df.iloc[-2]

    rsi_prev = prev["rsi"]
    rsi_curr = curr["rsi"]
    close = curr["close"]
    bb_upper = curr["bb_upper"]
    bb_lower = curr["bb_lower"]
    atr = curr["atr"]

    if any(pd.isna(x) for x in [rsi_prev, rsi_curr, bb_upper, bb_lower, atr]):
        return None

    # LONG: RSI erholt sich aus Überverkauft-Zone
    rsi_long_trigger = rsi_prev < Config.RSI_OVERSOLD and rsi_curr > Config.RSI_OVERSOLD_EXIT
    price_near_lower_bb = close <= bb_lower + 0.5 * atr

    if rsi_long_trigger and price_near_lower_bb:
        logger.info(
            "LONG-Signal: RSI %.1f → %.1f (Oversold-Recovery) | Close=%.2f | BB_lower=%.2f",
            rsi_prev, rsi_curr, close, bb_lower,
        )
        return Signal.LONG

    # SHORT: RSI fällt aus Überkauft-Zone
    rsi_short_trigger = rsi_prev > Config.RSI_OVERBOUGHT and rsi_curr < Config.RSI_OVERBOUGHT_EXIT
    price_near_upper_bb = close >= bb_upper - 0.5 * atr

    if rsi_short_trigger and price_near_upper_bb:
        logger.info(
            "SHORT-Signal: RSI %.1f → %.1f (Overbought-Recovery) | Close=%.2f | BB_upper=%.2f",
            rsi_prev, rsi_curr, close, bb_upper,
        )
        return Signal.SHORT

    return None


def generate_trade_setup(df: pd.DataFrame, current_price: float) -> Optional[TradeSetup]:
    """
    Analysiert den DataFrame und erzeugt ein TradeSetup wenn ein Signal vorliegt.
    Take Profit = Bollinger Band Mittellinie (Mean Reversion Ziel).
    """
    df = add_indicators(df)
    signal = detect_signal(df)

    if signal is None or signal == Signal.NONE:
        return None

    last = df.iloc[-2]
    atr = float(last["atr"])
    bb_mid = float(last["bb_mid"])
    bb_upper = float(last["bb_upper"])
    bb_lower = float(last["bb_lower"])

    if atr == 0 or np.isnan(atr):
        logger.warning("ATR = 0 oder NaN, Signal verworfen")
        return None

    stop_dist = Config.ATR_STOP_MULTIPLIER * atr

    if signal == Signal.LONG:
        stop_loss = current_price - stop_dist
        take_profit = bb_mid  # Ziel: Rückkehr zur Mitte
    else:
        stop_loss = current_price + stop_dist
        take_profit = bb_mid  # Ziel: Rückkehr zur Mitte

    setup = TradeSetup(
        signal=signal,
        entry_price=current_price,
        stop_loss=round(stop_loss, 2),
        take_profit=round(take_profit, 2),
        atr=round(atr, 4),
        rsi=round(float(last["rsi"]), 2),
        bb_upper=round(bb_upper, 2),
        bb_lower=round(bb_lower, 2),
        bb_mid=round(bb_mid, 2),
    )

    logger.info(
        "Trade-Setup: %s | Entry=%.2f | SL=%.2f | TP=%.2f (BB-Mid) | ATR=%.4f | R/R=%.2f",
        signal.value,
        setup.entry_price,
        setup.stop_loss,
        setup.take_profit,
        setup.atr,
        setup.risk_reward(),
    )
    return setup


def check_trailing_stop(
    position_direction: str,
    entry_price: float,
    current_price: float,
    current_stop: float,
    atr: float,
) -> Optional[float]:
    """
    Setzt Stop auf Breakeven wenn Profit ≥ 1× ATR.
    Kein weiteres Trailing – bei Mean Reversion ist das Ziel das BB-Mittel,
    daher reicht Breakeven-Schutz.
    """
    breakeven_trigger = Config.ATR_BREAKEVEN_MULTIPLIER * atr

    if position_direction == "BUY":
        profit = current_price - entry_price
        if profit >= breakeven_trigger and current_stop < entry_price:
            new_stop = round(entry_price + 0.01, 2)
            logger.info(
                "Breakeven: LONG | Entry=%.2f | Profit=%.2f | neuer Stop=%.2f",
                entry_price, profit, new_stop,
            )
            return new_stop

    elif position_direction == "SELL":
        profit = entry_price - current_price
        if profit >= breakeven_trigger and current_stop > entry_price:
            new_stop = round(entry_price - 0.01, 2)
            logger.info(
                "Breakeven: SHORT | Entry=%.2f | Profit=%.2f | neuer Stop=%.2f",
                entry_price, profit, new_stop,
            )
            return new_stop

    return None
