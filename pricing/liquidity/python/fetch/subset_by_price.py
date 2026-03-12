#!/usr/bin/env python3
"""
Subset liquid tickers by stock price.

Reads liquid_tickers.txt, fetches current prices in bulk via yfinance,
and outputs tickers into price segments.

Modes:
  --max-price 50        Single file: tickers below $50
  --segments            $10 steps up to $200, plus above $200
"""

import argparse
import sys
from pathlib import Path

import yfinance as yf

DATA_DIR = Path(__file__).resolve().parents[4] / "pricing" / "liquidity" / "data"


def load_liquid_tickers(path: Path) -> list[str]:
    """Read tickers from liquid_tickers.txt."""
    if not path.exists():
        print(f"Error: {path} not found", file=sys.stderr)
        sys.exit(1)
    return [t.strip() for t in path.read_text().splitlines() if t.strip()]


def fetch_prices(tickers: list[str]) -> dict[str, float]:
    """Fetch current prices for all tickers in one bulk call."""
    print(f"Fetching prices for {len(tickers)} tickers...")
    df = yf.download(tickers, period="1d", progress=False)
    prices = {}
    if "Close" in df.columns or hasattr(df["Close"], "columns"):
        close = df["Close"]
        if hasattr(close, "columns"):
            for ticker in close.columns:
                val = close[ticker].dropna()
                if not val.empty:
                    prices[ticker] = float(val.iloc[-1])
        else:
            if not close.dropna().empty:
                prices[tickers[0]] = float(close.dropna().iloc[-1])
    return prices


def write_segment(tickers: list[str], path: Path, label: str):
    """Write a segment file and print summary."""
    with open(path, "w") as f:
        for t in tickers:
            f.write(t + "\n")
    print(f"  {label}: {len(tickers)} tickers -> {path.name}")


def main():
    parser = argparse.ArgumentParser(
        description="Subset liquid tickers by stock price"
    )
    parser.add_argument(
        "--max-price", type=float, default=None,
        help="Single threshold: output tickers below this price",
    )
    parser.add_argument(
        "--segments", action="store_true",
        help="Generate all price segments ($10 steps to $200, plus above $200)",
    )
    parser.add_argument(
        "--input", default=str(DATA_DIR / "liquid_tickers.txt"),
        help="Input liquid tickers file",
    )
    parser.add_argument(
        "--prefix", default=None,
        help="Output file prefix (default: derived from input filename)",
    )

    args = parser.parse_args()

    if not args.max_price and not args.segments:
        parser.error("Provide --max-price or --segments")

    tickers = load_liquid_tickers(Path(args.input))
    if not tickers:
        print("No tickers to process")
        return

    # Derive prefix from input filename (liquid_tickers -> liquid_tickers, liquid_options -> liquid_options)
    prefix = args.prefix or Path(args.input).stem

    prices = fetch_prices(tickers)
    print(f"Got prices for {len(prices)}/{len(tickers)} tickers")

    if args.segments:
        boundaries = list(range(10, 201, 10))
        prev = 0
        for ceiling in boundaries:
            segment = sorted(t for t, p in prices.items() if prev < p <= ceiling)
            write_segment(segment, DATA_DIR / f"{prefix}_{prev+1}_to_{ceiling}_USD.txt", f"${prev+1}-${ceiling}")
            prev = ceiling
        above = sorted(t for t, p in prices.items() if p > 200)
        write_segment(above, DATA_DIR / f"{prefix}_above_200_USD.txt", "above $200")
    else:
        below = sorted(t for t, p in prices.items() if p <= args.max_price)
        path = DATA_DIR / f"{prefix}_below_{int(args.max_price)}_USD.txt"
        write_segment(below, path, f"below ${args.max_price:.0f}")


if __name__ == "__main__":
    main()
