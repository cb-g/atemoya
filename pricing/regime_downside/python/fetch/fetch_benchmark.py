"""Fetch S&P 500 benchmark data using yfinance."""

import yfinance as yf
import pandas as pd
from pathlib import Path
from datetime import datetime


def fetch_sp500_returns(
    start_date: str = "2015-01-01",
    end_date: str | None = None,
    output_dir: Path | None = None,
) -> pd.DataFrame:
    """
    Fetch S&P 500 total return data.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format (None = today)
        output_dir: Directory to save the CSV file (None = don't save)

    Returns:
        DataFrame with columns: date, return
    """
    if end_date is None:
        end_date = datetime.now().strftime("%Y-%m-%d")

    # Fetch S&P 500 data (^GSPC)
    sp500 = yf.download("^GSPC", start=start_date, end=end_date, progress=False, auto_adjust=False)

    # Calculate daily returns from adjusted close
    if "Adj Close" in sp500.columns:
        close_prices = sp500["Adj Close"]
    else:
        # Fallback to Close if Adj Close not available
        close_prices = sp500["Close"]

    # Flatten if multi-index
    if hasattr(close_prices, "squeeze"):
        close_prices = close_prices.squeeze()

    returns = close_prices.pct_change().dropna()

    # Create DataFrame
    df = pd.DataFrame({
        "date": [d.strftime("%Y-%m-%d") for d in returns.index],
        "return": returns.values.flatten() if hasattr(returns.values, "flatten") else returns.values
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
    # Get the data directory relative to this script
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
