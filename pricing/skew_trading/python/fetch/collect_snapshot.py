#!/usr/bin/env python3
"""
Daily vol surface snapshot collector for skew trading.

Fetches current option chains, calibrates SVI surfaces, computes real skew
metrics, and archives results. Designed for daily cron execution after
market close.

Each run:
- Archives full SVI snapshot to data/snapshots/{TICKER}/{YYYY-MM-DD}.json
- Appends one row to data/{TICKER}_skew_history.csv

Idempotent: skips tickers already collected today.
"""

import argparse
import json
import math
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# Add project root to path
sys.path.insert(0, str(Path(__file__).parents[4]))

from lib.python.retry import retry_with_backoff

# Reuse functions from fetch_options.py (no duplication)
from pricing.skew_trading.python.fetch.fetch_options import (
    calibrate_svi_surface,
    compute_implied_vols,
    fetch_option_chain,
    load_config,
    svi_variance,
)

CONFIG = load_config()

# CSV header matching the format OCaml io.ml expects (11 columns)
HISTORY_COLUMNS = [
    "timestamp", "ticker", "expiry", "rr25", "bf25", "skew_slope",
    "atm_vol", "put_25d_vol", "call_25d_vol", "put_25d_strike", "call_25d_strike"
]


def normal_cdf(x: float) -> float:
    """Standard normal CDF (matches OCaml erf-based implementation)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def bs_delta(option_type: str, spot: float, strike: float, expiry: float,
             rate: float, dividend: float, volatility: float) -> float:
    """Black-Scholes delta (matches OCaml skew_measurement.ml:51-60)."""
    if expiry <= 0.0 or volatility <= 0.0:
        return 0.0
    d1 = (math.log(spot / strike) + (rate - dividend + 0.5 * volatility ** 2) * expiry) \
         / (volatility * math.sqrt(expiry))
    if option_type == "call":
        return math.exp(-dividend * expiry) * normal_cdf(d1)
    else:
        return math.exp(-dividend * expiry) * (normal_cdf(d1) - 1.0)


def get_iv_from_svi(svi_entry: dict, strike: float, spot: float) -> float:
    """
    Evaluate SVI surface at a given strike.

    Matches OCaml get_iv_from_surface (skew_measurement.ml:26-48).
    """
    log_moneyness = math.log(strike / spot)
    a, b, rho, m, sigma = svi_entry["a"], svi_entry["b"], svi_entry["rho"], svi_entry["m"], svi_entry["sigma"]
    delta_k = log_moneyness - m
    sqrt_term = math.sqrt(delta_k ** 2 + sigma ** 2)
    total_var = a + b * (rho * delta_k + sqrt_term)
    return math.sqrt(max(0.0001, total_var / svi_entry["expiry"]))


def find_delta_strike(option_type: str, target_delta: float, spot: float,
                      expiry: float, rate: float, dividend: float,
                      svi_entry: dict) -> float | None:
    """
    Newton-Raphson to find strike where BS delta = target_delta.

    Direct port of OCaml find_delta_strike (skew_measurement.ml:66-115).
    """
    if expiry <= 0.0:
        return None

    # Initial guess: put-call symmetry approximation
    if option_type == "call":
        strike = spot * math.exp(0.5 * abs(target_delta))
    else:
        strike = spot * math.exp(-0.5 * abs(target_delta))

    for _ in range(20):
        iv = get_iv_from_svi(svi_entry, strike, spot)
        delta = bs_delta(option_type, spot, strike, expiry, rate, dividend, iv)
        error = delta - target_delta

        if abs(error) < 0.001:
            return strike

        # Numerical gamma: d(delta)/d(strike) via finite difference
        h = strike * 0.001
        iv_up = get_iv_from_svi(svi_entry, strike + h, spot)
        delta_up = bs_delta(option_type, spot, strike + h, expiry, rate, dividend, iv_up)
        d_delta_dk = (delta_up - delta) / h

        if abs(d_delta_dk) < 1e-10:
            return None

        new_strike = strike - error / d_delta_dk
        strike = max(spot * 0.5, min(spot * 2.0, new_strike))

    return None


def select_target_expiry(svi_params: list[dict], target_days: int) -> dict | None:
    """Select SVI parameter set closest to target expiry."""
    if not svi_params:
        return None
    target_years = target_days / 365.0
    return min(svi_params, key=lambda p: abs(p["expiry"] - target_years))


def compute_skew_metrics(svi_entry: dict, spot: float, rate: float,
                         dividend: float) -> dict:
    """
    Compute all skew metrics from a single SVI parameter set.

    Matches OCaml compute_skew_observation (skew_measurement.ml:182-218).
    """
    expiry = svi_entry["expiry"]

    # ATM vol: strike = spot (k = 0)
    atm_vol = get_iv_from_svi(svi_entry, spot, spot)

    # 25-delta strikes via Newton-Raphson
    call_strike = find_delta_strike("call", 0.25, spot, expiry, rate, dividend, svi_entry)
    put_strike = find_delta_strike("put", -0.25, spot, expiry, rate, dividend, svi_entry)

    # Fallback if convergence fails (matches OCaml lines 193-200)
    if call_strike is None:
        call_strike = spot * 1.1
    if put_strike is None:
        put_strike = spot * 0.9

    call_25d_vol = get_iv_from_svi(svi_entry, call_strike, spot)
    put_25d_vol = get_iv_from_svi(svi_entry, put_strike, spot)

    rr25 = call_25d_vol - put_25d_vol
    bf25 = (call_25d_vol + put_25d_vol) / 2.0 - atm_vol

    # Skew slope: IV change across 90%-110% moneyness range
    low_iv = get_iv_from_svi(svi_entry, spot * 0.9, spot)
    high_iv = get_iv_from_svi(svi_entry, spot * 1.1, spot)
    skew_slope = (low_iv - high_iv) / 0.2

    return {
        "expiry": expiry,
        "rr25": rr25,
        "bf25": bf25,
        "skew_slope": skew_slope,
        "atm_vol": atm_vol,
        "put_25d_vol": put_25d_vol,
        "call_25d_vol": call_25d_vol,
        "put_25d_strike": put_strike,
        "call_25d_strike": call_strike,
    }


def already_collected_today(ticker: str, data_dir: Path) -> bool:
    """Check if today's snapshot already exists."""
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_file = data_dir / "snapshots" / ticker / f"{today}.json"
    return snapshot_file.exists()


def archive_snapshot(svi_params: list[dict], ticker: str, spot: float,
                     data_dir: Path) -> Path:
    """Save full SVI snapshot to data/snapshots/{TICKER}/{YYYY-MM-DD}.json."""
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_dir = data_dir / "snapshots" / ticker
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    snapshot_file = snapshot_dir / f"{today}.json"
    snapshot_data = {
        "date": today,
        "ticker": ticker,
        "spot": spot,
        "model": "SVI",
        "params": svi_params,
    }

    with open(snapshot_file, "w") as f:
        json.dump(snapshot_data, f, indent=2)

    print(f"  Archived snapshot: {snapshot_file}")
    return snapshot_file


def archive_chain(chain_df: pd.DataFrame, ticker: str, data_dir: Path) -> None:
    """Save raw option chain to data/snapshots/{TICKER}/{YYYY-MM-DD}_chain.csv."""
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_dir = data_dir / "snapshots" / ticker
    chain_file = snapshot_dir / f"{today}_chain.csv"

    cols = ["strike", "expiry_years", "bid", "ask", "mid", "volume", "option_type", "implied_vol"]
    chain_df[[c for c in cols if c in chain_df.columns]].to_csv(chain_file, index=False)

    print(f"  Archived chain: {chain_file} ({len(chain_df)} quotes)")


def append_to_history(row: dict, ticker: str, data_dir: Path) -> None:
    """Append one row to {TICKER}_skew_history.csv."""
    history_file = data_dir / f"{ticker}_skew_history.csv"

    df = pd.DataFrame([row], columns=HISTORY_COLUMNS)

    if history_file.exists():
        df.to_csv(history_file, mode="a", header=False, index=False)
    else:
        df.to_csv(history_file, index=False)

    print(f"  Appended to history: {history_file}")


def collect_one_ticker(ticker: str, data_dir: Path, expiry_days: int,
                       rate: float) -> bool:
    """
    Full collection pipeline for one ticker.

    Returns True if collection succeeded, False if skipped or failed.
    """
    print(f"\n{'='*60}")
    print(f"Collecting: {ticker}")
    print(f"{'='*60}")

    # Idempotency check
    if already_collected_today(ticker, data_dir):
        print(f"  Already collected today, skipping {ticker}")
        return False

    # Fetch option chain (reuse from fetch_options.py)
    try:
        chain_df, spot = retry_with_backoff(lambda: fetch_option_chain(ticker))
    except Exception as e:
        print(f"  ERROR fetching options for {ticker}: {e}")
        return False

    # Compute implied vols
    chain_df = compute_implied_vols(chain_df, spot, rate)
    if len(chain_df) == 0:
        print(f"  ERROR: No valid IVs computed for {ticker}")
        return False

    # Calibrate SVI surface
    svi_params = calibrate_svi_surface(chain_df, spot)
    if not svi_params:
        print(f"  ERROR: SVI calibration failed for {ticker}")
        return False

    # Select target expiry slice
    target = select_target_expiry(svi_params, expiry_days)
    if target is None:
        print(f"  ERROR: No SVI params found for {ticker}")
        return False

    print(f"  Using SVI expiry: {target['expiry']:.4f} ({target['expiry']*365:.0f} days)")

    # Compute real skew metrics
    dividend = CONFIG.get("options", {}).get("dividend_yield", 0.0)
    metrics = compute_skew_metrics(target, spot, rate, dividend)

    print(f"  ATM Vol:  {metrics['atm_vol']*100:.2f}%")
    print(f"  RR25:     {metrics['rr25']*100:.2f}%")
    print(f"  BF25:     {metrics['bf25']*100:.2f}%")
    print(f"  Skew Slope: {metrics['skew_slope']:.4f}")

    # Archive full snapshot (SVI params + raw market chain)
    archive_snapshot(svi_params, ticker, spot, data_dir)
    archive_chain(chain_df, ticker, data_dir)

    # Build row and append to history
    now = datetime.now()
    timestamp = datetime(now.year, now.month, now.day).timestamp()

    row = {
        "timestamp": timestamp,
        "ticker": ticker,
        "expiry": metrics["expiry"],
        "rr25": metrics["rr25"],
        "bf25": metrics["bf25"],
        "skew_slope": metrics["skew_slope"],
        "atm_vol": metrics["atm_vol"],
        "put_25d_vol": metrics["put_25d_vol"],
        "call_25d_vol": metrics["call_25d_vol"],
        "put_25d_strike": metrics["put_25d_strike"],
        "call_25d_strike": metrics["call_25d_strike"],
    }
    append_to_history(row, ticker, data_dir)

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Daily vol surface snapshot collector for skew trading"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", type=str, help="Single ticker symbol")
    group.add_argument("--tickers", type=str,
                       help="Comma-separated tickers, 'all_liquid', or path to .txt file")
    parser.add_argument("--data-dir", type=str,
                        default="pricing/skew_trading/data",
                        help="Data directory (default: pricing/skew_trading/data)")
    parser.add_argument("--expiry-days", type=int, default=30,
                        help="Target expiry for skew metrics (default: 30)")
    parser.add_argument("--rate", type=float, default=None,
                        help="Risk-free rate (default: from config)")

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

    rate = args.rate if args.rate is not None else CONFIG.get("options", {}).get("risk_free_rate", 0.05)

    # Parse ticker list
    if args.ticker:
        tickers = [args.ticker.upper()]
    elif args.tickers == "all_liquid":
        liquid_file = Path(__file__).resolve().parents[4] / "pricing" / "liquidity" / "data" / "liquid_options.txt"
        if not liquid_file.exists():
            print(f"Error: {liquid_file} not found. Run filter_liquid_options.py first.", file=sys.stderr)
            return 1
        tickers = [t.strip() for t in liquid_file.read_text().splitlines() if t.strip()]
    elif args.tickers.endswith(".txt"):
        ticker_file = Path(args.tickers)
        if not ticker_file.exists():
            print(f"Error: {ticker_file} not found", file=sys.stderr)
            return 1
        tickers = [t.strip() for t in ticker_file.read_text().splitlines() if t.strip()]
    else:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]

    print(f"Daily Skew Collection: {len(tickers)} tickers")
    print(f"Data dir: {data_dir}")
    print(f"Target expiry: {args.expiry_days} days")
    print(f"Risk-free rate: {rate*100:.1f}%")

    successes = 0
    for ticker in tickers:
        if collect_one_ticker(ticker, data_dir, args.expiry_days, rate):
            successes += 1

    print(f"\nCollection complete: {successes}/{len(tickers)} tickers collected")
    return 0 if successes > 0 or all(
        already_collected_today(t, data_dir) for t in tickers
    ) else 1


if __name__ == "__main__":
    exit(main())
