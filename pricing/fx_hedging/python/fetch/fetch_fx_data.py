#!/usr/bin/env python3
"""
Fetch FX spot and futures data for hedging simulations.

Usage:
    python fetch_fx_data.py 6E
    python fetch_fx_data.py 6E --days 365
"""

import argparse
import sys
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

from lib.python.retry import retry_with_backoff
from lib.python.data_fetcher import fetch_ohlcv, get_available_providers

# Contract mappings
CONTRACT_MAPPINGS = {
    # FX futures
    "6E": {"name": "EUR/USD", "yahoo": "EURUSD=X", "type": "fx"},
    "6B": {"name": "GBP/USD", "yahoo": "GBPUSD=X", "type": "fx"},
    "6J": {"name": "JPY/USD", "yahoo": "JPYUSD=X", "type": "fx"},
    "6S": {"name": "CHF/USD", "yahoo": "CHFUSD=X", "type": "fx"},
    "6A": {"name": "AUD/USD", "yahoo": "AUDUSD=X", "type": "fx"},
    "6C": {"name": "CAD/USD", "yahoo": "CADUSD=X", "type": "fx"},
    # E-micro FX futures (1/10th standard, same spot as full-size)
    "M6E": {"name": "E-micro EUR/USD", "yahoo": "EURUSD=X", "type": "fx"},
    "M6B": {"name": "E-micro GBP/USD", "yahoo": "GBPUSD=X", "type": "fx"},
    "M6J": {"name": "E-micro JPY/USD", "yahoo": "JPYUSD=X", "type": "fx"},
    "M6S": {"name": "E-micro CHF/USD", "yahoo": "CHFUSD=X", "type": "fx"},
    "M6A": {"name": "E-micro AUD/USD", "yahoo": "AUDUSD=X", "type": "fx"},
    "M6C": {"name": "E-micro CAD/USD", "yahoo": "CADUSD=X", "type": "fx"},
    # Crypto futures (micro contracts share same spot as full-size)
    "BTC": {"name": "Bitcoin", "yahoo": "BTC-USD", "type": "crypto"},
    "MBT": {"name": "Micro Bitcoin", "yahoo": "BTC-USD", "type": "crypto"},
    "ETH": {"name": "Ether", "yahoo": "ETH-USD", "type": "crypto"},
    "MET": {"name": "Micro Ether", "yahoo": "ETH-USD", "type": "crypto"},
    "SOL": {"name": "Solana", "yahoo": "SOL-USD", "type": "crypto"},
    "MSOL": {"name": "Micro Solana", "yahoo": "SOL-USD", "type": "crypto"},
}

def fetch_fx_spot(contract_code: str, days: int = 252) -> pd.DataFrame:
    """
    Fetch FX spot rates using unified data_fetcher (IBKR if available, yfinance fallback).

    Args:
        contract_code: CME contract code (e.g., "6E" for EUR/USD)
        days: Number of days of history

    Returns:
        DataFrame with timestamp (days) and rate columns
    """
    if contract_code not in CONTRACT_MAPPINGS:
        raise ValueError(f"Unknown contract code: {contract_code}")

    mapping = CONTRACT_MAPPINGS[contract_code]
    providers = get_available_providers()
    print(f"Fetching {mapping['name']} spot rates ({days} days)... (providers: {', '.join(providers)})")

    # Map lookback to period string
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

    ticker_symbol = mapping["yahoo"]
    ohlcv = fetch_ohlcv(ticker_symbol, period=period, interval="1d")

    # Fallback to direct yfinance if data_fetcher returned nothing
    if ohlcv is None or len(ohlcv) == 0:
        print("  data_fetcher returned no data, falling back to direct yfinance...")
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)
        data = retry_with_backoff(lambda: yf.download(
            ticker_symbol,
            start=start_date.strftime("%Y-%m-%d"),
            end=end_date.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=True
        ))
        if data.empty:
            raise ValueError(f"No data found for {mapping['name']}")

        if isinstance(data.columns, pd.MultiIndex):
            close_prices = data['Close'].iloc[:, 0] if isinstance(data['Close'], pd.DataFrame) else data['Close']
        else:
            close_prices = data['Close']

        df = pd.DataFrame({
            'date': data.index,
            'rate': close_prices.values
        })
    else:
        dates = pd.to_datetime(ohlcv.dates)
        df = pd.DataFrame({
            'date': dates,
            'rate': ohlcv.close
        })

    # Convert to days since start (for OCaml)
    start_time = df['date'].iloc[0]
    df['timestamp'] = (df['date'] - start_time).dt.total_seconds() / (24 * 3600)

    # Reorder columns
    df = df[['timestamp', 'rate']]

    print(f"  Downloaded {len(df)} observations")
    print(f"  Rate range: {df['rate'].min():.6f} - {df['rate'].max():.6f}")

    return df

def fetch_fx_futures(contract_code: str, days: int = 252) -> pd.DataFrame:
    """
    Fetch FX/crypto futures prices.

    Note: Yahoo Finance doesn't have CME futures data directly.
    For now, we'll approximate futures using spot + estimated basis.

    In production, use Bloomberg, CME API, or other data source.
    """
    if contract_code not in CONTRACT_MAPPINGS:
        raise ValueError(f"Unknown contract code: {contract_code}")

    mapping = CONTRACT_MAPPINGS[contract_code]
    spot_df = fetch_fx_spot(contract_code, days)

    # Approximate futures with basis
    # F ≈ S × (1 + rate_diff × T)
    expiry = 90.0 / 365.0

    if mapping["type"] == "crypto":
        # Crypto futures typically have larger basis (contango)
        # Can range from 5-20% annualized
        rate_diff = 0.08  # 8% annualized for crypto
    else:
        # FX futures have small basis
        rate_diff = 0.02  # 2% for FX

    futures_df = spot_df.copy()
    futures_df['rate'] = spot_df['rate'] * (1 + rate_diff * expiry)

    print(f"  Approximated futures prices (basis ≈ {(rate_diff * expiry * 100):.2f}%)")

    return futures_df

def save_data(df: pd.DataFrame, filename: str):
    """Save DataFrame to CSV."""
    output_dir = Path(__file__).resolve().parent.parent.parent / "data"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / filename
    df.to_csv(output_file, index=False, header=True, float_format='%.8f')

    print(f"  Saved to: {output_file}")

def main():
    parser = argparse.ArgumentParser(
        description="Fetch FX spot and futures data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch EUR/USD data (1 year)
  python fetch_fx_data.py 6E

  # Fetch JPY/USD data (2 years)
  python fetch_fx_data.py 6J --days 504

  # Fetch all major pairs
  python fetch_fx_data.py --all
        """
    )

    parser.add_argument("contract", type=str, nargs='?', default="6E",
                       help="CME contract code (6E=EUR, 6J=JPY, 6B=GBP, 6S=CHF)")
    parser.add_argument("--days", type=int, default=252,
                       help="Days of history (default: 252)")
    parser.add_argument("--all", action="store_true",
                       help="Fetch all major currency pairs")

    args = parser.parse_args()

    contracts = list(CONTRACT_MAPPINGS.keys()) if args.all else [args.contract]

    for contract_code in contracts:
        try:
            print(f"\n=== {contract_code} ===")

            # Fetch spot rates
            spot_df = fetch_fx_spot(contract_code, args.days)
            spot_file = f"{contract_code.lower()}_spot.csv"
            save_data(spot_df, spot_file)

            # Fetch futures prices
            futures_df = fetch_fx_futures(contract_code, args.days)
            futures_file = f"{contract_code.lower()}_futures.csv"
            save_data(futures_df, futures_file)

            print(f"✓ Successfully fetched data for {contract_code}")

        except Exception as e:
            print(f"✗ Error fetching {contract_code}: {e}", file=sys.stderr)
            continue

    print(f"\nNext steps:")
    print(f"  1. Run the OCaml backtest:")
    print(f"     cd pricing/fx_hedging/ocaml")
    print(f"     dune exec fx_hedging -- -operation backtest -exposure 500000 -contract {args.contract}")
    print(f"  2. Visualize results:")
    print(f"     cd pricing/fx_hedging/python/viz")
    print(f"     python plot_hedge_performance.py {args.contract}")

if __name__ == "__main__":
    main()
