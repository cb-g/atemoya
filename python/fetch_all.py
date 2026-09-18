"""Fetch every ticker in reference/universe.json to data/financials/<TICKER>.json.

    uv run python/fetch_all.py [--universe FILE] [--out DIR]

This is the fetch half of the batch. Valuation is the other half and never refetches:

    dune exec atemoya -- data/financials --out output
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fetch
import fetch_sec
import reference

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_UNIVERSE = REPO_ROOT / "reference" / "universe.json"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--universe", type=Path, default=DEFAULT_UNIVERSE)
    parser.add_argument("--out", type=Path, default=fetch.DEFAULT_OUT)
    args = parser.parse_args(argv)
    universe_path: Path = args.universe
    out: Path = args.out
    universe = reference.Universe.from_json_string(universe_path.read_text())
    # Insurers need filed statements; everything else reads the vendor feed.
    filed = [e.ticker for e in universe.tickers if e.entity_class == "Insurer"]
    vendor = [e.ticker for e in universe.tickers if e.entity_class != "Insurer"]
    print(f"{len(vendor) + len(filed)} tickers from {universe_path}: {len(vendor)} via yfinance, {len(filed)} via SEC XBRL")
    status = fetch.main([*vendor, "--out", str(out)]) if vendor else 0
    if filed:
        status = max(status, fetch_sec.main([*filed, "--out", str(out)]))
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
