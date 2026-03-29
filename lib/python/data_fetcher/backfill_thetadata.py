"""Backfill historical EOD option chains from ThetaData.

Downloads raw option chain data for each ticker and stores one CSV per
ticker under pricing/thetadata/data/. These raw archives are then replayed
by per-module scripts to produce module-specific history CSVs.

Idempotent: checks existing data and only fetches missing date ranges.
Can be run repeatedly to grow history backwards incrementally.

Usage:
    # Backfill last 2 months for a few tickers
    uv run lib/python/data_fetcher/backfill_thetadata.py --tickers SPY,AAPL --days-back 60

    # Backfill last month for all liquid tickers
    uv run lib/python/data_fetcher/backfill_thetadata.py --ticker-file pricing/liquidity/data/liquid_options.txt --days-back 30

    # Extend existing data further back
    uv run lib/python/data_fetcher/backfill_thetadata.py --tickers SPY --days-back 120

Requires Theta Terminal running (./lib/thetadata/start_terminal.sh).
"""

import argparse
import csv
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from lib.python.data_fetcher.thetadata_provider import (
    BASE_URL,
    RATE_LIMIT,
    REQUEST_TIMEOUT,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_OUTPUT = PROJECT_ROOT / "pricing" / "thetadata" / "data"

HEADER = "symbol,expiration,strike,right,created,last_trade,open,high,low,close,volume,count,bid_size,bid_exchange,bid,bid_condition,ask_size,ask_exchange,ask,ask_condition"


def _rate_limit(request_times: list):
    """Block until we're under the rate limit ceiling."""
    now = time.monotonic()
    if len(request_times) >= RATE_LIMIT:
        oldest = request_times[0]
        elapsed = now - oldest
        if elapsed < 60:
            time.sleep(60 - elapsed + 0.1)
    request_times.append(time.monotonic())
    if len(request_times) > RATE_LIMIT:
        request_times.pop(0)


def _fetch_month(ticker: str, start: str, end: str, request_times: list) -> tuple[str, int]:
    """Fetch one month of EOD chain data. Returns (csv_text_without_header, status)."""
    _rate_limit(request_times)
    params = {
        "symbol": ticker,
        "expiration": "*",
        "strike": "*",
        "right": "both",
        "start_date": start,
        "end_date": end,
        "format": "csv",
    }
    try:
        resp = httpx.get(
            f"{BASE_URL}/v3/option/history/eod",
            params=params,
            timeout=REQUEST_TIMEOUT,
        )
        if resp.status_code != 200:
            return "", -1
        text = resp.text.strip()
        if not text:
            return "", 0
        # Strip header line — we manage our own header
        lines = text.split("\n", 1)
        return lines[1] if len(lines) > 1 else "", 0
    except (httpx.ConnectError, httpx.TimeoutException) as e:
        print(f"    {ticker} {start}-{end}: {e}", file=sys.stderr)
        return "", -1


def _month_chunks(start_date: str, end_date: str) -> list[tuple[str, str]]:
    """Split a date range into monthly chunks."""
    start = datetime.strptime(start_date, "%Y%m%d")
    end = datetime.strptime(end_date, "%Y%m%d")
    chunks = []
    cursor = start
    while cursor <= end:
        # End of this calendar month
        if cursor.month == 12:
            month_end = cursor.replace(year=cursor.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            month_end = cursor.replace(month=cursor.month + 1, day=1) - timedelta(days=1)
        chunk_end = min(month_end, end)
        chunks.append((cursor.strftime("%Y%m%d"), chunk_end.strftime("%Y%m%d")))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def _get_existing_dates(output_file: Path) -> set[str]:
    """Read existing CSV and return set of dates (from 'created' column, date part only)."""
    if not output_file.exists():
        return set()
    dates = set()
    try:
        with open(output_file) as f:
            reader = csv.DictReader(f)
            for row in reader:
                # created is like "2026-03-27T17:24:30.205"
                created = row.get("created", "")
                if "T" in created:
                    dates.add(created.split("T")[0].replace("-", ""))
    except Exception:
        pass
    return dates


def backfill_ticker(
    ticker: str,
    start_date: str,
    end_date: str,
    output_dir: Path,
    request_times: list,
) -> int:
    """Fetch historical EOD chain for one ticker, chunked by month.

    Idempotent: appends only months that contain dates not already in the file.
    Returns number of new rows fetched, or -1 on error.
    """
    output_file = output_dir / f"{ticker}.csv"
    output_dir.mkdir(parents=True, exist_ok=True)

    existing_dates = _get_existing_dates(output_file)
    chunks = _month_chunks(start_date, end_date)

    # Filter out chunks where all trading days are already present
    # (approximate: if any date in the chunk's range exists, we have that month)
    needed_chunks = []
    for cs, ce in chunks:
        # Check if any date in this month range is missing
        cs_dt = datetime.strptime(cs, "%Y%m%d")
        ce_dt = datetime.strptime(ce, "%Y%m%d")
        has_gap = False
        d = cs_dt
        while d <= ce_dt:
            if d.weekday() < 5 and d.strftime("%Y%m%d") not in existing_dates:
                has_gap = True
                break
            d += timedelta(days=1)
        if has_gap:
            needed_chunks.append((cs, ce))

    if not needed_chunks:
        return 0  # Everything already present

    # Determine write mode
    file_exists = output_file.exists() and output_file.stat().st_size > 0
    total_rows = 0

    with open(output_file, "a" if file_exists else "w") as f:
        if not file_exists:
            f.write(HEADER + "\n")

        for chunk_start, chunk_end in needed_chunks:
            text, status = _fetch_month(ticker, chunk_start, chunk_end, request_times)
            if status < 0:
                return -1
            if not text:
                continue
            f.write(text + "\n")
            total_rows += text.count("\n") + 1

    return total_rows


def main():
    parser = argparse.ArgumentParser(description="Backfill ThetaData EOD option chains")
    parser.add_argument("--tickers", type=str, help="Comma-separated ticker list")
    parser.add_argument("--ticker-file", type=str, help="File with one ticker per line")
    parser.add_argument("--days-back", type=int, default=60, help="Days of history to fetch (default: 60)")
    parser.add_argument("--start-date", type=str, help="Explicit start date YYYYMMDD (overrides --days-back)")
    parser.add_argument("--end-date", type=str, help="Explicit end date YYYYMMDD (default: last trading day)")
    parser.add_argument("--output-dir", type=str, default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    # Resolve tickers
    tickers = []
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
    elif args.ticker_file:
        path = Path(args.ticker_file)
        if not path.exists():
            print(f"Error: {path} not found", file=sys.stderr)
            sys.exit(1)
        tickers = [line.strip().upper() for line in path.read_text().splitlines() if line.strip()]
    else:
        print("Error: specify --tickers or --ticker-file", file=sys.stderr)
        sys.exit(1)

    # Resolve dates
    end = datetime.now()
    while end.weekday() >= 5:
        end -= timedelta(days=1)
    end_date = args.end_date or end.strftime("%Y%m%d")

    if args.start_date:
        start_date = args.start_date
    else:
        start = datetime.strptime(end_date, "%Y%m%d") - timedelta(days=args.days_back)
        start_date = start.strftime("%Y%m%d")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Check terminal
    try:
        httpx.get(f"{BASE_URL}/", timeout=5)
    except httpx.ConnectError:
        print("Error: Theta Terminal not running. Start with ./lib/thetadata/start_terminal.sh",
              file=sys.stderr)
        sys.exit(1)

    # Estimate: each ticker needs ~1 request per month in the range
    n_months = max(1, (datetime.strptime(end_date, "%Y%m%d") -
                       datetime.strptime(start_date, "%Y%m%d")).days // 30)
    total_requests = len(tickers) * n_months
    est_minutes = total_requests / RATE_LIMIT

    print(f"Backfill: {len(tickers)} tickers, {start_date} to {end_date} ({n_months} month(s))")
    print(f"Output: {output_dir}")
    print(f"Estimated: ~{total_requests} requests, ~{est_minutes:.0f} min at {RATE_LIMIT} req/min")
    print()

    request_times = []
    total_rows = 0
    success = 0
    skipped = 0
    failed = 0
    t0 = time.time()

    for i, ticker in enumerate(tickers, 1):
        elapsed = time.time() - t0
        rate = i / elapsed if elapsed > 0 else 0
        eta = (len(tickers) - i) / rate if rate > 0 else 0

        rows = backfill_ticker(ticker, start_date, end_date, output_dir, request_times)

        if rows < 0:
            failed += 1
            status = "FAILED"
        elif rows == 0:
            skipped += 1
            status = "up to date"
        else:
            success += 1
            total_rows += rows
            status = f"{rows:,} rows"

        print(f"  [{i}/{len(tickers)}] {ticker}: {status}" +
              (f" (ETA {eta:.0f}s)" if eta > 10 else ""))

    duration = time.time() - t0
    print(f"\nDone in {duration:.0f}s: {success} fetched, {skipped} up to date, "
          f"{failed} failed, {total_rows:,} new rows")


if __name__ == "__main__":
    main()
