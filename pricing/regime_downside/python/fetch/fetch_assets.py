"""Fetch asset return data using unified data_fetcher.

Uses IBKR if available, falls back to yfinance.
"""

import sys
import pandas as pd
from pathlib import Path
from datetime import datetime

# Add lib to path
sys.path.insert(0, str(Path(__file__).parents[4]))

from lib.python.data_fetcher import fetch_multiple_ohlcv, get_available_providers


def fetch_asset_returns(
    tickers: list[str],
    start_date: str = "2015-01-01",
    end_date: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Fetch return data for multiple assets.

    Uses unified data_fetcher (IBKR if available, yfinance fallback).

    Args:
        tickers: List of ticker symbols
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format (None = today)
        output_dir: Directory to save CSV files (None = don't save)

    Returns:
        Dictionary mapping ticker -> DataFrame with columns: date, return
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    print(f"Available providers: {get_available_providers()}")

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

    # Fetch all tickers using batch download
    ohlcv_data = fetch_multiple_ohlcv(tickers, period=period, interval="1d")

    results = {}

    for ticker in tickers:
        print(f"Processing {ticker}...", end=" ")
        try:
            if ticker not in ohlcv_data:
                print(f"✗ No data returned")
                continue

            ohlcv = ohlcv_data[ticker]

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

            results[ticker] = df

            # Save to CSV if output directory specified
            if output_dir is not None:
                output_dir.mkdir(parents=True, exist_ok=True)
                output_path = output_dir / f"{ticker}_returns.csv"
                df.to_csv(output_path, index=False)
                print(f"✓ Saved to {output_path.name}")
            else:
                print("✓")

        except Exception as e:
            print(f"✗ Error: {e}")
            continue

    return results


def main():
    """Fetch asset data and save to data directory."""
    import sys

    # Check if tickers provided as command-line argument
    if len(sys.argv) > 1:
        # Parse comma-separated tickers from command line
        ticker_string = sys.argv[1]
        tickers = [t.strip() for t in ticker_string.split(",")]
    else:
        # Default asset universe
        tickers = [
            "AAPL",    # Apple
            "GOOGL",   # Alphabet
            "MSFT",    # Microsoft
            "NVDA",    # NVIDIA
            "TSLA",    # Tesla
            "JPM",     # JPMorgan
            "V",       # Visa
            "UNH",     # UnitedHealth
        ]

    # Get the data directory relative to this script
    script_dir = Path(__file__).parent
    data_dir = script_dir.parent.parent / "data"

    print("Fetching asset return data...")
    print("=" * 60)

    results = fetch_asset_returns(
        tickers=tickers,
        start_date="2015-01-01",
        output_dir=data_dir,
    )

    print("=" * 60)
    print(f"\nSuccessfully fetched {len(results)} assets")

    if results:
        # Show summary statistics
        print("\nSummary:")
        for ticker, df in results.items():
            print(
                f"  {ticker}: {len(df)} days, "
                f"mean return: {df['return'].mean():.4%}, "
                f"volatility: {df['return'].std():.4%}"
            )


if __name__ == "__main__":
    main()
