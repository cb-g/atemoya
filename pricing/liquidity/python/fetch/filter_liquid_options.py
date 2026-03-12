#!/usr/bin/env python3
"""
Gate 2: Filter liquid tickers by options chain depth.

Reads liquid_tickers.txt (gate 1 output), fetches option chain metadata
for each ticker, and filters by minimum expiries and strikes per expiry.
Outputs liquid_options.txt containing tickers whose options chains are
deep enough for SVI calibration.

Thresholds are derived from the skew trading SVI calibrator:
- >= 3 expiries (7-365 DTE)
- >= 5 OTM strikes on at least 2 expiries
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import yfinance as yf

PROJECT_ROOT = Path(__file__).resolve().parents[4]
DATA_DIR = PROJECT_ROOT / "pricing" / "liquidity" / "data"
PROGRESS_FILE = DATA_DIR / "filter_options_progress.json"


def load_progress() -> dict:
    """Load progress from previous run."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"completed": [], "failed": [], "passing": [], "stats": {}, "timestamp": None}


def save_progress(progress: dict):
    """Save progress for resumability."""
    progress["timestamp"] = datetime.now().isoformat()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def write_liquid_options(progress: dict, output_path: Path):
    """Write liquid_options.txt from progress data."""
    passing = sorted(set(progress["passing"]))
    with open(output_path, "w") as f:
        for ticker in passing:
            f.write(ticker + "\n")


def check_chain_depth(ticker: str, min_expiries: int, min_strikes: int) -> dict | None:
    """
    Check if a ticker's option chain is deep enough for SVI calibration.

    Returns stats dict if passing, None if failing.
    """
    stock = yf.Ticker(ticker)

    try:
        expirations = stock.options
    except Exception:
        return None

    if not expirations:
        return None

    now = datetime.now()
    valid_expiries = []

    for exp_str in expirations:
        exp_date = datetime.strptime(exp_str, "%Y-%m-%d")
        dte = (exp_date - now).days
        if 7 <= dte <= 365:
            valid_expiries.append(exp_str)

    if len(valid_expiries) < min_expiries:
        return None

    # Get spot for OTM classification
    try:
        info = stock.info
        spot = info.get("regularMarketPrice") or info.get("previousClose") or info.get("currentPrice", 0)
    except Exception:
        spot = 0

    if spot <= 0:
        return None

    # Check strikes per expiry (only need min_strikes OTM on at least 2 expiries)
    deep_expiries = 0
    total_otm_strikes = 0

    for exp_str in valid_expiries[:5]:  # Check up to 5 nearest to avoid excessive API calls
        try:
            chain = stock.option_chain(exp_str)
        except Exception:
            continue

        otm_calls = chain.calls[chain.calls["strike"] >= spot]
        otm_puts = chain.puts[chain.puts["strike"] < spot]
        n_otm = len(otm_calls) + len(otm_puts)
        total_otm_strikes += n_otm

        if n_otm >= min_strikes:
            deep_expiries += 1

    if deep_expiries < 2:
        return None

    return {
        "ticker": ticker,
        "valid_expiries": len(valid_expiries),
        "deep_expiries": deep_expiries,
        "total_otm_strikes": total_otm_strikes,
        "spot": spot,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Filter liquid tickers by options chain depth (gate 2)"
    )
    parser.add_argument(
        "--input",
        default=str(DATA_DIR / "liquid_tickers.txt"),
        help="Input file (gate 1 output)",
    )
    parser.add_argument(
        "--output",
        default=str(DATA_DIR / "liquid_options.txt"),
        help="Output file for tickers with deep options chains",
    )
    parser.add_argument("--batch-size", type=int, default=20, help="Tickers per batch")
    parser.add_argument("--min-expiries", type=int, default=3, help="Minimum valid expiries (7-365 DTE)")
    parser.add_argument("--min-strikes", type=int, default=5, help="Minimum OTM strikes per expiry for SVI")
    parser.add_argument("--delay", type=float, default=2, help="Seconds between tickers")
    parser.add_argument("--no-resume", action="store_true", help="Ignore progress, start fresh")

    args = parser.parse_args()

    # Load input tickers
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: {input_path} not found. Run filter_liquid_tickers.py first.", file=sys.stderr)
        sys.exit(1)

    all_tickers = [t.strip() for t in input_path.read_text().splitlines() if t.strip()]
    if not all_tickers:
        print("Error: no tickers in input file", file=sys.stderr)
        sys.exit(1)
    print(f"Loaded {len(all_tickers)} liquid tickers (gate 1)")

    # Load or reset progress
    if args.no_resume:
        progress = {"completed": [], "failed": [], "passing": [], "stats": {}, "timestamp": None}
    else:
        progress = load_progress()
        if progress["completed"]:
            print(f"Resuming: {len(progress['completed'])} completed, {len(progress['passing'])} passing so far")

    # Filter to remaining (retry failed)
    done = set(progress["completed"])
    previously_failed = set(progress["failed"])
    remaining = [t for t in all_tickers if t not in done]
    if previously_failed:
        progress["failed"] = []
    print(f"Remaining: {len(remaining)} tickers ({len(previously_failed)} retries)")

    if not remaining:
        print("All tickers already processed")
    else:
        total_batches = (len(remaining) + args.batch_size - 1) // args.batch_size
        for batch_idx in range(total_batches):
            start = batch_idx * args.batch_size
            end = start + args.batch_size
            batch = remaining[start:end]

            print(f"\n--- Batch {batch_idx + 1}/{total_batches} ({len(batch)} tickers) ---")

            for i, ticker in enumerate(batch):
                print(f"  {ticker}...", end=" ", flush=True)
                try:
                    stats = check_chain_depth(ticker, args.min_expiries, args.min_strikes)
                    if stats:
                        progress["passing"].append(ticker)
                        progress["stats"][ticker] = stats
                        print(f"PASS ({stats['valid_expiries']} expiries, {stats['deep_expiries']} deep, {stats['total_otm_strikes']} OTM strikes)")
                    else:
                        print("fail")
                    progress["completed"].append(ticker)
                except Exception as e:
                    print(f"error: {e}")
                    progress["failed"].append(ticker)

                if args.delay > 0 and i < len(batch) - 1:
                    time.sleep(args.delay)

            save_progress(progress)
            write_liquid_options(progress, Path(args.output))
            print(f"  Progress: {len(progress['completed'])}/{len(all_tickers)} completed, {len(progress['passing'])} passing")

    output_path = Path(args.output)
    passing_count = len([t.strip() for t in output_path.read_text().splitlines() if t.strip()]) if output_path.exists() else 0
    print(f"\nDone: {passing_count} tickers with deep options chains in {args.output}")
    print(f"Total: {len(progress['completed'])} completed, {len(progress['failed'])} failed")


if __name__ == "__main__":
    main()
