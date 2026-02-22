"""
Unified data fetcher with pluggable providers.

Supports multiple data sources:
- yfinance (default, free, no API key required)
- IBKR (Interactive Brokers, requires account and running gateway)

Usage:
    from lib.python.data_fetcher import get_provider, fetch_ohlcv

    # Get default provider (yfinance)
    provider = get_provider()

    # Get specific provider
    provider = get_provider("ibkr")

    # Convenience functions use default provider
    ohlcv = fetch_ohlcv("AAPL", period="3mo")
    info = fetch_ticker_info("AAPL")
    btc = fetch_crypto_price("BTC")

Configuration:
    Set DATA_PROVIDER environment variable to change default:
    - DATA_PROVIDER=yfinance (default)
    - DATA_PROVIDER=ibkr

    For IBKR, also set:
    - IBKR_MODE=tws or portal
    - IBKR_HOST, IBKR_PORT, IBKR_CLIENT_ID (for TWS mode)
    - IBKR_GATEWAY_URL, IBKR_ACCOUNT_ID (for portal mode)
"""

import os
from typing import Optional

from .base import (
    DataProvider,
    OHLCV,
    TickerInfo,
    OptionChain,
    OptionContract,
    CryptoPrice,
    FinancialStatements,
    ExtendedTickerInfo,
    DividendData,
)
from .yfinance_provider import YFinanceProvider
from .ibkr_provider import IBKRProvider

__all__ = [
    "DataProvider",
    "OHLCV",
    "TickerInfo",
    "OptionChain",
    "OptionContract",
    "CryptoPrice",
    "FinancialStatements",
    "ExtendedTickerInfo",
    "DividendData",
    "get_provider",
    "get_available_providers",
    "fetch_ohlcv",
    "fetch_ticker_info",
    "fetch_option_chain",
    "fetch_crypto_price",
    "fetch_financial_statements",
    "fetch_extended_info",
    "fetch_dividends",
]

# Provider registry
_PROVIDERS = {
    "yfinance": YFinanceProvider,
    "ibkr": IBKRProvider,
}

# Cached provider instances
_provider_cache: dict[str, DataProvider] = {}

# Default provider (can be overridden by DATA_PROVIDER env var)
_default_provider: Optional[str] = None


def get_available_providers() -> list[str]:
    """Get list of available provider names."""
    available = []
    for name, cls in _PROVIDERS.items():
        try:
            provider = cls()
            if provider.is_available():
                available.append(name)
        except Exception:
            pass
    return available


def get_provider(name: Optional[str] = None) -> DataProvider:
    """
    Get a data provider instance.

    Args:
        name: Provider name ("yfinance", "ibkr") or None for default

    Returns:
        DataProvider instance

    Raises:
        ValueError: If provider not found or not available
    """
    global _default_provider

    if name is None:
        # Use environment variable or default to yfinance
        name = os.environ.get("DATA_PROVIDER", "yfinance").lower()

    if name not in _PROVIDERS:
        raise ValueError(f"Unknown provider: {name}. Available: {list(_PROVIDERS.keys())}")

    # Return cached instance if available
    if name in _provider_cache:
        return _provider_cache[name]

    # Create new instance
    provider = _PROVIDERS[name]()

    if not provider.is_available():
        # Try fallback to yfinance
        if name != "yfinance":
            print(f"Warning: {name} not available, falling back to yfinance")
            return get_provider("yfinance")
        raise ValueError(f"Provider {name} is not available (missing dependencies or configuration)")

    _provider_cache[name] = provider
    return provider


def set_default_provider(name: str):
    """Set the default provider."""
    global _default_provider
    if name not in _PROVIDERS:
        raise ValueError(f"Unknown provider: {name}")
    _default_provider = name


# Convenience functions using default provider

def fetch_ohlcv(
    ticker: str,
    period: str = "3mo",
    interval: str = "1d",
    provider: Optional[str] = None
) -> Optional[OHLCV]:
    """
    Fetch OHLCV data for a ticker.

    Args:
        ticker: Stock/ETF symbol
        period: Time period ("1mo", "3mo", "6mo", "1y", "5y")
        interval: Bar interval ("1d", "1h", "5m")
        provider: Specific provider name or None for default

    Returns:
        OHLCV data or None if unavailable
    """
    return get_provider(provider).fetch_ohlcv(ticker, period, interval)


def fetch_ticker_info(
    ticker: str,
    provider: Optional[str] = None
) -> Optional[TickerInfo]:
    """
    Fetch basic ticker information.

    Args:
        ticker: Stock/ETF symbol
        provider: Specific provider name or None for default

    Returns:
        TickerInfo or None if unavailable
    """
    return get_provider(provider).fetch_ticker_info(ticker)


def fetch_option_chain(
    ticker: str,
    expiry: Optional[str] = None,
    provider: Optional[str] = None
) -> Optional[OptionChain]:
    """
    Fetch option chain for a ticker.

    Args:
        ticker: Underlying symbol
        expiry: Specific expiry (YYYY-MM-DD) or None for nearest
        provider: Specific provider name or None for default

    Returns:
        OptionChain or None if unavailable
    """
    return get_provider(provider).fetch_option_chain(ticker, expiry)


def fetch_crypto_price(
    symbol: str,
    provider: Optional[str] = None
) -> Optional[CryptoPrice]:
    """
    Fetch cryptocurrency price.

    Args:
        symbol: Crypto symbol ("BTC", "ETH")
        provider: Specific provider name or None for default

    Returns:
        CryptoPrice or None if unavailable
    """
    return get_provider(provider).fetch_crypto_price(symbol)


def fetch_multiple_ohlcv(
    tickers: list[str],
    period: str = "3mo",
    interval: str = "1d",
    provider: Optional[str] = None
) -> dict[str, OHLCV]:
    """
    Fetch OHLCV data for multiple tickers (batch optimized).

    Args:
        tickers: List of stock/ETF symbols
        period: Time period
        interval: Bar interval
        provider: Specific provider name or None for default

    Returns:
        Dictionary mapping ticker to OHLCV data
    """
    return get_provider(provider).fetch_multiple_ohlcv(tickers, period, interval)


def fetch_financial_statements(
    ticker: str,
    provider: Optional[str] = None
) -> Optional[FinancialStatements]:
    """
    Fetch financial statements (income, balance sheet, cash flow).

    Args:
        ticker: Stock symbol
        provider: Specific provider name or None for default

    Returns:
        FinancialStatements or None if unavailable
    """
    return get_provider(provider).fetch_financial_statements(ticker)


def fetch_extended_info(
    ticker: str,
    provider: Optional[str] = None
) -> Optional[ExtendedTickerInfo]:
    """
    Fetch extended ticker info with valuation/growth metrics.

    Args:
        ticker: Stock symbol
        provider: Specific provider name or None for default

    Returns:
        ExtendedTickerInfo or None if unavailable
    """
    return get_provider(provider).fetch_extended_info(ticker)


def fetch_dividends(
    ticker: str,
    provider: Optional[str] = None
) -> Optional[DividendData]:
    """
    Fetch dividend data and history.

    Args:
        ticker: Stock symbol
        provider: Specific provider name or None for default

    Returns:
        DividendData or None if unavailable
    """
    return get_provider(provider).fetch_dividends(ticker)
