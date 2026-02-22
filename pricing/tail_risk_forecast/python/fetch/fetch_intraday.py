#!/usr/bin/env python3
"""
Fetch intraday data for tail risk forecasting.

Uses the unified data_fetcher library which supports:
- IBKR (preferred): Up to 1 year of intraday data with proper subscription
- yfinance (fallback): Limited to 60 days of intraday data

Usage:
    python fetch_intraday.py --ticker AAPL
    python fetch_intraday.py --ticker AAPL --provider ibkr
    python fetch_intraday.py --ticker AAPL --days 252  # Full year with IBKR
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

# Add lib to path for data_fetcher
sys.path.insert(0, str(Path(__file__).parents[4]))

from lib.python.data_fetcher import get_provider, get_available_providers, OHLCV
from lib.python.retry import retry_with_backoff


def fetch_intraday_ibkr(ticker: str, days: int = 252, interval: str = "5m") -> dict | None:
    """Fetch intraday data using IBKR provider."""
    try:
        provider = get_provider("ibkr")
        if not provider.is_available():
            return None

        print(f"Using IBKR provider for {ticker}...")

        # IBKR supports longer periods for intraday
        # Map days to period string
        if days <= 30:
            period = "1mo"
        elif days <= 90:
            period = "3mo"
        elif days <= 180:
            period = "6mo"
        else:
            period = "1y"

        ohlcv = provider.fetch_ohlcv(ticker, period=period, interval=interval)
        if not ohlcv:
            return None

        return _process_ohlcv(ticker, ohlcv, interval)
    except Exception as e:
        print(f"IBKR fetch failed: {e}")
        return None


def fetch_intraday_yfinance(ticker: str, days: int = 60, interval: str = "5m") -> dict | None:
    """Fetch intraday data using yfinance (fallback)."""
    try:
        import yfinance as yf

        print(f"Using yfinance for {ticker} (limited to {min(days, 60)} days)...")

        # yfinance limits: 5m data available for last 60 days only
        days = min(days, 60)
        end = datetime.now()
        start = end - timedelta(days=days)

        stock = yf.Ticker(ticker)
        df = retry_with_backoff(lambda: stock.history(start=start, end=end, interval=interval))

        if df.empty:
            print(f"Warning: No data returned for {ticker}")
            return None

        print(f"  Retrieved {len(df)} bars")

        # Add date column for grouping
        df["date"] = df.index.date
        df["log_return"] = np.log(df["Close"] / df["Close"].shift(1))

        # Group by day
        daily_data = []
        for date, group in df.groupby("date"):
            returns = group["log_return"].dropna().tolist()
            close = group["Close"].iloc[-1] if len(group) > 0 else 0.0

            if len(returns) >= 10:  # Need minimum observations per day
                daily_data.append({
                    "date": str(date),
                    "close": float(close),
                    "returns": returns,
                    "n_obs": len(returns),
                })

        if len(daily_data) < 30:
            print(f"Warning: Only {len(daily_data)} days with sufficient data")

        return {
            "ticker": ticker,
            "interval": interval,
            "start_date": str(start.date()),
            "end_date": str(end.date()),
            "fetch_time": datetime.now().isoformat(),
            "provider": "yfinance",
            "total_bars": len(df),
            "daily_data": daily_data,
        }
    except Exception as e:
        print(f"yfinance fetch failed: {e}")
        return None


def _process_ohlcv(ticker: str, ohlcv: OHLCV, interval: str) -> dict:
    """Process OHLCV data into daily returns format."""
    # Convert OHLCV to returns grouped by day
    closes = np.array(ohlcv.close)
    dates = ohlcv.dates

    # Compute log returns
    log_returns = np.diff(np.log(closes))

    # Group by date
    daily_data = []
    current_date = None
    current_returns = []
    current_close = 0.0

    for i, date_str in enumerate(dates[1:], 1):  # Skip first (no return)
        # Extract date part (handle both datetime and date strings)
        if "T" in date_str:
            date_part = date_str.split("T")[0]
        elif " " in date_str:
            date_part = date_str.split(" ")[0]
        else:
            date_part = date_str

        if date_part != current_date:
            # Save previous day
            if current_date and len(current_returns) >= 10:
                daily_data.append({
                    "date": current_date,
                    "close": float(current_close),
                    "returns": current_returns,
                    "n_obs": len(current_returns),
                })
            # Start new day
            current_date = date_part
            current_returns = []

        current_returns.append(float(log_returns[i - 1]))
        current_close = float(closes[i])

    # Don't forget last day
    if current_date and len(current_returns) >= 10:
        daily_data.append({
            "date": current_date,
            "close": float(current_close),
            "returns": current_returns,
            "n_obs": len(current_returns),
        })

    return {
        "ticker": ticker,
        "interval": interval,
        "start_date": dates[0].split("T")[0] if "T" in dates[0] else dates[0].split(" ")[0],
        "end_date": dates[-1].split("T")[0] if "T" in dates[-1] else dates[-1].split(" ")[0],
        "fetch_time": datetime.now().isoformat(),
        "provider": "ibkr",
        "total_bars": len(closes),
        "daily_data": daily_data,
    }


def fetch_intraday(ticker: str, days: int = 60, interval: str = "5m", provider: str | None = None) -> dict | None:
    """
    Fetch intraday data with automatic provider selection.

    Priority:
    1. If provider specified, use that
    2. If IBKR available, use IBKR (longer history)
    3. Fall back to yfinance
    """
    if provider == "ibkr":
        result = fetch_intraday_ibkr(ticker, days, interval)
        if result:
            return result
        print("IBKR failed, falling back to yfinance")

    if provider == "yfinance" or provider is None:
        # Check if IBKR is available first (for auto-selection)
        if provider is None:
            available = get_available_providers()
            if "ibkr" in available:
                result = fetch_intraday_ibkr(ticker, days, interval)
                if result:
                    return result

        # Fall back to yfinance
        return fetch_intraday_yfinance(ticker, days, interval)

    return None


def main():
    parser = argparse.ArgumentParser(description="Fetch intraday data for tail risk")
    parser.add_argument("--ticker", required=True, help="Ticker symbol")
    parser.add_argument("--days", type=int, default=60, help="Days of history (IBKR: up to 252, yfinance: max 60)")
    parser.add_argument("--interval", default="5m", help="Bar interval (default: 5m)")
    parser.add_argument("--provider", choices=["ibkr", "yfinance"], help="Force specific provider")
    parser.add_argument("--output", help="Output directory")
    args = parser.parse_args()

    # Show available providers
    available = get_available_providers()
    print(f"Available providers: {available}")

    data = fetch_intraday(args.ticker, days=args.days, interval=args.interval, provider=args.provider)

    if data is None:
        print("Failed to fetch data")
        return 1

    # Output path
    if args.output:
        output_dir = Path(args.output)
    else:
        output_dir = Path(__file__).resolve().parent.parent.parent / "data"

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"intraday_{args.ticker}.json"

    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nSaved to: {output_file}")
    print(f"Provider: {data.get('provider', 'unknown')}")

    # Summary stats
    if data["daily_data"]:
        all_returns = []
        for day in data["daily_data"]:
            all_returns.extend(day["returns"])

        all_returns = np.array(all_returns)
        daily_rv = [sum(r**2 for r in day["returns"]) for day in data["daily_data"]]

        print(f"\nSummary:")
        print(f"  Days: {len(data['daily_data'])}")
        print(f"  Avg returns/day: {len(all_returns) / len(data['daily_data']):.1f}")
        print(f"  Avg daily RV: {np.mean(daily_rv):.6f}")
        print(f"  Avg daily vol: {np.sqrt(np.mean(daily_rv)) * 100:.2f}%")
        print(f"  Annualized vol: {np.sqrt(np.mean(daily_rv) * 252) * 100:.1f}%")

    return 0


if __name__ == "__main__":
    sys.exit(main())
