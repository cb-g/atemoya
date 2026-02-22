#!/usr/bin/env python3
"""Fetch ETF data for analysis."""

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf
import numpy as np

from lib.python.retry import retry_with_backoff


def _normalize_expense_ratio(info: dict) -> float:
    """Extract expense ratio as a ratio (e.g., 0.0035 for 0.35%).

    annualReportExpenseRatio returns ratio form, but netExpenseRatio
    returns percentage form (0.35 = 0.35%), so we normalize.
    """
    # Try ratio-form key first
    er = info.get("annualReportExpenseRatio")
    if er:
        return er

    # Fallback keys return percentage form — divide by 100 to get ratio
    er_pct = (info.get("netExpenseRatio")
              or info.get("fundOperationsExpenseRatio")
              or info.get("totalExpenseRatio")
              or 0)
    return er_pct / 100.0 if er_pct else 0


def fetch_etf_data(ticker: str, benchmark_ticker: str = None) -> dict:
    """Fetch comprehensive ETF data."""
    etf = yf.Ticker(ticker)
    info = retry_with_backoff(lambda: etf.info)

    # Determine ETF type and default benchmark
    quote_type = info.get("quoteType", "")
    category = info.get("category", "")

    # Auto-detect benchmark if not provided
    if benchmark_ticker is None:
        benchmark_ticker = detect_benchmark(category, ticker)

    benchmark = yf.Ticker(benchmark_ticker) if benchmark_ticker else None

    # Basic ETF info
    result = {
        "ticker": ticker,
        "name": info.get("longName", info.get("shortName", ticker)),
        "category": category,
        "benchmark_ticker": benchmark_ticker,
        "quote_type": quote_type,
        "fund_family": info.get("fundFamily", ""),
        "inception_date": info.get("fundInceptionDate", ""),

        # Price data
        "current_price": info.get("regularMarketPrice", info.get("previousClose", 0)),
        "nav": info.get("navPrice", 0),  # May not be available for all ETFs
        "previous_close": info.get("previousClose", 0),
        "fifty_two_week_high": info.get("fiftyTwoWeekHigh", 0),
        "fifty_two_week_low": info.get("fiftyTwoWeekLow", 0),

        # Cost metrics — annualReportExpenseRatio returns ratio (0.0035 = 0.35%),
        # but netExpenseRatio returns percentage form (0.35 = 0.35%), so normalize
        "expense_ratio": _normalize_expense_ratio(info),
        "total_expense_ratio": info.get("totalExpenseRatio", 0) or 0,

        # Size and liquidity
        "aum": info.get("totalAssets", 0) or 0,
        "avg_volume": info.get("averageVolume", 0) or 0,
        "avg_volume_10d": info.get("averageVolume10days", 0) or 0,
        "bid": info.get("bid", 0) or 0,
        "ask": info.get("ask", 0) or 0,

        # Yield data
        "yield": info.get("yield", 0) or 0,
        "trailing_annual_dividend_yield": info.get("trailingAnnualDividendYield", 0) or 0,
        "dividend_rate": info.get("dividendRate", 0) or 0,

        # Holdings info
        "holdings_count": info.get("holdingsCount", 0) or 0,

        # Beta to market
        "beta_3y": info.get("beta3Year", 0) or 0,
    }

    # Calculate bid-ask spread
    if result["bid"] > 0 and result["ask"] > 0:
        spread = result["ask"] - result["bid"]
        mid_price = (result["ask"] + result["bid"]) / 2
        result["bid_ask_spread"] = spread
        result["bid_ask_spread_pct"] = (spread / mid_price) * 100 if mid_price > 0 else 0
    else:
        result["bid_ask_spread"] = 0
        result["bid_ask_spread_pct"] = 0

    # Calculate premium/discount to NAV
    if result["nav"] > 0 and result["current_price"] > 0:
        result["premium_discount"] = result["current_price"] - result["nav"]
        result["premium_discount_pct"] = ((result["current_price"] / result["nav"]) - 1) * 100
    else:
        result["premium_discount"] = 0
        result["premium_discount_pct"] = 0

    # Fetch historical data for tracking analysis
    end_date = datetime.now()
    start_date = end_date - timedelta(days=365)

    etf_hist = retry_with_backoff(lambda: etf.history(start=start_date, end=end_date))

    if len(etf_hist) > 0:
        # Calculate returns
        etf_returns = etf_hist["Close"].pct_change().dropna()

        result["returns"] = {
            "ytd": calculate_ytd_return(etf_hist),
            "one_month": calculate_period_return(etf_hist, 21),
            "three_month": calculate_period_return(etf_hist, 63),
            "one_year": calculate_period_return(etf_hist, 252),
            "volatility_1y": float(etf_returns.std() * np.sqrt(252) * 100) if len(etf_returns) > 20 else 0,
        }

        # Tracking analysis vs benchmark
        if benchmark:
            bench_hist = retry_with_backoff(lambda: benchmark.history(start=start_date, end=end_date))
            if len(bench_hist) > 0:
                tracking = calculate_tracking_metrics(etf_hist, bench_hist)
                result["tracking"] = tracking

                # Capture ratios
                capture = calculate_capture_ratios(etf_hist, bench_hist)
                result["capture_ratios"] = capture
    else:
        result["returns"] = {
            "ytd": 0, "one_month": 0, "three_month": 0, "one_year": 0, "volatility_1y": 0
        }
        result["tracking"] = {}
        result["capture_ratios"] = {}

    # Detect derivatives-based ETF type
    result["derivatives_type"] = detect_derivatives_type(ticker, info.get("longBusinessSummary", ""), category)

    # Fetch dividend history for covered call ETFs
    if result["derivatives_type"] in ["covered_call", "put_write"]:
        divs = retry_with_backoff(lambda: etf.dividends)
        if len(divs) > 0:
            result["distribution_analysis"] = analyze_distributions(divs, result["current_price"])

    # Fetch top holdings
    result["top_holdings"] = fetch_top_holdings(etf)

    # Use actual holdings count if yfinance didn't provide one
    if result["holdings_count"] == 0 and result["top_holdings"]:
        result["holdings_count"] = len(result["top_holdings"])

    return result


def detect_benchmark(category: str, ticker: str) -> str:
    """Detect appropriate benchmark for ETF category."""
    category_lower = category.lower() if category else ""
    ticker_upper = ticker.upper()

    # S&P 500 trackers
    if any(x in ticker_upper for x in ["SPY", "VOO", "IVV", "SPLG"]):
        return "^GSPC"

    # Nasdaq trackers
    if any(x in ticker_upper for x in ["QQQ", "QQQM"]):
        return "^NDX"

    # Covered call ETFs on S&P
    if any(x in ticker_upper for x in ["JEPI", "XYLD", "SPYI"]):
        return "SPY"

    # Covered call ETFs on Nasdaq
    if any(x in ticker_upper for x in ["JEPQ", "QYLD"]):
        return "QQQ"

    # By category
    if "large cap" in category_lower or "s&p 500" in category_lower:
        return "SPY"
    if "nasdaq" in category_lower or "technology" in category_lower:
        return "QQQ"
    if "small cap" in category_lower:
        return "IWM"
    if "international" in category_lower or "emerging" in category_lower:
        return "VEU"
    if "bond" in category_lower or "fixed income" in category_lower:
        return "BND"

    # Default to S&P 500
    return "SPY"


def detect_derivatives_type(ticker: str, description: str, category: str) -> str:
    """Detect if ETF uses derivatives strategies."""
    ticker_upper = ticker.upper()
    desc_lower = description.lower() if description else ""
    cat_lower = category.lower() if category else ""

    # Covered call / buy-write ETFs
    covered_call_tickers = ["JEPI", "JEPQ", "QYLD", "XYLD", "RYLD", "DIVO", "SPYI", "GPIQ", "DJIA"]
    if ticker_upper in covered_call_tickers:
        return "covered_call"
    if "covered call" in desc_lower or "buy-write" in desc_lower or "premium income" in desc_lower:
        return "covered_call"
    if "option income" in cat_lower or "covered call" in cat_lower:
        return "covered_call"

    # Buffer / defined outcome ETFs
    buffer_prefixes = ["BAPR", "BJAN", "BJUL", "BOCT", "PJAN", "PAPR", "PJUL", "POCT", "TJUL", "TAPR"]
    if any(ticker_upper.startswith(p) for p in buffer_prefixes):
        return "buffer"
    if "buffer" in desc_lower or "defined outcome" in desc_lower:
        return "buffer"

    # Volatility ETFs
    vol_tickers = ["VXX", "UVXY", "SVXY", "VIXY", "VIXM"]
    if ticker_upper in vol_tickers:
        return "volatility"
    if "vix" in ticker_upper.lower() or "volatility" in desc_lower:
        return "volatility"

    # Put-write ETFs
    if ticker_upper == "PUTW" or "put-write" in desc_lower or "putwrite" in desc_lower:
        return "put_write"

    # Leveraged/inverse
    leveraged_tickers = ["TQQQ", "SQQQ", "SPXL", "SPXS", "SOXL", "SOXS", "UPRO", "SH"]
    if ticker_upper in leveraged_tickers:
        return "leveraged"
    if "leveraged" in cat_lower or "inverse" in cat_lower:
        return "leveraged"

    return "standard"


def calculate_ytd_return(hist) -> float:
    """Calculate year-to-date return."""
    if len(hist) == 0:
        return 0

    current_year = datetime.now().year
    ytd_data = hist[hist.index.year == current_year]

    if len(ytd_data) < 2:
        return 0

    first_price = ytd_data["Close"].iloc[0]
    last_price = ytd_data["Close"].iloc[-1]

    return ((last_price / first_price) - 1) * 100


def calculate_period_return(hist, days: int) -> float:
    """Calculate return over specified trading days."""
    if len(hist) < days:
        return 0

    end_price = hist["Close"].iloc[-1]
    start_price = hist["Close"].iloc[-min(days, len(hist))]

    return ((end_price / start_price) - 1) * 100


def calculate_tracking_metrics(etf_hist, bench_hist) -> dict:
    """Calculate tracking error and tracking difference."""
    # Align dates
    common_dates = etf_hist.index.intersection(bench_hist.index)
    if len(common_dates) < 20:
        return {}

    etf_prices = etf_hist.loc[common_dates, "Close"]
    bench_prices = bench_hist.loc[common_dates, "Close"]

    etf_returns = etf_prices.pct_change().dropna()
    bench_returns = bench_prices.pct_change().dropna()

    # Align returns
    common_return_dates = etf_returns.index.intersection(bench_returns.index)
    etf_returns = etf_returns.loc[common_return_dates]
    bench_returns = bench_returns.loc[common_return_dates]

    if len(etf_returns) < 20:
        return {}

    # Tracking difference (return difference)
    return_diff = etf_returns - bench_returns

    # Tracking error (std dev of return differences)
    tracking_error = float(return_diff.std() * np.sqrt(252) * 100)

    # Cumulative tracking difference
    etf_cum = (1 + etf_returns).prod() - 1
    bench_cum = (1 + bench_returns).prod() - 1
    tracking_diff = float((etf_cum - bench_cum) * 100)

    # Correlation
    correlation = float(etf_returns.corr(bench_returns))

    # Beta
    covariance = etf_returns.cov(bench_returns)
    bench_variance = bench_returns.var()
    beta = float(covariance / bench_variance) if bench_variance > 0 else 1.0

    return {
        "tracking_error_pct": tracking_error,
        "tracking_difference_pct": tracking_diff,
        "correlation": correlation,
        "beta": beta,
    }


def calculate_capture_ratios(etf_hist, bench_hist) -> dict:
    """Calculate upside and downside capture ratios."""
    # Align dates
    common_dates = etf_hist.index.intersection(bench_hist.index)
    if len(common_dates) < 20:
        return {}

    etf_prices = etf_hist.loc[common_dates, "Close"]
    bench_prices = bench_hist.loc[common_dates, "Close"]

    etf_returns = etf_prices.pct_change().dropna()
    bench_returns = bench_prices.pct_change().dropna()

    # Align returns
    common_return_dates = etf_returns.index.intersection(bench_returns.index)
    etf_returns = etf_returns.loc[common_return_dates]
    bench_returns = bench_returns.loc[common_return_dates]

    if len(etf_returns) < 20:
        return {}

    # Up days
    up_days = bench_returns > 0
    # Down days
    down_days = bench_returns < 0

    # Upside capture
    if up_days.sum() > 0:
        etf_up = etf_returns[up_days].sum()
        bench_up = bench_returns[up_days].sum()
        upside_capture = (etf_up / bench_up) * 100 if bench_up != 0 else 0
    else:
        upside_capture = 0

    # Downside capture
    if down_days.sum() > 0:
        etf_down = etf_returns[down_days].sum()
        bench_down = bench_returns[down_days].sum()
        downside_capture = (etf_down / bench_down) * 100 if bench_down != 0 else 0
    else:
        downside_capture = 0

    return {
        "upside_capture_pct": float(upside_capture),
        "downside_capture_pct": float(downside_capture),
    }


def fetch_top_holdings(etf, max_holdings: int = 50) -> list:
    """Fetch top holdings for the ETF (fetches up to max_holdings, display controlled by OCaml)."""
    holdings = []

    try:
        # Method 1: Try funds_data.top_holdings (newer yfinance API)
        try:
            funds_data = etf.funds_data
            if hasattr(funds_data, 'top_holdings') and funds_data.top_holdings is not None:
                holdings_df = funds_data.top_holdings
                if len(holdings_df) > 0:
                    for idx, row in holdings_df.head(max_holdings).iterrows():
                        holding = {
                            "symbol": str(idx) if isinstance(idx, str) else row.get("Symbol", ""),
                            "name": row.get("Name", row.get("holdingName", "")),
                            "weight": float(row.get("Holding Percent", row.get("holdingPercent", 0))) * 100
                                if row.get("Holding Percent", row.get("holdingPercent", 0)) else 0,
                        }
                        if holding["symbol"] and holding["weight"] > 0:
                            holdings.append(holding)
        except Exception:
            pass

        # Method 2: Try equity_holdings if available (contains more detailed data)
        if len(holdings) < max_holdings:
            try:
                funds_data = etf.funds_data
                if hasattr(funds_data, 'equity_holdings') and funds_data.equity_holdings is not None:
                    eq_holdings = funds_data.equity_holdings
                    if len(eq_holdings) > 0:
                        existing_symbols = {h["symbol"] for h in holdings}
                        for idx, row in eq_holdings.head(max_holdings).iterrows():
                            symbol = str(idx) if isinstance(idx, str) else row.get("Symbol", "")
                            if symbol and symbol not in existing_symbols:
                                holding = {
                                    "symbol": symbol,
                                    "name": row.get("Name", row.get("holdingName", "")),
                                    "weight": float(row.get("Holding Percent", row.get("holdingPercent", 0))) * 100
                                        if row.get("Holding Percent", row.get("holdingPercent", 0)) else 0,
                                }
                                if holding["weight"] > 0:
                                    holdings.append(holding)
                                    existing_symbols.add(symbol)
            except Exception:
                pass

        # Method 3: Fallback to info dict
        if len(holdings) == 0:
            info = etf.info
            if "holdings" in info and isinstance(info["holdings"], list):
                holdings = info["holdings"][:max_holdings]

        return holdings[:max_holdings]
    except Exception as e:
        print(f"  Note: Could not fetch holdings data: {e}")
        return []
    except Exception as e:
        print(f"  Note: Could not fetch holdings data: {e}")
        return []


def analyze_distributions(dividends, current_price: float) -> dict:
    """Analyze distribution history for income ETFs."""
    if len(dividends) == 0:
        return {}

    # Last 12 months of distributions
    one_year_ago = datetime.now() - timedelta(days=365)
    recent_divs = dividends[dividends.index >= one_year_ago.strftime("%Y-%m-%d")]

    if len(recent_divs) == 0:
        return {}

    total_12m = float(recent_divs.sum())
    distribution_yield = (total_12m / current_price) * 100 if current_price > 0 else 0

    # Distribution frequency
    if len(recent_divs) >= 12:
        frequency = "Monthly"
    elif len(recent_divs) >= 4:
        frequency = "Quarterly"
    else:
        frequency = "Other"

    # Distribution consistency
    div_values = recent_divs.values
    if len(div_values) > 1:
        div_std = float(np.std(div_values))
        div_mean = float(np.mean(div_values))
        div_cv = (div_std / div_mean) * 100 if div_mean > 0 else 0  # Coefficient of variation
    else:
        div_cv = 0

    return {
        "total_12m": total_12m,
        "distribution_yield_pct": distribution_yield,
        "distribution_count_12m": len(recent_divs),
        "frequency": frequency,
        "avg_distribution": float(np.mean(div_values)) if len(div_values) > 0 else 0,
        "min_distribution": float(np.min(div_values)) if len(div_values) > 0 else 0,
        "max_distribution": float(np.max(div_values)) if len(div_values) > 0 else 0,
        "distribution_variability_pct": div_cv,
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python fetch_etf_data.py <ticker> [benchmark_ticker]")
        sys.exit(1)

    ticker = sys.argv[1].upper()
    benchmark = sys.argv[2].upper() if len(sys.argv) > 2 else None

    data = fetch_etf_data(ticker, benchmark)

    # Output to file
    output_dir = Path(__file__).parent.parent.parent / "data"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"etf_data_{ticker}.json"

    with open(output_file, "w") as f:
        json.dump(data, f, indent=2, default=str)

    print(f"ETF data saved to {output_file}")

    # Also print summary
    print(f"\n{data['name']} ({ticker})")
    print(f"Category: {data['category']}")
    print(f"Type: {data['derivatives_type']}")
    print(f"Price: ${data['current_price']:.2f}")
    print(f"AUM: ${data['aum']/1e9:.2f}B" if data['aum'] > 0 else "AUM: N/A")
    print(f"Expense Ratio: {data['expense_ratio']*100:.2f}%" if data['expense_ratio'] > 0 else "")
    print(f"Yield: {data['yield']*100:.2f}%" if data['yield'] > 0 else "")
    if data.get('tracking'):
        print(f"Tracking Error (1Y): {data['tracking'].get('tracking_error_pct', 0):.2f}%")

    # Print top holdings if available (show first 10 in fetch summary)
    if data.get('top_holdings') and len(data['top_holdings']) > 0:
        total = len(data['top_holdings'])
        print(f"\nTop Holdings ({total} available from data source):")
        for h in data['top_holdings'][:10]:
            sym = h.get('symbol', '???')
            name = h.get('name', '')[:30]
            weight = h.get('weight', 0)
            print(f"  {sym:6s} {weight:5.2f}%  {name}")
        if total > 10:
            print(f"  ... and {total - 10} more")
        if total < 15:
            print(f"  (Note: Yahoo Finance typically only provides top 10 holdings)")


if __name__ == "__main__":
    main()
