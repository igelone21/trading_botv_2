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

    # Strategie-Parameter (Supertrend + ATR)
    SUPERTREND_PERIOD     = 10    # ATR-Periode für Supertrend
    SUPERTREND_MULTIPLIER = 3.0   # Multiplikator (höher = weniger Signale, ruhiger)
    ATR_PERIOD            = 10    # ATR-Periode für Stop/TP (= SUPERTREND_PERIOD)
    ATR_STOP_MULTIPLIER   = 1.5   # Stop  = 1.5 × ATR vom Entry
    ATR_TP_MULTIPLIER     = 3.0   # TP    = 3.0 × ATR vom Entry  →  R/R = 2.0
    ATR_BREAKEVEN_MULTIPLIER = 1.0  # Breakeven wenn Profit ≥ 1 × ATR

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
