import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # IG API
    IG_USERNAME = os.getenv("IG_USERNAME", "")
    IG_PASSWORD = os.getenv("IG_PASSWORD", "")
    IG_API_KEY = os.getenv("IG_API_KEY", "")
    IG_ACCOUNT_TYPE = os.getenv("IG_ACCOUNT_TYPE", "DEMO")
    IG_ACCOUNT_ID = os.getenv("IG_ACCOUNT_ID", "")

    # IG API Base URLs
    IG_API_URL_LIVE = "https://api.ig.com/gateway/deal"
    IG_API_URL_DEMO = "https://demo-api.ig.com/gateway/deal"

    @classmethod
    def get_api_url(cls) -> str:
        if cls.IG_ACCOUNT_TYPE.upper() == "LIVE":
            return cls.IG_API_URL_LIVE
        return cls.IG_API_URL_DEMO

    # Instrument
    TRADING_EPIC = os.getenv("TRADING_EPIC", "IX.D.DAX.IFD.IP")
    TRADING_RESOLUTION = os.getenv("TRADING_RESOLUTION", "MINUTE_15")

    # Strategie-Parameter (RSI Mean Reversion + Bollinger Bands)
    BB_PERIOD = 20           # Bollinger Band Periode
    BB_STDDEV = 2.0          # Bollinger Band Standardabweichungen
    RSI_PERIOD = 14
    RSI_OVERSOLD = 30.0      # RSI-Level für Überverkauft (Long-Signal)
    RSI_OVERSOLD_EXIT = 35.0 # RSI muss darüber steigen für Long-Entry
    RSI_OVERBOUGHT = 70.0    # RSI-Level für Überkauft (Short-Signal)
    RSI_OVERBOUGHT_EXIT = 65.0  # RSI muss darunter fallen für Short-Entry
    ATR_PERIOD = 14
    ATR_STOP_MULTIPLIER = 1.5
    ATR_BREAKEVEN_MULTIPLIER = 1.0
    EMA_TREND_PERIOD = 50        # 50×15min = ~12h Intraday-Trendfilter (LONG wenn > EMA, SHORT wenn < EMA)

    # Risikomanagement
    RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", "1.0"))
    MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "1"))   # Gleichzeitige Positionen (1 = nur eine auf einmal)
    MIN_ACCOUNT_BALANCE = float(os.getenv("MIN_ACCOUNT_BALANCE", "500.0"))  # Mindestkapital für neuen Trade

    # Wie viele Candles werden geladen
    CANDLE_COUNT = 100

    # Bot-Timing
    CHECK_INTERVAL_SECONDS = int(os.getenv("CHECK_INTERVAL_SECONDS", "60"))

    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

    # Logging
    LOG_FILE = "logs/trading_bot_v2.log"
    LOG_LEVEL = "INFO"
