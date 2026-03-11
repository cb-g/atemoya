#!/usr/bin/env python3
"""
Fetch the full list of optionable tickers from CBOE's symbol directory.
Updated daily by CBOE using information from the previous business day.
"""

import argparse
import csv
import io
from pathlib import Path

import requests

CBOE_URL = "https://www.cboe.com/us/options/symboldir/equity-index-options/download/"


def fetch_optionable_tickers() -> list[dict]:
    """Download the CBOE optionable tickers CSV and return all rows."""
    resp = requests.get(CBOE_URL, timeout=30)
    resp.raise_for_status()

    reader = csv.DictReader(io.StringIO(resp.text))
    # Normalize header whitespace (CBOE has " Stock Symbol" etc.)
    reader.fieldnames = [f.strip() for f in reader.fieldnames]

    rows = []
    for row in reader:
        rows.append({k.strip(): v.strip().strip('"') for k, v in row.items()})
    return rows


def main():
    parser = argparse.ArgumentParser(description="Fetch optionable tickers from CBOE")
    parser.add_argument(
        "--output",
        default="pricing/liquidity/data/optionable_tickers.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()

    print("Fetching optionable tickers from CBOE...")
    rows = fetch_optionable_tickers()

    if not rows:
        print("Error: no tickers returned")
        raise SystemExit(1)

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    fieldnames = list(rows[0].keys())
    with open(output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved {len(rows)} optionable tickers to {output}")


if __name__ == "__main__":
    main()
