#!/usr/bin/env python3
"""
Fetch Earnings Calendar

Fetches upcoming earnings dates and historical EPS surprise data
for a list of tickers using yfinance.

Usage:
    python fetch_earnings_calendar.py --tickers AAPL,NVDA,TSLA
    python fetch_earnings_calendar.py --portfolio monitoring/watchlist/data/portfolio.json
    python fetch_earnings_calendar.py --tickers AAPL --days-ahead 7 --notify
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[4]))

import argparse
import json
import warnings
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd
import yfinance as yf

from lib.python.retry import retry_with_backoff

warnings.filterwarnings("ignore")


def _safe_float(val) -> float | None:
    """Convert to float or return None for NaN/None."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if pd.isna(f) else f
    except (ValueError, TypeError):
        return None


def detect_bmo_amc(dt: pd.Timestamp) -> str:
    """
    Detect BMO/AMC from timezone-aware earnings date timestamp.

    yfinance encodes timing in the hour of the datetime:
    - BMO: ~6:00-9:59 AM ET (pre-market)
    - AMC: ~4:00 PM+ ET (post-market)
    """
    try:
        if dt.tzinfo is not None:
            et = dt.tz_convert("US/Eastern")
        else:
            et = dt
        hour = et.hour
        if 6 <= hour < 10:
            return "BMO"
        elif hour >= 16:
            return "AMC"
        else:
            return "Unknown"
    except Exception:
        return "Unknown"


def fetch_single_ticker(ticker: str) -> dict:
    """Fetch earnings calendar data for a single ticker."""
    stock = yf.Ticker(ticker)
    result = {
        "ticker": ticker,
        "upcoming": None,
        "history": [],
        "error": None,
    }

    # 1. Upcoming earnings via stock.calendar
    try:
        calendar = retry_with_backoff(lambda: stock.calendar)
        if calendar is not None:
            # Handle both dict and DataFrame formats
            if isinstance(calendar, dict) and "Earnings Date" in calendar:
                earnings_dates_raw = calendar["Earnings Date"]
                if isinstance(earnings_dates_raw, list) and len(earnings_dates_raw) > 0:
                    next_date = earnings_dates_raw[0]
                elif isinstance(earnings_dates_raw, pd.Timestamp):
                    next_date = earnings_dates_raw
                else:
                    next_date = None

                if next_date is not None:
                    if isinstance(next_date, pd.Timestamp):
                        next_date_str = next_date.strftime("%Y-%m-%d")
                    else:
                        next_date_str = str(next_date)[:10]

                    try:
                        days_away = (datetime.strptime(next_date_str, "%Y-%m-%d") - datetime.now()).days
                    except ValueError:
                        days_away = None

                    result["upcoming"] = {
                        "date": next_date_str,
                        "days_away": days_away,
                        "timing": None,
                        "eps_estimate_avg": _safe_float(calendar.get("Earnings Average")),
                        "eps_estimate_high": _safe_float(calendar.get("Earnings High")),
                        "eps_estimate_low": _safe_float(calendar.get("Earnings Low")),
                        "revenue_estimate_avg": _safe_float(calendar.get("Revenue Average")),
                    }

            elif hasattr(calendar, "iloc") and "Earnings Date" in calendar:
                ed = calendar["Earnings Date"].iloc[0]
                if isinstance(ed, pd.Timestamp):
                    next_date_str = ed.strftime("%Y-%m-%d")
                else:
                    next_date_str = str(ed)[:10]
                try:
                    days_away = (datetime.strptime(next_date_str, "%Y-%m-%d") - datetime.now()).days
                except ValueError:
                    days_away = None
                result["upcoming"] = {
                    "date": next_date_str,
                    "days_away": days_away,
                    "timing": None,
                    "eps_estimate_avg": None,
                    "eps_estimate_high": None,
                    "eps_estimate_low": None,
                    "revenue_estimate_avg": None,
                }
    except Exception as e:
        result["upcoming"] = {"error": str(e)}

    # 2. Historical earnings + BMO/AMC via stock.get_earnings_dates
    try:
        earnings_dates_df = retry_with_backoff(lambda: stock.get_earnings_dates(limit=8))
        if earnings_dates_df is not None and len(earnings_dates_df) > 0:
            for idx_dt, row in earnings_dates_df.iterrows():
                timing = detect_bmo_amc(idx_dt)
                date_str = idx_dt.strftime("%Y-%m-%d")

                eps_est = _safe_float(row.get("EPS Estimate"))
                eps_act = _safe_float(row.get("Reported EPS"))
                surprise_pct = _safe_float(row.get("Surprise(%)"))

                entry = {
                    "date": date_str,
                    "timing": timing,
                    "eps_estimate": eps_est,
                    "eps_actual": eps_act,
                    "surprise_pct": surprise_pct,
                }

                # Future date: use to fill timing on the upcoming entry
                if idx_dt.date() > datetime.now().date():
                    if (result["upcoming"]
                            and isinstance(result["upcoming"], dict)
                            and result["upcoming"].get("date") == date_str):
                        result["upcoming"]["timing"] = timing
                else:
                    result["history"].append(entry)
    except Exception as e:
        if result["error"] is None:
            result["error"] = str(e)

    return result


def fetch_all(tickers: list[str], workers: int = 4) -> list[dict]:
    """Fetch earnings data for all tickers in parallel."""
    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(fetch_single_ticker, t): t for t in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            try:
                result = future.result()
                status = "OK" if result.get("error") is None else f"WARN: {result['error']}"
                upcoming_str = ""
                if (result.get("upcoming")
                        and isinstance(result["upcoming"], dict)
                        and result["upcoming"].get("date")):
                    days = result["upcoming"].get("days_away", "?")
                    timing = result["upcoming"].get("timing") or ""
                    upcoming_str = f" -> {result['upcoming']['date']} ({days}d) {timing}"
                print(f"  {ticker}: {status}{upcoming_str}")
                results.append(result)
            except Exception as e:
                print(f"  {ticker}: FAILED - {e}")
                results.append({"ticker": ticker, "error": str(e), "upcoming": None, "history": []})
    results.sort(key=lambda r: r["ticker"])
    return results


def generate_alerts(results: list[dict], days_ahead: int) -> list[dict]:
    """Generate alerts for tickers with earnings within the alert window."""
    alerts = []
    for r in results:
        upcoming = r.get("upcoming")
        if not upcoming or not isinstance(upcoming, dict) or not upcoming.get("date"):
            continue
        days = upcoming.get("days_away")
        if days is None or days > days_ahead or days < 0:
            continue

        timing = upcoming.get("timing") or "Unknown"
        ticker = r["ticker"]
        date_str = upcoming["date"]

        if days <= 1:
            priority = "URGENT"
        elif days <= 3:
            priority = "HIGH"
        elif days <= 7:
            priority = "NORMAL"
        else:
            priority = "INFO"

        eps_str = ""
        if upcoming.get("eps_estimate_avg") is not None:
            eps_str = f" | EPS est: ${upcoming['eps_estimate_avg']:.2f}"

        message = f"Earnings in {days}d ({date_str}) [{timing}]{eps_str}"

        alerts.append({
            "ticker": ticker,
            "priority": priority,
            "message": message,
        })

    alerts.sort(key=lambda a: {"URGENT": 0, "HIGH": 1, "NORMAL": 2, "INFO": 3}.get(a["priority"], 4))
    return alerts


def main():
    parser = argparse.ArgumentParser(description="Fetch earnings calendar data")
    parser.add_argument("--tickers", "-t", type=str,
                        help="Comma-separated ticker symbols")
    parser.add_argument("--portfolio", "-p", type=Path,
                        help="Path to watchlist portfolio.json")
    parser.add_argument("--output", "-o", type=Path,
                        default=Path(__file__).parents[2] / "data" / "earnings_calendar.json",
                        help="Output JSON path")
    parser.add_argument("--days-ahead", "-d", type=int, default=14,
                        help="Alert window in days (default: 14)")
    parser.add_argument("--notify", action="store_true",
                        help="Print alerts JSON to stdout for ntfy.sh piping")
    parser.add_argument("--workers", "-w", type=int, default=4,
                        help="Number of parallel fetch workers (default: 4)")
    args = parser.parse_args()

    # Resolve tickers
    tickers = []
    if args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
    if args.portfolio:
        portfolio_path = args.portfolio
        if not portfolio_path.is_absolute():
            portfolio_path = Path(__file__).parents[4] / portfolio_path
        if not portfolio_path.exists():
            print(f"Error: Portfolio file not found: {portfolio_path}", file=sys.stderr)
            sys.exit(1)
        with open(portfolio_path) as f:
            portfolio = json.load(f)
        portfolio_tickers = [p["ticker"] for p in portfolio.get("positions", [])]
        tickers.extend(portfolio_tickers)
    tickers = list(dict.fromkeys(tickers))  # deduplicate, preserve order

    if not tickers:
        print("Error: provide --tickers or --portfolio", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching earnings calendar for {len(tickers)} ticker(s)...")
    results = fetch_all(tickers, workers=args.workers)

    # Generate alerts
    alerts = generate_alerts(results, args.days_ahead)

    # Build output
    output = {
        "fetch_time": datetime.now().isoformat(),
        "days_ahead": args.days_ahead,
        "ticker_count": len(results),
        "tickers": results,
        "alerts": alerts,
    }

    # Write JSON
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nSaved: {args.output}")

    # Print summary
    upcoming_count = sum(
        1 for r in results
        if r.get("upcoming") and isinstance(r["upcoming"], dict) and r["upcoming"].get("date")
    )
    print(f"  Upcoming earnings found: {upcoming_count}/{len(results)}")
    if alerts:
        print(f"  Alerts ({len(alerts)}):")
        for a in alerts:
            print(f"    [{a['priority']}] {a['ticker']}: {a['message']}")

    # --notify: print alerts JSON to stdout for piping to ntfy
    if args.notify and alerts:
        notify_output = {"alerts": alerts}
        print("\n--- ALERTS JSON (for ntfy.sh) ---")
        print(json.dumps(notify_output, indent=2))


if __name__ == "__main__":
    main()
