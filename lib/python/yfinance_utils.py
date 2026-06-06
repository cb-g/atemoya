"""
Yahoo Finance utilities for fetching market data.

This module provides common functions for extracting data from yfinance,
avoiding code duplication across valuation modules.
"""

from typing import Any, Optional
import functools
import math
import sys

import yfinance as yf


@functools.lru_cache(maxsize=512)
def fx_rate(from_ccy: str, to_ccy: str) -> Optional[float]:
    """Spot FX rate: units of ``to_ccy`` per 1 unit of ``from_ccy``.

    Returns 1.0 when the currencies match or are empty, and None when the rate
    cannot be fetched (the caller should *flag* the result rather than silently
    assume 1.0, which would re-introduce the cross-currency bug). Cached per
    process, so each currency pair costs at most one network call.
    """
    f = (from_ccy or "").upper()
    t = (to_ccy or "").upper()
    if not f or not t or f == t:
        return 1.0

    def _quote(symbol: str) -> Optional[float]:
        try:
            tk = yf.Ticker(symbol)
            rate = None
            try:
                rate = float(tk.fast_info["lastPrice"])
            except Exception:
                rate = None
            if not rate or rate != rate or rate <= 0:  # NaN/None/non-positive
                info = tk.info
                r = info.get("regularMarketPrice") or info.get("currentPrice")
                rate = float(r) if r else None
            return rate if (rate and rate == rate and rate > 0) else None
        except Exception:
            return None

    # Try the direct pair, then the inverse (some exotic pairs, e.g. tenge, are
    # only quoted in one direction on Yahoo).
    rate = _quote(f"{f}{t}=X")
    if rate is None:
        inv = _quote(f"{t}{f}=X")
        rate = (1.0 / inv) if inv else None
    return rate


def financial_fx_factor(info: dict) -> tuple[float, str, str, bool]:
    """Factor to convert financial-statement-currency amounts onto the trading
    (price) currency basis, with (factor, trading_ccy, financial_ccy, ok).

    factor == 1.0 in the common case where the two currencies match (no network
    call). ``ok`` is False when a needed FX lookup failed: factor falls back to
    1.0 but the caller should flag the result as currency-unconverted rather than
    emit a silently-wrong number.
    """
    trading = (info.get("currency") or "USD").upper()
    financial = (info.get("financialCurrency") or trading).upper()
    if financial == trading:
        return 1.0, trading, financial, True
    rate = fx_rate(financial, trading)
    if rate is None:
        return 1.0, trading, financial, False
    return rate, trading, financial, True


def to_trading_basis(raw: float, ref_trading: float, fx: float) -> float:
    """Normalize a value of *ambiguous* currency to the trading basis.

    yfinance `.info` per-share fields are stored inconsistently — some already in
    trading currency, some in financialCurrency, and it varies by field AND by
    ticker (e.g. KSPI trailingEps is USD but forwardEps is KZT). Given a trusted
    trading-currency reference of comparable magnitude (e.g. a statement-derived
    trailing EPS), pick whichever of {raw, raw*fx} is closer in log-magnitude to
    the reference. No-op when fx == 1.0 or no usable reference.
    """
    if not raw or fx == 1.0 or not ref_trading:
        return raw
    a, b = raw, raw * fx
    da = abs(math.log(abs(a) / abs(ref_trading))) if a else float("inf")
    db = abs(math.log(abs(b) / abs(ref_trading))) if b else float("inf")
    return b if db < da else a


def convert_financial_fields(d: dict, keys, factor: float) -> None:
    """In place, multiply the given monetary ``keys`` of dict ``d`` by ``factor``.

    No-op when factor == 1.0 (same-currency / US tickers). Lists are converted
    element-wise (for time-series fetchers). Only convert statement-derived
    (financialCurrency) fields — never price/marketCap/debt/cash (already trading
    currency) or unitless ratios.
    """
    if factor == 1.0:
        return
    for k in keys:
        if k not in d:
            continue
        v = d[k]
        if isinstance(v, list):
            d[k] = [x * factor if isinstance(x, (int, float)) and not isinstance(x, bool) else x for x in v]
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            d[k] = v * factor


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
        "financial_currency": info.get("financialCurrency") or info.get("currency") or "USD",
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
