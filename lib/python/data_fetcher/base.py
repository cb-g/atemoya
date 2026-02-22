"""
Abstract base class for market data providers.

This module defines the interface that all data providers must implement,
allowing the system to switch between yfinance, IBKR, and other providers.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class OHLCV:
    """OHLCV (Open-High-Low-Close-Volume) data container."""
    dates: list[str]
    open: list[float]
    high: list[float]
    low: list[float]
    close: list[float]
    volume: list[float]

    def __len__(self) -> int:
        return len(self.dates)

    def to_dict(self) -> dict:
        return {
            "dates": self.dates,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
        }


@dataclass
class TickerInfo:
    """Basic ticker information."""
    ticker: str
    price: float
    market_cap: float
    shares_outstanding: float
    currency: str = "USD"
    country: str = "USA"
    industry: str = "Unknown"
    total_debt: float = 0.0

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "price": self.price,
            "market_cap": self.market_cap,
            "shares_outstanding": self.shares_outstanding,
            "currency": self.currency,
            "country": self.country,
            "industry": self.industry,
            "total_debt": self.total_debt,
        }


@dataclass
class OptionContract:
    """Single option contract data."""
    strike: float
    expiry: str
    option_type: str  # "call" or "put"
    bid: float
    ask: float
    last: float
    volume: int
    open_interest: int
    implied_volatility: float


@dataclass
class OptionChain:
    """Option chain for a ticker."""
    ticker: str
    underlying_price: float
    expiries: list[str]
    calls: list[OptionContract]
    puts: list[OptionContract]


@dataclass
class CryptoPrice:
    """Cryptocurrency price data."""
    symbol: str  # e.g., "BTC", "ETH"
    price_usd: float
    market_cap: float
    volume_24h: float
    timestamp: str


@dataclass
class FinancialStatements:
    """Financial statement data (annual)."""
    ticker: str
    currency: str
    # Income statement items
    revenue: list[float]
    operating_income: list[float]
    net_income: list[float]
    ebitda: list[float]
    # Balance sheet items
    total_assets: list[float]
    total_debt: list[float]
    cash: list[float]
    total_equity: list[float]
    # Cash flow items
    operating_cash_flow: list[float]
    capital_expenditure: list[float]
    free_cash_flow: list[float]
    # Dates for each period
    fiscal_years: list[str]

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "currency": self.currency,
            "revenue": self.revenue,
            "operating_income": self.operating_income,
            "net_income": self.net_income,
            "ebitda": self.ebitda,
            "total_assets": self.total_assets,
            "total_debt": self.total_debt,
            "cash": self.cash,
            "total_equity": self.total_equity,
            "operating_cash_flow": self.operating_cash_flow,
            "capital_expenditure": self.capital_expenditure,
            "free_cash_flow": self.free_cash_flow,
            "fiscal_years": self.fiscal_years,
        }


@dataclass
class DividendData:
    """Dividend history and metrics."""
    ticker: str
    dividend_yield: float
    annual_dividend: float
    payout_ratio: float
    dividend_growth_5y: float
    ex_dividend_date: Optional[str]
    dividend_history: list[tuple[str, float]]  # (date, amount)

    def to_dict(self) -> dict:
        return {
            "ticker": self.ticker,
            "dividend_yield": self.dividend_yield,
            "annual_dividend": self.annual_dividend,
            "payout_ratio": self.payout_ratio,
            "dividend_growth_5y": self.dividend_growth_5y,
            "ex_dividend_date": self.ex_dividend_date,
            "dividend_history": self.dividend_history,
        }


@dataclass
class ExtendedTickerInfo(TickerInfo):
    """Extended ticker info with valuation metrics."""
    # Valuation
    pe_ratio: float = 0.0
    forward_pe: float = 0.0
    pb_ratio: float = 0.0
    ps_ratio: float = 0.0
    ev_ebitda: float = 0.0
    # Growth
    revenue_growth: float = 0.0
    earnings_growth: float = 0.0
    # Profitability
    profit_margin: float = 0.0
    operating_margin: float = 0.0
    roe: float = 0.0
    roa: float = 0.0
    # Other
    beta: float = 1.0
    fifty_two_week_high: float = 0.0
    fifty_two_week_low: float = 0.0
    average_volume: int = 0
    sector: str = "Unknown"

    def to_dict(self) -> dict:
        base = super().to_dict()
        base.update({
            "pe_ratio": self.pe_ratio,
            "forward_pe": self.forward_pe,
            "pb_ratio": self.pb_ratio,
            "ps_ratio": self.ps_ratio,
            "ev_ebitda": self.ev_ebitda,
            "revenue_growth": self.revenue_growth,
            "earnings_growth": self.earnings_growth,
            "profit_margin": self.profit_margin,
            "operating_margin": self.operating_margin,
            "roe": self.roe,
            "roa": self.roa,
            "beta": self.beta,
            "fifty_two_week_high": self.fifty_two_week_high,
            "fifty_two_week_low": self.fifty_two_week_low,
            "average_volume": self.average_volume,
            "sector": self.sector,
        })
        return base


class DataProvider(ABC):
    """Abstract base class for market data providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'yfinance', 'ibkr')."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Check if the provider is available and configured."""
        pass

    @abstractmethod
    def fetch_ohlcv(
        self,
        ticker: str,
        period: str = "3mo",
        interval: str = "1d"
    ) -> Optional[OHLCV]:
        """
        Fetch OHLCV data for a ticker.

        Args:
            ticker: Stock/ETF symbol
            period: Time period (e.g., "1mo", "3mo", "1y", "5y")
            interval: Data interval (e.g., "1d", "1h", "5m")

        Returns:
            OHLCV data or None if unavailable
        """
        pass

    @abstractmethod
    def fetch_ticker_info(self, ticker: str) -> Optional[TickerInfo]:
        """
        Fetch basic ticker information.

        Args:
            ticker: Stock/ETF symbol

        Returns:
            TickerInfo or None if unavailable
        """
        pass

    @abstractmethod
    def fetch_option_chain(
        self,
        ticker: str,
        expiry: Optional[str] = None
    ) -> Optional[OptionChain]:
        """
        Fetch option chain for a ticker.

        Args:
            ticker: Underlying symbol
            expiry: Specific expiry date (YYYY-MM-DD) or None for all

        Returns:
            OptionChain or None if unavailable
        """
        pass

    @abstractmethod
    def fetch_crypto_price(self, symbol: str) -> Optional[CryptoPrice]:
        """
        Fetch cryptocurrency price.

        Args:
            symbol: Crypto symbol (e.g., "BTC", "ETH")

        Returns:
            CryptoPrice or None if unavailable
        """
        pass

    def fetch_multiple_ohlcv(
        self,
        tickers: list[str],
        period: str = "3mo",
        interval: str = "1d"
    ) -> dict[str, OHLCV]:
        """
        Fetch OHLCV for multiple tickers.

        Default implementation calls fetch_ohlcv for each ticker.
        Providers can override for batch optimization.
        """
        results = {}
        for ticker in tickers:
            data = self.fetch_ohlcv(ticker, period, interval)
            if data:
                results[ticker] = data
        return results

    def fetch_financial_statements(self, ticker: str) -> Optional["FinancialStatements"]:
        """
        Fetch financial statements (income, balance sheet, cash flow).

        Args:
            ticker: Stock symbol

        Returns:
            FinancialStatements or None if unavailable
        """
        return None  # Default: not supported

    def fetch_extended_info(self, ticker: str) -> Optional["ExtendedTickerInfo"]:
        """
        Fetch extended ticker info with valuation/growth metrics.

        Args:
            ticker: Stock symbol

        Returns:
            ExtendedTickerInfo or None if unavailable
        """
        return None  # Default: not supported

    def fetch_dividends(self, ticker: str) -> Optional["DividendData"]:
        """
        Fetch dividend data and history.

        Args:
            ticker: Stock symbol

        Returns:
            DividendData or None if unavailable
        """
        return None  # Default: not supported
