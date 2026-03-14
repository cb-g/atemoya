#!/usr/bin/env python3
"""
Daily dispersion trading snapshot collector.

Fetches ATM IV for an index (SPY) and its top constituents, then computes
dispersion level, implied correlation, and realized correlation.

Each run:
- Fetches ATM IV for SPY and top 10 S&P 500 constituents
- Computes weighted average constituent IV
- Computes dispersion level = weighted_avg_iv - index_iv
- Computes implied correlation from the variance decomposition
- Computes realized correlation from price returns
- Archives full snapshot to data/snapshots/{YYYY-MM-DD}.json
- Appends one row to data/dispersion_history.csv

Idempotent: skips if today's snapshot already exists.

Implied correlation formula (matching OCaml correlation.ml):
  rho_impl = (sigma_index^2 - sum(w_i^2 * sigma_i^2)) / (2 * sum_{i<j} w_i * w_j * sigma_i * sigma_j)
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import argparse

# Add project root to path
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf
from lib.python.retry import retry_with_backoff
from lib.python.data_fetcher import get_provider

# CSV header for dispersion history
HISTORY_COLUMNS = [
    "date", "index", "index_iv", "weighted_avg_iv",
    "dispersion_level", "implied_correlation", "realized_correlation",
]

# Default constituents (top 10 S&P 500 by weight)
DEFAULT_INDEX = "SPY"
DEFAULT_CONSTITUENTS = [
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
    "META", "TSLA", "JPM", "V", "UNH",
]


def already_collected_today(data_dir: Path) -> bool:
    """Check if today's snapshot already exists."""
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_file = data_dir / "snapshots" / f"{today}.json"
    return snapshot_file.exists()


def get_atm_iv(provider, ticker: str, spot: float) -> float:
    """Fetch ATM IV from nearest-expiry option chain."""
    chain = provider.fetch_option_chain(ticker)
    if chain is None or not chain.expiries:
        return 0.0

    # Pick nearest expiry 7-45 days out
    today = datetime.now().date()
    best_expiry = None
    best_diff = float('inf')
    for exp_str in chain.expiries:
        dte = (pd.to_datetime(exp_str).date() - today).days
        if 7 <= dte <= 45:
            diff = abs(dte - 30)
            if diff < best_diff:
                best_expiry = exp_str
                best_diff = diff

    if not best_expiry:
        best_expiry = chain.expiries[0]

    chain = provider.fetch_option_chain(ticker, expiry=best_expiry)
    if chain is None:
        return 0.0

    calls = [c for c in chain.calls if c.expiry == best_expiry]
    puts = [p for p in chain.puts if p.expiry == best_expiry]

    if not calls or not puts:
        return 0.0

    all_strikes = sorted(set(c.strike for c in calls))
    if not all_strikes:
        return 0.0

    arr = np.array(all_strikes)
    atm_strike = arr[np.argmin(np.abs(arr - spot))]

    atm_calls = [c for c in calls if c.strike == atm_strike]
    atm_puts = [p for p in puts if p.strike == atm_strike]

    if not atm_calls or not atm_puts:
        return 0.0

    call_iv = atm_calls[0].implied_volatility
    put_iv = atm_puts[0].implied_volatility
    if call_iv > 0 and put_iv > 0:
        return (call_iv + put_iv) / 2
    return call_iv if call_iv > 0 else put_iv


def compute_implied_correlation(index_iv: float, constituent_ivs: np.ndarray,
                                 weights: np.ndarray) -> float:
    """
    Compute implied correlation from index and constituent IVs.

    Matches OCaml correlation.ml logic:
      rho = (sigma_idx^2 - sum(w_i^2 * sigma_i^2)) / (2 * sum_{i<j} w_i*w_j*sigma_i*sigma_j)
    """
    n = len(constituent_ivs)
    if n < 2 or index_iv <= 0:
        return 0.0

    # Sum of weighted individual variances
    var_single = np.sum(weights ** 2 * constituent_ivs ** 2)

    # Cross-term denominator
    cov_denom = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            cov_denom += weights[i] * weights[j] * constituent_ivs[i] * constituent_ivs[j]

    if cov_denom <= 0:
        return 0.0

    index_var = index_iv ** 2
    implied_corr = (index_var - var_single) / (2.0 * cov_denom)
    return float(np.clip(implied_corr, -1.0, 1.0))


def compute_realized_correlation(prices_dict: dict[str, np.ndarray],
                                  weights: np.ndarray, lookback: int = 15) -> float:
    """Compute realized correlation from price returns (weighted average pairwise)."""
    tickers = list(prices_dict.keys())
    n = len(tickers)
    if n < 2:
        return 0.0

    # Compute log returns
    returns = {}
    for t in tickers:
        p = prices_dict[t]
        if len(p) < lookback + 1:
            return 0.0
        r = np.diff(np.log(p[-lookback - 1:]))
        returns[t] = r

    # Weighted average pairwise correlation
    weighted_corr = 0.0
    weight_sum = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            r_i = returns[tickers[i]]
            r_j = returns[tickers[j]]
            m = min(len(r_i), len(r_j))
            if m < 5:
                continue
            corr = np.corrcoef(r_i[-m:], r_j[-m:])[0, 1]
            w = weights[i] * weights[j]
            weighted_corr += w * corr
            weight_sum += w

    if weight_sum > 0:
        return float(weighted_corr / weight_sum)
    return 0.0


def archive_snapshot(snapshot_data: dict, data_dir: Path) -> Path:
    """Save full snapshot to data/snapshots/{YYYY-MM-DD}.json."""
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_dir = data_dir / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    snapshot_file = snapshot_dir / f"{today}.json"
    with open(snapshot_file, "w") as f:
        json.dump(snapshot_data, f, indent=2)

    print(f"  Archived snapshot: {snapshot_file}")
    return snapshot_file


def append_to_history(row: dict, data_dir: Path) -> None:
    """Append one row to dispersion_history.csv, skipping if date already exists."""
    history_file = data_dir / "dispersion_history.csv"

    df = pd.DataFrame([row], columns=HISTORY_COLUMNS)
    today = row["date"]

    if history_file.exists():
        existing = pd.read_csv(history_file, usecols=["date"], dtype=str)
        if today in existing["date"].values:
            print(f"  Skipped: {today} already in history")
            return
        df.to_csv(history_file, mode="a", header=False, index=False)
    else:
        df.to_csv(history_file, index=False)

    print(f"  Appended to history: {history_file}")


def collect(data_dir: Path, index_ticker: str, constituents: list[str]) -> bool:
    """Full collection pipeline."""
    print(f"\n{'='*60}")
    print(f"Dispersion Trading Snapshot")
    print(f"Index: {index_ticker}, Constituents: {len(constituents)}")
    print(f"{'='*60}")

    # Idempotency check
    if already_collected_today(data_dir):
        print(f"  Already collected today, skipping")
        return False

    provider = get_provider()
    n = len(constituents)
    weights = np.ones(n) / n  # Equal weights

    # Fetch index IV
    try:
        info = provider.fetch_ticker_info(index_ticker)
        if info is None or info.price <= 0:
            print(f"  ERROR: Could not get spot for {index_ticker}")
            return False
        index_spot = info.price

        index_iv = retry_with_backoff(lambda: get_atm_iv(provider, index_ticker, index_spot))
        if index_iv <= 0:
            print(f"  ERROR: Could not get IV for {index_ticker}")
            return False
        print(f"  {index_ticker}: spot=${index_spot:.2f}  IV={index_iv*100:.1f}%")
    except Exception as e:
        print(f"  ERROR fetching {index_ticker}: {e}")
        return False

    # Fetch constituent IVs and prices
    constituent_ivs = []
    constituent_tickers = []
    prices_dict = {}

    for ticker in constituents:
        try:
            info = provider.fetch_ticker_info(ticker)
            if info is None or info.price <= 0:
                print(f"  {ticker}: SKIP (no spot)")
                continue

            iv = retry_with_backoff(lambda t=ticker, s=info.price: get_atm_iv(provider, t, s))
            if iv <= 0:
                print(f"  {ticker}: SKIP (no IV)")
                continue

            # Fetch prices for realized correlation
            stock = yf.Ticker(ticker)
            hist = retry_with_backoff(lambda: stock.history(period="1mo"))
            if hist is not None and len(hist) >= 10:
                prices_dict[ticker] = hist["Close"].values

            constituent_ivs.append(iv)
            constituent_tickers.append(ticker)
            print(f"  {ticker}: spot=${info.price:.2f}  IV={iv*100:.1f}%")

        except Exception as e:
            print(f"  {ticker}: SKIP ({e})")
            continue

    if len(constituent_ivs) < 3:
        print(f"  ERROR: Too few constituents ({len(constituent_ivs)}, need >=3)")
        return False

    # Recompute equal weights for available constituents
    n_avail = len(constituent_ivs)
    weights = np.ones(n_avail) / n_avail
    ivs = np.array(constituent_ivs)

    # Dispersion metrics
    weighted_avg_iv = float(np.sum(weights * ivs))
    dispersion_level = weighted_avg_iv - index_iv

    # Implied correlation
    implied_corr = compute_implied_correlation(index_iv, ivs, weights)

    # Realized correlation
    if len(prices_dict) >= 3:
        # Use only tickers we have prices for
        avail_prices = {t: prices_dict[t] for t in constituent_tickers if t in prices_dict}
        avail_weights = np.ones(len(avail_prices)) / len(avail_prices)
        realized_corr = compute_realized_correlation(avail_prices, avail_weights)
    else:
        realized_corr = 0.0

    print(f"\n  Weighted Avg IV: {weighted_avg_iv*100:.1f}%")
    print(f"  Index IV:        {index_iv*100:.1f}%")
    print(f"  Dispersion:      {dispersion_level*100:+.1f}%")
    print(f"  Implied Corr:    {implied_corr:.3f}")
    print(f"  Realized Corr:   {realized_corr:.3f}")

    # Archive
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_data = {
        "date": today,
        "index": index_ticker,
        "index_spot": index_spot,
        "index_iv": index_iv,
        "constituents": [
            {"ticker": t, "iv": float(ivs[i]), "weight": float(weights[i])}
            for i, t in enumerate(constituent_tickers)
        ],
        "weighted_avg_iv": weighted_avg_iv,
        "dispersion_level": dispersion_level,
        "implied_correlation": implied_corr,
        "realized_correlation": realized_corr,
        "provider": provider.name,
    }
    archive_snapshot(snapshot_data, data_dir)

    # Append to history
    row = {
        "date": today,
        "index": index_ticker,
        "index_iv": index_iv,
        "weighted_avg_iv": weighted_avg_iv,
        "dispersion_level": dispersion_level,
        "implied_correlation": implied_corr,
        "realized_correlation": realized_corr,
    }
    append_to_history(row, data_dir)

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Daily dispersion trading snapshot collector"
    )
    parser.add_argument("--index", type=str, default=DEFAULT_INDEX,
                        help=f"Index ticker (default: {DEFAULT_INDEX})")
    parser.add_argument("--constituents", type=str,
                        default=",".join(DEFAULT_CONSTITUENTS),
                        help="Comma-separated constituent tickers")
    parser.add_argument("--data-dir", type=str,
                        default="pricing/dispersion_trading/data",
                        help="Data directory")

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    constituents = [t.strip().upper() for t in args.constituents.split(",")]

    success = collect(data_dir, args.index.upper(), constituents)
    return 0 if success else 1


if __name__ == "__main__":
    exit(main())
