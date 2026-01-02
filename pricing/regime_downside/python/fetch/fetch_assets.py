"""Fetch asset return data using yfinance."""

import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime


def fetch_asset_returns(
    tickers: list[str],
    start_date: str = "2015-01-01",
    end_date: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, pd.DataFrame]:
    """
    Fetch return data for multiple assets.

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

    results = {}

    for ticker in tickers:
        print(f"Fetching {ticker}...", end=" ")
        try:
            # Fetch asset data
            data = yf.download(ticker, start=start_date, end=end_date, progress=False, auto_adjust=False)

            # Calculate daily returns
            if "Adj Close" in data.columns:
                close_prices = data["Adj Close"]
            else:
                close_prices = data["Close"]

            # Flatten if multi-index
            if hasattr(close_prices, "squeeze"):
                close_prices = close_prices.squeeze()

            returns = close_prices.pct_change().dropna()

            # Create DataFrame
            df = pd.DataFrame({
                "date": [d.strftime("%Y-%m-%d") for d in returns.index],
                "return": returns.values.flatten() if hasattr(returns.values, "flatten") else returns.values
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
