"""
Yahoo Finance utilities for fetching market data.

This module provides common functions for extracting data from yfinance,
avoiding code duplication across valuation modules.
"""

from typing import Any, Optional
import sys

import yfinance as yf


def get_ticker(symbol: str) -> Any:
    """
    Get a yfinance Ticker object for a symbol.

    Args:
        symbol: Stock ticker symbol (e.g., 'AAPL')

    Returns:
        yfinance Ticker object
    """
    return yf.Ticker(symbol)


def fetch_market_data(ticker_obj: Any, ticker_symbol: str) -> dict[str, Any]:
    """
    Extract market data from yfinance ticker.

    Args:
        ticker_obj: yfinance Ticker object
        ticker_symbol: The ticker symbol string

    Returns:
        Dictionary containing:
        - ticker: Symbol string
        - price: Current stock price
        - mve: Market value of equity (market cap)
        - mvb: Market value of debt (total debt)
        - shares_outstanding: Number of shares
        - currency: Trading currency
        - country: Company country
        - industry: Company industry
    """
    info = ticker_obj.info

    return {
        "ticker": ticker_symbol,
        "price": info.get("currentPrice", info.get("regularMarketPrice", 0.0)),
        "mve": info.get("marketCap", 0.0),
        "mvb": info.get("totalDebt", 0.0),
        "shares_outstanding": info.get("sharesOutstanding", 0.0),
        "currency": info.get("currency", "USD"),
        "country": info.get("country", "USA"),
        "industry": info.get("industry", "Unknown"),
    }


def safe_get_value(
    data: dict[str, Any],
    keys: list[str],
    default: float = 0.0
) -> float:
    """
    Safely get a numeric value from a dictionary, trying multiple keys.

    Args:
        data: Dictionary to search
        keys: List of keys to try in order
        default: Default value if no key found or value is NaN

    Returns:
        The first valid numeric value found, or default
    """
    for key in keys:
        val = data.get(key)
        if val is not None and val == val:  # val == val is False for NaN
            try:
                return float(val)
            except (ValueError, TypeError):
                continue
    return default


def get_financial_value(
    df: Any,
    field_names: list[str],
    default: float = 0.0
) -> float:
    """
    Get a value from a financial statement DataFrame.

    Tries multiple field names to handle variations in yfinance data.

    Args:
        df: pandas DataFrame from yfinance (income_stmt, balance_sheet, etc.)
        field_names: List of possible field names to try
        default: Default value if field not found

    Returns:
        The most recent value for the field, or default
    """
    if df is None or df.empty:
        return default

    for field in field_names:
        if field in df.index:
            val = df.loc[field].iloc[0]
            if val is not None and val == val:  # Check for NaN
                try:
                    return float(val)
                except (ValueError, TypeError):
                    continue
    return default
