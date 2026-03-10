"""
IG Markets REST API Wrapper
Docs: https://labs.ig.com/rest-trading-api-reference
"""
import logging
import time
from typing import Optional

import requests

from config import Config

logger = logging.getLogger(__name__)


class IGApiError(Exception):
    pass


class IGApi:
    def __init__(self):
        self.base_url = Config.get_api_url()
        self.api_key = Config.IG_API_KEY
        self.account_id = Config.IG_ACCOUNT_ID
        self.session_token: Optional[str] = None
        self.client_token: Optional[str] = None
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def login(self) -> bool:
        """Authentifiziert und speichert Session-Tokens."""
        url = f"{self.base_url}/session"
        headers = {
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json; charset=UTF-8",
            "X-IG-API-KEY": self.api_key,
            "Version": "2",
        }
        payload = {
            "identifier": Config.IG_USERNAME,
            "password": Config.IG_PASSWORD,
        }
        try:
            resp = self._session.post(url, json=payload, headers=headers, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            self.session_token = resp.headers.get("X-SECURITY-TOKEN")
            self.client_token = resp.headers.get("CST")
            self.account_id = data.get("currentAccountId", self.account_id)
            logger.info("IG Login erfolgreich. Account: %s", self.account_id)
            return True
        except requests.RequestException as exc:
            logger.error("IG Login fehlgeschlagen: %s", exc)
            return False

    def _headers(self, version: str = "1") -> dict:
        if not self.session_token or not self.client_token:
            raise IGApiError("Nicht eingeloggt. Bitte zuerst login() aufrufen.")
        return {
            "Content-Type": "application/json; charset=UTF-8",
            "Accept": "application/json; charset=UTF-8",
            "X-IG-API-KEY": self.api_key,
            "X-SECURITY-TOKEN": self.session_token,
            "CST": self.client_token,
            "Version": version,
        }

    def _get(self, path: str, version: str = "1", params: dict = None) -> dict:
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.get(
                url, headers=self._headers(version), params=params, timeout=15
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("GET %s fehlgeschlagen: %s", path, exc)
            raise IGApiError(str(exc)) from exc

    def _post(self, path: str, payload: dict, version: str = "1") -> dict:
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.post(
                url, json=payload, headers=self._headers(version), timeout=15
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("POST %s fehlgeschlagen: %s", path, exc)
            raise IGApiError(str(exc)) from exc

    def _put(self, path: str, payload: dict, version: str = "1") -> dict:
        url = f"{self.base_url}{path}"
        try:
            resp = self._session.put(
                url, json=payload, headers=self._headers(version), timeout=15
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("PUT %s fehlgeschlagen: %s", path, exc)
            raise IGApiError(str(exc)) from exc

    def _delete(self, path: str, payload: dict = None, version: str = "1") -> dict:
        url = f"{self.base_url}{path}"
        headers = self._headers(version)
        # IG nutzt DELETE mit Body via POST + _method override
        headers["_method"] = "DELETE"
        try:
            resp = self._session.post(
                url, json=payload or {}, headers=headers, timeout=15
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            logger.error("DELETE %s fehlgeschlagen: %s", path, exc)
            raise IGApiError(str(exc)) from exc

    # ------------------------------------------------------------------
    # Account
    # ------------------------------------------------------------------

    def get_account_balance(self) -> dict:
        """Gibt Kontostand zurück: balance, deposit, profitLoss, available."""
        data = self._get("/accounts", version="1")
        for acc in data.get("accounts", []):
            if acc.get("accountId") == self.account_id:
                return acc.get("balance", {})
        return {}

    # ------------------------------------------------------------------
    # Marktdaten
    # ------------------------------------------------------------------

    def get_candles(self, epic: str, resolution: str, count: int) -> list[dict]:
        """
        Lädt historische Kerzen via Yahoo Finance (^GDAXI).
        resolution wird auf yfinance-Intervall gemappt.
        """
        import yfinance as yf

        interval_map = {
            "MINUTE": "1m", "MINUTE_2": "2m", "MINUTE_5": "5m",
            "MINUTE_15": "15m", "MINUTE_30": "30m",
            "HOUR": "1h", "HOUR_4": "4h", "DAY": "1d",
        }
        interval = interval_map.get(resolution, "15m")
        period = "5d" if "MINUTE" in resolution else "60d"

        ticker = yf.Ticker("^GDAXI")
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            return []

        df = df.tail(count).reset_index()
        candles = []
        for _, row in df.iterrows():
            candles.append({
                "snapshotTime": str(row.get("Datetime", row.get("Date", ""))),
                "openPrice":  {"bid": float(row["Open"]),  "ask": float(row["Open"])},
                "highPrice":  {"bid": float(row["High"]),  "ask": float(row["High"])},
                "lowPrice":   {"bid": float(row["Low"]),   "ask": float(row["Low"])},
                "closePrice": {"bid": float(row["Close"]), "ask": float(row["Close"])},
                "lastTradedVolume": float(row.get("Volume", 0)),
            })
        return candles

    def get_market_details(self, epic: str) -> dict:
        """Gibt Marktdetails inkl. min. Deal Size, Pip-Wert, Spread zurück."""
        data = self._get(f"/markets/{epic}", version="3")
        return data

    def get_current_price(self, epic: str) -> tuple[float, float]:
        """Gibt (bid, offer) des aktuellen Preises zurück."""
        data = self.get_market_details(epic)
        snapshot = data.get("snapshot", {})
        bid = float(snapshot.get("bid", 0))
        offer = float(snapshot.get("offer", 0))
        return bid, offer

    # ------------------------------------------------------------------
    # Positionen
    # ------------------------------------------------------------------

    def get_open_positions(self) -> list[dict]:
        """Gibt alle offenen Positionen zurück."""
        data = self._get("/positions", version="2")
        return data.get("positions", [])

    def open_position(
        self,
        epic: str,
        direction: str,  # "BUY" oder "SELL"
        size: float,
        stop_distance: Optional[float] = None,
        limit_distance: Optional[float] = None,
        guaranteed_stop: bool = False,
        currency: str = "EUR",
    ) -> dict:
        """
        Öffnet eine OTC Position.
        stop_distance / limit_distance in Punkten (relativ zum Einstiegspreis).
        """
        payload = {
            "epic": epic,
            "expiry": "-",
            "direction": direction.upper(),
            "size": str(size),
            "orderType": "MARKET",
            "timeInForce": "FILL_OR_KILL",
            "guaranteedStop": guaranteed_stop,
            "forceOpen": True,
            "currencyCode": currency,
        }
        if stop_distance is not None:
            payload["stopDistance"] = str(round(stop_distance, 2))
        if limit_distance is not None:
            payload["limitDistance"] = str(round(limit_distance, 2))

        result = self._post("/positions/otc", payload, version="2")
        deal_ref = result.get("dealReference", "")
        logger.info(
            "Position geöffnet: %s %s x%s | dealRef=%s", direction, epic, size, deal_ref
        )
        # Deal-Bestätigung abrufen
        time.sleep(1)
        confirm = self.get_deal_confirmation(deal_ref)
        return confirm

    def close_position(self, deal_id: str, direction: str, size: float) -> dict:
        """Schließt eine offene Position."""
        # Gegenteilige Richtung zum Schließen
        close_direction = "SELL" if direction.upper() == "BUY" else "BUY"
        payload = {
            "dealId": deal_id,
            "direction": close_direction,
            "size": str(size),
            "orderType": "MARKET",
            "timeInForce": "FILL_OR_KILL",
        }
        result = self._delete("/positions/otc", payload, version="1")
        logger.info("Position geschlossen: dealId=%s", deal_id)
        return result

    def update_stop_limit(
        self,
        deal_id: str,
        stop_level: Optional[float] = None,
        limit_level: Optional[float] = None,
    ) -> dict:
        """Aktualisiert Stop/Limit einer Position (absoluter Preiswert)."""
        payload = {}
        if stop_level is not None:
            payload["stopLevel"] = str(round(stop_level, 2))
        if limit_level is not None:
            payload["limitLevel"] = str(round(limit_level, 2))
        payload["trailingStop"] = False
        result = self._put(f"/positions/otc/{deal_id}", payload, version="2")
        logger.info("Stop/Limit aktualisiert für %s: stop=%s limit=%s", deal_id, stop_level, limit_level)
        return result

    def get_deal_confirmation(self, deal_reference: str) -> dict:
        """Holt die Deal-Bestätigung."""
        return self._get(f"/confirms/{deal_reference}", version="1")
