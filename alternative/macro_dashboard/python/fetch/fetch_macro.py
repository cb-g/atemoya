#!/usr/bin/env python3
"""Fetch macroeconomic data from FRED and market sources.

This product uses the FRED® API but is not endorsed or certified by the
Federal Reserve Bank of St. Louis.
FRED® API Terms of Use: https://fred.stlouisfed.org/docs/api/terms_of_use.html

Data sources: Federal Reserve Board, BLS, BEA, U.S. Census Bureau, via FRED.
No FRED data is stored, cached, or redistributed — users fetch directly with
their own API key. This module uses a rule-based classifier; no machine
learning or AI training is performed on FRED data.

Gathers key indicators across categories:
- Interest Rates & Yield Curve
- Inflation
- Employment
- Growth
- Market Risk
- Consumer/Business Sentiment
- Housing
- Leading Indicators

Usage:
    uv run python fetch_macro.py [--output data/macro_data.json]
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import pandas as pd
import yfinance as yf

from lib.python.retry import retry_with_backoff

# Try to import fredapi, provide instructions if missing
try:
    from fredapi import Fred
    FRED_AVAILABLE = True
except ImportError:
    FRED_AVAILABLE = False
    print("Warning: fredapi not installed. Run: uv pip install fredapi")


# FRED series definitions with metadata
FRED_SERIES = {
    # Interest Rates
    "DFF": {"name": "Fed Funds Rate", "category": "interest_rates", "unit": "%", "frequency": "daily"},
    "DGS10": {"name": "10Y Treasury", "category": "interest_rates", "unit": "%", "frequency": "daily"},
    "DGS2": {"name": "2Y Treasury", "category": "interest_rates", "unit": "%", "frequency": "daily"},
    "DGS3MO": {"name": "3M Treasury", "category": "interest_rates", "unit": "%", "frequency": "daily"},
    "T10Y2Y": {"name": "10Y-2Y Spread", "category": "yield_curve", "unit": "%", "frequency": "daily"},
    "T10Y3M": {"name": "10Y-3M Spread", "category": "yield_curve", "unit": "%", "frequency": "daily"},

    # Inflation
    "CPIAUCSL": {"name": "CPI (All Urban)", "category": "inflation", "unit": "index", "frequency": "monthly", "yoy": True},
    "CPILFESL": {"name": "Core CPI (ex Food/Energy)", "category": "inflation", "unit": "index", "frequency": "monthly", "yoy": True},
    "PCEPI": {"name": "PCE Price Index", "category": "inflation", "unit": "index", "frequency": "monthly", "yoy": True},
    "PCEPILFE": {"name": "Core PCE", "category": "inflation", "unit": "index", "frequency": "monthly", "yoy": True},
    "PPIFIS": {"name": "PPI (Final Demand)", "category": "inflation", "unit": "index", "frequency": "monthly", "yoy": True},

    # Employment
    "UNRATE": {"name": "Unemployment Rate", "category": "employment", "unit": "%", "frequency": "monthly"},
    "PAYEMS": {"name": "Nonfarm Payrolls", "category": "employment", "unit": "thousands", "frequency": "monthly", "mom_change": True},
    "ICSA": {"name": "Initial Jobless Claims", "category": "employment", "unit": "thousands", "frequency": "weekly"},
    "CCSA": {"name": "Continued Claims", "category": "employment", "unit": "thousands", "frequency": "weekly"},
    "JTSJOL": {"name": "Job Openings (JOLTS)", "category": "employment", "unit": "thousands", "frequency": "monthly"},

    # Growth
    "GDP": {"name": "Nominal GDP", "category": "growth", "unit": "billions", "frequency": "quarterly"},
    "GDPC1": {"name": "Real GDP", "category": "growth", "unit": "billions", "frequency": "quarterly", "yoy": True},
    "A191RL1Q225SBEA": {"name": "Real GDP Growth (QoQ Ann.)", "category": "growth", "unit": "%", "frequency": "quarterly"},
    "INDPRO": {"name": "Industrial Production", "category": "growth", "unit": "index", "frequency": "monthly", "yoy": True},

    # Consumer
    "RSAFS": {"name": "Retail Sales", "category": "consumer", "unit": "millions", "frequency": "monthly", "yoy": True},
    "PCE": {"name": "Personal Consumption", "category": "consumer", "unit": "billions", "frequency": "monthly", "yoy": True},

    # Business/Manufacturing
    "MANEMP": {"name": "Manufacturing Employment", "category": "manufacturing", "unit": "thousands", "frequency": "monthly"},
    "DGORDER": {"name": "Durable Goods Orders", "category": "manufacturing", "unit": "millions", "frequency": "monthly", "yoy": True},
    "NEWORDER": {"name": "Manufacturers New Orders", "category": "manufacturing", "unit": "millions", "frequency": "monthly"},

    # Housing
    "HOUST": {"name": "Housing Starts", "category": "housing", "unit": "thousands", "frequency": "monthly"},
    "PERMIT": {"name": "Building Permits", "category": "housing", "unit": "thousands", "frequency": "monthly"},
    "EXHOSLUSM495S": {"name": "Existing Home Sales", "category": "housing", "unit": "millions", "frequency": "monthly"},
    "MORTGAGE30US": {"name": "30Y Mortgage Rate", "category": "housing", "unit": "%", "frequency": "weekly"},

    # Credit/Risk
    "TEDRATE": {"name": "TED Spread", "category": "credit", "unit": "%", "frequency": "daily"},

    # Money Supply
    "M2SL": {"name": "M2 Money Supply", "category": "money", "unit": "billions", "frequency": "monthly", "yoy": True},
    "WALCL": {"name": "Fed Balance Sheet", "category": "money", "unit": "millions", "frequency": "weekly"},

    # Leading Indicators
    "USSLIND": {"name": "Leading Index", "category": "leading", "unit": "index", "frequency": "monthly"},
    "USREC": {"name": "Recession Indicator", "category": "leading", "unit": "binary", "frequency": "monthly"},
}

# Market tickers from yfinance
MARKET_TICKERS = {
    "^VIX": {"name": "VIX", "category": "volatility"},
    "^MOVE": {"name": "MOVE Index", "category": "volatility"},
    "DX-Y.NYB": {"name": "Dollar Index (DXY)", "category": "currency"},
    "GC=F": {"name": "Gold", "category": "commodities"},
    "CL=F": {"name": "Crude Oil (WTI)", "category": "commodities"},
    "HG=F": {"name": "Copper", "category": "commodities"},
    "^GSPC": {"name": "S&P 500", "category": "equity"},
    "^IXIC": {"name": "Nasdaq", "category": "equity"},
    "^TNX": {"name": "10Y Yield (Market)", "category": "rates"},
    "TLT": {"name": "20+ Treasury ETF", "category": "bonds"},
    "LQD": {"name": "IG Corporate ETF", "category": "bonds"},
    "HYG": {"name": "HY Corporate ETF", "category": "bonds"},
}


def get_fred_api_key() -> str | None:
    """Get FRED API key from environment or .env file."""
    import os

    # Check environment variable
    key = os.environ.get("FRED_API_KEY")
    if key:
        return key

    # Check .env file
    env_file = Path(__file__).parents[4] / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if line.startswith("FRED_API_KEY="):
                    return line.strip().split("=", 1)[1].strip('"\'')

    return None


def fetch_fred_series(fred: "Fred", series_id: str, lookback_years: int = 5) -> dict | None:
    """Fetch a single FRED series."""
    try:
        meta = FRED_SERIES[series_id]
        end_date = datetime.now()
        start_date = end_date - timedelta(days=lookback_years * 365)

        data = fred.get_series(series_id, start_date, end_date)

        if data is None or len(data) == 0:
            return None

        # Get latest value
        latest_date = data.index[-1]
        latest_value = float(data.iloc[-1])

        result = {
            "series_id": series_id,
            "name": meta["name"],
            "category": meta["category"],
            "unit": meta["unit"],
            "frequency": meta["frequency"],
            "latest_date": latest_date.strftime("%Y-%m-%d"),
            "latest_value": latest_value,
        }

        # Compute YoY change if applicable
        if meta.get("yoy") and len(data) > 12:
            # Find value ~12 months ago
            target_date = latest_date - timedelta(days=365)
            past_data = data[data.index <= target_date]
            if len(past_data) > 0:
                past_value = float(past_data.iloc[-1])
                if past_value != 0:
                    yoy_change = (latest_value / past_value - 1) * 100
                    result["yoy_change"] = round(yoy_change, 2)

        # Compute MoM change if applicable (for payrolls)
        if meta.get("mom_change") and len(data) > 1:
            mom_change = latest_value - float(data.iloc[-2])
            result["mom_change"] = round(mom_change, 1)

        # Historical percentile (where current value sits vs history)
        if len(data) > 20:
            percentile = (data < latest_value).sum() / len(data) * 100
            result["percentile_5y"] = round(percentile, 1)

        # Recent trend (3-month average vs 12-month average)
        if len(data) > 60:
            recent_avg = data.iloc[-20:].mean()
            longer_avg = data.iloc[-60:].mean()
            if longer_avg != 0:
                trend = (recent_avg / longer_avg - 1) * 100
                result["trend_3m_vs_12m"] = round(trend, 2)

        return result

    except Exception as e:
        print(f"  Warning: Failed to fetch {series_id}: {e}")
        return None


def fetch_market_data(ticker: str, lookback_days: int = 252) -> dict | None:
    """Fetch market data from yfinance."""
    try:
        meta = MARKET_TICKERS[ticker]

        # Use Ticker object for more reliable fetching
        t = yf.Ticker(ticker)
        data = retry_with_backoff(lambda: t.history(period="1y"))

        if data is None or len(data) == 0:
            return None

        latest = data.iloc[-1]
        latest_date = data.index[-1]

        # Extract scalar values properly
        close_price = float(latest["Close"].item() if hasattr(latest["Close"], "item") else latest["Close"])

        result = {
            "ticker": ticker,
            "name": meta["name"],
            "category": meta["category"],
            "latest_date": latest_date.strftime("%Y-%m-%d"),
            "latest_price": round(close_price, 2),
        }

        # Daily change
        if len(data) > 1:
            prev_close = float(data.iloc[-2]["Close"].item() if hasattr(data.iloc[-2]["Close"], "item") else data.iloc[-2]["Close"])
            daily_change = (close_price / prev_close - 1) * 100
            result["daily_change_pct"] = round(daily_change, 2)

        # 1-month change
        if len(data) > 21:
            month_ago = float(data.iloc[-22]["Close"].item() if hasattr(data.iloc[-22]["Close"], "item") else data.iloc[-22]["Close"])
            monthly_change = (close_price / month_ago - 1) * 100
            result["monthly_change_pct"] = round(monthly_change, 2)

        # YTD change
        ytd_start = data[data.index >= f"{datetime.now().year}-01-01"]
        if len(ytd_start) > 0:
            first_val = ytd_start.iloc[0]["Close"]
            first_price = float(first_val.item() if hasattr(first_val, "item") else first_val)
            ytd_change = (close_price / first_price - 1) * 100
            result["ytd_change_pct"] = round(ytd_change, 2)

        # 52-week high/low
        high_val = data["High"].max()
        low_val = data["Low"].min()
        high_52w = float(high_val.item() if hasattr(high_val, "item") else high_val)
        low_52w = float(low_val.item() if hasattr(low_val, "item") else low_val)
        result["high_52w"] = round(high_52w, 2)
        result["low_52w"] = round(low_52w, 2)
        result["pct_from_high"] = round((close_price / high_52w - 1) * 100, 1)
        result["pct_from_low"] = round((close_price / low_52w - 1) * 100, 1)

        return result

    except Exception as e:
        print(f"  Warning: Failed to fetch {ticker}: {e}")
        return None


def classify_environment(data: dict) -> dict:
    """Classify the macro environment based on indicators."""
    classifications = {}

    fred_data = {d["series_id"]: d for d in data.get("fred", []) if d}
    market_data = {d["ticker"]: d for d in data.get("market", []) if d}

    # Yield curve assessment
    spread_10y2y = fred_data.get("T10Y2Y", {}).get("latest_value")
    spread_10y3m = fred_data.get("T10Y3M", {}).get("latest_value")
    if spread_10y2y is not None:
        if spread_10y2y < -0.5:
            classifications["yield_curve"] = {"status": "Deeply Inverted", "signal": "Recession Warning", "value": spread_10y2y}
        elif spread_10y2y < 0:
            classifications["yield_curve"] = {"status": "Inverted", "signal": "Caution", "value": spread_10y2y}
        elif spread_10y2y < 0.5:
            classifications["yield_curve"] = {"status": "Flat", "signal": "Neutral", "value": spread_10y2y}
        else:
            classifications["yield_curve"] = {"status": "Normal", "signal": "Expansionary", "value": spread_10y2y}

    # Inflation assessment
    core_pce_yoy = fred_data.get("PCEPILFE", {}).get("yoy_change")
    core_cpi_yoy = fred_data.get("CPILFESL", {}).get("yoy_change")
    inflation_rate = core_pce_yoy or core_cpi_yoy
    if inflation_rate is not None:
        if inflation_rate > 4:
            classifications["inflation"] = {"status": "High", "signal": "Hawkish Fed", "value": inflation_rate}
        elif inflation_rate > 2.5:
            classifications["inflation"] = {"status": "Elevated", "signal": "Watch Fed", "value": inflation_rate}
        elif inflation_rate > 1.5:
            classifications["inflation"] = {"status": "Target", "signal": "Neutral", "value": inflation_rate}
        else:
            classifications["inflation"] = {"status": "Low", "signal": "Dovish Fed", "value": inflation_rate}

    # Labor market assessment
    unemployment = fred_data.get("UNRATE", {}).get("latest_value")
    claims = fred_data.get("ICSA", {}).get("latest_value")
    if unemployment is not None:
        if unemployment > 6:
            classifications["labor"] = {"status": "Weak", "signal": "Recession", "unemployment": unemployment}
        elif unemployment > 4.5:
            classifications["labor"] = {"status": "Softening", "signal": "Slowdown", "unemployment": unemployment}
        elif unemployment > 3.5:
            classifications["labor"] = {"status": "Healthy", "signal": "Neutral", "unemployment": unemployment}
        else:
            classifications["labor"] = {"status": "Tight", "signal": "Inflationary", "unemployment": unemployment}

    # Volatility/Risk assessment
    vix = market_data.get("^VIX", {}).get("latest_price")

    if vix is not None:
        if vix > 30:
            classifications["volatility"] = {"status": "High Fear", "signal": "Risk-Off", "vix": vix}
        elif vix > 20:
            classifications["volatility"] = {"status": "Elevated", "signal": "Caution", "vix": vix}
        elif vix > 15:
            classifications["volatility"] = {"status": "Normal", "signal": "Neutral", "vix": vix}
        else:
            classifications["volatility"] = {"status": "Complacent", "signal": "Risk-On", "vix": vix}

    # Growth assessment
    gdp_growth = fred_data.get("A191RL1Q225SBEA", {}).get("latest_value")
    if gdp_growth is not None:
        if gdp_growth < 0:
            classifications["growth"] = {"status": "Contracting", "signal": "Recession Risk", "gdp_growth": gdp_growth}
        elif gdp_growth < 1:
            classifications["growth"] = {"status": "Stagnant", "signal": "Slowdown", "gdp_growth": gdp_growth}
        elif gdp_growth < 2.5:
            classifications["growth"] = {"status": "Moderate", "signal": "Neutral", "gdp_growth": gdp_growth}
        else:
            classifications["growth"] = {"status": "Strong", "signal": "Expansion", "gdp_growth": gdp_growth}

    # Overall regime
    signals = [c.get("signal", "") for c in classifications.values()]
    recession_signals = sum(1 for s in signals if "Recession" in s or s == "Risk-Off")
    expansion_signals = sum(1 for s in signals if "Expansion" in s or s == "Risk-On")

    if recession_signals >= 3:
        overall = "RECESSION RISK"
    elif recession_signals >= 2:
        overall = "LATE CYCLE / CAUTION"
    elif expansion_signals >= 3:
        overall = "EXPANSION"
    elif expansion_signals >= 2:
        overall = "EARLY/MID CYCLE"
    else:
        overall = "MIXED / TRANSITION"

    classifications["overall_regime"] = overall

    return classifications


def fetch_all_data(fred_api_key: str | None = None) -> dict:
    """Fetch all macro data."""
    result = {
        "timestamp": datetime.now().isoformat(),
        "fred": [],
        "market": [],
    }

    # Fetch FRED data
    if FRED_AVAILABLE and fred_api_key:
        print("Fetching FRED data...")
        fred = Fred(api_key=fred_api_key)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(fetch_fred_series, fred, series_id): series_id
                for series_id in FRED_SERIES
            }

            for future in as_completed(futures):
                series_id = futures[future]
                try:
                    data = future.result()
                    if data:
                        result["fred"].append(data)
                        print(f"  {series_id}: {data['latest_value']:.2f}")
                except Exception as e:
                    print(f"  {series_id}: Error - {e}")
    else:
        if not FRED_AVAILABLE:
            print("Skipping FRED data (fredapi not installed)")
        else:
            print("Skipping FRED data (no API key)")

    # Fetch market data
    print("\nFetching market data...")
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(fetch_market_data, ticker): ticker
            for ticker in MARKET_TICKERS
        }

        for future in as_completed(futures):
            ticker = futures[future]
            try:
                data = future.result()
                if data:
                    result["market"].append(data)
                    print(f"  {ticker}: {data['latest_price']:.2f}")
            except Exception as e:
                print(f"  {ticker}: Error - {e}")

    # Classify environment
    print("\nClassifying macro environment...")
    result["classifications"] = classify_environment(result)

    return result


def print_dashboard(data: dict) -> None:
    """Print a formatted macro dashboard."""
    print("\n" + "=" * 70)
    print("MACRO ECONOMIC DASHBOARD")
    print("=" * 70)
    print(f"As of: {data['timestamp'][:10]}")
    print()

    classifications = data.get("classifications", {})

    # Overall regime
    overall = classifications.get("overall_regime", "Unknown")
    print(f"OVERALL REGIME: {overall}")
    print("-" * 70)

    # Key classifications
    for key, info in classifications.items():
        if key == "overall_regime":
            continue
        if isinstance(info, dict):
            status = info.get("status", "")
            signal = info.get("signal", "")
            # Get the primary value
            value_key = [k for k in info if k not in ["status", "signal"]]
            value_str = ""
            if value_key:
                val = info[value_key[0]]
                value_str = f" ({value_key[0]}: {val:.1f})" if isinstance(val, (int, float)) else ""
            print(f"  {key.upper():15} {status:15} [{signal}]{value_str}")

    print()

    # Group FRED data by category
    fred_by_cat = {}
    for item in data.get("fred", []):
        if item:
            cat = item["category"]
            if cat not in fred_by_cat:
                fred_by_cat[cat] = []
            fred_by_cat[cat].append(item)

    # Print key indicators by category
    print("KEY INDICATORS")
    print("-" * 70)

    priority_cats = ["interest_rates", "yield_curve", "inflation", "employment", "growth", "credit"]
    for cat in priority_cats:
        if cat in fred_by_cat:
            print(f"\n  {cat.upper().replace('_', ' ')}:")
            for item in fred_by_cat[cat]:
                val = item["latest_value"]
                yoy = item.get("yoy_change")
                pct = item.get("percentile_5y")

                line = f"    {item['name']:30} {val:>10.2f}"
                if yoy is not None:
                    line += f"  YoY: {yoy:+.1f}%"
                if pct is not None:
                    line += f"  [P{pct:.0f}]"
                print(line)

    # Market data
    print("\n  MARKET INDICATORS:")
    for item in data.get("market", []):
        if item:
            price = item["latest_price"]
            daily = item.get("daily_change_pct", 0)
            monthly = item.get("monthly_change_pct", 0)
            print(f"    {item['name']:30} {price:>10.2f}  D: {daily:+.1f}%  M: {monthly:+.1f}%")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Fetch macroeconomic data")
    parser.add_argument("--output", "-o", type=str, default="data/macro_data.json",
                        help="Output JSON file")
    parser.add_argument("--api-key", type=str, help="FRED API key (or set FRED_API_KEY env var)")
    parser.add_argument("--quiet", "-q", action="store_true", help="Suppress output")
    args = parser.parse_args()

    # Get API key
    api_key = args.api_key or get_fred_api_key()
    if not api_key:
        print("Note: No FRED API key found. Set FRED_API_KEY env var or use --api-key")
        print("      Get a free key at: https://fred.stlouisfed.org/docs/api/api_key.html")
        print("      Will fetch market data only.\n")

    # Fetch all data
    data = fetch_all_data(api_key)

    # Print dashboard
    if not args.quiet:
        print_dashboard(data)

    # Save to file
    output_path = Path(__file__).parents[2] / args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2, default=str)

    print(f"\nSaved to: {output_path}")


if __name__ == "__main__":
    main()
