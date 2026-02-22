#!/usr/bin/env python3
"""
Fetch intraday price data for gamma scalping simulations.

Uses the unified data_fetcher library which supports:
- IBKR (preferred): Up to 1 year of intraday data with proper subscription
- yfinance (fallback): Limited to 60 days of intraday data

Usage:
    uv run pricing/gamma_scalping/python/fetch/fetch_intraday.py --ticker SPY
    uv run pricing/gamma_scalping/python/fetch/fetch_intraday.py --ticker SPY --days 10
    uv run pricing/gamma_scalping/python/fetch/fetch_intraday.py --ticker AAPL --provider ibkr
"""

import argparse
import sys
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import pandas as pd

from lib.python.data_fetcher import get_provider, get_available_providers, OHLCV
from lib.python.retry import retry_with_backoff


def _days_to_period(days: int) -> str:
    """Map number of days to yfinance period string."""
    if days <= 5:
        return "5d"
    elif days <= 30:
        return "1mo"
    elif days <= 90:
        return "3mo"
    elif days <= 180:
        return "6mo"
    else:
        return "1y"


def _ohlcv_to_df(ohlcv: OHLCV) -> pd.DataFrame:
    """Convert OHLCV data to timestamp_days,price DataFrame for OCaml."""
    dates = pd.to_datetime(ohlcv.dates)
    closes = ohlcv.close

    start_time = dates[0]
    timestamp_days = [(d - start_time).total_seconds() / (24 * 3600) for d in dates]

    df = pd.DataFrame({
        "timestamp_days": timestamp_days,
        "price": closes,
    })

    print(f"  Downloaded {len(df)} observations")
    print(f"  Time range: {dates[0]} to {dates[-1]}")
    print(f"  Price range: ${min(closes):.2f} - ${max(closes):.2f}")

    return df


def fetch_intraday_ibkr(ticker: str, days: int, interval: str = "5m") -> pd.DataFrame | None:
    """Fetch intraday data using IBKR provider."""
    try:
        provider = get_provider("ibkr")
        if not provider.is_available():
            return None

        print(f"Using IBKR provider for {ticker}...")
        period = _days_to_period(days)
        ohlcv = provider.fetch_ohlcv(ticker, period=period, interval=interval)
        if not ohlcv:
            return None

        return _ohlcv_to_df(ohlcv)
    except Exception as e:
        print(f"IBKR fetch failed: {e}")
        return None


def fetch_intraday_yfinance(ticker: str, days: int, interval: str = "5m") -> pd.DataFrame | None:
    """Fetch intraday data using yfinance (fallback)."""
    import yfinance as yf

    # yfinance limits: 5m data available for last 60 days only
    effective_days = min(days, 60)
    period = _days_to_period(effective_days)

    print(f"Using yfinance for {ticker} (period: {period})...")

    data = retry_with_backoff(lambda: yf.download(
        ticker,
        interval=interval,
        period=period,
        progress=False,
        auto_adjust=True,
    ))

    if data.empty:
        return None

    # Extract close prices (handle both single and multi-ticker downloads)
    if isinstance(data.columns, pd.MultiIndex):
        close_prices = data["Close"][ticker]
    else:
        close_prices = data["Close"]

    # Convert timestamp to days since start (for OCaml)
    start_time = data.index[0]
    timestamp_days = (data.index - start_time).total_seconds() / (24 * 3600)

    df = pd.DataFrame({
        "timestamp_days": timestamp_days,
        "price": close_prices.values,
    })

    print(f"  Downloaded {len(df)} observations")
    print(f"  Time range: {data.index[0]} to {data.index[-1]}")
    print(f"  Price range: ${df['price'].min():.2f} - ${df['price'].max():.2f}")

    return df


def fetch_intraday(ticker: str, days: int = 5, interval: str = "5m",
                   provider: str | None = None) -> pd.DataFrame | None:
    """
    Fetch intraday data with automatic provider selection.

    Priority:
    1. If provider specified, use that
    2. If IBKR available, use IBKR (longer history)
    3. Fall back to yfinance
    """
    if provider == "ibkr":
        result = fetch_intraday_ibkr(ticker, days, interval)
        if result is not None:
            return result
        print("IBKR failed, falling back to yfinance")

    if provider == "yfinance" or provider is None:
        if provider is None:
            available = get_available_providers()
            if "ibkr" in available:
                result = fetch_intraday_ibkr(ticker, days, interval)
                if result is not None:
                    return result

        return fetch_intraday_yfinance(ticker, days, interval)

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Fetch intraday price data for gamma scalping simulations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch 5-minute bars for SPY (last 5 days)
  uv run pricing/gamma_scalping/python/fetch/fetch_intraday.py --ticker SPY

  # Fetch with more history
  uv run pricing/gamma_scalping/python/fetch/fetch_intraday.py --ticker AAPL --days 30

  # Force IBKR provider
  uv run pricing/gamma_scalping/python/fetch/fetch_intraday.py --ticker QQQ --provider ibkr
        """,
    )

    parser.add_argument("--ticker", type=str, required=True, help="Stock ticker symbol (e.g., SPY, AAPL)")
    parser.add_argument("--days", type=int, default=5,
                        help="Days of history (IBKR: up to 252, yfinance: max 60) (default: 5)")
    parser.add_argument("--interval", type=str, default="5m",
                        choices=["1m", "5m", "15m", "30m", "60m"],
                        help="Data interval (default: 5m)")
    parser.add_argument("--provider", type=str, choices=["ibkr", "yfinance"],
                        help="Force specific data provider")
    parser.add_argument("--output-dir", type=str, default="pricing/gamma_scalping/data",
                        help="Output directory (default: pricing/gamma_scalping/data)")

    args = parser.parse_args()

    # Show available providers
    available = get_available_providers()
    print(f"Available providers: {available}")

    try:
        df = fetch_intraday(args.ticker, args.days, args.interval, args.provider)

        if df is None or df.empty:
            print(f"\nError: No data found for {args.ticker}", file=sys.stderr)
            sys.exit(1)

        # Save to CSV
        Path(args.output_dir).mkdir(parents=True, exist_ok=True)
        output_file = f"{args.output_dir}/{args.ticker}_intraday.csv"
        df.to_csv(output_file, index=False, header=True)

        print(f"\nSaved to: {output_file}")
        print(f"Format: timestamp_days,price")
        print(f"Ready for OCaml simulation")

    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
