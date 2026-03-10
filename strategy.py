"""
Strategie: Supertrend + ATR

Supertrend(10, 3.0) bestimmt Trend-Richtung.
Signal:   Richtungswechsel des Supertrend (bearisch→bullisch = LONG, umgekehrt = SHORT)
Stop:     ATR_STOP_MULTIPLIER × ATR unter/über Einstieg
TP:       ATR_TP_MULTIPLIER × ATR unter/über Einstieg  (Standard R/R = 2.0)
Breakeven: Stop auf Entry wenn Profit ≥ ATR_BREAKEVEN_MULTIPLIER × ATR
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
    LONG  = "BUY"
    SHORT = "SELL"
    NONE  = "NONE"


@dataclass
class TradeSetup:
    signal:      Signal
    entry_price: float
    stop_loss:   float
    take_profit: float
    atr:         float
    supertrend:  float

    def stop_distance(self) -> float:
        return abs(self.entry_price - self.stop_loss)

    def target_distance(self) -> float:
        return abs(self.take_profit - self.entry_price)

    def risk_reward(self) -> float:
        if self.stop_distance() == 0:
            return 0.0
        return self.target_distance() / self.stop_distance()


# ---------------------------------------------------------------------------
# Daten-Konvertierung
# ---------------------------------------------------------------------------

def candles_to_dataframe(candles: list[dict]) -> pd.DataFrame:
    """Konvertiert IG-Kerzen-API-Antwort in einen DataFrame."""
    rows = []
    for c in candles:
        try:
            rows.append({
                "time":   c.get("snapshotTime", ""),
                "open":   float(c["openPrice"]["bid"]),
                "high":   float(c["highPrice"]["bid"]),
                "low":    float(c["lowPrice"]["bid"]),
                "close":  float(c["closePrice"]["bid"]),
                "volume": float(c.get("lastTradedVolume", 0) or 0),
            })
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Kerze übersprungen: %s", exc)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    df["time"] = pd.to_datetime(df["time"], errors="coerce")
    df = df.dropna(subset=["time"]).sort_values("time").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Indikatoren
# ---------------------------------------------------------------------------

def _atr(df: pd.DataFrame, period: int) -> pd.Series:
    high       = df["high"]
    low        = df["low"]
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low  - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def _supertrend(df: pd.DataFrame, period: int, multiplier: float):
    """
    Berechnet Supertrend-Indikator.
    Gibt (supertrend_series, direction_series) zurück.
    direction: +1 = bullisch (LONG), -1 = bärisch (SHORT)
    """
    close = df["close"].values
    high  = df["high"].values
    low   = df["low"].values
    n     = len(df)

    atr_vals    = _atr(df, period).values
    hl2         = (high + low) / 2.0
    basic_upper = hl2 + multiplier * atr_vals
    basic_lower = hl2 - multiplier * atr_vals

    final_upper = np.full(n, np.nan)
    final_lower = np.full(n, np.nan)
    supertrend  = np.full(n, np.nan)
    direction   = np.zeros(n, dtype=int)

    # Ersten gültigen Index finden
    start = period
    while start < n and np.isnan(atr_vals[start]):
        start += 1
    if start >= n:
        return pd.Series(supertrend, index=df.index), pd.Series(direction, index=df.index)

    final_upper[start] = basic_upper[start]
    final_lower[start] = basic_lower[start]
    supertrend[start]  = basic_upper[start]
    direction[start]   = -1

    for i in range(start + 1, n):
        if np.isnan(atr_vals[i]):
            final_upper[i] = final_upper[i - 1]
            final_lower[i] = final_lower[i - 1]
            supertrend[i]  = supertrend[i - 1]
            direction[i]   = direction[i - 1]
            continue

        # Final Upper: nur absenken (Widerstand rückt nicht nach oben)
        if basic_upper[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1]:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = final_upper[i - 1]

        # Final Lower: nur anheben (Support rückt nicht nach unten)
        if basic_lower[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1]:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = final_lower[i - 1]

        # Supertrend Richtung
        if direction[i - 1] == -1:
            if close[i] > final_upper[i]:
                direction[i]  = 1
                supertrend[i] = final_lower[i]
            else:
                direction[i]  = -1
                supertrend[i] = final_upper[i]
        else:
            if close[i] < final_lower[i]:
                direction[i]  = -1
                supertrend[i] = final_upper[i]
            else:
                direction[i]  = 1
                supertrend[i] = final_lower[i]

    return pd.Series(supertrend, index=df.index), pd.Series(direction, index=df.index)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Fügt Supertrend, ATR zum DataFrame hinzu."""
    df = df.copy()
    df["atr"] = _atr(df, Config.SUPERTREND_PERIOD)
    st, st_dir = _supertrend(df, Config.SUPERTREND_PERIOD, Config.SUPERTREND_MULTIPLIER)
    df["supertrend"] = st
    df["st_dir"]     = st_dir
    return df


# ---------------------------------------------------------------------------
# Signal-Erkennung
# ---------------------------------------------------------------------------

def detect_signal(df: pd.DataFrame) -> Optional[Signal]:
    """
    Supertrend Richtungswechsel = Signal.
    LONG:  st_dir wechselt von -1 → +1 (bearisch → bullisch)
    SHORT: st_dir wechselt von +1 → -1 (bullisch → bärisch)
    """
    if len(df) < Config.SUPERTREND_PERIOD + 3:
        return None

    prev = df.iloc[-3]
    curr = df.iloc[-2]

    if pd.isna(prev["st_dir"]) or pd.isna(curr["st_dir"]):
        return None

    prev_dir = int(prev["st_dir"])
    curr_dir = int(curr["st_dir"])

    if prev_dir == -1 and curr_dir == 1:
        logger.info(
            "LONG-Signal: Supertrend bullisch | Close=%.2f | ST=%.2f | ATR=%.2f",
            float(curr["close"]), float(curr["supertrend"]), float(curr["atr"]),
        )
        return Signal.LONG

    if prev_dir == 1 and curr_dir == -1:
        logger.info(
            "SHORT-Signal: Supertrend bärisch | Close=%.2f | ST=%.2f | ATR=%.2f",
            float(curr["close"]), float(curr["supertrend"]), float(curr["atr"]),
        )
        return Signal.SHORT

    return None


# ---------------------------------------------------------------------------
# Trade-Setup
# ---------------------------------------------------------------------------

def generate_trade_setup(df: pd.DataFrame, current_price: float) -> Optional[TradeSetup]:
    """Erzeugt TradeSetup auf Basis des Supertrend-Signals."""
    df     = add_indicators(df)
    signal = detect_signal(df)

    if signal is None or signal == Signal.NONE:
        return None

    last = df.iloc[-2]
    atr  = float(last["atr"])
    st   = float(last["supertrend"])

    if atr == 0 or np.isnan(atr):
        logger.warning("ATR = 0 oder NaN, Signal verworfen")
        return None

    stop_dist = Config.ATR_STOP_MULTIPLIER * atr
    tp_dist   = Config.ATR_TP_MULTIPLIER   * atr

    if signal == Signal.LONG:
        stop_loss   = current_price - stop_dist
        take_profit = current_price + tp_dist
    else:
        stop_loss   = current_price + stop_dist
        take_profit = current_price - tp_dist

    setup = TradeSetup(
        signal      = signal,
        entry_price = current_price,
        stop_loss   = round(stop_loss,   2),
        take_profit = round(take_profit, 2),
        atr         = round(atr, 4),
        supertrend  = round(st,  2),
    )

    logger.info(
        "Trade-Setup: %s | Entry=%.2f | SL=%.2f | TP=%.2f | ATR=%.2f | R/R=%.2f",
        signal.value, setup.entry_price, setup.stop_loss,
        setup.take_profit, setup.atr, setup.risk_reward(),
    )
    return setup


# ---------------------------------------------------------------------------
# Trailing Stop (Breakeven)
# ---------------------------------------------------------------------------

def check_trailing_stop(
    position_direction: str,
    entry_price:        float,
    current_price:      float,
    current_stop:       float,
    atr:                float,
) -> Optional[float]:
    """Setzt Stop auf Breakeven wenn Profit ≥ ATR_BREAKEVEN_MULTIPLIER × ATR."""
    trigger = Config.ATR_BREAKEVEN_MULTIPLIER * atr

    if position_direction == "BUY":
        profit = current_price - entry_price
        if profit >= trigger and current_stop < entry_price:
            new_stop = round(entry_price + 0.01, 2)
            logger.info("Breakeven LONG | Entry=%.2f | Profit=%.2f | neuer Stop=%.2f",
                        entry_price, profit, new_stop)
            return new_stop

    elif position_direction == "SELL":
        profit = entry_price - current_price
        if profit >= trigger and current_stop > entry_price:
            new_stop = round(entry_price - 0.01, 2)
            logger.info("Breakeven SHORT | Entry=%.2f | Profit=%.2f | neuer Stop=%.2f",
                        entry_price, profit, new_stop)
            return new_stop

    return None
