#!/usr/bin/env python3
"""
Daily volatility arbitrage snapshot collector.

Fetches ATM implied volatility from option chains and computes realized
volatility (Yang-Zhang estimator) and EWMA forecast from price history.
Signals when IV diverges from forecast RV.

Each run:
- Fetches ATM IV from nearest expiry option chain
- Fetches 3 months of OHLC for Yang-Zhang RV computation
- Computes EWMA vol forecast (lambda=0.94)
- Archives full snapshot to data/snapshots/{TICKER}/{YYYY-MM-DD}.json
- Appends one row to data/{TICKER}_volarb_history_yfinance.csv

Idempotent: skips tickers already collected today.

Yang-Zhang estimator (matching OCaml realized_vol.ml):
  sigma^2 = sigma^2_overnight + k * sigma^2_close + (1-k) * sigma^2_rs
  where k = 0.34 / (1.34 + (n+1)/(n-1))
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

# CSV header for vol arb history
HISTORY_COLUMNS = [
    "date", "ticker", "spot", "atm_iv",
    "rv_yang_zhang", "rv_ewma", "rv_forecast",
    "iv_rv_spread", "iv_rv_ratio",
]

# EWMA decay factor (RiskMetrics standard)
EWMA_LAMBDA = 0.94


def already_collected_today(ticker: str, data_dir: Path) -> bool:
    """Check if today's snapshot already exists."""
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_file = data_dir / "snapshots" / ticker / f"{today}.json"
    return snapshot_file.exists()


def yang_zhang_rv(ohlc: pd.DataFrame, window: int = 21) -> float:
    """
    Yang-Zhang realized volatility estimator (annualized).

    Combines overnight, open-to-close, and Rogers-Satchell components.
    Matches OCaml realized_vol.ml logic.
    """
    if len(ohlc) < window + 1:
        return 0.0

    df = ohlc.iloc[-window - 1:].copy()
    o = df["Open"].values[1:]
    h = df["High"].values[1:]
    l = df["Low"].values[1:]
    c = df["Close"].values[1:]
    c_prev = df["Close"].values[:-1]

    n = len(o)
    if n < 2:
        return 0.0

    # Overnight returns: log(open / prev_close)
    overnight = np.log(o / c_prev)
    # Open-to-close returns: log(close / open)
    oc = np.log(c / o)

    # Overnight variance
    mean_overnight = np.mean(overnight)
    var_overnight = np.sum((overnight - mean_overnight) ** 2) / (n - 1)

    # Open-to-close variance
    mean_oc = np.mean(oc)
    var_close = np.sum((oc - mean_oc) ** 2) / (n - 1)

    # Rogers-Satchell variance
    log_ho = np.log(h / o)
    log_hc = np.log(h / c)
    log_lo = np.log(l / o)
    log_lc = np.log(l / c)
    var_rs = np.mean(log_ho * log_hc + log_lo * log_lc)

    # Yang-Zhang combination
    k = 0.34 / (1.34 + (n + 1) / (n - 1))
    var_yz = var_overnight + k * var_close + (1 - k) * var_rs

    # Annualize
    return float(np.sqrt(max(0.0, var_yz) * 252))


def ewma_forecast(returns: np.ndarray, lam: float = EWMA_LAMBDA) -> float:
    """
    EWMA volatility forecast (annualized).

    sigma^2_t = lambda * sigma^2_{t-1} + (1-lambda) * r^2_{t-1}
    Matches OCaml vol_forecast.ml EWMA logic.
    """
    if len(returns) < 2:
        return 0.0

    # Initialize with sample variance
    var = np.var(returns[:21]) if len(returns) >= 21 else np.var(returns)

    for r in returns:
        var = lam * var + (1 - lam) * r ** 2

    return float(np.sqrt(max(0.0, var) * 252))


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
        # Fallback: use first available
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
    """Append one row to {TICKER}_volarb_history_yfinance.csv, skipping if date already exists."""
    history_file = data_dir / f"{ticker}_volarb_history_yfinance.csv"

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


def collect_one_ticker(ticker: str, data_dir: Path) -> bool:
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

    # Fetch ATM IV
    try:
        atm_iv = retry_with_backoff(lambda: get_atm_iv(provider, ticker, spot))
        if atm_iv <= 0:
            print(f"  ERROR: Could not get ATM IV for {ticker}")
            return False
    except Exception as e:
        print(f"  ERROR fetching IV for {ticker}: {e}")
        return False

    # Fetch OHLC for RV computation
    try:
        stock = yf.Ticker(ticker)
        hist = retry_with_backoff(lambda: stock.history(period="3mo"))
        if hist is None or len(hist) < 22:
            print(f"  ERROR: Insufficient OHLC history for {ticker}")
            return False
    except Exception as e:
        print(f"  ERROR fetching OHLC for {ticker}: {e}")
        return False

    # Yang-Zhang realized vol (21-day)
    rv_yz = yang_zhang_rv(hist, window=21)
    if rv_yz <= 0:
        # Fallback to close-to-close
        closes = hist["Close"].values
        log_rets = np.diff(np.log(closes[-22:]))
        rv_yz = float(np.std(log_rets, ddof=1) * np.sqrt(252)) if len(log_rets) > 1 else 0.0

    # EWMA forecast
    closes = hist["Close"].values
    log_returns = np.diff(np.log(closes))
    rv_ewma = ewma_forecast(log_returns, lam=EWMA_LAMBDA)

    # Use EWMA as primary forecast (simple, no parameters to estimate)
    rv_forecast = rv_ewma

    # IV-RV metrics
    iv_rv_spread = atm_iv - rv_yz
    iv_rv_ratio = atm_iv / rv_yz if rv_yz > 0 else 0.0

    print(f"  Spot:           ${spot:.2f}")
    print(f"  ATM IV:         {atm_iv*100:.1f}%")
    print(f"  RV (YZ 21d):    {rv_yz*100:.1f}%")
    print(f"  RV (EWMA):      {rv_ewma*100:.1f}%")
    print(f"  IV-RV spread:   {iv_rv_spread*100:+.1f}%")
    print(f"  IV/RV ratio:    {iv_rv_ratio:.2f}")

    # Archive full snapshot
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_data = {
        "date": today,
        "ticker": ticker,
        "spot": spot,
        "atm_iv": atm_iv,
        "rv_yang_zhang": rv_yz,
        "rv_ewma": rv_ewma,
        "rv_forecast": rv_forecast,
        "iv_rv_spread": iv_rv_spread,
        "iv_rv_ratio": iv_rv_ratio,
        "provider": provider.name,
    }
    archive_snapshot(snapshot_data, ticker, data_dir)

    # Append to CSV history
    row = {
        "date": today,
        "ticker": ticker,
        "spot": spot,
        "atm_iv": atm_iv,
        "rv_yang_zhang": rv_yz,
        "rv_ewma": rv_ewma,
        "rv_forecast": rv_forecast,
        "iv_rv_spread": iv_rv_spread,
        "iv_rv_ratio": iv_rv_ratio,
    }
    append_to_history(row, ticker, data_dir)

    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Daily volatility arbitrage snapshot collector"
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--ticker", type=str, help="Single ticker symbol")
    group.add_argument("--tickers", type=str,
                       help="Comma-separated tickers, 'all_liquid', or path to .txt file")
    parser.add_argument("--data-dir", type=str,
                        default="pricing/volatility_arbitrage/data",
                        help="Data directory (default: pricing/volatility_arbitrage/data)")

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

    print(f"Volatility Arbitrage Collection: {len(tickers)} tickers")
    print(f"Data dir: {data_dir}")

    successes = 0
    for ticker in tickers:
        if collect_one_ticker(ticker, data_dir):
            successes += 1

    print(f"\nCollection complete: {successes}/{len(tickers)} tickers collected")
    return 0 if successes > 0 or all(
        already_collected_today(t, data_dir) for t in tickers
    ) else 1


if __name__ == "__main__":
    exit(main())
