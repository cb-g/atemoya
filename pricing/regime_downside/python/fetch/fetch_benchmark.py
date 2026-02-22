"""Fetch S&P 500 benchmark data using unified data_fetcher."""

import sys
from pathlib import Path

import pandas as pd

# Add lib to path
sys.path.insert(0, str(Path(__file__).parents[4]))

from lib.python.data_fetcher import fetch_ohlcv, get_available_providers


def fetch_sp500_returns(
    start_date: str = "2015-01-01",
    end_date: str | None = None,
    output_dir: Path | None = None,
) -> pd.DataFrame:
    """
    Fetch S&P 500 total return data.

    Uses unified data_fetcher (IBKR if available, yfinance fallback).

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format (None = today)
        output_dir: Directory to save the CSV file (None = don't save)

    Returns:
        DataFrame with columns: date, return
    """
    from datetime import datetime

    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    # Calculate period from dates
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days = (end - start).days

    if days <= 30:
        period = "1mo"
    elif days <= 90:
        period = "3mo"
    elif days <= 180:
        period = "6mo"
    elif days <= 365:
        period = "1y"
    elif days <= 730:
        period = "2y"
    else:
        period = "5y"

    print(f"Available providers: {get_available_providers()}")

    # Fetch S&P 500 data (^GSPC)
    ohlcv = fetch_ohlcv("^GSPC", period=period, interval="1d")

    if ohlcv is None:
        raise RuntimeError("Failed to fetch S&P 500 data")

    # Calculate daily returns from close prices
    closes = pd.Series(ohlcv.close, index=pd.to_datetime(ohlcv.dates))
    returns = closes.pct_change().dropna()

    # Filter to date range
    returns = returns[start_date:end_date]

    # Create DataFrame
    df = pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in returns.index],
        "return": returns.values
    })

    # Save to CSV if output directory specified
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / "sp500_returns.csv"
        df.to_csv(output_path, index=False)
        print(f"Saved S&P 500 returns to {output_path}")

    return df


def main():
    """Fetch S&P 500 data and save to data directory."""
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent.parent / "data"

    print("Fetching S&P 500 benchmark data...")
    df = fetch_sp500_returns(
        start_date="2015-01-01",
        output_dir=data_dir,
    )

    print(f"\nFetched {len(df)} days of data")
    print(f"Date range: {df['date'].iloc[0]} to {df['date'].iloc[-1]}")
    print(f"\nFirst few rows:")
    print(df.head())
    print(f"\nStatistics:")
    print(df["return"].describe())


if __name__ == "__main__":
    main()
