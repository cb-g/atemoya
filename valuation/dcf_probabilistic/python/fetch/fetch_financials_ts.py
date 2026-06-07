#!/usr/bin/env python3
"""
Fetch 4-year time series financial data for probabilistic DCF valuation using yfinance.
Outputs market_data and time_series JSON files.

Supports specialized models:
- Banks: Excess Return Model (ROE-based)
- Insurance: Float-Based Model (combined ratio + float)
- Oil & Gas: NAV Model (reserve-based)
- Standard: FCFE/FCFF (default)
"""

import argparse
import json
import sys
import time
import random
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[4]))

import yfinance as yf

from lib.python.retry import retry_with_backoff
from lib.python.yfinance_utils import fx_rate, convert_financial_fields

# Sector-specific monetary fields embedded in market_data (financialCurrency).
# Excludes trading-currency values (price/mve/mvb/debt), ratios (combined/loss/
# expense), ratio histories (roe/cr/yield), and physical O&G quantities.
_MARKET_FINANCIAL_KEYS = [
    "book_value_equity", "net_income", "tangible_book_value",
    "net_interest_income", "non_interest_income", "non_interest_expense",
    "total_deposits", "total_loans",
    "premiums_earned", "losses_incurred", "underwriting_expenses", "investment_income",
    "float_amount",
]
# Time-series monetary lists (financialCurrency), converted element-wise.
_TS_FINANCIAL_KEYS = [
    "ebit", "net_income", "capex", "depreciation", "dividend_payout",
    "current_assets", "current_liabilities", "book_value_equity", "invested_capital",
]


def detect_model_type(info, ticker_obj=None):
    """Detect specialized model type. Statement signatures (robust endpoints) take
    precedence over the rate-limit-fragile .info["industry"] string, which under the
    panel's parallel load often returns empty and silently routed banks/insurers to
    the generic corporate DCF."""
    industry = info.get("industry", "").lower()
    info_bank = any(term in industry for term in [
        "bank", "regional banks", "diversified banks", "money center",
        "investment banking", "capital markets",
        "credit services",
    ])
    info_ins = any(term in industry for term in [
        "insurance", "property & casualty", "life insurance", "health insurance",
        "reinsurance", "insurance brokers", "insurance—diversified",
        "insurance—property & casualty", "insurance—life",
    ])
    info_og = any(term in industry for term in [
        "oil & gas e&p", "oil & gas exploration", "oil & gas production",
        "oil & gas integrated", "oil & gas midstream", "oil & gas drilling",
        "oil & gas refining", "oil & gas equipment",
    ])
    stmt_bank = stmt_ins = False
    if ticker_obj is not None:
        try:
            bs, inc = ticker_obj.balance_sheet, ticker_obj.income_stmt
            stmt_bank = (_get_value(bs, ["Total Deposits", "Deposits"]) > 0.0
                         or _get_value(inc, ["Net Interest Income"]) > 0.0)
            # CLEAN premium lines only (the insurer field read elsewhere falls back to
            # Total Revenue, which every company has — useless as a signature).
            stmt_ins = _get_value(inc, [
                "Net Premiums Earned", "Total Premiums Earned", "Premiums Earned",
                "Insurance Premiums", "Net Premium Earned",
            ]) > 0.0
        except Exception:
            pass

    if stmt_bank or info_bank:
        return "bank"
    if stmt_ins or info_ins:
        return "insurance"
    if info_og:
        return "oil_gas"
    return "standard"


def fetch_market_data(ticker_obj, ticker_symbol):
    """Extract market data from yfinance ticker."""
    info = ticker_obj.info

    market_data = {
        "ticker": ticker_symbol,
        "price": info.get("currentPrice", info.get("regularMarketPrice", 0.0)),
        "mve": info.get("marketCap", 0.0),
        "mvb": info.get("totalDebt", 0.0),
        "shares_outstanding": info.get("sharesOutstanding", 0.0),
        "currency": info.get("currency", "USD"),
        "financial_currency": info.get("financialCurrency") or info.get("currency") or "USD",
        "country": info.get("country", "USA"),
        "sector": info.get("sector", "Unknown"),
        "industry": info.get("industry", "Unknown"),
    }

    # For cross-currency listings (ADRs / foreign reporting) use an effective
    # ADR-equivalent share count (marketCap/price) so per-share intrinsic value is
    # comparable to the trading price even when 1 ADR != 1 ordinary share. Same-
    # currency (US/local) names keep yfinance's reported share count unchanged.
    if (market_data["financial_currency"] != market_data["currency"]
            and market_data["mve"] and market_data["price"]):
        market_data["shares_reported"] = market_data["shares_outstanding"]
        market_data["shares_outstanding"] = market_data["mve"] / market_data["price"]

    model_type = detect_model_type(info, ticker_obj)
    market_data["model_type"] = model_type
    if not info.get("industry") and model_type in ("bank", "insurance"):
        print(f"WARN {ticker_symbol}: empty .info industry (likely throttled) — "
              f"classified via statement signature as {model_type}", file=sys.stderr)

    # Add sector-specific fields
    if model_type == "bank":
        _add_bank_fields(ticker_obj, market_data)
    elif model_type == "insurance":
        _add_insurance_fields(ticker_obj, market_data)
    elif model_type == "oil_gas":
        _add_oil_gas_fields(ticker_obj, market_data)

    return market_data


def _get_value(df, keys, default=0.0):
    """Safely get a value from a dataframe with multiple key fallbacks."""
    if isinstance(keys, str):
        keys = [keys]
    for key in keys:
        if key in df.index:
            val = df.loc[key].iloc[0] if not df.loc[key].empty else default
            return float(val) if val == val else default  # NaN check
    return default


def _get_series(df, keys, default=0.0):
    """Extract up to 4-year series from a dataframe."""
    if isinstance(keys, str):
        keys = [keys]
    for key in keys:
        if key in df.index:
            series = df.loc[key].fillna(default).tolist()
            return series[:4]
    return [default] * 4


def _add_bank_fields(ticker_obj, market_data):
    """Add bank-specific fields to market_data."""
    income_stmt = ticker_obj.income_stmt
    balance_sheet = ticker_obj.balance_sheet

    # Current snapshot values
    book_value_equity = _get_value(balance_sheet, [
        "Stockholders Equity", "Total Equity Gross Minority Interest", "Common Stock Equity"
    ])
    net_income = _get_value(income_stmt, ["Net Income", "Net Income Common Stockholders"])

    goodwill = _get_value(balance_sheet, ["Goodwill"])
    intangibles = _get_value(balance_sheet, ["Other Intangible Assets", "Intangible Assets"])
    tangible_book_value = book_value_equity - goodwill - intangibles

    net_interest_income = _get_value(income_stmt, ["Net Interest Income"])
    if net_interest_income == 0.0:
        ii = _get_value(income_stmt, ["Interest Income", "Total Interest Income"])
        ie = _get_value(income_stmt, ["Interest Expense"])
        net_interest_income = ii - abs(ie)

    non_interest_income = _get_value(income_stmt, [
        "Non Interest Income", "Other Non Interest Income", "Total Non Interest Income"
    ])
    non_interest_expense = _get_value(income_stmt, [
        "Non Interest Expense", "Total Non Interest Expense"
    ])
    total_deposits = _get_value(balance_sheet, ["Total Deposits", "Deposits"])
    total_loans = _get_value(balance_sheet, ["Net Loan", "Total Net Loans", "Gross Loan"])

    market_data["book_value_equity"] = book_value_equity
    market_data["net_income"] = net_income
    market_data["tangible_book_value"] = tangible_book_value
    market_data["net_interest_income"] = net_interest_income
    market_data["non_interest_income"] = non_interest_income
    market_data["non_interest_expense"] = non_interest_expense
    market_data["total_deposits"] = total_deposits
    market_data["total_loans"] = total_loans

    # 4-year ROE history for stochastic sampling
    ni_series = _get_series(income_stmt, ["Net Income", "Net Income Common Stockholders"])
    bve_series = _get_series(balance_sheet, [
        "Stockholders Equity", "Total Equity Gross Minority Interest", "Common Stock Equity"
    ])
    roe_history = []
    for ni, bve in zip(ni_series, bve_series):
        if bve > 0:
            roe_history.append(ni / bve)
        else:
            roe_history.append(0.0)
    market_data["roe_history"] = roe_history


def _add_insurance_fields(ticker_obj, market_data):
    """Add insurance-specific fields to market_data."""
    income_stmt = ticker_obj.income_stmt
    balance_sheet = ticker_obj.balance_sheet

    book_value_equity = _get_value(balance_sheet, [
        "Stockholders Equity", "Total Equity Gross Minority Interest", "Common Stock Equity"
    ])

    premiums_earned = _get_value(income_stmt, [
        "Total Revenue", "Operating Revenue", "Net Premiums Earned", "Total Premiums Earned"
    ])

    losses_incurred = abs(_get_value(income_stmt, [
        "Loss Adjustment Expense", "Net Policyholder Benefits And Claims",
        "Policyholder Benefits Gross", "Losses Benefits And Adjustments",
        "Benefits Cost And Expense",
    ]))

    total_expenses = abs(_get_value(income_stmt, ["Total Expenses"]))
    interest_exp = abs(_get_value(income_stmt, ["Interest Expense"]))
    if total_expenses > 0 and losses_incurred > 0:
        underwriting_expenses = total_expenses - losses_incurred - interest_exp
    else:
        underwriting_expenses = abs(_get_value(income_stmt, [
            "Selling General And Administration", "Operating Expense",
            "General And Administrative Expense",
        ]))

    investment_income = _get_value(income_stmt, [
        "Other Income Expense", "Net Investment Income", "Investment Income"
    ])
    if investment_income <= 0:
        investments = _get_value(balance_sheet, ["Investments And Advances"])
        if investments > 0:
            investment_income = investments * 0.04

    total_liabilities = _get_value(balance_sheet, ["Total Liabilities Net Minority Interest"])
    total_debt = _get_value(balance_sheet, ["Total Debt", "Long Term Debt"])
    float_amount = max(0.0, total_liabilities - total_debt) if total_liabilities > 0 else 0.0

    # Ratios
    loss_ratio = losses_incurred / premiums_earned if premiums_earned > 0 else 0.0
    expense_ratio = underwriting_expenses / premiums_earned if premiums_earned > 0 else 0.0
    combined_ratio = loss_ratio + expense_ratio

    market_data["book_value_equity"] = book_value_equity
    market_data["premiums_earned"] = premiums_earned
    market_data["losses_incurred"] = losses_incurred
    market_data["underwriting_expenses"] = underwriting_expenses
    market_data["investment_income"] = investment_income
    market_data["float_amount"] = float_amount
    market_data["combined_ratio"] = combined_ratio
    market_data["loss_ratio"] = loss_ratio
    market_data["expense_ratio"] = expense_ratio

    # 4-year CR and yield history for stochastic sampling
    prem_series = _get_series(income_stmt, [
        "Total Revenue", "Operating Revenue", "Net Premiums Earned"
    ])
    loss_series = [abs(x) for x in _get_series(income_stmt, [
        "Loss Adjustment Expense", "Net Policyholder Benefits And Claims",
        "Policyholder Benefits Gross", "Losses Benefits And Adjustments",
        "Benefits Cost And Expense",
    ])]

    cr_history = []
    for prem, loss in zip(prem_series, loss_series):
        if prem > 0:
            cr_history.append(loss / prem + expense_ratio)  # Use current expense ratio as proxy
        else:
            cr_history.append(1.0)
    market_data["cr_history"] = cr_history

    # Yield history
    inv_income_series = _get_series(income_stmt, [
        "Other Income Expense", "Net Investment Income", "Investment Income"
    ])
    yield_history = []
    for inc in inv_income_series:
        if float_amount > 0:
            yield_history.append(inc / float_amount)
        else:
            yield_history.append(0.04)  # Default 4%
    market_data["yield_history"] = yield_history


def _add_oil_gas_fields(ticker_obj, market_data):
    """Add O&G-specific fields to market_data."""
    info = ticker_obj.info
    income_stmt = ticker_obj.income_stmt
    balance_sheet = ticker_obj.balance_sheet

    book_value_equity = _get_value(balance_sheet, [
        "Stockholders Equity", "Total Equity Gross Minority Interest", "Common Stock Equity"
    ])

    # O&G reserves/production aren't available from yfinance
    # Use static fallback data or SEC fetch (handled by deterministic module)
    # For probabilistic, we read from og_reserves.json if available
    market_data["book_value_equity"] = book_value_equity
    market_data["debt"] = info.get("totalDebt", 0.0)

    # Try to load O&G reserve data from deterministic module's static file
    og_reserves_path = Path(__file__).parents[4] / "valuation" / "dcf_deterministic" / "data" / "og_reserves.json"
    ticker_symbol = market_data["ticker"]

    if og_reserves_path.exists():
        with open(og_reserves_path) as f:
            og_data = json.load(f)
        companies = og_data.get("companies", og_data)
        if ticker_symbol in companies:
            entry = companies[ticker_symbol]
            market_data["proven_reserves"] = entry.get("proven_reserves_mmboe", entry.get("proven_reserves", 0.0))
            market_data["production_boe_day"] = entry.get("production_boe_day", 0.0)
            market_data["oil_pct"] = entry.get("oil_pct", 0.5)
            market_data["lifting_cost"] = entry.get("lifting_cost", 10.0)
            market_data["finding_cost"] = entry.get("finding_cost", 15.0)
            print(f"  Loaded O&G reserves from {og_reserves_path}")
            return

    # Fallback defaults if no reserve data found
    print(f"  Warning: No O&G reserve data found for {ticker_symbol}, using estimates")
    total_revenue = _get_value(income_stmt, ["Total Revenue", "Operating Revenue"])
    production_est = total_revenue / 50.0 / 365.0 if total_revenue > 0 else 0.0
    market_data["proven_reserves"] = 0.0
    market_data["production_boe_day"] = production_est
    market_data["oil_pct"] = 0.5
    market_data["lifting_cost"] = 10.0
    market_data["finding_cost"] = 15.0


def extract_time_series(ticker_obj):
    """Extract 4-year time series from financial statements."""

    income_stmt = ticker_obj.income_stmt
    balance_sheet = ticker_obj.balance_sheet
    cash_flow = ticker_obj.cash_flow

    if income_stmt.empty or balance_sheet.empty or cash_flow.empty:
        raise ValueError("Financial data not available")

    # Income statement time series
    ebit = _get_series(income_stmt, ["EBIT", "Operating Income", "Operating Income Loss"])
    net_income = _get_series(income_stmt, ["Net Income", "Net Income Common Stockholders"])

    # Cash flow statement time series
    capex = [abs(x) for x in _get_series(cash_flow, ["Capital Expenditure", "Capital Expenditures"])]
    depreciation = [abs(x) for x in _get_series(cash_flow, [
        "Depreciation And Amortization",
        "Depreciation",
        "Reconciled Depreciation"
    ])]
    dividend_payout = [abs(x) for x in _get_series(cash_flow, [
        "Cash Dividends Paid",
        "Common Stock Dividend Paid"
    ])]

    # Balance sheet time series
    current_assets = _get_series(balance_sheet, ["Current Assets"])
    current_liabilities = _get_series(balance_sheet, ["Current Liabilities"])
    book_value_equity = _get_series(balance_sheet, [
        "Stockholders Equity",
        "Total Equity Gross Minority Interest",
        "Common Stock Equity"
    ])

    total_debt = _get_series(balance_sheet, ["Total Debt"])

    # Calculate invested capital for each period
    invested_capital = [bve + td for bve, td in zip(book_value_equity, total_debt)]

    time_series = {
        "ebit": ebit,
        "net_income": net_income,
        "capex": capex,
        "depreciation": depreciation,
        "current_assets": current_assets,
        "current_liabilities": current_liabilities,
        "book_value_equity": book_value_equity,
        "dividend_payout": dividend_payout,
        "invested_capital": invested_capital,
    }

    return time_series


def main():
    parser = argparse.ArgumentParser(description="Fetch 4-year time series for probabilistic DCF")
    parser.add_argument("--ticker", required=True, help="Ticker symbol (e.g., AAPL)")
    parser.add_argument("--output", default="/tmp", help="Output directory for JSON files")
    args = parser.parse_args()

    ticker_symbol = args.ticker.upper()
    output_dir = Path(args.output)

    # Add small random delay to reduce parallel request contention (0-500ms)
    initial_delay = random.uniform(0, 0.5)
    time.sleep(initial_delay)

    print(f"Fetching 4-year time series for {ticker_symbol}...")

    try:
        # Fetch ticker data with retry logic for cookie database conflicts
        ticker = retry_with_backoff(lambda: yf.Ticker(ticker_symbol))

        # Extract data (also wrap in retry for property access)
        market_data = retry_with_backoff(lambda: fetch_market_data(ticker, ticker_symbol))
        time_series = retry_with_backoff(lambda: extract_time_series(ticker))

        # Validate
        if market_data["shares_outstanding"] == 0.0:
            raise ValueError("Shares outstanding is zero or not available")
        if market_data["price"] == 0.0:
            raise ValueError("Current price is zero or not available")

        # Currency normalization: convert financialCurrency fields (sector fields
        # in market_data + all time-series monetary lists) onto the trading basis,
        # so fcfe_mean/fcff_mean per share are comparable to the trading price.
        # No-op when financialCurrency == trading currency (most tickers).
        trading_ccy = market_data.get("currency", "USD")
        financial_ccy = market_data.get("financial_currency", trading_ccy)
        fx = fx_rate(financial_ccy, trading_ccy)
        fx_ok = fx is not None
        if not fx_ok:
            print(
                f"WARN: FX {financial_ccy}->{trading_ccy} unavailable for {ticker_symbol}; "
                f"financial fields left unconverted",
                file=sys.stderr,
            )
            fx = 1.0
        convert_financial_fields(market_data, _MARKET_FINANCIAL_KEYS, fx)
        convert_financial_fields(time_series, _TS_FINANCIAL_KEYS, fx)
        market_data["fx_to_trading"] = fx
        market_data["fx_ok"] = fx_ok

        print(f"  Model type: {market_data['model_type']}")

        # Wrap time series in required format
        output_data = {
            "time_series": time_series
        }

        # Write JSON files
        output_dir.mkdir(parents=True, exist_ok=True)
        market_data_file = output_dir / f"dcf_prob_market_data_{ticker_symbol}.json"
        time_series_file = output_dir / f"dcf_prob_time_series_{ticker_symbol}.json"

        with open(market_data_file, "w") as f:
            json.dump(market_data, f, indent=2)
        print(f"Market data written to: {market_data_file}")

        with open(time_series_file, "w") as f:
            json.dump(output_data, f, indent=2)
        print(f"Time series written to: {time_series_file}")

        print("Data fetch successful!")

    except Exception as e:
        print(f"Error fetching data: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
