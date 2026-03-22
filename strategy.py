"""
Strategie: Supertrend + ATR

Logik:
  LONG:  Supertrend wechselt von BEAR → BULL (Trend-Crossover)
  SHORT: Supertrend wechselt von BULL → BEAR (Trend-Crossover)

Stop:    1.5 × ATR(14) unter/über Einstieg
TP:      3.0 × ATR(14) über/unter Einstieg  (R/R = 2.0)
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
    supertrend: float
    trend: int  # 1 = BULL, -1 = BEAR

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


def _rsi(df: pd.DataFrame, period: int) -> pd.Series:
    delta = df["close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


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


def _supertrend(df: pd.DataFrame, period: int, multiplier: float) -> tuple[pd.Series, pd.Series]:
    """
    Berechnet Supertrend-Linie und Trend-Richtung.
    Gibt (supertrend, trend) zurück. trend: 1=BULL, -1=BEAR
    """
    hl2 = (df["high"] + df["low"]) / 2
    atr = _atr(df, period)

    basic_upper = (hl2 + multiplier * atr).tolist()
    basic_lower = (hl2 - multiplier * atr).tolist()
    close = df["close"].tolist()

    final_upper = basic_upper[:]
    final_lower = basic_lower[:]
    supertrend = [np.nan] * len(df)
    trend = [0] * len(df)

    for i in range(1, len(df)):
        # Final Upper Band
        if basic_upper[i] < final_upper[i - 1] or close[i - 1] > final_upper[i - 1]:
            final_upper[i] = basic_upper[i]
        else:
            final_upper[i] = final_upper[i - 1]

        # Final Lower Band
        if basic_lower[i] > final_lower[i - 1] or close[i - 1] < final_lower[i - 1]:
            final_lower[i] = basic_lower[i]
        else:
            final_lower[i] = final_lower[i - 1]

        # Trend bestimmen
        prev_st = supertrend[i - 1]
        if np.isnan(prev_st) or prev_st >= final_upper[i - 1]:
            # War in BEAR
            if close[i] > final_upper[i]:
                supertrend[i] = final_lower[i]
                trend[i] = 1
            else:
                supertrend[i] = final_upper[i]
                trend[i] = -1
        else:
            # War in BULL
            if close[i] < final_lower[i]:
                supertrend[i] = final_upper[i]
                trend[i] = -1
            else:
                supertrend[i] = final_lower[i]
                trend[i] = 1

    return pd.Series(supertrend, index=df.index), pd.Series(trend, index=df.index)


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Fügt Supertrend, Trend, ATR und RSI zum DataFrame hinzu."""
    df = df.copy()
    df["atr"] = _atr(df, Config.ATR_PERIOD)
    st, trend = _supertrend(df, Config.SUPERTREND_PERIOD, Config.SUPERTREND_MULTIPLIER)
    df["supertrend"] = st
    df["trend"] = trend
    df["rsi"] = _rsi(df, Config.RSI_PERIOD)
    return df


def detect_signal(df: pd.DataFrame) -> Optional[Signal]:
    """
    Erkennt Handelssignale auf 2 Arten:

    1. Supertrend-Crossover:
       LONG:  Trend wechselt BEAR (-1) → BULL (1)
       SHORT: Trend wechselt BULL (1) → BEAR (-1)

    2. RSI-Pullback (in-Trend):
       LONG:  Supertrend=BULL und RSI < RSI_OVERSOLD (40)
       SHORT: Supertrend=BEAR und RSI > RSI_OVERBOUGHT (60)
    """
    if len(df) < Config.SUPERTREND_PERIOD + 5:
        return None

    prev = df.iloc[-3]
    curr = df.iloc[-2]

    if any(pd.isna(x) for x in [prev["trend"], curr["trend"], curr["atr"], curr["supertrend"]]):
        return None

    prev_trend = int(prev["trend"])
    curr_trend = int(curr["trend"])
    curr_rsi = float(curr["rsi"]) if not pd.isna(curr.get("rsi", float("nan"))) else float("nan")

    logger.info(
        "Indikatoren: Close=%.1f | Supertrend=%.1f | ATR=%.1f | Trend=%s | RSI=%.1f | prev_trend=%s",
        curr["close"],
        curr["supertrend"],
        curr["atr"],
        "BULL" if curr_trend == 1 else "BEAR",
        curr_rsi if not np.isnan(curr_rsi) else -1,
        "BULL" if prev_trend == 1 else "BEAR",
    )

    # 1) Supertrend-Crossover
    if prev_trend == -1 and curr_trend == 1:
        logger.info("LONG-Signal [Crossover]: Supertrend BEAR → BULL | Close=%.2f | RSI=%.1f", curr["close"], curr_rsi)
        return Signal.LONG

    if prev_trend == 1 and curr_trend == -1:
        logger.info("SHORT-Signal [Crossover]: Supertrend BULL → BEAR | Close=%.2f | RSI=%.1f", curr["close"], curr_rsi)
        return Signal.SHORT

    # 2) RSI-Pullback in Trend-Richtung
    if not np.isnan(curr_rsi):
        if curr_trend == 1 and curr_rsi < Config.RSI_OVERSOLD:
            logger.info(
                "LONG-Signal [RSI-Pullback]: Supertrend=BULL | RSI=%.1f < %d | Close=%.2f",
                curr_rsi, Config.RSI_OVERSOLD, curr["close"],
            )
            return Signal.LONG

        if curr_trend == -1 and curr_rsi > Config.RSI_OVERBOUGHT:
            logger.info(
                "SHORT-Signal [RSI-Pullback]: Supertrend=BEAR | RSI=%.1f > %d | Close=%.2f",
                curr_rsi, Config.RSI_OVERBOUGHT, curr["close"],
            )
            return Signal.SHORT

        logger.info(
            "Kein Signal: Trend=%s | RSI=%.1f (LONG<%.0f / SHORT>%.0f)",
            "BULL" if curr_trend == 1 else "BEAR",
            curr_rsi,
            Config.RSI_OVERSOLD,
            Config.RSI_OVERBOUGHT,
        )
    else:
        logger.info("Kein Signal: RSI nicht verfügbar (Trend=%s)", "BULL" if curr_trend == 1 else "BEAR")

    return None


def generate_trade_setup(df: pd.DataFrame, current_price: float) -> Optional[TradeSetup]:
    """
    Analysiert den DataFrame und erzeugt ein TradeSetup wenn ein Signal vorliegt.
    Stop: 1.5 × ATR | TP: 3.0 × ATR → R/R = 2.0
    """
    df = add_indicators(df)
    signal = detect_signal(df)

    if signal is None or signal == Signal.NONE:
        return None

    last = df.iloc[-2]
    atr = float(last["atr"])
    supertrend_val = float(last["supertrend"])
    trend_val = int(last["trend"])

    if atr == 0 or np.isnan(atr):
        logger.warning("ATR = 0 oder NaN, Signal verworfen")
        return None

    stop_dist = Config.ATR_STOP_MULTIPLIER * atr
    tp_dist = Config.ATR_TP_MULTIPLIER * atr

    if signal == Signal.LONG:
        stop_loss = current_price - stop_dist
        take_profit = current_price + tp_dist
    else:
        stop_loss = current_price + stop_dist
        take_profit = current_price - tp_dist

    setup = TradeSetup(
        signal=signal,
        entry_price=current_price,
        stop_loss=round(stop_loss, 2),
        take_profit=round(take_profit, 2),
        atr=round(atr, 4),
        supertrend=round(supertrend_val, 2),
        trend=trend_val,
    )

    logger.info(
        "Trade-Setup: %s | Entry=%.2f | SL=%.2f | TP=%.2f | ATR=%.4f | R/R=%.2f",
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
