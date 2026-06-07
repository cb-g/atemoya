#!/usr/bin/env python3
"""
Fetch option chain data for vol surface calibration.

Prefers ThetaData EOD chains (tighter bid/ask; IV computed from mid-quotes via
Newton-Raphson since ThetaData carries no IV on the free tier) and falls back to
yfinance when the Theta Terminal isn't running. The output schema is identical
across sources:  ticker, option_type, strike, expiry (years), bid, ask,
implied_volatility.
"""

import argparse
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf
import pandas as pd
import numpy as np

from lib.python.retry import retry_with_backoff
from lib.python.data_fetcher import get_available_providers
from lib.python.data_fetcher.thetadata_provider import ThetaDataProvider
from lib.python.iv import implied_vol_newton_raphson

# Risk-free rate for IV inversion. IV is only weakly sensitive to r over the
# short-to-medium expiries used for hedging, so a current short-rate constant is
# adequate (matches the refreshed US short end).
RISK_FREE_RATE = 0.043

OUTPUT_COLUMNS = ["ticker", "option_type", "strike", "expiry", "bid", "ask", "implied_volatility"]


def _finalize(df: pd.DataFrame) -> pd.DataFrame:
    """Apply the shared validity filter and select the output columns."""
    df = df[
        (df["bid"] > 0)
        & (df["ask"] > df["bid"])
        & (df["implied_volatility"].notna())
        & (df["implied_volatility"] > 0)
    ]
    return df[OUTPUT_COLUMNS].reset_index(drop=True)


def fetch_chain_yfinance(ticker: str, min_days: int = 7, max_days: int = 730) -> pd.DataFrame:
    """Fetch the option chain from yfinance (IV is provided directly)."""
    print(f"Fetching option chain for {ticker} (yfinance)...")
    stock = yf.Ticker(ticker)

    try:
        expirations = retry_with_backoff(lambda: stock.options)
    except Exception as e:
        raise ValueError(f"Failed to fetch option expirations for {ticker}: {e}")

    if not expirations:
        raise ValueError(f"No options data available for {ticker}")

    chains = []
    now = datetime.now()
    for expiry_str in expirations:
        expiry_dt = datetime.strptime(expiry_str, "%Y-%m-%d")
        days_to_expiry = (expiry_dt - now).days
        if days_to_expiry < min_days or days_to_expiry > max_days:
            continue
        try:
            chain = retry_with_backoff(lambda exp=expiry_str: stock.option_chain(exp))
        except Exception as e:
            print(f"  Warning: Failed to fetch chain for {expiry_str}: {e}")
            continue

        calls = chain.calls.copy()
        calls["option_type"] = "call"
        calls["expiry"] = days_to_expiry / 365.0
        puts = chain.puts.copy()
        puts["option_type"] = "put"
        puts["expiry"] = days_to_expiry / 365.0
        combined = pd.concat([calls, puts], ignore_index=True)
        combined["ticker"] = ticker
        chains.append(combined)
        print(f"  Fetched {expiry_str} ({days_to_expiry} days): {len(calls)} calls, {len(puts)} puts")

    if not chains:
        raise ValueError(f"No valid option chains found for {ticker}")

    full_chain = pd.concat(chains, ignore_index=True)
    for col in ["ticker", "option_type", "strike", "expiry", "bid", "ask", "impliedVolatility"]:
        if col not in full_chain.columns:
            full_chain[col] = np.nan
    full_chain = full_chain.rename(columns={"impliedVolatility": "implied_volatility"})
    return _finalize(full_chain)


def fetch_chain_thetadata(ticker: str, min_days: int = 7, max_days: int = 730, otm_only: bool = True):
    """Fetch the current EOD chain from ThetaData, computing IV from mid-quotes.

    ThetaData carries no IV, so it's inverted via Newton-Raphson. Restricted to
    OTM options with quality gates (mid > 0.05, spread/mid < 1.0, DTE >= 14) for
    robust fits — the same zero-fake-data discipline the other ThetaData modules
    use. Returns None when the Terminal is unavailable or the chain yields no
    usable quotes (the caller then falls back to yfinance).
    """
    provider = ThetaDataProvider()
    if not provider.is_available():
        return None
    print(f"Fetching option chain for {ticker} (thetadata)...")
    # Walk back from today to the most recent available EOD snapshot — handles
    # weekends / holidays / pre-EOD (the "live" chain is just today's historical
    # snapshot, which is empty on non-trading days).
    chain = None
    snap = datetime.now()
    for back in range(6):
        d = datetime.now() - timedelta(days=back)
        cand = retry_with_backoff(
            lambda dd=d.strftime("%Y%m%d"): provider.fetch_option_chain_historical(ticker, dd)
        )
        if cand is not None and (cand.calls or cand.puts):
            chain, snap = cand, d
            break
    if chain is None or chain.underlying_price <= 0:
        return None
    spot = chain.underlying_price

    rows = []
    for c in list(chain.calls) + list(chain.puts):
        try:
            dte = (datetime.strptime(c.expiry, "%Y-%m-%d") - snap).days
        except ValueError:
            continue
        if dte < max(min_days, 14) or dte > max_days:        # DTE >= 14 quality gate
            continue
        if c.bid <= 0 or c.ask <= c.bid:
            continue
        mid = 0.5 * (c.bid + c.ask)
        if mid < 0.05 or (c.ask - c.bid) / mid >= 1.0:       # liquidity gates
            continue
        if otm_only:
            is_otm = (c.option_type == "call" and c.strike > spot) or (
                c.option_type == "put" and c.strike < spot
            )
            if not is_otm:                                   # OTM-only for clean IV fits
                continue
        rows.append((c.option_type, c.strike, dte / 365.0, c.bid, c.ask, mid))

    if not rows:
        return None
    df = pd.DataFrame(rows, columns=["option_type", "strike", "expiry", "bid", "ask", "mid"])
    df["implied_volatility"] = implied_vol_newton_raphson(
        prices=df["mid"].to_numpy(dtype=float),
        spots=np.full(len(df), spot, dtype=float),
        strikes=df["strike"].to_numpy(dtype=float),
        expiries=df["expiry"].to_numpy(dtype=float),
        rates=np.full(len(df), RISK_FREE_RATE, dtype=float),
        option_types=df["option_type"].to_numpy(),
    )
    df["ticker"] = ticker
    return _finalize(df)


def fetch_option_chain(
    ticker: str, min_days: int = 7, max_days: int = 730, source: str = "auto"
) -> pd.DataFrame:
    """Fetch an option chain, preferring ThetaData and falling back to yfinance.

    source: "auto" (thetadata preferred, yfinance fallback), "thetadata", or
    "yfinance".
    """
    print(f"Available providers: {get_available_providers()}")
    if source in ("auto", "thetadata"):
        try:
            td = fetch_chain_thetadata(ticker, min_days, max_days)
        except Exception as e:
            td = None
            print(f"  ThetaData fetch failed: {e}", file=sys.stderr)
        if td is not None and not td.empty:
            print(f"\nSource: thetadata — {len(td)} valid quotes")
            return td
        if source == "thetadata":
            raise ValueError(f"No ThetaData option chain available for {ticker}")
        print("  ThetaData unavailable/empty; falling back to yfinance")

    df = fetch_chain_yfinance(ticker, min_days, max_days)
    print(f"\nSource: yfinance — {len(df)} valid quotes")
    return df


def main():
    parser = argparse.ArgumentParser(description="Fetch option chain data")
    parser.add_argument("--ticker", required=True, help="Stock ticker symbol")
    parser.add_argument("--output-dir", default="pricing/options_hedging/data", help="Output directory")
    parser.add_argument("--min-days", type=int, default=7, help="Minimum days to expiry (default: 7)")
    parser.add_argument("--max-days", type=int, default=730, help="Maximum days to expiry (default: 730)")
    parser.add_argument(
        "--source",
        choices=["auto", "thetadata", "yfinance"],
        default="auto",
        help="Chain source (default: auto = thetadata preferred, yfinance fallback)",
    )

    args = parser.parse_args()

    try:
        chain = fetch_option_chain(args.ticker, args.min_days, args.max_days, args.source)

        if chain.empty:
            print("Error: No valid option data found", file=sys.stderr)
            sys.exit(1)

        print(f"\n=== Option Chain Summary: {args.ticker} ===")
        print(f"Total Quotes: {len(chain)}")
        print(f"Calls: {len(chain[chain['option_type'] == 'call'])}")
        print(f"Puts: {len(chain[chain['option_type'] == 'put'])}")

        expiries = chain["expiry"].unique()
        print(f"Expiries: {len(expiries)} ({expiries.min():.2f} to {expiries.max():.2f} years)")

        strikes = chain["strike"].unique()
        print(f"Strikes: {len(strikes)} (${strikes.min():.2f} to ${strikes.max():.2f})")

        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{args.ticker}_options.csv"
        chain.to_csv(output_file, index=False)

        print(f"\n✓ Saved option chain to {output_file}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
