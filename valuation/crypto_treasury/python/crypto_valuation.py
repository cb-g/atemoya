#!/usr/bin/env python3
"""
Crypto Treasury Valuation - mNAV Model

Valuates companies that hold Bitcoin as a treasury asset using the
multiple of Net Asset Value (mNAV) methodology.

Key Metrics:
- NAV: BTC Holdings × BTC Price
- mNAV: Market Cap / NAV (premium/discount to holdings)
- BTC/Share: Holdings exposure per share
- Implied BTC Price: What market prices BTC at via the stock
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[3]))

import yfinance as yf

from lib.python.retry import retry_with_backoff


def load_holdings(data_dir: Path) -> dict:
    """Load BTC holdings data from JSON file."""
    holdings_file = data_dir / "holdings.json"
    if not holdings_file.exists():
        raise FileNotFoundError(f"Holdings file not found: {holdings_file}")

    with open(holdings_file) as f:
        data = json.load(f)

    return data["holdings"]


def fetch_btc_price() -> float:
    """Fetch current BTC price from yfinance."""
    btc = yf.Ticker("BTC-USD")
    info = retry_with_backoff(lambda: btc.info)
    price = info.get("regularMarketPrice")
    if not price:
        raise ValueError("Could not fetch BTC price")
    return float(price)


def fetch_eth_price() -> float:
    """Fetch current ETH price from yfinance."""
    eth = yf.Ticker("ETH-USD")
    info = retry_with_backoff(lambda: eth.info)
    price = info.get("regularMarketPrice")
    if not price:
        raise ValueError("Could not fetch ETH price")
    return float(price)


def fetch_company_data(ticker: str) -> dict:
    """Fetch company market data from yfinance."""
    company = yf.Ticker(ticker)
    info = retry_with_backoff(lambda: company.info)

    return {
        "ticker": ticker,
        "name": info.get("shortName", ticker),
        "price": info.get("regularMarketPrice", 0),
        "market_cap": info.get("marketCap", 0),
        "shares_outstanding": info.get("sharesOutstanding", 0),
        "industry": info.get("industry", "Unknown"),
        "total_debt": info.get("totalDebt", 0),
        "total_cash": info.get("totalCash", 0),
    }


def calculate_mnav_metrics(
    company_data: dict,
    btc_holdings: int,
    btc_price: float,
    eth_holdings: int = 0,
    eth_price: float = 0,
    btc_avg_cost: float = 0,
    eth_avg_cost: float = 0,
) -> dict:
    """Calculate mNAV and related metrics for BTC and ETH holdings."""

    market_cap = company_data["market_cap"]
    shares = company_data["shares_outstanding"]
    price = company_data["price"]
    total_debt = company_data.get("total_debt", 0)

    # Core NAV calculations
    btc_value = btc_holdings * btc_price
    eth_value = eth_holdings * eth_price
    nav = btc_value + eth_value  # Combined NAV = BTC value + ETH value
    nav_per_share = nav / shares if shares > 0 else 0

    # mNAV (multiple of NAV)
    mnav = market_cap / nav if nav > 0 else float('inf')

    # Premium/Discount
    premium_pct = (mnav - 1) * 100

    # Per share metrics
    btc_per_share = btc_holdings / shares if shares > 0 else 0
    eth_per_share = eth_holdings / shares if shares > 0 else 0

    # Implied prices (what market values crypto at via stock)
    # For mixed holdings, attribute premium/discount proportionally
    if btc_holdings > 0 and eth_holdings == 0:
        implied_btc_price = market_cap / btc_holdings
        implied_eth_price = 0
    elif eth_holdings > 0 and btc_holdings == 0:
        implied_eth_price = market_cap / eth_holdings
        implied_btc_price = 0
    elif btc_holdings > 0 and eth_holdings > 0:
        # For mixed holdings, use proportional allocation.
        # NOTE: This assumes the mNAV premium/discount applies equally to both
        # assets. In reality the market may value the BTC and ETH portions
        # differently, especially when one dominates the portfolio.
        implied_btc_price = btc_price * mnav
        implied_eth_price = eth_price * mnav
    else:
        implied_btc_price = 0
        implied_eth_price = 0

    # Cost basis metrics - BTC
    if btc_avg_cost > 0 and btc_holdings > 0:
        btc_unrealized_gain = (btc_price - btc_avg_cost) * btc_holdings
        btc_unrealized_gain_pct = (btc_price / btc_avg_cost - 1) * 100
    else:
        btc_unrealized_gain = 0
        btc_unrealized_gain_pct = 0

    # Cost basis metrics - ETH
    if eth_avg_cost > 0 and eth_holdings > 0:
        eth_unrealized_gain = (eth_price - eth_avg_cost) * eth_holdings
        eth_unrealized_gain_pct = (eth_price / eth_avg_cost - 1) * 100
    else:
        eth_unrealized_gain = 0
        eth_unrealized_gain_pct = 0

    # Combined unrealized gain
    total_unrealized_gain = btc_unrealized_gain + eth_unrealized_gain

    # Leverage metrics
    debt_to_nav = total_debt / nav if nav > 0 else 0

    # Determine holding type
    if btc_holdings > 0 and eth_holdings == 0:
        holding_type = "BTC"
    elif eth_holdings > 0 and btc_holdings == 0:
        holding_type = "ETH"
    else:
        holding_type = "Mixed"

    # Investment signal
    if mnav < 0.8:
        signal = "Strong Buy"
        signal_color = "green"
    elif mnav < 1.0:
        signal = "Buy"
        signal_color = "green"
    elif mnav < 1.2:
        signal = "Hold"
        signal_color = "yellow"
    elif mnav < 1.5:
        signal = "Caution"
        signal_color = "yellow"
    else:
        signal = "Overvalued"
        signal_color = "red"

    return {
        "ticker": company_data["ticker"],
        "name": company_data["name"],
        "price": price,
        "market_cap": market_cap,
        "shares_outstanding": shares,
        "holding_type": holding_type,
        # BTC metrics
        "btc_holdings": btc_holdings,
        "btc_price": btc_price,
        "btc_value": btc_value,
        "btc_per_share": btc_per_share,
        "implied_btc_price": implied_btc_price,
        "btc_avg_cost": btc_avg_cost,
        "btc_unrealized_gain": btc_unrealized_gain,
        "btc_unrealized_gain_pct": btc_unrealized_gain_pct,
        # ETH metrics
        "eth_holdings": eth_holdings,
        "eth_price": eth_price,
        "eth_value": eth_value,
        "eth_per_share": eth_per_share,
        "implied_eth_price": implied_eth_price,
        "eth_avg_cost": eth_avg_cost,
        "eth_unrealized_gain": eth_unrealized_gain,
        "eth_unrealized_gain_pct": eth_unrealized_gain_pct,
        # Combined metrics
        "nav": nav,
        "nav_per_share": nav_per_share,
        "mnav": mnav,
        "premium_pct": premium_pct,
        "total_unrealized_gain": total_unrealized_gain,
        "debt_to_nav": debt_to_nav,
        "signal": signal,
        "signal_color": signal_color,
    }


def format_currency(value: float, decimals: int = 2) -> str:
    """Format value as currency."""
    if abs(value) >= 1e12:
        return f"${value/1e12:.{decimals}f}T"
    elif abs(value) >= 1e9:
        return f"${value/1e9:.{decimals}f}B"
    elif abs(value) >= 1e6:
        return f"${value/1e6:.{decimals}f}M"
    else:
        return f"${value:,.{decimals}f}"


def format_output(metrics: dict) -> str:
    """Format valuation results for display."""

    # Color codes
    colors = {
        "green": "\033[0;32m",
        "yellow": "\033[0;33m",
        "red": "\033[1;31m",
        "reset": "\033[0m",
    }

    signal_color = colors.get(metrics["signal_color"], "")
    reset = colors["reset"]

    holding_type = metrics.get("holding_type", "BTC")

    output = f"""
========================================
Crypto Treasury Valuation: {metrics['ticker']}
========================================

Company: {metrics['name']}
Industry: Crypto Treasury ({holding_type})

Market Data:
  Stock Price: ${metrics['price']:,.2f}
  Market Cap: {format_currency(metrics['market_cap'])}
  Shares Outstanding: {metrics['shares_outstanding']:,.0f}
"""

    # BTC Holdings section
    if metrics['btc_holdings'] > 0:
        output += f"""
Bitcoin Holdings:
  BTC Holdings: {metrics['btc_holdings']:,} BTC
  BTC Price: ${metrics['btc_price']:,.2f}
  BTC Value: {format_currency(metrics['btc_value'])}
  BTC/Share: {metrics['btc_per_share']:.6f} BTC
"""
        if metrics.get('btc_avg_cost', 0) > 0:
            output += f"  Avg Cost: ${metrics['btc_avg_cost']:,.2f}/BTC\n"
            output += f"  Unrealized Gain: {format_currency(metrics['btc_unrealized_gain'])} ({metrics['btc_unrealized_gain_pct']:+.1f}%)\n"

    # ETH Holdings section
    if metrics.get('eth_holdings', 0) > 0:
        output += f"""
Ethereum Holdings:
  ETH Holdings: {metrics['eth_holdings']:,} ETH
  ETH Price: ${metrics['eth_price']:,.2f}
  ETH Value: {format_currency(metrics['eth_value'])}
  ETH/Share: {metrics['eth_per_share']:.6f} ETH
"""
        if metrics.get('eth_avg_cost', 0) > 0:
            output += f"  Avg Cost: ${metrics['eth_avg_cost']:,.2f}/ETH\n"
            output += f"  Unrealized Gain: {format_currency(metrics['eth_unrealized_gain'])} ({metrics['eth_unrealized_gain_pct']:+.1f}%)\n"

    # NAV Metrics
    output += f"""
NAV Metrics:
  Total NAV: {format_currency(metrics['nav'])}
  NAV per Share: ${metrics['nav_per_share']:,.2f}
  mNAV: {metrics['mnav']:.3f}x
  Premium/Discount: {metrics['premium_pct']:+.1f}%
"""

    # Implied prices
    if metrics['btc_holdings'] > 0:
        output += f"  Implied BTC Price: ${metrics['implied_btc_price']:,.2f}\n"
    if metrics.get('eth_holdings', 0) > 0:
        output += f"  Implied ETH Price: ${metrics['implied_eth_price']:,.2f}\n"

    if metrics['debt_to_nav'] > 0:
        output += f"""
Leverage:
  Debt/NAV: {metrics['debt_to_nav']:.2f}x
"""

    output += f"""
Investment Signal: {signal_color}{metrics['signal']}{reset}
"""

    # Add interpretation
    if metrics['mnav'] < 1.0:
        output += f"  Trading at {abs(metrics['premium_pct']):.1f}% discount to crypto holdings.\n"
        if holding_type == "BTC":
            output += f"  Buying stock = buying BTC at ${metrics['implied_btc_price']:,.0f} (vs ${metrics['btc_price']:,.0f} spot).\n"
        elif holding_type == "ETH":
            output += f"  Buying stock = buying ETH at ${metrics['implied_eth_price']:,.0f} (vs ${metrics['eth_price']:,.0f} spot).\n"
        else:
            output += f"  Buying stock = buying crypto at {metrics['mnav']:.2f}x NAV.\n"
    else:
        output += f"  Trading at {metrics['premium_pct']:.1f}% premium to crypto holdings.\n"
        output += f"  Market pricing in future accumulation or management premium.\n"

    return output


def valuate_single(ticker: str, holdings_data: dict, btc_price: float, eth_price: float) -> dict:
    """Valuate a single crypto treasury company."""

    if ticker not in holdings_data:
        raise ValueError(f"No holdings data for {ticker}. Add to holdings.json first.")

    holding = holdings_data[ticker]
    company_data = fetch_company_data(ticker)

    metrics = calculate_mnav_metrics(
        company_data=company_data,
        btc_holdings=holding.get("btc_holdings", 0),
        btc_price=btc_price,
        eth_holdings=holding.get("eth_holdings", 0),
        eth_price=eth_price,
        btc_avg_cost=holding.get("btc_avg_cost", 0),
        eth_avg_cost=holding.get("eth_avg_cost", 0),
    )

    return metrics


def valuate_all(holdings_data: dict, btc_price: float, eth_price: float) -> list:
    """Valuate all companies in holdings database."""
    results = []
    skipped_etfs = []

    for ticker in holdings_data:
        try:
            metrics = valuate_single(ticker, holdings_data, btc_price, eth_price)
            # ETFs/trusts often return 0 market cap from yfinance
            if metrics["market_cap"] == 0:
                skipped_etfs.append(ticker)
                continue
            results.append(metrics)
        except Exception as e:
            print(f"Warning: Could not valuate {ticker}: {e}", file=sys.stderr)

    if skipped_etfs:
        print(f"Note: Skipped ETFs/trusts (no market cap data): {', '.join(skipped_etfs)}", file=sys.stderr)

    # Sort by mNAV (lowest first = most undervalued)
    results.sort(key=lambda x: x["mnav"])

    return results


def print_summary_table(results: list):
    """Print summary comparison table."""

    print("\n" + "=" * 120)
    print("Crypto Treasury Valuation Summary")
    print("=" * 120)
    print(f"{'Ticker':<8} {'Type':<6} {'Price':>10} {'BTC':>10} {'ETH':>10} {'NAV':>12} {'mNAV':>8} {'Premium':>10} {'Signal':<12}")
    print("-" * 120)

    for m in results:
        signal_color = {"green": "\033[0;32m", "yellow": "\033[0;33m", "red": "\033[1;31m"}.get(m["signal_color"], "")
        reset = "\033[0m"

        btc_str = f"{m['btc_holdings']:,}" if m['btc_holdings'] > 0 else "-"
        eth_str = f"{m.get('eth_holdings', 0):,}" if m.get('eth_holdings', 0) > 0 else "-"

        print(f"{m['ticker']:<8} "
              f"{m.get('holding_type', 'BTC'):<6} "
              f"${m['price']:>8,.2f} "
              f"{btc_str:>10} "
              f"{eth_str:>10} "
              f"{format_currency(m['nav']):>12} "
              f"{m['mnav']:>7.3f}x "
              f"{m['premium_pct']:>+9.1f}% "
              f"{signal_color}{m['signal']:<12}{reset}")

    print("=" * 120)


def main():
    parser = argparse.ArgumentParser(
        description="Crypto Treasury Valuation - mNAV Model"
    )
    parser.add_argument(
        "--ticker",
        help="Single ticker to valuate (default: all)",
    )
    parser.add_argument(
        "--data-dir",
        default=str(Path(__file__).parent.parent / "data"),
        help="Directory containing holdings.json",
    )
    parser.add_argument(
        "--output-dir",
        default=str(Path(__file__).parent.parent / "output"),
        help="Output directory for results",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON",
    )

    args = parser.parse_args()
    data_dir = Path(args.data_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        # Load holdings data
        holdings_data = load_holdings(data_dir)

        # Fetch crypto prices
        print("Fetching crypto prices...")
        btc_price = fetch_btc_price()
        eth_price = fetch_eth_price()
        print(f"BTC Price: ${btc_price:,.2f}")
        print(f"ETH Price: ${eth_price:,.2f}\n")

        if args.ticker:
            # Single ticker valuation
            ticker = args.ticker.upper()
            metrics = valuate_single(ticker, holdings_data, btc_price, eth_price)

            if args.json:
                print(json.dumps(metrics, indent=2))
            else:
                print(format_output(metrics))

                # Save to file
                output_file = output_dir / f"crypto_{ticker}.json"
                with open(output_file, "w") as f:
                    json.dump(metrics, f, indent=2)
                print(f"\nResults saved to: {output_file}")

        else:
            # All tickers
            results = valuate_all(holdings_data, btc_price, eth_price)

            if args.json:
                print(json.dumps(results, indent=2))
            else:
                # Print individual reports
                for metrics in results:
                    print(format_output(metrics))

                # Print summary table
                print_summary_table(results)

                # Save results
                output_file = output_dir / "crypto_treasury_all.json"
                with open(output_file, "w") as f:
                    json.dump({
                        "btc_price": btc_price,
                        "eth_price": eth_price,
                        "timestamp": datetime.now().isoformat(),
                        "results": results,
                    }, f, indent=2)
                print(f"\nResults saved to: {output_file}")

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
