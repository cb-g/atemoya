#!/usr/bin/env python3
"""
Daily skew verticals snapshot collector.

Fetches option chains and price history, then computes the metrics needed
for the triple-filter scanner:
  1. Skew z-score (call and put, vs rolling history)
  2. VRP = ATM IV - realized vol (and OTM IV > RV check)
  3. Momentum score (-1 to +1)
  4. Edge score (0-100)

Designed for daily cron after market close.

Each run:
- Fetches option chain for ~14 DTE expiry
- Fetches 3 months of price history + SPY for beta
- Computes skew metrics, momentum, VRP
- Archives full snapshot to data/snapshots/{TICKER}/{YYYY-MM-DD}.json
- Appends one row to data/{TICKER}_skewvert_history.csv

Idempotent: skips tickers already collected today.
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import argparse

# Add project root to path
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf
from lib.python.retry import retry_with_backoff
from lib.python.data_fetcher import get_provider

# CSV header for skew verticals history
HISTORY_COLUMNS = [
    "date", "ticker", "spot", "atm_iv",
    "call_25d_iv", "put_25d_iv",
    "call_skew", "put_skew",
    "rv_30d", "vrp",
    "return_1w", "return_1m", "return_3m",
    "momentum_score", "edge_score",
]


def already_collected_today(ticker: str, data_dir: Path) -> bool:
    """Check if today's snapshot already exists."""
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_file = data_dir / "snapshots" / ticker / f"{today}.json"
    return snapshot_file.exists()


def find_target_expiry(expiries: list[str], target_days: int = 14) -> str | None:
    """Find expiration closest to target_days DTE, within 7-45 day range."""
    today = datetime.now().date()
    best = None
    best_diff = float('inf')

    for exp_str in expiries:
        exp_date = pd.to_datetime(exp_str).date()
        dte = (exp_date - today).days
        if dte < 7 or dte > 45:
            continue
        diff = abs(dte - target_days)
        if diff < best_diff:
            best = exp_str
            best_diff = diff

    return best


def compute_skew_metrics(calls_iv: dict[float, float], puts_iv: dict[float, float],
                         spot: float) -> dict:
    """
    Compute call/put skew from IV by strike.

    Skew = (ATM_IV - 25delta_IV) / ATM_IV
    Negative = OTM expensive relative to ATM (what we want to sell).
    """
    # Find ATM strike (closest to spot)
    all_strikes = sorted(calls_iv.keys())
    if not all_strikes:
        return {}

    atm_strike = min(all_strikes, key=lambda k: abs(k - spot))
    atm_iv = calls_iv.get(atm_strike, 0)

    if atm_iv <= 0:
        return {}

    # Approximate 25-delta strikes:
    # 25-delta call ≈ spot * (1 + 0.05 to 0.15), pick closest
    # 25-delta put ≈ spot * (1 - 0.05 to 0.15), pick closest
    call_25d_target = spot * 1.06
    put_25d_target = spot * 0.94

    call_25d_strike = min(all_strikes, key=lambda k: abs(k - call_25d_target))
    put_strikes = sorted(puts_iv.keys())
    put_25d_strike = min(put_strikes, key=lambda k: abs(k - put_25d_target)) if put_strikes else atm_strike

    call_25d_iv = calls_iv.get(call_25d_strike, 0)
    put_25d_iv = puts_iv.get(put_25d_strike, 0)

    # Skew: negative means OTM is expensive relative to ATM
    call_skew = (atm_iv - call_25d_iv) / atm_iv if call_25d_iv > 0 else 0
    put_skew = (atm_iv - put_25d_iv) / atm_iv if put_25d_iv > 0 else 0

    return {
        "atm_iv": atm_iv,
        "call_25d_iv": call_25d_iv,
        "put_25d_iv": put_25d_iv,
        "call_skew": call_skew,
        "put_skew": put_skew,
    }


def compute_realized_vol(prices: np.ndarray, lookback: int = 30) -> float:
    """Annualized realized vol from close-to-close log returns."""
    if len(prices) < lookback + 1:
        return 0.0
    closes = prices[-lookback:]
    log_returns = np.diff(np.log(closes))
    if len(log_returns) < 2:
        return 0.0
    return float(np.std(log_returns, ddof=1) * np.sqrt(252))


def compute_momentum(prices: np.ndarray, spy_prices: np.ndarray) -> dict:
    """
    Compute momentum score (-1 to +1).

    Components (matching OCaml momentum.ml):
      30% from 1M return sign + magnitude
      30% from 3M return
      20% from 52W high proximity
      20% from alpha (excess return vs beta * market)
    """
    if len(prices) < 5:
        return {"return_1w": 0, "return_1m": 0, "return_3m": 0, "momentum_score": 0}

    current = prices[-1]
    ret_1w = (current / prices[-5] - 1) if len(prices) >= 5 else 0
    ret_1m = (current / prices[-21] - 1) if len(prices) >= 21 else 0
    ret_3m = (current / prices[-63] - 1) if len(prices) >= 63 else 0
    high_52w = np.max(prices)
    pct_from_high = (current - high_52w) / high_52w if high_52w > 0 else 0

    # Beta and alpha
    alpha = 0.0
    if len(prices) >= 21 and len(spy_prices) >= 21:
        n = min(len(prices), len(spy_prices))
        stock_rets = np.diff(np.log(prices[-n:]))
        spy_rets = np.diff(np.log(spy_prices[-n:]))
        if len(stock_rets) > 1 and len(spy_rets) > 1:
            m = min(len(stock_rets), len(spy_rets))
            stock_rets = stock_rets[-m:]
            spy_rets = spy_rets[-m:]
            cov = np.cov(stock_rets, spy_rets)
            beta = cov[0, 1] / cov[1, 1] if cov[1, 1] > 0 else 1.0
            spy_1m = (spy_prices[-1] / spy_prices[-21] - 1) if len(spy_prices) >= 21 else 0
            alpha = ret_1m - beta * spy_1m

    # Composite score
    def sign_scaled(x, scale=1.0):
        return np.clip(np.sign(x) * min(abs(x) * scale, 1.0), -1, 1)

    score = (
        0.30 * sign_scaled(ret_1m, 5) +
        0.30 * sign_scaled(ret_3m, 3) +
        0.20 * np.clip(1.0 + pct_from_high, 0, 1) +
        0.20 * sign_scaled(alpha, 10)
    )
    score = np.clip(score, -1, 1)

    return {
        "return_1w": float(ret_1w),
        "return_1m": float(ret_1m),
        "return_3m": float(ret_3m),
        "momentum_score": float(score),
    }


def compute_edge_score(call_skew_z: float, put_skew_z: float,
                       momentum_score: float, vrp: float) -> float:
    """
    Compute edge score 0-100 (matching OCaml scanner.ml).

    40 pts: skew z-score magnitude
    20 pts: momentum strength
    30 pts: VRP magnitude (proxy for reward/risk)
    10 pts: direction alignment bonus
    """
    skew_z = max(abs(call_skew_z), abs(put_skew_z))
    skew_pts = min(skew_z * 10, 40)

    momentum_pts = abs(momentum_score) * 20

    vrp_pts = min(max(vrp * 100, 0), 30)  # 0-30 based on VRP magnitude

    # Direction alignment bonus
    align_pts = 0
    if (momentum_score > 0.3 and put_skew_z < -2) or \
       (momentum_score < -0.3 and call_skew_z < -2):
        align_pts = 10

    return min(skew_pts + momentum_pts + vrp_pts + align_pts, 100)


def archive_snapshot(snapshot_data: dict, ticker: str, data_dir: Path) -> Path:
    """Save full snapshot to data/snapshots/{TICKER}/{YYYY-MM-DD}.json."""
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_dir = data_dir / "snapshots" / ticker
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    snapshot_file = snapshot_dir / f"{today}.json"
    with open(snapshot_file, "w") as f:
        json.dump(snapshot_data, f, indent=2)

    print(f"  Archived snapshot: {snapshot_file}")
    return snapshot_file


def append_to_history(row: dict, ticker: str, data_dir: Path) -> None:
    """Append one row to {TICKER}_skewvert_history.csv, skipping if date already exists."""
    history_file = data_dir / f"{ticker}_skewvert_history.csv"

    df = pd.DataFrame([row], columns=HISTORY_COLUMNS)
    today = row["date"]

    if history_file.exists():
        existing = pd.read_csv(history_file, usecols=["date"], dtype=str)
        if today in existing["date"].values:
            print(f"  Skipped {ticker}: {today} already in history")
            return
        df.to_csv(history_file, mode="a", header=False, index=False)
    else:
        df.to_csv(history_file, index=False)

    print(f"  Appended to history: {history_file}")


def collect_one_ticker(ticker: str, data_dir: Path,
                       spy_prices: np.ndarray | None = None) -> bool:
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

    # Get provider and spot price
    provider = get_provider()

    try:
        info = provider.fetch_ticker_info(ticker)
        if info is None or info.price <= 0:
            print(f"  ERROR: Could not get spot price for {ticker}")
            return False
        spot = info.price
    except Exception as e:
        print(f"  ERROR fetching spot for {ticker}: {e}")
        return False

    # Get option chain for ~14 DTE expiry
    try:
        chain = provider.fetch_option_chain(ticker)
        if chain is None or not chain.expiries:
            print(f"  ERROR: No options available for {ticker}")
            return False

        target_expiry = find_target_expiry(chain.expiries)
        if not target_expiry:
            print(f"  No expiry in 7-45 day range, skipping")
            return False

        chain = provider.fetch_option_chain(ticker, expiry=target_expiry)
        if chain is None:
            print(f"  ERROR: Could not fetch chain for {target_expiry}")
            return False

        calls = [c for c in chain.calls if c.expiry == target_expiry]
        puts = [p for p in chain.puts if p.expiry == target_expiry]

        if not calls or not puts:
            print(f"  ERROR: No calls/puts for expiry {target_expiry}")
            return False

    except Exception as e:
        print(f"  ERROR fetching options for {ticker}: {e}")
        return False

    # Build IV maps by strike
    calls_iv = {c.strike: c.implied_volatility for c in calls if c.implied_volatility > 0}
    puts_iv = {p.strike: p.implied_volatility for p in puts if p.implied_volatility > 0}

    if not calls_iv or not puts_iv:
        print(f"  ERROR: No valid IVs for {ticker}")
        return False

    # Compute skew metrics
    skew = compute_skew_metrics(calls_iv, puts_iv, spot)
    if not skew:
        print(f"  ERROR: Could not compute skew for {ticker}")
        return False

    # Fetch price history for RV and momentum
    try:
        stock = yf.Ticker(ticker)
        hist = retry_with_backoff(lambda: stock.history(period="3mo"))
        if hist is None or len(hist) < 21:
            print(f"  ERROR: Insufficient price history for {ticker}")
            return False
        prices = hist["Close"].values
    except Exception as e:
        print(f"  ERROR fetching prices for {ticker}: {e}")
        return False

    # Realized vol
    rv = compute_realized_vol(prices, lookback=30)

    # VRP = ATM IV - realized vol
    vrp = skew["atm_iv"] - rv

    # Momentum
    if spy_prices is None:
        try:
            spy = yf.Ticker("SPY")
            spy_hist = retry_with_backoff(lambda: spy.history(period="3mo"))
            spy_prices = spy_hist["Close"].values if spy_hist is not None else np.array([])
        except Exception:
            spy_prices = np.array([])

    momentum = compute_momentum(prices, spy_prices)

    # Compute skew z-scores (need history for proper z-scores, use skew magnitude as proxy on day 1)
    history_file = data_dir / f"{ticker}_skewvert_history.csv"
    call_skew_z = 0.0
    put_skew_z = 0.0
    if history_file.exists():
        try:
            hist_df = pd.read_csv(history_file)
            if len(hist_df) >= 3:
                cs = hist_df["call_skew"].dropna()
                if len(cs) >= 3 and cs.iloc[:-1].std() > 0:
                    call_skew_z = (skew["call_skew"] - cs.iloc[:-1].mean()) / cs.iloc[:-1].std()
                ps = hist_df["put_skew"].dropna()
                if len(ps) >= 3 and ps.iloc[:-1].std() > 0:
                    put_skew_z = (skew["put_skew"] - ps.iloc[:-1].mean()) / ps.iloc[:-1].std()
        except Exception:
            pass

    # Edge score
    edge = compute_edge_score(call_skew_z, put_skew_z,
                              momentum["momentum_score"], vrp)

    print(f"  Spot:           ${spot:.2f}")
    print(f"  ATM IV:         {skew['atm_iv']*100:.1f}%")
    print(f"  Call skew:      {skew['call_skew']:+.4f}")
    print(f"  Put skew:       {skew['put_skew']:+.4f}")
    print(f"  RV (30d):       {rv*100:.1f}%")
    print(f"  VRP:            {vrp*100:.1f}%")
    print(f"  Momentum:       {momentum['momentum_score']:+.2f}")
    print(f"  Edge score:     {edge:.0f}/100")

    # Archive full snapshot
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_data = {
        "date": today,
        "ticker": ticker,
        "spot": spot,
        "expiry": target_expiry,
        "skew": skew,
        "rv_30d": rv,
        "vrp": vrp,
        "momentum": momentum,
        "call_skew_z": call_skew_z,
        "put_skew_z": put_skew_z,
        "edge_score": edge,
        "provider": provider.name,
    }
    archive_snapshot(snapshot_data, ticker, data_dir)

    # Append to CSV history
    row = {
        "date": today,
        "ticker": ticker,
        "spot": spot,
        "atm_iv": skew["atm_iv"],
        "call_25d_iv": skew["call_25d_iv"],
        "put_25d_iv": skew["put_25d_iv"],
        "call_skew": skew["call_skew"],
        "put_skew": skew["put_skew"],
        "rv_30d": rv,
        "vrp": vrp,
        "return_1w": momentum["return_1w"],
        "return_1m": momentum["return_1m"],
        "return_3m": momentum["return_3m"],
        "momentum_score": momentum["momentum_score"],
        "edge_score": edge,
    }
    append_to_history(row, ticker, data_dir)

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Daily skew verticals snapshot collector"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", type=str, help="Single ticker symbol")
    group.add_argument("--tickers", type=str,
                       help="Comma-separated tickers, 'all_liquid', or path to .txt file")
    parser.add_argument("--data-dir", type=str,
                        default="pricing/skew_verticals/data",
                        help="Data directory (default: pricing/skew_verticals/data)")

    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)

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

    print(f"Skew Verticals Collection: {len(tickers)} tickers")
    print(f"Data dir: {data_dir}")

    # Pre-fetch SPY prices once for all tickers
    try:
        spy = yf.Ticker("SPY")
        spy_hist = retry_with_backoff(lambda: spy.history(period="3mo"))
        spy_prices = spy_hist["Close"].values if spy_hist is not None else np.array([])
        print(f"SPY history: {len(spy_prices)} days")
    except Exception:
        spy_prices = np.array([])

    successes = 0
    for ticker in tickers:
        if collect_one_ticker(ticker, data_dir, spy_prices):
            successes += 1

    print(f"\nCollection complete: {successes}/{len(tickers)} tickers collected")
    return 0 if successes > 0 or all(
        already_collected_today(t, data_dir) for t in tickers
    ) else 1


if __name__ == "__main__":
    exit(main())
