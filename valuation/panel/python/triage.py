"""Ticker classification and routing for the valuation panel."""

import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

import yfinance as yf
from lib.python.retry import retry_with_backoff

# Reuse universe definitions from analyst_upside
sys.path.insert(0, str(Path(__file__).parents[2] / "analyst_upside" / "python"))
from fetch_targets import UNIVERSES

PROJECT_ROOT = Path(__file__).parents[3]
HOLDINGS_FILE = PROJECT_ROOT / "valuation" / "crypto_treasury" / "data" / "holdings.json"
PORTFOLIO_FILE = PROJECT_ROOT / "monitoring" / "watchlist" / "data" / "portfolio.json"

# Load crypto treasury tickers
def _load_crypto_tickers() -> set:
    try:
        with open(HOLDINGS_FILE) as f:
            data = json.load(f)
        return set(data.get("holdings", {}).keys())
    except (FileNotFoundError, json.JSONDecodeError):
        return set()

CRYPTO_TICKERS = _load_crypto_tickers()


def resolve_universe(universe: str) -> list[str]:
    """Resolve a universe specifier to a list of ticker symbols."""
    if universe in UNIVERSES:
        return UNIVERSES[universe]

    if universe == "portfolio":
        return _load_portfolio_tickers(include_watching=False)
    if universe == "watchlist":
        return _load_portfolio_tickers(watching_only=True)
    if universe == "all_portfolio":
        return _load_portfolio_tickers(include_watching=True)
    if universe == "liquid":
        liquid_file = PROJECT_ROOT / "pricing" / "liquidity" / "data" / "liquid_tickers.txt"
        if liquid_file.exists():
            return [t.strip() for t in liquid_file.read_text().splitlines() if t.strip()]
        return []

    # Assume comma-separated tickers
    return [t.strip().upper() for t in universe.split(",") if t.strip()]


def _load_portfolio_tickers(include_watching=True, watching_only=False) -> list[str]:
    try:
        with open(PORTFOLIO_FILE) as f:
            data = json.load(f)
        tickers = []
        for pos in data.get("positions", []):
            ptype = pos.get("position_type", "").lower()
            if watching_only and ptype != "watching":
                continue
            if not include_watching and ptype == "watching":
                continue
            ticker = pos.get("ticker", "")
            if ticker:
                tickers.append(ticker)
        return tickers
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def triage_ticker(ticker: str) -> dict:
    """Fetch metadata for a single ticker and classify it."""
    try:
        info = retry_with_backoff(lambda: yf.Ticker(ticker).info)
        return {
            "ticker": ticker,
            "quote_type": info.get("quoteType", "EQUITY"),
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice") or 0.0,
            "market_cap": info.get("marketCap", 0),
            "has_dividends": bool(info.get("dividendRate")),
            "trailing_pe": info.get("trailingPE"),
            "forward_pe": info.get("forwardPE"),
            "eps_trailing": info.get("trailingEps"),
            "eps_forward": info.get("forwardEps"),
            "analyst_count": info.get("numberOfAnalystOpinions", 0),
            "revenue_growth": info.get("revenueGrowth"),
            "company_name": info.get("shortName", ticker),
            "error": None,
        }
    except Exception as e:
        return {"ticker": ticker, "error": str(e)}


def triage_all(tickers: list[str], max_workers: int = 10) -> list[dict]:
    """Triage all tickers in parallel."""
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(triage_ticker, t): t for t in tickers}
        for future in as_completed(futures):
            results.append(future.result())
    # Preserve original order
    by_ticker = {r["ticker"]: r for r in results}
    return [by_ticker[t] for t in tickers if t in by_ticker]


def build_execution_plan(
    triage_results: list[dict],
    include_probabilistic: bool = False,
) -> dict[str, list[str]]:
    """Route each ticker to its applicable valuation modules."""
    plan = {}

    for info in triage_results:
        ticker = info["ticker"]
        if info.get("error"):
            continue

        modules = []
        quote_type = info.get("quote_type", "EQUITY")
        sector = info.get("sector", "")

        # Exclusive gates
        if quote_type == "ETF":
            plan[ticker] = ["etf_analysis"]
            continue

        if sector == "Real Estate" and quote_type == "EQUITY":
            plan[ticker] = ["dcf_reit"]
            continue

        # Crypto treasury gate (non-exclusive — also runs general modules)
        if ticker in CRYPTO_TICKERS:
            modules.append("crypto_treasury")

        # General stock modules
        modules.append("analyst_upside")

        if info.get("eps_trailing") is not None:
            modules.append("dcf_deterministic")
            if include_probabilistic:
                modules.append("dcf_probabilistic")

        if info.get("trailing_pe") is not None:
            modules.append("normalized_multiples")

        if info.get("eps_trailing") is not None and info.get("eps_trailing", 0) > 0 and info.get("forward_pe") is not None:
            modules.append("garp_peg")

        if info.get("revenue_growth") is not None:
            modules.append("growth_analysis")

        if info.get("has_dividends"):
            modules.append("dividend_income")

        plan[ticker] = modules

    return plan
