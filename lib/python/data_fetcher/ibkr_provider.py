"""
Interactive Brokers (IBKR) data provider implementation.

Uses the IBKR Client Portal API or TWS API for market data.
Requires an IBKR account and API credentials.

Setup:
1. Enable API access in IBKR Account Management
2. Set environment variables:
   - IBKR_HOST: Gateway/TWS host (default: 127.0.0.1)
   - IBKR_PORT: Gateway/TWS port (default: 5000 for live, 5001 for paper)
   - IBKR_CLIENT_ID: Unique client ID (default: 1)

For Client Portal API:
   - IBKR_GATEWAY_URL: Client Portal Gateway URL
   - IBKR_ACCOUNT_ID: Your IBKR account ID

Note: IBKR requires a running gateway (TWS or IB Gateway) for the TWS API,
or the Client Portal Gateway for the REST API.
"""

import os
import sys
from datetime import datetime
from typing import Optional

from .base import (
    DataProvider,
    OHLCV,
    TickerInfo,
    OptionChain,
    OptionContract,
    CryptoPrice,
)

# Try to import ib_insync for TWS API
try:
    from ib_insync import IB, Stock, Option, Forex, Crypto, util
    IB_INSYNC_AVAILABLE = True
except ImportError:
    IB_INSYNC_AVAILABLE = False
    IB = None

# Try to import requests for Client Portal API
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False


class IBKRProvider(DataProvider):
    """
    Interactive Brokers data provider.

    Supports two modes:
    1. TWS API (via ib_insync) - requires TWS or IB Gateway running
    2. Client Portal API (REST) - requires Client Portal Gateway

    Configuration via environment variables:
    - IBKR_MODE: "tws" or "portal" (default: "tws")
    - IBKR_HOST: Host for TWS API (default: 127.0.0.1)
    - IBKR_PORT: Port for TWS API (default: 7497 for TWS paper, 4002 for Gateway paper)
    - IBKR_CLIENT_ID: Client ID for TWS API (default: 1)
    - IBKR_GATEWAY_URL: URL for Client Portal API
    - IBKR_ACCOUNT_ID: Account ID for Client Portal API
    """

    def __init__(self):
        self._ib: Optional[IB] = None
        self._connected = False
        self._mode = os.environ.get("IBKR_MODE", "tws")
        self._host = os.environ.get("IBKR_HOST", "127.0.0.1")
        self._port = int(os.environ.get("IBKR_PORT", "7497"))
        self._client_id = int(os.environ.get("IBKR_CLIENT_ID", "1"))
        self._gateway_url = os.environ.get("IBKR_GATEWAY_URL", "https://localhost:5000/v1/api")
        self._account_id = os.environ.get("IBKR_ACCOUNT_ID", "")

    @property
    def name(self) -> str:
        return "ibkr"

    def is_available(self) -> bool:
        """Check if IBKR is configured and available."""
        if self._mode == "tws":
            return IB_INSYNC_AVAILABLE
        else:
            return REQUESTS_AVAILABLE and bool(self._account_id)

    def _connect_tws(self) -> bool:
        """Connect to TWS/Gateway."""
        if not IB_INSYNC_AVAILABLE:
            return False

        if self._connected and self._ib and self._ib.isConnected():
            return True

        try:
            self._ib = IB()
            self._ib.connect(
                host=self._host,
                port=self._port,
                clientId=self._client_id,
                readonly=True,
            )
            self._connected = True
            return True
        except Exception as e:
            print(f"IBKR TWS connection failed: {e}", file=sys.stderr)
            self._connected = False
            return False

    def _disconnect_tws(self):
        """Disconnect from TWS/Gateway."""
        if self._ib and self._ib.isConnected():
            self._ib.disconnect()
        self._connected = False

    def _portal_request(self, endpoint: str, method: str = "GET", data: dict = None) -> Optional[dict]:
        """Make a Client Portal API request."""
        if not REQUESTS_AVAILABLE:
            return None

        try:
            url = f"{self._gateway_url}/{endpoint}"
            headers = {"Content-Type": "application/json"}

            if method == "GET":
                resp = requests.get(url, headers=headers, verify=False, timeout=10)
            else:
                resp = requests.post(url, headers=headers, json=data, verify=False, timeout=10)

            if resp.status_code == 200:
                return resp.json()
            else:
                print(f"IBKR Portal API error: {resp.status_code} - {resp.text}", file=sys.stderr)
                return None
        except Exception as e:
            print(f"IBKR Portal API request failed: {e}", file=sys.stderr)
            return None

    def fetch_ohlcv(
        self,
        ticker: str,
        period: str = "3mo",
        interval: str = "1d"
    ) -> Optional[OHLCV]:
        """Fetch OHLCV data from IBKR."""
        if self._mode == "tws":
            return self._fetch_ohlcv_tws(ticker, period, interval)
        else:
            return self._fetch_ohlcv_portal(ticker, period, interval)

    def _fetch_ohlcv_tws(
        self,
        ticker: str,
        period: str,
        interval: str
    ) -> Optional[OHLCV]:
        """Fetch OHLCV using TWS API."""
        if not self._connect_tws():
            return None

        try:
            # Convert period to IBKR duration string
            duration_map = {
                "1mo": "1 M",
                "3mo": "3 M",
                "6mo": "6 M",
                "1y": "1 Y",
                "2y": "2 Y",
                "5y": "5 Y",
            }
            duration = duration_map.get(period, "3 M")

            # Convert interval to IBKR bar size
            bar_size_map = {
                "1m": "1 min",
                "5m": "5 mins",
                "15m": "15 mins",
                "1h": "1 hour",
                "1d": "1 day",
                "1wk": "1 week",
            }
            bar_size = bar_size_map.get(interval, "1 day")

            # Create contract
            contract = Stock(ticker, "SMART", "USD")
            self._ib.qualifyContracts(contract)

            # Request historical data
            bars = self._ib.reqHistoricalData(
                contract,
                endDateTime="",
                durationStr=duration,
                barSizeSetting=bar_size,
                whatToShow="TRADES",
                useRTH=True,
            )

            if not bars:
                return None

            return OHLCV(
                dates=[bar.date.strftime("%Y-%m-%d") if hasattr(bar.date, "strftime") else str(bar.date) for bar in bars],
                open=[bar.open for bar in bars],
                high=[bar.high for bar in bars],
                low=[bar.low for bar in bars],
                close=[bar.close for bar in bars],
                volume=[int(bar.volume) for bar in bars],
            )
        except Exception as e:
            print(f"IBKR TWS error fetching {ticker}: {e}", file=sys.stderr)
            return None

    def _fetch_ohlcv_portal(
        self,
        ticker: str,
        period: str,
        interval: str
    ) -> Optional[OHLCV]:
        """Fetch OHLCV using Client Portal API."""
        # Convert period to portal API format
        period_map = {
            "1mo": "1m",
            "3mo": "3m",
            "6mo": "6m",
            "1y": "1y",
            "2y": "2y",
            "5y": "5y",
        }
        portal_period = period_map.get(period, "3m")

        # First, search for the contract
        search_result = self._portal_request(f"iserver/secdef/search?symbol={ticker}&name=false")
        if not search_result or not search_result:
            return None

        conid = search_result[0].get("conid")
        if not conid:
            return None

        # Fetch market data history
        bar_map = {"1d": "1d", "1h": "1h", "1wk": "1w"}
        bar = bar_map.get(interval, "1d")

        data = self._portal_request(f"iserver/marketdata/history?conid={conid}&period={portal_period}&bar={bar}")
        if not data or "data" not in data:
            return None

        bars = data["data"]
        return OHLCV(
            dates=[datetime.fromtimestamp(bar["t"] / 1000).strftime("%Y-%m-%d") for bar in bars],
            open=[bar["o"] for bar in bars],
            high=[bar["h"] for bar in bars],
            low=[bar["l"] for bar in bars],
            close=[bar["c"] for bar in bars],
            volume=[int(bar["v"]) for bar in bars],
        )

    def fetch_ticker_info(self, ticker: str) -> Optional[TickerInfo]:
        """Fetch ticker info from IBKR."""
        if self._mode == "tws":
            return self._fetch_ticker_info_tws(ticker)
        else:
            return self._fetch_ticker_info_portal(ticker)

    def _fetch_ticker_info_tws(self, ticker: str) -> Optional[TickerInfo]:
        """Fetch ticker info using TWS API."""
        if not self._connect_tws():
            return None

        try:
            contract = Stock(ticker, "SMART", "USD")
            self._ib.qualifyContracts(contract)

            # Request fundamental data and current price
            self._ib.reqMktData(contract, "", False, False)
            self._ib.sleep(2)  # Wait for data

            ticker_obj = self._ib.ticker(contract)

            # Get price
            price = ticker_obj.marketPrice()
            if price != price:  # NaN check
                price = ticker_obj.close or 0.0

            # Note: IBKR doesn't provide market cap directly
            # Would need to calculate from price * shares outstanding
            # Shares outstanding requires fundamental data subscription

            return TickerInfo(
                ticker=ticker,
                price=float(price) if price else 0.0,
                market_cap=0.0,  # Not directly available
                shares_outstanding=0.0,  # Requires fundamental data
                currency="USD",
                country="USA",
                industry="Unknown",
            )
        except Exception as e:
            print(f"IBKR TWS error fetching info for {ticker}: {e}", file=sys.stderr)
            return None

    def _fetch_ticker_info_portal(self, ticker: str) -> Optional[TickerInfo]:
        """Fetch ticker info using Client Portal API."""
        # Search for contract
        search_result = self._portal_request(f"iserver/secdef/search?symbol={ticker}&name=false")
        if not search_result:
            return None

        conid = search_result[0].get("conid")
        if not conid:
            return None

        # Get snapshot
        snapshot = self._portal_request(f"iserver/marketdata/snapshot?conids={conid}&fields=31,84,85,86")
        if not snapshot or not snapshot:
            return None

        data = snapshot[0] if snapshot else {}

        return TickerInfo(
            ticker=ticker,
            price=float(data.get("31", 0)),  # Last price
            market_cap=0.0,  # Not available in snapshot
            shares_outstanding=0.0,
            currency="USD",
            country="USA",
            industry="Unknown",
        )

    def fetch_option_chain(
        self,
        ticker: str,
        expiry: Optional[str] = None
    ) -> Optional[OptionChain]:
        """Fetch option chain from IBKR."""
        if self._mode == "tws":
            return self._fetch_option_chain_tws(ticker, expiry)
        else:
            return self._fetch_option_chain_portal(ticker, expiry)

    def _fetch_option_chain_tws(
        self,
        ticker: str,
        expiry: Optional[str] = None
    ) -> Optional[OptionChain]:
        """Fetch option chain using TWS API."""
        if not self._connect_tws():
            return None

        try:
            # Get underlying contract
            stock = Stock(ticker, "SMART", "USD")
            self._ib.qualifyContracts(stock)

            # Get option chain definition
            chains = self._ib.reqSecDefOptParams(stock.symbol, "", stock.secType, stock.conId)
            if not chains:
                return None

            chain = chains[0]  # Use first exchange

            # Get current price
            self._ib.reqMktData(stock, "", False, False)
            self._ib.sleep(1)
            stock_ticker = self._ib.ticker(stock)
            underlying_price = stock_ticker.marketPrice() or stock_ticker.close or 0.0

            calls = []
            puts = []

            # Filter expiries
            expiries = sorted(chain.expirations)[:3]  # Limit to 3 nearest
            if expiry:
                expiries = [exp for exp in expiries if exp == expiry.replace("-", "")]

            # Get strikes around ATM
            all_strikes = sorted(chain.strikes)
            atm_idx = min(range(len(all_strikes)), key=lambda i: abs(all_strikes[i] - underlying_price))
            strikes = all_strikes[max(0, atm_idx - 5):atm_idx + 6]  # 11 strikes around ATM

            for exp in expiries:
                for strike in strikes:
                    for right in ["C", "P"]:
                        opt = Option(ticker, exp, strike, right, "SMART")
                        try:
                            self._ib.qualifyContracts(opt)
                            self._ib.reqMktData(opt, "", False, False)
                        except Exception:
                            continue

            self._ib.sleep(3)  # Wait for data

            for exp in expiries:
                for strike in strikes:
                    for right in ["C", "P"]:
                        opt = Option(ticker, exp, strike, right, "SMART")
                        try:
                            ticker_data = self._ib.ticker(opt)
                            if ticker_data:
                                contract = OptionContract(
                                    strike=strike,
                                    expiry=f"{exp[:4]}-{exp[4:6]}-{exp[6:8]}",
                                    option_type="call" if right == "C" else "put",
                                    bid=float(ticker_data.bid or 0),
                                    ask=float(ticker_data.ask or 0),
                                    last=float(ticker_data.last or 0),
                                    volume=int(ticker_data.volume or 0),
                                    open_interest=0,  # Not in real-time data
                                    implied_volatility=float(ticker_data.modelGreeks.impliedVol if ticker_data.modelGreeks else 0),
                                )
                                if right == "C":
                                    calls.append(contract)
                                else:
                                    puts.append(contract)
                        except Exception:
                            continue

            return OptionChain(
                ticker=ticker,
                underlying_price=float(underlying_price),
                expiries=[f"{exp[:4]}-{exp[4:6]}-{exp[6:8]}" for exp in expiries],
                calls=calls,
                puts=puts,
            )
        except Exception as e:
            print(f"IBKR TWS error fetching options for {ticker}: {e}", file=sys.stderr)
            return None

    def _fetch_option_chain_portal(
        self,
        ticker: str,
        expiry: Optional[str] = None
    ) -> Optional[OptionChain]:
        """Fetch option chain using Client Portal API."""
        # Search for underlying
        search_result = self._portal_request(f"iserver/secdef/search?symbol={ticker}&name=false")
        if not search_result:
            return None

        conid = search_result[0].get("conid")
        if not conid:
            return None

        # Get option chain strikes
        strikes_data = self._portal_request(f"iserver/secdef/strikes?conid={conid}&sectype=OPT")
        if not strikes_data:
            return None

        # This is a simplified implementation
        # Full implementation would iterate through strikes and expiries
        return None  # Portal API option chain is complex, implement as needed

    def fetch_crypto_price(self, symbol: str) -> Optional[CryptoPrice]:
        """Fetch crypto price from IBKR."""
        if self._mode == "tws":
            return self._fetch_crypto_price_tws(symbol)
        else:
            return self._fetch_crypto_price_portal(symbol)

    def _fetch_crypto_price_tws(self, symbol: str) -> Optional[CryptoPrice]:
        """Fetch crypto price using TWS API."""
        if not self._connect_tws():
            return None

        try:
            # IBKR crypto contract
            crypto = Crypto(symbol, "PAXOS", "USD")
            self._ib.qualifyContracts(crypto)

            self._ib.reqMktData(crypto, "", False, False)
            self._ib.sleep(2)

            ticker_data = self._ib.ticker(crypto)
            price = ticker_data.marketPrice()
            if price != price:  # NaN
                price = ticker_data.close or 0.0

            return CryptoPrice(
                symbol=symbol,
                price_usd=float(price),
                market_cap=0.0,  # Not available
                volume_24h=float(ticker_data.volume or 0),
                timestamp=datetime.now().isoformat(),
            )
        except Exception as e:
            print(f"IBKR TWS error fetching crypto {symbol}: {e}", file=sys.stderr)
            return None

    def _fetch_crypto_price_portal(self, symbol: str) -> Optional[CryptoPrice]:
        """Fetch crypto price using Client Portal API."""
        # Search for crypto contract
        search_result = self._portal_request(f"iserver/secdef/search?symbol={symbol}&name=false&secType=CRYPTO")
        if not search_result:
            return None

        conid = search_result[0].get("conid")
        if not conid:
            return None

        # Get snapshot
        snapshot = self._portal_request(f"iserver/marketdata/snapshot?conids={conid}&fields=31")
        if not snapshot:
            return None

        data = snapshot[0] if snapshot else {}

        return CryptoPrice(
            symbol=symbol,
            price_usd=float(data.get("31", 0)),
            market_cap=0.0,
            volume_24h=0.0,
            timestamp=datetime.now().isoformat(),
        )

    def __del__(self):
        """Cleanup on deletion."""
        self._disconnect_tws()
