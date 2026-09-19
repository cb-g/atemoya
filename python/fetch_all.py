"""Fetch every ticker in reference/universe.json to data/financials/<TICKER>.json.

    uv run python/fetch_all.py [--universe FILE] [--out DIR]

This is the fetch half of the batch; fetch.py decides the statements provider per ticker.
Valuation is the other half and never refetches:

    dune exec atemoya -- data/financials --out output
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import fetch
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
    tickers = [e.ticker for e in universe.tickers]
    print(f"{len(tickers)} tickers from {universe_path}")
    return fetch.main([*tickers, "--out", str(out)])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
