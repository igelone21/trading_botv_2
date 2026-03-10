"""
Backtest: RSI Mean Reversion + Bollinger Bands + EMA200 Trend-Filter
Datenquelle: Yahoo Finance (^GDAXI, 15min)

Aufruf:
    python3 backtest.py
    python3 backtest.py --period 60d
"""
import argparse
import sys

import numpy as np
import pandas as pd
import yfinance as yf

from config import Config
from strategy import add_indicators, detect_signal, Signal


# ---------------------------------------------------------------------------
# Hilfsfunktionen
# ---------------------------------------------------------------------------

def download_data(period: str = "60d") -> pd.DataFrame:
    print(f"Lade DAX 15min-Daten ({period}) von Yahoo Finance ...")
    df = yf.Ticker("^GDAXI").history(period=period, interval="15m")
    if df.empty:
        print("FEHLER: Keine Daten empfangen.")
        sys.exit(1)
    df = df.reset_index().rename(columns={
        "Datetime": "time", "Open": "open", "High": "high",
        "Low": "low", "Close": "close", "Volume": "volume",
    })
    df["time"] = pd.to_datetime(df["time"], utc=True).dt.tz_convert("Europe/Berlin")
    df = df[["time", "open", "high", "low", "close", "volume"]].sort_values("time").reset_index(drop=True)
    print(f"  {len(df)} Kerzen geladen | {df['time'].iloc[0]} → {df['time'].iloc[-1]}")
    return df


def is_trading_hours(ts: pd.Timestamp) -> bool:
    """Mo-Fr 09:30-17:15 MEZ."""
    if ts.weekday() >= 5:
        return False
    t = ts.time()
    from datetime import time as dtime
    return dtime(9, 30) <= t <= dtime(17, 15)


# ---------------------------------------------------------------------------
# Backtest-Engine
# ---------------------------------------------------------------------------

def run_backtest(df: pd.DataFrame, initial_balance: float = 10_000.0) -> dict:
    df = add_indicators(df)
    balance = initial_balance
    trades = []
    open_trade = None

    for i in range(Config.BB_PERIOD + 10, len(df)):
        window = df.iloc[: i + 1]
        ts = df.iloc[i]["time"]
        close = float(df.iloc[i]["close"])

        # Offenen Trade prüfen (Stop/Limit)
        if open_trade:
            high = float(df.iloc[i]["high"])
            low  = float(df.iloc[i]["low"])

            hit_stop  = low  <= open_trade["stop"]  if open_trade["dir"] == "LONG" else high >= open_trade["stop"]
            hit_limit = high >= open_trade["limit"] if open_trade["dir"] == "LONG" else low  <= open_trade["limit"]

            if hit_stop or hit_limit:
                exit_price = open_trade["stop"] if hit_stop else open_trade["limit"]
                pnl = (exit_price - open_trade["entry"]) if open_trade["dir"] == "LONG" else (open_trade["entry"] - exit_price)
                pnl_eur = pnl * open_trade["size"]
                balance += pnl_eur
                trades.append({
                    "entry_time": open_trade["entry_time"],
                    "exit_time":  ts,
                    "dir":        open_trade["dir"],
                    "entry":      open_trade["entry"],
                    "exit":       exit_price,
                    "pnl_pts":    round(pnl, 2),
                    "pnl_eur":    round(pnl_eur, 2),
                    "result":     "WIN" if pnl > 0 else "LOSS",
                })
                open_trade = None

        # Kein offener Trade → Signal prüfen
        if open_trade is None and is_trading_hours(ts):
            signal = detect_signal(window)
            if signal is not None:
                atr  = float(window.iloc[-2]["atr"])
                bb_mid = float(window.iloc[-2]["bb_mid"])
                stop_dist  = Config.ATR_STOP_MULTIPLIER * atr
                risk_eur   = balance * (Config.RISK_PER_TRADE_PCT / 100)
                size       = max(1.0, round(risk_eur / stop_dist, 1)) if stop_dist > 0 else 1.0

                if signal == Signal.LONG:
                    entry = close
                    stop  = round(entry - stop_dist, 2)
                    limit = round(bb_mid, 2)
                else:
                    entry = close
                    stop  = round(entry + stop_dist, 2)
                    limit = round(bb_mid, 2)

                if abs(limit - entry) / stop_dist >= 1.5:  # R/R ≥ 1.5
                    open_trade = {
                        "dir": signal.name, "entry": entry,
                        "stop": stop, "limit": limit,
                        "size": size, "entry_time": ts,
                    }

    # ---------------------------------------------------------------------------
    # Auswertung
    # ---------------------------------------------------------------------------
    if not trades:
        print("\nKeine Trades im Backtest-Zeitraum.")
        return {}

    df_t = pd.DataFrame(trades)
    wins  = df_t[df_t["result"] == "WIN"]
    losses = df_t[df_t["result"] == "LOSS"]
    win_rate = len(wins) / len(df_t) * 100
    gross_profit = wins["pnl_eur"].sum()
    gross_loss   = abs(losses["pnl_eur"].sum())
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")
    total_pnl = df_t["pnl_eur"].sum()
    max_dd = (df_t["pnl_eur"].cumsum() - df_t["pnl_eur"].cumsum().cummax()).min()

    print("\n" + "=" * 55)
    print("  BACKTEST ERGEBNIS")
    print("=" * 55)
    print(f"  Zeitraum:       {df['time'].iloc[0].date()} → {df['time'].iloc[-1].date()}")
    print(f"  Startkapital:   {initial_balance:>10.2f} €")
    print(f"  Endkapital:     {initial_balance + total_pnl:>10.2f} €")
    print(f"  Gesamt P&L:     {total_pnl:>+10.2f} €")
    print(f"  Trades gesamt:  {len(df_t)}")
    print(f"  Wins / Losses:  {len(wins)} / {len(losses)}")
    print(f"  Win-Rate:       {win_rate:.1f}%")
    print(f"  Profit-Faktor:  {profit_factor:.2f}")
    print(f"  Max Drawdown:   {max_dd:.2f} €")
    print(f"  Ø P&L/Trade:    {df_t['pnl_eur'].mean():.2f} €")
    print("=" * 55)

    print("\nLetzte 10 Trades:")
    print(df_t[["entry_time", "dir", "entry", "exit", "pnl_pts", "pnl_eur", "result"]].tail(10).to_string(index=False))

    return {
        "trades": len(df_t), "win_rate": win_rate,
        "profit_factor": profit_factor, "total_pnl": total_pnl,
        "max_drawdown": max_dd,
    }


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backtest RSI+BB+EMA200 Strategie")
    parser.add_argument("--period", default="60d", help="Zeitraum z.B. 30d, 60d (max 60d für 15min)")
    parser.add_argument("--balance", type=float, default=10_000.0, help="Startkapital in €")
    args = parser.parse_args()

    data = download_data(period=args.period)
    run_backtest(data, initial_balance=args.balance)
