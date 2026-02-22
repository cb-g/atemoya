#!/usr/bin/env python3
"""
Portfolio/Watchlist Management CLI

Add, remove, list, and update positions in your portfolio.

Usage:
    python manage.py list
    python manage.py add AAPL --type watching --note "Waiting for pullback"
    python manage.py add NVDA --type long --shares 100 --cost 125.50
    python manage.py remove AAPL
    python manage.py update AAPL --stop-loss 130 --sell-target 200
    python manage.py show AAPL
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


DEFAULT_PORTFOLIO = Path(__file__).parent.parent / "data" / "portfolio.json"


def load_portfolio(path: Path) -> dict:
    """Load portfolio JSON file."""
    if not path.exists():
        return {"positions": []}
    with open(path) as f:
        return json.load(f)


def save_portfolio(portfolio: dict, path: Path):
    """Save portfolio to JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(portfolio, f, indent=2)
    print(f"Portfolio saved to {path}")


def find_position(portfolio: dict, ticker: str) -> tuple[int, dict | None]:
    """Find a position by ticker. Returns (index, position) or (-1, None)."""
    ticker = ticker.upper()
    for i, pos in enumerate(portfolio.get("positions", [])):
        if pos.get("ticker", "").upper() == ticker:
            return i, pos
    return -1, None


def cmd_list(args):
    """List all positions in portfolio."""
    portfolio = load_portfolio(args.portfolio)
    positions = portfolio.get("positions", [])

    if not positions:
        print("Portfolio is empty. Add positions with: manage.py add TICKER")
        return

    print(f"\n{'Ticker':<8} {'Type':<10} {'Shares':>10} {'Cost':>10} {'Stop':>10} {'Target':>10}")
    print("-" * 68)

    for pos in positions:
        ticker = pos.get("ticker", "???")
        pos_info = pos.get("position", {})
        pos_type = pos_info.get("type", "watching")
        shares = pos_info.get("shares", 0)
        cost = pos_info.get("avg_cost", 0)
        levels = pos.get("levels", {})
        stop = levels.get("stop_loss", "-")
        target = levels.get("sell_target", "-")

        shares_str = f"{shares:,.0f}" if shares else "-"
        cost_str = f"${cost:,.2f}" if cost else "-"
        stop_str = f"${stop:,.2f}" if isinstance(stop, (int, float)) else "-"
        target_str = f"${target:,.2f}" if isinstance(target, (int, float)) else "-"

        print(f"{ticker:<8} {pos_type:<10} {shares_str:>10} {cost_str:>10} {stop_str:>10} {target_str:>10}")

    print(f"\nTotal positions: {len(positions)}")
    longs = sum(1 for p in positions if p.get("position", {}).get("type") == "long")
    shorts = sum(1 for p in positions if p.get("position", {}).get("type") == "short")
    watching = len(positions) - longs - shorts
    print(f"  Long: {longs}  |  Short: {shorts}  |  Watching: {watching}")


def cmd_add(args):
    """Add a new position to portfolio."""
    portfolio = load_portfolio(args.portfolio)
    ticker = args.ticker.upper()

    # Check if already exists
    idx, existing = find_position(portfolio, ticker)
    if existing:
        print(f"Error: {ticker} already exists in portfolio. Use 'update' to modify.")
        sys.exit(1)

    # Build position
    position = {
        "ticker": ticker,
        "name": args.name or ticker,
        "position": {
            "type": args.type,
            "shares": args.shares or 0,
            "avg_cost": args.cost or 0,
        },
        "levels": {},
        "bull": [],
        "bear": [],
        "catalysts": [],
        "notes": args.note or "",
    }

    # Add price levels if provided
    if args.buy_target:
        position["levels"]["buy_target"] = args.buy_target
    if args.sell_target:
        position["levels"]["sell_target"] = args.sell_target
    if args.stop_loss:
        position["levels"]["stop_loss"] = args.stop_loss

    portfolio.setdefault("positions", []).append(position)
    save_portfolio(portfolio, args.portfolio)
    print(f"Added {ticker} ({args.type})")


def cmd_remove(args):
    """Remove a position from portfolio."""
    portfolio = load_portfolio(args.portfolio)
    ticker = args.ticker.upper()

    idx, existing = find_position(portfolio, ticker)
    if not existing:
        print(f"Error: {ticker} not found in portfolio")
        sys.exit(1)

    if not args.yes:
        confirm = input(f"Remove {ticker}? [y/N] ").strip().lower()
        if confirm != "y":
            print("Cancelled")
            return

    portfolio["positions"].pop(idx)
    save_portfolio(portfolio, args.portfolio)
    print(f"Removed {ticker}")


def cmd_update(args):
    """Update an existing position."""
    portfolio = load_portfolio(args.portfolio)
    ticker = args.ticker.upper()

    idx, pos = find_position(portfolio, ticker)
    if not pos:
        print(f"Error: {ticker} not found in portfolio. Use 'add' first.")
        sys.exit(1)

    # Update fields if provided
    if args.type:
        pos["position"]["type"] = args.type
    if args.shares is not None:
        pos["position"]["shares"] = args.shares
    if args.cost is not None:
        pos["position"]["avg_cost"] = args.cost
    if args.name:
        pos["name"] = args.name
    if args.note:
        pos["notes"] = args.note

    # Update levels
    if args.buy_target is not None:
        pos.setdefault("levels", {})["buy_target"] = args.buy_target if args.buy_target > 0 else None
    if args.sell_target is not None:
        pos.setdefault("levels", {})["sell_target"] = args.sell_target if args.sell_target > 0 else None
    if args.stop_loss is not None:
        pos.setdefault("levels", {})["stop_loss"] = args.stop_loss if args.stop_loss > 0 else None

    # Clean up None values in levels
    pos["levels"] = {k: v for k, v in pos.get("levels", {}).items() if v is not None}

    portfolio["positions"][idx] = pos
    save_portfolio(portfolio, args.portfolio)
    print(f"Updated {ticker}")


def cmd_show(args):
    """Show details for a specific position."""
    portfolio = load_portfolio(args.portfolio)
    ticker = args.ticker.upper()

    idx, pos = find_position(portfolio, ticker)
    if not pos:
        print(f"Error: {ticker} not found in portfolio")
        sys.exit(1)

    print(f"\n{pos.get('ticker', '???')} - {pos.get('name', 'Unknown')}")
    print("=" * 50)

    pos_info = pos.get("position", {})
    print(f"Type: {pos_info.get('type', 'watching')}")
    if pos_info.get("shares"):
        print(f"Shares: {pos_info['shares']:,.0f}")
    if pos_info.get("avg_cost"):
        print(f"Cost Basis: ${pos_info['avg_cost']:,.2f}")

    levels = pos.get("levels", {})
    if levels:
        print("\nPrice Levels:")
        if levels.get("buy_target"):
            print(f"  Buy Target:  ${levels['buy_target']:,.2f}")
        if levels.get("sell_target"):
            print(f"  Sell Target: ${levels['sell_target']:,.2f}")
        if levels.get("stop_loss"):
            print(f"  Stop Loss:   ${levels['stop_loss']:,.2f}")

    bull = pos.get("bull", [])
    if bull:
        print("\nBull Thesis:")
        for arg in bull:
            print(f"  [{arg.get('weight', '?')}/10] {arg.get('arg', '')}")

    bear = pos.get("bear", [])
    if bear:
        print("\nBear Thesis:")
        for arg in bear:
            print(f"  [{arg.get('weight', '?')}/10] {arg.get('arg', '')}")

    catalysts = pos.get("catalysts", [])
    if catalysts:
        print("\nCatalysts:")
        for c in catalysts:
            print(f"  - {c}")

    if pos.get("notes"):
        print(f"\nNotes: {pos['notes']}")


def cmd_thesis(args):
    """Add a bull or bear thesis argument to a position."""
    portfolio = load_portfolio(args.portfolio)
    ticker = args.ticker.upper()

    idx, pos = find_position(portfolio, ticker)
    if not pos:
        print(f"Error: {ticker} not found in portfolio")
        sys.exit(1)

    thesis_type = "bull" if args.bull else "bear"
    thesis_arg = {
        "arg": args.argument,
        "weight": args.weight,
    }

    pos.setdefault(thesis_type, []).append(thesis_arg)
    portfolio["positions"][idx] = pos
    save_portfolio(portfolio, args.portfolio)
    print(f"Added {thesis_type} thesis to {ticker}: [{args.weight}/10] {args.argument}")


def cmd_catalyst(args):
    """Add a catalyst to a position."""
    portfolio = load_portfolio(args.portfolio)
    ticker = args.ticker.upper()

    idx, pos = find_position(portfolio, ticker)
    if not pos:
        print(f"Error: {ticker} not found in portfolio")
        sys.exit(1)

    pos.setdefault("catalysts", []).append(args.catalyst)
    portfolio["positions"][idx] = pos
    save_portfolio(portfolio, args.portfolio)
    print(f"Added catalyst to {ticker}: {args.catalyst}")


def main():
    parser = argparse.ArgumentParser(
        description="Manage your portfolio/watchlist",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list
  %(prog)s add AAPL --type watching --note "Wait for pullback"
  %(prog)s add NVDA --type long --shares 100 --cost 125.50 --stop-loss 100
  %(prog)s update AAPL --type long --shares 50 --cost 150
  %(prog)s thesis AAPL --bull "Services growing 20%% YoY" --weight 8
  %(prog)s thesis AAPL --bear "iPhone sales peaked" --weight 7
  %(prog)s catalyst AAPL "Q1 Earnings Jan 30"
  %(prog)s show AAPL
  %(prog)s remove AAPL
        """
    )
    parser.add_argument(
        "--portfolio", "-p",
        type=Path,
        default=DEFAULT_PORTFOLIO,
        help="Portfolio JSON file"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # list
    sub_list = subparsers.add_parser("list", help="List all positions")
    sub_list.set_defaults(func=cmd_list)

    # add
    sub_add = subparsers.add_parser("add", help="Add a new position")
    sub_add.add_argument("ticker", help="Ticker symbol")
    sub_add.add_argument("--type", "-t", choices=["long", "short", "watching"], default="watching")
    sub_add.add_argument("--shares", "-s", type=float, help="Number of shares")
    sub_add.add_argument("--cost", "-c", type=float, help="Average cost basis")
    sub_add.add_argument("--name", "-n", help="Company name")
    sub_add.add_argument("--note", help="Notes")
    sub_add.add_argument("--buy-target", type=float, help="Buy target price")
    sub_add.add_argument("--sell-target", type=float, help="Sell target price")
    sub_add.add_argument("--stop-loss", type=float, help="Stop loss price")
    sub_add.set_defaults(func=cmd_add)

    # remove
    sub_remove = subparsers.add_parser("remove", help="Remove a position")
    sub_remove.add_argument("ticker", help="Ticker symbol")
    sub_remove.add_argument("--yes", "-y", action="store_true", help="Skip confirmation")
    sub_remove.set_defaults(func=cmd_remove)

    # update
    sub_update = subparsers.add_parser("update", help="Update an existing position")
    sub_update.add_argument("ticker", help="Ticker symbol")
    sub_update.add_argument("--type", "-t", choices=["long", "short", "watching"])
    sub_update.add_argument("--shares", "-s", type=float)
    sub_update.add_argument("--cost", "-c", type=float)
    sub_update.add_argument("--name", "-n")
    sub_update.add_argument("--note")
    sub_update.add_argument("--buy-target", type=float, help="Set to 0 to remove")
    sub_update.add_argument("--sell-target", type=float, help="Set to 0 to remove")
    sub_update.add_argument("--stop-loss", type=float, help="Set to 0 to remove")
    sub_update.set_defaults(func=cmd_update)

    # show
    sub_show = subparsers.add_parser("show", help="Show position details")
    sub_show.add_argument("ticker", help="Ticker symbol")
    sub_show.set_defaults(func=cmd_show)

    # thesis
    sub_thesis = subparsers.add_parser("thesis", help="Add a thesis argument")
    sub_thesis.add_argument("ticker", help="Ticker symbol")
    thesis_group = sub_thesis.add_mutually_exclusive_group(required=True)
    thesis_group.add_argument("--bull", "-b", dest="argument", metavar="ARG", help="Bull thesis argument")
    thesis_group.add_argument("--bear", "-B", dest="argument", metavar="ARG", help="Bear thesis argument")
    sub_thesis.add_argument("--weight", "-w", type=int, default=5, choices=range(1, 11), help="Weight 1-10")
    sub_thesis.set_defaults(func=cmd_thesis, bull=True)

    # catalyst
    sub_catalyst = subparsers.add_parser("catalyst", help="Add a catalyst")
    sub_catalyst.add_argument("ticker", help="Ticker symbol")
    sub_catalyst.add_argument("catalyst", help="Catalyst description")
    sub_catalyst.set_defaults(func=cmd_catalyst)

    args = parser.parse_args()

    # Fix thesis bull/bear flag
    if args.command == "thesis":
        args.bull = "--bull" in sys.argv or "-b" in sys.argv

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
