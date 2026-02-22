#!/usr/bin/env python3
"""
Fetch market data for variance swaps analysis

Downloads:
- Historical price data (OHLC)
- Current spot price and dividend yield
- Implied volatility surface (from options chain)

Uses unified data_fetcher (IBKR if available, yfinance fallback).
Options chain always uses yfinance (IBKR portal chain not implemented).
"""

import sys
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[3]))

import yfinance as yf
import pandas as pd
import numpy as np
import json
from datetime import datetime, timedelta
import argparse

from lib.python.retry import retry_with_backoff
from lib.python.data_fetcher import fetch_ohlcv, fetch_ticker_info, get_available_providers


def fetch_price_data(ticker: str, lookback_days: int = 365) -> pd.DataFrame:
    """Fetch historical price data (OHLC + close).

    Uses unified data_fetcher (IBKR if available, yfinance fallback).
    """
    providers = get_available_providers()
    print(f"Fetching {lookback_days} days of price data for {ticker}... (providers: {', '.join(providers)})")

    # Map lookback to period string
    if lookback_days <= 30:
        period = "1mo"
    elif lookback_days <= 90:
        period = "3mo"
    elif lookback_days <= 180:
        period = "6mo"
    elif lookback_days <= 365:
        period = "1y"
    elif lookback_days <= 730:
        period = "2y"
    else:
        period = "5y"

    ohlcv = fetch_ohlcv(ticker, period=period, interval="1d")

    if ohlcv is None or len(ohlcv) == 0:
        raise ValueError(f"No price data found for {ticker}")

    dates = pd.to_datetime(ohlcv.dates)
    df = pd.DataFrame({
        'date': dates.astype(int) // 10**9,
        'open': ohlcv.open,
        'high': ohlcv.high,
        'low': ohlcv.low,
        'close': ohlcv.close,
    })

    print(f"  ✓ Fetched {len(df)} price observations")
    return df


def fetch_underlying_data(ticker: str) -> dict:
    """Fetch current spot price and dividend yield.

    Uses unified data_fetcher for spot price, yfinance for dividend yield
    (not available in base TickerInfo).
    """
    print(f"Fetching underlying data for {ticker}...")

    # Try unified provider for spot price
    info = fetch_ticker_info(ticker)
    spot_price = info.price if info and info.price else None

    # Fallback: get dividend yield from yfinance (not in base TickerInfo)
    stock = yf.Ticker(ticker)
    yf_info = retry_with_backoff(lambda: stock.info)

    if spot_price is None or spot_price == 0:
        spot_price = yf_info.get('currentPrice') or yf_info.get('regularMarketPrice')
        if spot_price is None:
            hist = retry_with_backoff(lambda: stock.history(period='1d'))
            spot_price = hist['Close'].iloc[-1] if not hist.empty else 100.0

    dividend_yield = yf_info.get('dividendYield') or 0.0
    # Sanity check: dividend yield should be < 20% for any reasonable equity
    if dividend_yield > 0.20:
        dividend_yield = 0.0

    data = {
        'ticker': ticker,
        'spot_price': float(spot_price),
        'dividend_yield': float(dividend_yield)
    }

    print(f"  ✓ Spot: ${spot_price:.2f}, Dividend Yield: {dividend_yield*100:.2f}%")
    return data


def fetch_options_chain(ticker: str) -> pd.DataFrame:
    """Fetch option chain for implied volatility calibration.

    Uses yfinance directly (IBKR portal option chain not implemented).
    """
    print(f"Fetching options chain for {ticker}...")

    stock = yf.Ticker(ticker)
    expirations = retry_with_backoff(lambda: stock.options)

    if not expirations:
        print("  ⚠ No options available, creating dummy vol surface")
        return pd.DataFrame()

    all_options = []

    for expiry_str in expirations[:5]:  # First 5 expiries
        expiry_dt = datetime.strptime(expiry_str, '%Y-%m-%d')
        # Use naive datetime for comparison
        now_naive = datetime.now().replace(tzinfo=None)
        days_to_expiry = (expiry_dt - now_naive).days

        if days_to_expiry < 7 or days_to_expiry > 365:
            continue

        try:
            chain = retry_with_backoff(lambda exp=expiry_str: stock.option_chain(exp))

            # Process calls
            calls = chain.calls[['strike', 'impliedVolatility', 'bid', 'ask', 'volume']].copy()
            calls['option_type'] = 'call'
            calls['expiry'] = days_to_expiry / 365.0

            # Process puts
            puts = chain.puts[['strike', 'impliedVolatility', 'bid', 'ask', 'volume']].copy()
            puts['option_type'] = 'put'
            puts['expiry'] = days_to_expiry / 365.0

            all_options.append(pd.concat([calls, puts], ignore_index=True))
        except Exception as e:
            print(f"  ⚠ Error fetching expiry {expiry_str}: {e}")
            continue

    if not all_options:
        print("  ⚠ No valid options data")
        return pd.DataFrame()

    df = pd.concat(all_options, ignore_index=True)

    # Filter valid quotes
    df = df[
        (df['impliedVolatility'] > 0) &
        (df['bid'] > 0) &
        (df['ask'] > df['bid']) &
        (df['volume'] > 0)
    ]

    print(f"  ✓ Fetched {len(df)} valid option quotes across {len(all_options)} expiries")
    return df


def calibrate_svi_surface(options_df: pd.DataFrame, spot_price: float) -> dict:
    """Calibrate SVI volatility surface (simplified)"""
    print("Calibrating SVI volatility surface...")

    if options_df.empty:
        # Create default flat surface (~20% vol)
        # SVI: w(k) = a + b*(rho*(k-m) + sqrt((k-m)^2 + sigma^2))
        # At ATM (k=0, m=0, rho=0): w = a + b*sigma
        # Want IV = 0.20, so w = IV^2 * T, hence a = IV^2*T - b*sigma
        print("  ⚠ Using default flat surface (20% vol)")
        atm_iv = 0.20
        b_val = 0.01
        sigma_val = 0.1
        expiries = [0.0822, 0.25, 0.5]  # 30d, 90d, 180d
        params = []
        for t in expiries:
            a_val = atm_iv**2 * t - b_val * sigma_val
            params.append({
                'expiry': t,
                'a': round(a_val, 6),
                'b': b_val,
                'rho': -0.1,  # mild negative skew (typical equity)
                'm': 0.0,
                'sigma': sigma_val,
            })
        return {
            'model': 'SVI',
            'params': params
        }

    # Group by expiry
    expiries = sorted(options_df['expiry'].unique())
    params_list = []

    for expiry in expiries:
        expiry_data = options_df[options_df['expiry'] == expiry]

        # Simple calibration: fit ATM vol
        atm_options = expiry_data[
            (expiry_data['strike'] > 0.95 * spot_price) &
            (expiry_data['strike'] < 1.05 * spot_price)
        ]

        if len(atm_options) == 0:
            continue

        atm_vol = atm_options['impliedVolatility'].median()
        total_var = atm_vol ** 2 * expiry

        # SVI parameters (simplified)
        params = {
            'expiry': float(expiry),
            'a': float(total_var * 0.8),  # Minimum variance
            'b': float(total_var * 0.4),  # Slope
            'rho': 0.0,  # Correlation (neutral)
            'm': 0.0,    # ATM log-moneyness
            'sigma': 0.1  # Curvature
        }

        params_list.append(params)

    if not params_list:
        # Fallback: flat 20% vol
        atm_iv = 0.20
        b_val = 0.01
        sigma_val = 0.1
        for t in [0.0822, 0.25, 0.5]:
            params_list.append({
                'expiry': t,
                'a': round(atm_iv**2 * t - b_val * sigma_val, 6),
                'b': b_val,
                'rho': -0.1,
                'm': 0.0,
                'sigma': sigma_val,
            })

    print(f"  ✓ Calibrated SVI surface with {len(params_list)} expiries")

    return {
        'model': 'SVI',
        'params': params_list
    }


def main():
    parser = argparse.ArgumentParser(description="Fetch market data for variance swaps")
    parser.add_argument('--ticker', type=str, required=True, help='Ticker symbol')
    parser.add_argument('--lookback', type=int, default=365, help='Days of price history')
    parser.add_argument('--output', type=str, default='pricing/variance_swaps/data', help='Output directory')

    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Fetch price data
        prices_df = fetch_price_data(args.ticker, args.lookback)
        prices_file = output_dir / f"{args.ticker}_prices.csv"
        prices_df.to_csv(prices_file, index=False)
        print(f"✓ Saved price data to {prices_file}")

        # Fetch underlying data
        underlying_data = fetch_underlying_data(args.ticker)
        underlying_file = output_dir / f"{args.ticker}_underlying.json"
        with open(underlying_file, 'w') as f:
            json.dump(underlying_data, f, indent=2)
        print(f"✓ Saved underlying data to {underlying_file}")

        # Fetch and calibrate volatility surface
        options_df = fetch_options_chain(args.ticker)
        vol_surface = calibrate_svi_surface(options_df, underlying_data['spot_price'])
        vol_surface_file = output_dir / f"{args.ticker}_vol_surface.json"
        with open(vol_surface_file, 'w') as f:
            json.dump(vol_surface, f, indent=2)
        print(f"✓ Saved vol surface to {vol_surface_file}")

        print(f"\n✅ Data fetch complete for {args.ticker}")

    except Exception as e:
        print(f"\n❌ Error: {e}")
        return 1

    return 0


if __name__ == '__main__':
    exit(main())
