"""Watchlist analysis CLI -- pure Python fallback for OCaml watchlist binary."""

import argparse
import sys
from pathlib import Path

from .analysis import run_analysis
from .io import load_market_data, load_portfolio, print_portfolio_summary, save_analysis


def main():
    parser = argparse.ArgumentParser(description="Portfolio Watchlist Tracker")
    parser.add_argument("--portfolio", required=True, type=Path)
    parser.add_argument("--prices", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    try:
        positions = load_portfolio(args.portfolio)
    except Exception as e:
        print(f"Error loading portfolio: {e}", file=sys.stderr)
        sys.exit(1)

    if not positions:
        print("No positions found in portfolio")
        sys.exit(0)

    market_data = {}
    if args.prices:
        try:
            market_data = load_market_data(args.prices)
        except Exception as e:
            print(f"Warning: Could not load market data: {e}", file=sys.stderr)

    result = run_analysis(positions, market_data)

    if not args.quiet:
        print_portfolio_summary(result)
    elif result.all_alerts:
        print("Alerts triggered:")
        for a in result.all_alerts:
            print(f"  [{a.priority.value}] {a.ticker}: {a.message}")
    else:
        print("No alerts triggered")

    if args.output:
        save_analysis(result, args.output)
        print(f"\nAnalysis saved to {args.output}")


if __name__ == "__main__":
    main()
