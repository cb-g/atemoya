#!/usr/bin/env python3
"""
Filter the CBOE optionable universe down to liquid tickers.

Reads optionable_tickers.csv, runs the existing liquidity pipeline
(Python fetch + OCaml analysis) in batches, and outputs liquid_tickers.txt
containing tickers with liquidity_score >= threshold.
"""

import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path for lib imports
PROJECT_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT_ROOT))

from pricing.liquidity.python.fetch.fetch_liquidity_data import fetch_ticker_data

DATA_DIR = PROJECT_ROOT / "pricing" / "liquidity" / "data"
PROGRESS_FILE = DATA_DIR / "filter_progress.json"
BATCH_DATA_FILE = DATA_DIR / "batch_market_data.json"
BATCH_RESULTS_FILE = DATA_DIR / "batch_results.json"


def load_tickers(input_path: Path) -> list[str]:
    """Load ticker symbols from optionable_tickers.csv."""
    tickers = []
    with open(input_path) as f:
        reader = csv.DictReader(f)
        # Normalize header whitespace
        reader.fieldnames = [field.strip() for field in reader.fieldnames]
        for row in reader:
            symbol = row.get("Stock Symbol", "").strip().strip('"')
            if symbol:
                tickers.append(symbol)
    return tickers


def load_progress() -> dict:
    """Load progress from previous run."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"completed": [], "failed": [], "passing": [], "scores": {}, "timestamp": None}


def save_progress(progress: dict):
    """Save progress for resumability."""
    progress["timestamp"] = datetime.now().isoformat()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def write_liquid_tickers(progress: dict, min_score: float, output_path: Path):
    """Write liquid_tickers.txt from progress data."""
    scores = progress.get("scores", {})
    if scores:
        passing = sorted(t for t, s in scores.items() if s >= min_score)
    else:
        passing = sorted(set(progress["passing"]))
    with open(output_path, "w") as f:
        for ticker in passing:
            f.write(ticker + "\n")


def read_liquid_tickers(output_path: Path) -> list[str]:
    """Read liquid_tickers.txt."""
    if output_path.exists():
        return [t.strip() for t in output_path.read_text().splitlines() if t.strip()]
    return []


def fetch_batch(tickers: list[str], delay: float) -> list[dict]:
    """Fetch market data for a batch of tickers."""
    results = []
    for i, ticker in enumerate(tickers):
        print(f"  {ticker}...", end=" ", flush=True)
        data = fetch_ticker_data(ticker)
        if data:
            results.append(data)
            print("ok")
        else:
            print("skip")
        # Delay between tickers (not after last one)
        if delay > 0 and i < len(tickers) - 1:
            time.sleep(delay)
    return results


def write_batch_data(ticker_data: list[dict]):
    """Write batch market data in the format OCaml expects."""
    payload = {
        "timestamp": datetime.now().isoformat(),
        "period": "3mo",
        "tickers": ticker_data,
    }
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(BATCH_DATA_FILE, "w") as f:
        json.dump(payload, f, indent=2)


def run_ocaml_analysis() -> list[dict]:
    """Run the OCaml liquidity analysis on batch data."""
    cmd = [
        "dune", "exec", "liquidity_exe", "--",
        "--data", str(BATCH_DATA_FILE),
        "--output", str(BATCH_RESULTS_FILE),
        "--json",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  OCaml error: {result.stderr.strip()}", file=sys.stderr)
        return []

    if not BATCH_RESULTS_FILE.exists():
        print("  No results file produced", file=sys.stderr)
        return []

    with open(BATCH_RESULTS_FILE) as f:
        data = json.load(f)
    return data.get("results", [])


def main():
    parser = argparse.ArgumentParser(
        description="Filter optionable tickers by liquidity score"
    )
    parser.add_argument(
        "--input",
        default=str(DATA_DIR / "optionable_tickers.csv"),
        help="Path to optionable_tickers.csv",
    )
    parser.add_argument(
        "--output",
        default=str(DATA_DIR / "liquid_tickers.txt"),
        help="Output file for liquid tickers",
    )
    parser.add_argument("--batch-size", type=int, default=20, help="Tickers per batch")
    parser.add_argument("--min-score", type=float, default=75, help="Minimum liquidity score")
    parser.add_argument("--delay", type=float, default=10, help="Seconds between tickers")
    parser.add_argument("--no-resume", action="store_true", help="Ignore progress, start fresh")

    args = parser.parse_args()

    # Load all tickers
    all_tickers = load_tickers(Path(args.input))
    if not all_tickers:
        print("Error: no tickers found in input file", file=sys.stderr)
        sys.exit(1)
    print(f"Loaded {len(all_tickers)} optionable tickers")

    # Load or reset progress
    if args.no_resume:
        progress = {"completed": [], "failed": [], "passing": [], "scores": {}, "timestamp": None}
    else:
        progress = load_progress()
        if progress["completed"]:
            print(f"Resuming: {len(progress['completed'])} completed, {len(progress['failed'])} failed (will retry), {len(progress['passing'])} passing so far")

    # Filter to remaining tickers (retry failed ones too)
    done = set(progress["completed"])
    previously_failed = set(progress["failed"])
    remaining = [t for t in all_tickers if t not in done]
    if previously_failed:
        progress["failed"] = []  # Reset failed list so retries get a fresh slate
    print(f"Remaining: {len(remaining)} tickers to process ({len(previously_failed)} retries)")

    if not remaining:
        print("All tickers already processed")
    else:
        # Process in batches
        total_batches = (len(remaining) + args.batch_size - 1) // args.batch_size
        for batch_idx in range(total_batches):
            start = batch_idx * args.batch_size
            end = start + args.batch_size
            batch = remaining[start:end]

            print(f"\n--- Batch {batch_idx + 1}/{total_batches} ({len(batch)} tickers) ---")

            # Fetch market data
            ticker_data = fetch_batch(batch, args.delay)
            fetched_tickers = {d["ticker"] for d in ticker_data}
            failed_tickers = [t for t in batch if t not in fetched_tickers]

            progress["failed"].extend(failed_tickers)
            if failed_tickers:
                print(f"  Failed to fetch: {len(failed_tickers)} tickers")

            if not ticker_data:
                print("  No data fetched for this batch, skipping analysis")
                progress["completed"].extend([])
                save_progress(progress)
                continue

            # Write batch data and run OCaml analysis
            write_batch_data(ticker_data)
            results = run_ocaml_analysis()

            # Collect scores and passing tickers
            if "scores" not in progress:
                progress["scores"] = {}
            for r in results:
                ticker = r["ticker"]
                score = r.get("liquidity_score", 0)
                progress["scores"][ticker] = score
                if score >= args.min_score:
                    progress["passing"].append(ticker)
                    print(f"  PASS: {ticker} (score={score:.1f})")
                progress["completed"].append(ticker)

            # Mark fetched-but-not-in-results tickers as completed too
            result_tickers = {r["ticker"] for r in results}
            for t in fetched_tickers - result_tickers:
                progress["completed"].append(t)

            save_progress(progress)
            write_liquid_tickers(progress, args.min_score, Path(args.output))
            print(f"  Progress saved: {len(progress['completed'])} completed, {len(progress['passing'])} passing")

    print(f"\nDone: {len(read_liquid_tickers(Path(args.output)))} liquid tickers (score >= {args.min_score}) in {args.output}")
    print(f"Total processed: {len(progress['completed'])} completed, {len(progress['failed'])} failed")


if __name__ == "__main__":
    main()
