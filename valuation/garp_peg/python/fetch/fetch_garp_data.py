#!/usr/bin/env python3
"""
Fetch GARP/PEG analysis data.

Uses yfinance for fundamental data (analyst estimates, financials).
Note: IBKR doesn't provide fundamental data, so yfinance is required here.
Outputs garp_data JSON file with P/E ratios, growth estimates, and quality metrics.
"""

import argparse
import functools
import json
import sys
import time
import random
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf

from lib.python.retry import retry_with_backoff
from lib.python.yfinance_utils import (
    get_financial_value,
    financial_fx_factor,
    to_trading_basis,
)

# Cost-of-equity inputs are sourced from the SHARED country config the DCF uses,
# so GARP's discount rate stays consistent with the DCF and auto-updates with the
# refreshed risk-free / ERP / terminal-growth tables.
_COE_DEFAULTS = {"risk_free": 0.043, "erp": 0.045, "terminal_growth": 0.04}

# Trading currency -> the country whose risk-free / terminal-growth to use. The
# discount rate must be in the VALUATION (trading) currency: a USD-listed ADR is
# discounted at the US risk-free, NOT its local (e.g. tenge 15% / Taiwan 1.6%) rate.
_CCY_TO_RF_COUNTRY = {
    "USD": "United States", "EUR": "Germany", "GBP": "United Kingdom",
    "JPY": "Japan", "CHF": "Switzerland", "CAD": "Canada", "AUD": "Australia",
    "HKD": "Hong Kong", "SGD": "Singapore", "CNY": "China", "INR": "India",
    "BRL": "Brazil", "KRW": "South Korea", "TWD": "Taiwan", "SEK": "Sweden",
    "ILS": "Israel", "KZT": "Kazakhstan",
}


@functools.lru_cache(maxsize=1)
def _load_country_config() -> dict:
    base = Path(__file__).parents[4] / "valuation" / "dcf_deterministic" / "data"
    out = {}
    for key, fname in [("rf", "risk_free_rates.json"),
                       ("erp", "equity_risk_premiums.json"),
                       ("params", "params.json")]:
        try:
            out[key] = json.loads((base / fname).read_text())
        except Exception:
            out[key] = {}
    return out


def cost_of_equity_for(country: str, trading_currency: str, beta: float) -> tuple[float, float]:
    """CAPM cost of equity in the VALUATION (trading) currency, plus a terminal
    growth rate, from the shared DCF country config.

    Risk-free and terminal growth are taken from the TRADING currency's country
    (so a USD-listed ADR is discounted at the US risk-free, not its local rate);
    the equity risk premium uses the company's COUNTRY (which carries country
    risk). Returns (cost_of_equity, terminal_growth) as decimals; cost_of_equity
    is clamped to a sane [6%, 20%] band. Falls back to US / defaults throughout.
    """
    cfg = _load_country_config()
    rf_tbl, erp_tbl = cfg.get("rf", {}), cfg.get("erp", {})
    tg_tbl = (cfg.get("params", {}) or {}).get("terminal_growth_rate", {})
    rf_country = _CCY_TO_RF_COUNTRY.get((trading_currency or "USD").upper(), country)
    row = rf_tbl.get(rf_country) or rf_tbl.get("USA") or {}
    rf = row.get("7y") or row.get("10y") or _COE_DEFAULTS["risk_free"]
    # International CAPM: CoE = rf + beta*mature_ERP + country_risk_premium.
    # Adding CRP SEPARATELY (not beta-scaled) avoids diluting country risk when an
    # illiquid EM ADR carries an unreliably low yfinance beta. mature_ERP is the
    # base (Germany ~4.23% in the refreshed table); CRP = country_ERP - mature_ERP.
    mature_erp = erp_tbl.get("Germany") or 0.0423
    country_erp = erp_tbl.get(country) or erp_tbl.get("USA") or _COE_DEFAULTS["erp"]
    crp = max(0.0, country_erp - mature_erp)
    b = beta if (beta and beta > 0) else 1.0
    coe = max(0.07, min(0.20, rf + b * mature_erp + crp))
    tg = tg_tbl.get(rf_country) or tg_tbl.get("default") or _COE_DEFAULTS["terminal_growth"]
    return coe, tg


def fetch_garp_data(ticker_obj, ticker_symbol):
    """Extract GARP/PEG analysis data from yfinance ticker."""
    info = ticker_obj.info

    price = info.get("currentPrice", info.get("regularMarketPrice", 0.0))
    market_cap = info.get("marketCap", 0.0)
    fx, trading_ccy, financial_ccy, fx_ok = financial_fx_factor(info)
    if not fx_ok:
        print(
            f"WARN: FX {financial_ccy}->{trading_ccy} unavailable; "
            f"GARP figures may be currency-mismatched",
            file=sys.stderr,
        )

    if financial_ccy == trading_ccy:
        # Same currency (US / local listing): .info fields are reliable and match
        # reported EPS -> keep original behavior exactly.
        shares_outstanding = info.get("sharesOutstanding", 0.0)
        eps_trailing = info.get("trailingEps", 0.0)
        eps_forward = info.get("forwardEps", 0.0)
        pe_trailing = info.get("trailingPE", 0.0)
        pe_forward = info.get("forwardPE", 0.0)
        free_cash_flow = info.get("freeCashflow", 0.0)
        operating_cash_flow = info.get("operatingCashflow", 0.0)
        net_income = info.get("netIncomeToCommon", 0.0)
        total_revenue = info.get("totalRevenue", 0.0)
        total_debt = info.get("totalDebt", 0.0)
        total_cash = info.get("totalCash", 0.0)
        book_value_ps = info.get("bookValue", 0.0)
        total_equity = book_value_ps * shares_outstanding if book_value_ps and shares_outstanding else 0.0
    else:
        # Cross-currency (ADR / foreign-reporting): .info per-share fields have
        # unreliable, per-ticker-inconsistent currency, so derive monetary figures
        # from the statements (consistently financialCurrency) x fx, with an
        # effective share count = marketCap/price (cancels currency AND ADR ratio).
        income_stmt = ticker_obj.income_stmt
        balance_sheet = ticker_obj.balance_sheet
        cash_flow = ticker_obj.cash_flow
        shares_outstanding = (market_cap / price) if (market_cap and price) \
            else info.get("sharesOutstanding", 0.0)

        net_income = get_financial_value(income_stmt, ["Net Income", "Net Income Common Stockholders"]) * fx
        total_revenue = get_financial_value(income_stmt, ["Total Revenue", "Operating Revenue"]) * fx
        total_equity = get_financial_value(balance_sheet, ["Stockholders Equity", "Total Equity Gross Minority Interest", "Common Stock Equity"]) * fx
        ocf = get_financial_value(cash_flow, ["Operating Cash Flow", "Total Cash From Operating Activities", "Cash Flow From Continuing Operating Activities"]) * fx
        capex = abs(get_financial_value(cash_flow, ["Capital Expenditure", "Capital Expenditures"])) * fx
        free_cash_flow = (ocf - capex) if ocf else 0.0
        operating_cash_flow = ocf
        total_debt = get_financial_value(balance_sheet, ["Total Debt", "Long Term Debt"]) * fx
        total_cash = get_financial_value(balance_sheet, ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"]) * fx

        eps_trailing = net_income / shares_outstanding if shares_outstanding > 0 else 0.0
        # Forward EPS isn't in the statements; normalize the .info value against the
        # trustworthy statement-derived trailing anchor (its currency varies by ticker).
        eps_forward = to_trading_basis(info.get("forwardEps", 0.0) or 0.0, eps_trailing, fx)
        book_value_ps = total_equity / shares_outstanding if shares_outstanding > 0 else 0.0
        pe_trailing = price / eps_trailing if eps_trailing > 0 else 0.0
        pe_forward = price / eps_forward if eps_forward > 0 else 0.0

    # Growth estimates (decimals, currency-neutral)
    earnings_growth = info.get("earningsGrowth", 0.0)
    earnings_quarterly_growth = info.get("earningsQuarterlyGrowth", 0.0)
    revenue_growth = info.get("revenueGrowth", 0.0)
    peg_ratio_yf = info.get("pegRatio", 0.0)

    # 1Y EPS growth (forward vs trailing)
    if eps_trailing > 0 and eps_forward > 0:
        eps_growth_1y = (eps_forward - eps_trailing) / eps_trailing
    else:
        eps_growth_1y = 0.0
    growth_estimate_5y = info.get("earningsGrowth", 0.0)

    # Returns (decimals, currency-neutral)
    roe = info.get("returnOnEquity", 0.0)
    roa = info.get("returnOnAssets", 0.0)

    # Dividend (for PEGY ratio)
    dividend_yield = info.get("dividendYield", 0.0)
    dividend_rate = info.get("dividendRate", 0.0)

    # Debt to Equity ratio (yfinance provides as percentage, e.g. 39.16 = 39.16%)
    debt_to_equity_raw = info.get("debtToEquity", 0.0)
    debt_to_equity = (debt_to_equity_raw / 100.0) if debt_to_equity_raw else 0.0

    # Derived metrics (ratios are currency-invariant)
    fcf_conversion = free_cash_flow / net_income if net_income > 0 else 0.0
    fcf_per_share = free_cash_flow / shares_outstanding if shares_outstanding > 0 else 0.0
    net_cash = total_cash - total_debt
    net_cash_per_share = net_cash / shares_outstanding if shares_outstanding > 0 else 0.0

    # Sector and industry for context
    sector = info.get("sector", "Unknown")
    industry = info.get("industry", "Unknown")

    # Discount-rate inputs for the justified-P/E model: CAPM cost of equity
    # (rf + beta*ERP) and terminal growth, from the shared country config.
    country = info.get("country", "USA")
    beta = info.get("beta") or 1.0
    cost_of_equity, terminal_growth = cost_of_equity_for(
        country, info.get("currency", "USD"), beta)

    garp_data = {
        "ticker": ticker_symbol,
        "price": price,
        "market_cap": market_cap,
        "shares_outstanding": shares_outstanding,
        "currency": trading_ccy,
        "financial_currency": financial_ccy,
        "fx_to_trading": fx,
        "fx_ok": fx_ok,

        # EPS data
        "eps_trailing": eps_trailing,
        "eps_forward": eps_forward,

        # P/E ratios
        "pe_trailing": pe_trailing,
        "pe_forward": pe_forward,

        # Growth rates (as decimals, e.g., 0.15 = 15%)
        "earnings_growth": earnings_growth,
        "earnings_quarterly_growth": earnings_quarterly_growth,
        "revenue_growth": revenue_growth,
        "eps_growth_1y": eps_growth_1y,
        "growth_estimate_5y": growth_estimate_5y,

        # PEG from yfinance (for comparison)
        "peg_ratio_yf": peg_ratio_yf,

        # Quality metrics
        "free_cash_flow": free_cash_flow,
        "operating_cash_flow": operating_cash_flow,
        "net_income": net_income,
        "total_revenue": total_revenue,

        # Balance sheet
        "total_debt": total_debt,
        "total_equity": total_equity,
        "total_cash": total_cash,
        "debt_to_equity": debt_to_equity,

        # Returns (as decimals)
        "roe": roe,
        "roa": roa,

        # Derived metrics
        "fcf_conversion": fcf_conversion,
        "fcf_per_share": fcf_per_share,
        "book_value_per_share": book_value_ps,
        "net_cash_per_share": net_cash_per_share,

        # Dividend (for PEGY)
        "dividend_yield": dividend_yield,
        "dividend_rate": dividend_rate,

        # Classification
        "sector": sector,
        "industry": industry,

        # Discount-rate inputs for the justified-P/E fair-value model
        "country": country,
        "beta": beta,
        "cost_of_equity": cost_of_equity,
        "terminal_growth": terminal_growth,
    }

    return garp_data



def main():
    parser = argparse.ArgumentParser(description="Fetch GARP/PEG analysis data")
    parser.add_argument("--ticker", required=True, help="Ticker symbol (e.g., AAPL)")
    parser.add_argument("--output", default="/tmp", help="Output directory for JSON files")
    args = parser.parse_args()

    ticker_symbol = args.ticker.upper()
    output_dir = Path(args.output)

    # Add small random delay to reduce parallel request contention
    initial_delay = random.uniform(0, 0.5)
    time.sleep(initial_delay)

    print(f"Fetching GARP data for {ticker_symbol}...")

    try:
        # Fetch ticker data with retry logic
        ticker = retry_with_backoff(lambda: yf.Ticker(ticker_symbol))

        # Extract GARP data
        garp_data = retry_with_backoff(lambda: fetch_garp_data(ticker, ticker_symbol))

        # Validate critical fields
        if garp_data["price"] == 0.0:
            raise ValueError("Current price is zero or not available")
        if garp_data["eps_trailing"] == 0.0 and garp_data["eps_forward"] == 0.0:
            print("Warning: No EPS data available - PEG calculation may be invalid", file=sys.stderr)

        # Write JSON file
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"garp_data_{ticker_symbol}.json"

        with open(output_file, "w") as f:
            json.dump(garp_data, f, indent=2)
        print(f"GARP data written to: {output_file}")

        print("Data fetch successful!")

    except Exception as e:
        print(f"Error fetching data: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
