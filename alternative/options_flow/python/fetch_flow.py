#!/usr/bin/env python3
"""
Fetch options flow data for tickers.

Uses Yahoo Finance to get options chain data including volume, open interest,
and pricing. Identifies unusual activity based on volume/OI ratios and premium.

Note: Yahoo Finance provides delayed/EOD data. For real-time flow,
a paid service like Unusual Whales or Polygon.io would be needed.

Usage:
    python fetch_flow.py AAPL NVDA TSLA
    python fetch_flow.py --file tickers.txt
"""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[3]))

import yfinance as yf
import numpy as np

from lib.python.retry import retry_with_backoff


def fetch_options_chain(ticker: str) -> dict:
    """
    Fetch options chain data for a ticker.

    Returns dict with calls, puts, and unusual activity metrics.
    """
    try:
        stock = yf.Ticker(ticker)
        info = retry_with_backoff(lambda: stock.info)

        # Get current price
        spot_price = info.get("regularMarketPrice", info.get("previousClose", 0)) or 0

        # Get available expiration dates
        expirations = retry_with_backoff(lambda: stock.options)
        if not expirations:
            return {
                "ticker": ticker,
                "fetch_time": datetime.now().isoformat(),
                "error": "No options data available",
            }

        # Fetch options for nearest expirations (focus on near-term)
        all_calls = []
        all_puts = []
        unusual_activity = []

        # Look at first 4 expirations (typically covers ~1 month)
        for exp_date in expirations[:4]:
            try:
                opt_chain = retry_with_backoff(lambda exp=exp_date: stock.option_chain(exp))
                calls = opt_chain.calls
                puts = opt_chain.puts

                # Calculate DTE
                exp_datetime = datetime.strptime(exp_date, "%Y-%m-%d")
                dte = (exp_datetime - datetime.now()).days

                # Process calls
                for _, row in calls.iterrows():
                    call_data = process_option_row(row, "CALL", ticker, exp_date, dte, spot_price)
                    if call_data:
                        all_calls.append(call_data)
                        if call_data.get("unusual_score", 0) >= 50:
                            unusual_activity.append(call_data)

                # Process puts
                for _, row in puts.iterrows():
                    put_data = process_option_row(row, "PUT", ticker, exp_date, dte, spot_price)
                    if put_data:
                        all_puts.append(put_data)
                        if put_data.get("unusual_score", 0) >= 50:
                            unusual_activity.append(put_data)

            except Exception as e:
                continue  # Skip problematic expirations

        # Calculate aggregate metrics
        total_call_volume = sum(c.get("volume", 0) for c in all_calls)
        total_put_volume = sum(p.get("volume", 0) for p in all_puts)
        total_call_oi = sum(c.get("open_interest", 0) for c in all_calls)
        total_put_oi = sum(p.get("open_interest", 0) for p in all_puts)

        # Estimate premium (volume * last price * 100)
        total_call_premium = sum(c.get("volume", 0) * c.get("last_price", 0) * 100 for c in all_calls)
        total_put_premium = sum(p.get("volume", 0) * p.get("last_price", 0) * 100 for p in all_puts)

        # Put/Call ratio
        if total_call_volume > 0:
            put_call_ratio = total_put_volume / total_call_volume
        else:
            put_call_ratio = 0

        # Call/Put premium ratio
        if total_put_premium > 0:
            call_put_premium_ratio = total_call_premium / total_put_premium
        elif total_call_premium > 0:
            call_put_premium_ratio = 999  # Very bullish
        else:
            call_put_premium_ratio = 1

        # Sort unusual activity by score
        unusual_activity = sorted(unusual_activity, key=lambda x: x.get("unusual_score", 0), reverse=True)

        # Determine overall sentiment
        if call_put_premium_ratio > 2:
            sentiment = "bullish"
        elif call_put_premium_ratio > 1.2:
            sentiment = "slightly_bullish"
        elif call_put_premium_ratio < 0.5:
            sentiment = "bearish"
        elif call_put_premium_ratio < 0.8:
            sentiment = "slightly_bearish"
        else:
            sentiment = "neutral"

        result = {
            "ticker": ticker,
            "name": info.get("shortName", ticker),
            "fetch_time": datetime.now().isoformat(),
            "spot_price": spot_price,
            "expirations_analyzed": len(expirations[:4]),

            "volume_summary": {
                "total_call_volume": total_call_volume,
                "total_put_volume": total_put_volume,
                "total_call_oi": total_call_oi,
                "total_put_oi": total_put_oi,
                "put_call_ratio": round(put_call_ratio, 2),
            },

            "premium_summary": {
                "total_call_premium": round(total_call_premium, 2),
                "total_put_premium": round(total_put_premium, 2),
                "call_put_premium_ratio": round(call_put_premium_ratio, 2),
                "total_premium": round(total_call_premium + total_put_premium, 2),
            },

            "sentiment": sentiment,
            "unusual_activity_count": len(unusual_activity),
            "unusual_activity": unusual_activity[:20],  # Top 20

            "error": None,
        }

        return result

    except Exception as e:
        return {
            "ticker": ticker,
            "fetch_time": datetime.now().isoformat(),
            "error": str(e),
        }


def process_option_row(row, option_type: str, ticker: str, exp_date: str, dte: int, spot_price: float) -> Optional[dict]:
    """
    Process a single option row and calculate unusual score.

    Returns dict with option data or None if invalid.
    """
    try:
        strike = float(row.get("strike", 0))
        volume = int(row.get("volume", 0) or 0)
        open_interest = int(row.get("openInterest", 0) or 0)
        last_price = float(row.get("lastPrice", 0) or 0)
        bid = float(row.get("bid", 0) or 0)
        ask = float(row.get("ask", 0) or 0)
        implied_vol = float(row.get("impliedVolatility", 0) or 0)

        # Skip options with no activity
        if volume == 0 and open_interest == 0:
            return None

        # Calculate metrics
        if open_interest > 0:
            vol_oi_ratio = volume / open_interest
        else:
            vol_oi_ratio = volume if volume > 0 else 0

        # Premium estimate
        premium = volume * last_price * 100

        # Moneyness
        if spot_price > 0:
            if option_type == "CALL":
                moneyness = (spot_price - strike) / spot_price
            else:
                moneyness = (strike - spot_price) / spot_price
        else:
            moneyness = 0

        # Estimate delta (rough approximation)
        if option_type == "CALL":
            if moneyness > 0.1:  # Deep ITM
                delta = 0.9
            elif moneyness > 0:  # ITM
                delta = 0.6 + moneyness * 2
            elif moneyness > -0.1:  # ATM
                delta = 0.5 + moneyness * 3
            else:  # OTM
                delta = max(0.1, 0.5 + moneyness * 3)
        else:  # PUT
            if moneyness > 0.1:  # Deep ITM
                delta = -0.9
            elif moneyness > 0:  # ITM
                delta = -0.6 - moneyness * 2
            elif moneyness > -0.1:  # ATM
                delta = -0.5 + moneyness * 3
            else:  # OTM
                delta = min(-0.1, -0.5 + moneyness * 3)

        # Calculate unusual score
        unusual_score = calculate_unusual_score(
            premium=premium,
            vol_oi_ratio=vol_oi_ratio,
            dte=dte,
            delta=delta,
            volume=volume,
        )

        return {
            "ticker": ticker,
            "option_type": option_type,
            "strike": strike,
            "expiry": exp_date,
            "dte": dte,
            "volume": volume,
            "open_interest": open_interest,
            "vol_oi_ratio": round(vol_oi_ratio, 2),
            "last_price": last_price,
            "bid": bid,
            "ask": ask,
            "premium": round(premium, 2),
            "implied_vol": round(implied_vol, 4),
            "delta": round(delta, 2),
            "moneyness": round(moneyness, 4),
            "unusual_score": unusual_score,
        }

    except Exception:
        return None


def calculate_unusual_score(premium: float, vol_oi_ratio: float, dte: int, delta: float, volume: int) -> int:
    """
    Calculate how unusual this options activity is (0-100).

    Factors:
    - Premium size (0-30 points)
    - Volume vs OI (0-25 points)
    - DTE urgency (0-20 points)
    - OTM premium / high conviction (0-15 points)
    - Raw volume (0-10 points)
    """
    score = 0

    # Premium size (0-30 points)
    if premium >= 1_000_000:
        score += 30
    elif premium >= 500_000:
        score += 25
    elif premium >= 250_000:
        score += 20
    elif premium >= 100_000:
        score += 15
    elif premium >= 50_000:
        score += 10
    elif premium >= 25_000:
        score += 5

    # Volume vs OI (0-25 points) - new positions
    if vol_oi_ratio >= 10:
        score += 25
    elif vol_oi_ratio >= 5:
        score += 20
    elif vol_oi_ratio >= 3:
        score += 15
    elif vol_oi_ratio >= 2:
        score += 10
    elif vol_oi_ratio >= 1:
        score += 5

    # DTE urgency (0-20 points)
    if dte <= 3:
        score += 20
    elif dte <= 7:
        score += 15
    elif dte <= 14:
        score += 10
    elif dte <= 30:
        score += 5

    # OTM high conviction (0-15 points)
    abs_delta = abs(delta)
    if abs_delta < 0.2:  # Deep OTM
        score += 15
    elif abs_delta < 0.3:  # OTM
        score += 10
    elif abs_delta < 0.4:
        score += 5

    # Raw volume bonus (0-10 points)
    if volume >= 10000:
        score += 10
    elif volume >= 5000:
        score += 7
    elif volume >= 1000:
        score += 5
    elif volume >= 500:
        score += 2

    return min(score, 100)


def classify_flow_sentiment(option_data: dict) -> str:
    """Classify individual option flow as bullish/bearish."""
    option_type = option_data.get("option_type", "")
    # For now, simple classification (would need trade direction for more accuracy)
    # High volume on calls = bullish, high volume on puts = bearish
    if option_type == "CALL":
        return "bullish"
    else:
        return "bearish"


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Fetch options flow data")
    parser.add_argument("tickers", nargs="*", help="Ticker symbols")
    parser.add_argument("--file", type=Path, help="File with tickers (one per line)")
    parser.add_argument("--output", type=Path,
                        default=Path(__file__).parent.parent / "data" / "options_flow.json")

    args = parser.parse_args()

    # Collect tickers
    tickers = []
    if args.tickers:
        tickers.extend([t.upper() for t in args.tickers])
    if args.file and args.file.exists():
        with open(args.file) as f:
            tickers.extend([line.strip().upper() for line in f if line.strip()])

    if not tickers:
        print("Error: No tickers specified", file=sys.stderr)
        print("Usage: python fetch_flow.py AAPL NVDA TSLA", file=sys.stderr)
        sys.exit(1)

    # Remove duplicates
    tickers = list(dict.fromkeys(tickers))

    print(f"Fetching options flow for {len(tickers)} ticker(s)...\n")

    results = []
    for ticker in tickers:
        print(f"{ticker}:", end=" ", flush=True)

        data = fetch_options_chain(ticker)

        if data.get("error"):
            print(f"ERROR - {data['error']}")
            results.append(data)
            continue

        # Print summary
        vol = data.get("volume_summary", {})
        prem = data.get("premium_summary", {})
        unusual_count = data.get("unusual_activity_count", 0)

        call_prem_m = prem.get("total_call_premium", 0) / 1_000_000
        put_prem_m = prem.get("total_put_premium", 0) / 1_000_000

        print(f"Calls: ${call_prem_m:.1f}M | Puts: ${put_prem_m:.1f}M | "
              f"P/C: {vol.get('put_call_ratio', 0):.2f} | "
              f"Unusual: {unusual_count} | "
              f"Sentiment: {data.get('sentiment', 'N/A')}")

        results.append(data)

    # Save results
    args.output.parent.mkdir(parents=True, exist_ok=True)
    output_data = {
        "fetch_time": datetime.now().isoformat(),
        "ticker_count": len(results),
        "tickers": results,
    }

    with open(args.output, "w") as f:
        json.dump(output_data, f, indent=2)

    print(f"\nResults saved to {args.output}")

    # Print summary table
    print("\n" + "=" * 75)
    print("OPTIONS FLOW SUMMARY")
    print("=" * 75)
    print(f"{'Ticker':<8} {'Call $':>10} {'Put $':>10} {'P/C Ratio':>10} {'Unusual':>8} {'Sentiment':>12}")
    print("-" * 75)

    for r in results:
        if r.get("error"):
            print(f"{r['ticker']:<8} {'ERROR':>10}")
            continue

        vol = r.get("volume_summary", {})
        prem = r.get("premium_summary", {})

        call_str = f"${prem.get('total_call_premium', 0) / 1_000_000:.1f}M"
        put_str = f"${prem.get('total_put_premium', 0) / 1_000_000:.1f}M"

        print(f"{r['ticker']:<8} {call_str:>10} {put_str:>10} "
              f"{vol.get('put_call_ratio', 0):>10.2f} "
              f"{r.get('unusual_activity_count', 0):>8} "
              f"{r.get('sentiment', 'N/A'):>12}")

    # Print top unusual activity
    all_unusual = []
    for r in results:
        if not r.get("error"):
            for u in r.get("unusual_activity", []):
                all_unusual.append(u)

    if all_unusual:
        all_unusual = sorted(all_unusual, key=lambda x: x.get("unusual_score", 0), reverse=True)
        print("\n" + "-" * 75)
        print("TOP UNUSUAL ACTIVITY")
        print("-" * 75)
        print(f"{'Ticker':<6} {'Type':<6} {'Strike':>8} {'Exp':>12} {'Vol':>8} {'Premium':>12} {'Score':>6}")
        print("-" * 75)

        for u in all_unusual[:10]:
            prem_str = f"${u.get('premium', 0):,.0f}"
            print(f"{u['ticker']:<6} {u['option_type']:<6} {u['strike']:>8.0f} "
                  f"{u['expiry']:>12} {u['volume']:>8,} {prem_str:>12} {u['unusual_score']:>6}")


if __name__ == "__main__":
    main()
