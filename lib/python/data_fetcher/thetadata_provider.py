"""ThetaData provider — historical and EOD options data via local Theta Terminal.

Requires Theta Terminal running at localhost:25503.
Start it with: ./lib/thetadata/start_terminal.sh

Free tier: EOD option chains with 1-year lookback, 20 req/min.
No IV/Greeks on free tier — collectors compute their own.
"""

import csv
import io
import socket
import sys
import time
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

import httpx

from .base import (
    DataProvider,
    OHLCV,
    TickerInfo,
    OptionChain,
    OptionContract,
    CryptoPrice,
)

BASE_URL = "http://127.0.0.1:25503"
RATE_LIMIT = 20  # requests per minute (free tier)
REQUEST_TIMEOUT = 120  # seconds — full chains can be large


class ThetaDataProvider(DataProvider):

    def __init__(self):
        self._request_times: deque[float] = deque(maxlen=RATE_LIMIT)

    @property
    def name(self) -> str:
        return "thetadata"

    def is_available(self) -> bool:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            s.connect(("127.0.0.1", 25503))
            s.close()
            return True
        except (ConnectionRefusedError, OSError):
            return False

    def _rate_limit(self):
        """Block until we're under the rate limit ceiling."""
        now = time.monotonic()
        if len(self._request_times) >= RATE_LIMIT:
            oldest = self._request_times[0]
            elapsed = now - oldest
            if elapsed < 60:
                sleep_time = 60 - elapsed + 0.1
                time.sleep(sleep_time)
        self._request_times.append(time.monotonic())

    def _request_csv(self, endpoint: str, params: dict) -> list[dict]:
        """Make a rate-limited GET request and parse CSV response."""
        self._rate_limit()
        url = f"{BASE_URL}{endpoint}"
        params["format"] = "csv"

        try:
            resp = httpx.get(url, params=params, timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                return []
            rows = []
            reader = csv.DictReader(io.StringIO(resp.text))
            for row in reader:
                rows.append(row)
            return rows
        except (httpx.ConnectError, httpx.TimeoutException) as e:
            print(f"ThetaData request failed: {e}", file=sys.stderr)
            return []

    def _parse_option_rows(self, rows: list[dict], underlying_price: float) -> OptionChain:
        """Convert ThetaData CSV rows into an OptionChain."""
        calls = []
        puts = []
        expiries = set()

        for row in rows:
            strike = float(row.get("strike", 0))
            expiry = row.get("expiration", "").strip('"')
            right = row.get("right", "").strip('"').lower()
            bid = float(row.get("bid", 0))
            ask = float(row.get("ask", 0))
            close = float(row.get("close", 0))
            volume = int(row.get("volume", 0))

            if right not in ("call", "put"):
                continue

            expiries.add(expiry)
            contract = OptionContract(
                strike=strike,
                expiry=expiry,
                option_type=right,
                bid=bid,
                ask=ask,
                last=close,
                volume=volume,
                open_interest=0,
                implied_volatility=0.0,
            )
            if right == "call":
                calls.append(contract)
            else:
                puts.append(contract)

        ticker = rows[0].get("symbol", "").strip('"') if rows else ""
        return OptionChain(
            ticker=ticker,
            underlying_price=underlying_price,
            expiries=sorted(expiries),
            calls=calls,
            puts=puts,
        )

    def _fetch_underlying_price(self, ticker: str, date: str) -> float:
        """Get underlying closing price for a date. date format: YYYYMMDD."""
        rows = self._request_csv("/v3/stock/history/eod", {
            "symbol": ticker,
            "start_date": date,
            "end_date": date,
        })
        if rows:
            return float(rows[0].get("close", 0))
        return 0.0

    def fetch_option_chain(
        self,
        ticker: str,
        expiry: Optional[str] = None
    ) -> Optional[OptionChain]:
        today = datetime.now().strftime("%Y%m%d")
        return self.fetch_option_chain_historical(ticker, today, expiry)

    def fetch_option_chain_historical(
        self,
        ticker: str,
        date: str,
        expiry: Optional[str] = None,
    ) -> Optional[OptionChain]:
        """Fetch option chain for a specific historical date.

        Args:
            ticker: Underlying symbol
            date: Date as YYYYMMDD
            expiry: Specific expiry as YYYYMMDD, or None for all
        """
        params = {
            "symbol": ticker,
            "expiration": expiry or "*",
            "strike": "*",
            "right": "both",
            "start_date": date,
            "end_date": date,
        }
        rows = self._request_csv("/v3/option/history/eod", params)
        if not rows:
            return None

        underlying_price = self._fetch_underlying_price(ticker, date)
        return self._parse_option_rows(rows, underlying_price)

    def fetch_ohlcv(
        self,
        ticker: str,
        period: str = "3mo",
        interval: str = "1d"
    ) -> Optional[OHLCV]:
        period_map = {
            "1mo": 30, "3mo": 90, "6mo": 180, "1y": 365, "5y": 1825,
        }
        days = period_map.get(period, 90)
        end = datetime.now()
        start = end - timedelta(days=days)

        rows = self._request_csv("/v3/stock/history/eod", {
            "symbol": ticker,
            "start_date": start.strftime("%Y%m%d"),
            "end_date": end.strftime("%Y%m%d"),
        })
        if not rows:
            return None

        dates = []
        opens = []
        highs = []
        lows = []
        closes = []
        volumes = []
        for row in rows:
            dates.append(row.get("date", ""))
            opens.append(float(row.get("open", 0)))
            highs.append(float(row.get("high", 0)))
            lows.append(float(row.get("low", 0)))
            closes.append(float(row.get("close", 0)))
            volumes.append(float(row.get("volume", 0)))

        return OHLCV(
            dates=dates, open=opens, high=highs,
            low=lows, close=closes, volume=volumes,
        )

    def fetch_ticker_info(self, ticker: str) -> Optional[TickerInfo]:
        today = datetime.now().strftime("%Y%m%d")
        price = self._fetch_underlying_price(ticker, today)
        if price == 0.0:
            return None
        return TickerInfo(
            ticker=ticker,
            price=price,
            market_cap=0.0,
            shares_outstanding=0.0,
        )

    def fetch_crypto_price(self, symbol: str) -> Optional[CryptoPrice]:
        return None  # ThetaData does not cover crypto
