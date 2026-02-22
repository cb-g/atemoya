#!/usr/bin/env python3
"""
Fetch financial data for DCF valuation using yfinance.
Outputs market_data and financial_data JSON files.
"""

import argparse
import json
import os
import sys
import time
import random
from pathlib import Path

# Add project root to path for lib imports
sys.path.insert(0, str(Path(__file__).parents[3]))

import yfinance as yf

from lib.python.retry import retry_with_backoff


def fetch_market_data(ticker_obj, ticker_symbol):
    """Extract market data from yfinance ticker."""
    info = ticker_obj.info

    # Extract basic market data
    market_data = {
        "ticker": ticker_symbol,
        "price": info.get("currentPrice", info.get("regularMarketPrice", 0.0)),
        "mve": info.get("marketCap", 0.0),
        "mvb": info.get("totalDebt", 0.0),
        "shares_outstanding": info.get("sharesOutstanding", 0.0),
        "currency": info.get("currency", "USD"),
        "country": info.get("country", "USA"),
        "industry": info.get("industry", "Unknown"),
    }

    return market_data


def fetch_financial_data(ticker_obj):
    """Extract financial statement data from yfinance ticker."""

    # Get financial statements
    income_stmt = ticker_obj.income_stmt
    balance_sheet = ticker_obj.balance_sheet
    cash_flow = ticker_obj.cash_flow
    info = ticker_obj.info

    # Use most recent annual data (column 0)
    if income_stmt.empty or balance_sheet.empty or cash_flow.empty:
        raise ValueError("Financial data not available for this ticker")

    # Helper to safely get value with fallback
    def get_value(df, keys, default=0.0):
        """Try multiple keys in order, return first match or default."""
        if isinstance(keys, str):
            keys = [keys]
        for key in keys:
            if key in df.index:
                val = df.loc[key].iloc[0] if not df.loc[key].empty else default
                return float(val) if val == val else default  # Check for NaN
        return default

    # Extract EBIT (with multiple fallback strategies)
    ebit_keys = ["EBIT", "Operating Income", "Operating Income Loss"]
    ebit = get_value(income_stmt, ebit_keys)

    # If EBIT not found, reconstruct: EBIT = EBT + Interest Expense
    if ebit == 0.0:
        ebt = get_value(income_stmt, ["Pretax Income", "Income Before Tax"])
        interest_exp = get_value(income_stmt, ["Interest Expense"])
        if ebt != 0.0:
            ebit = ebt + abs(interest_exp)  # Interest expense is usually negative

    # Check if this is a bank (financial services)
    # Includes commercial banks, investment banks, and credit card companies
    industry = info.get("industry", "").lower()
    is_bank = any(term in industry for term in [
        "bank", "regional banks", "diversified banks", "money center",
        "investment banking", "capital markets",  # Investment banks (GS, MS)
        "credit services",  # Credit card companies (COF, DFS)
    ])

    # Check if this is an insurance company
    is_insurance = any(term in industry for term in [
        "insurance", "property & casualty", "life insurance", "health insurance",
        "reinsurance", "insurance brokers", "insurance—diversified",
        "insurance—property & casualty", "insurance—life",
    ])

    # Check if this is an Oil & Gas E&P company
    is_oil_gas = any(term in industry for term in [
        "oil & gas e&p", "oil & gas exploration", "oil & gas production",
        "oil & gas integrated", "oil & gas midstream", "oil & gas drilling",
        "oil & gas refining", "oil & gas equipment",
    ])

    # Bank-specific fields (default to 0 for non-banks)
    net_interest_income = 0.0
    non_interest_income = 0.0
    non_interest_expense = 0.0
    provision_for_loan_losses = 0.0
    tangible_book_value = 0.0
    total_loans = 0.0
    total_deposits = 0.0
    tier1_capital_ratio = 0.0
    npl_ratio = 0.0

    # Insurance-specific fields (default to 0 for non-insurers)
    premiums_earned = 0.0
    losses_incurred = 0.0
    underwriting_expenses = 0.0
    investment_income = 0.0
    float_amount = 0.0
    loss_ratio = 0.0
    expense_ratio = 0.0
    combined_ratio = 0.0

    # Oil & Gas E&P specific fields (default to 0 for non-O&G)
    proven_reserves = 0.0  # MMBOE - typically from SEC filings, not yfinance
    production_boe_day = 0.0  # BOE/day - typically from SEC filings
    ebitdax = 0.0  # EBITDA + Exploration expense
    exploration_expense = 0.0
    dd_and_a = 0.0  # Depletion, depreciation, amortization
    finding_cost = 0.0  # F&D cost per BOE - from company reports
    lifting_cost = 0.0  # Operating cost per BOE - from company reports
    oil_pct = 0.5  # Default 50/50 oil vs gas

    # Extract book value early (needed for bank TBV calculation)
    book_value_equity_early = get_value(balance_sheet, [
        "Stockholders Equity",
        "Total Equity Gross Minority Interest",
        "Common Stock Equity"
    ])

    # For banks, fetch additional data
    if is_bank:
        # Net Interest Income (Interest Income - Interest Expense)
        interest_income = get_value(income_stmt, ["Interest Income", "Total Interest Income"])
        interest_exp_for_nii = get_value(income_stmt, ["Interest Expense"])
        net_interest_income = get_value(income_stmt, ["Net Interest Income"])
        if net_interest_income == 0.0 and interest_income != 0.0:
            net_interest_income = interest_income - abs(interest_exp_for_nii)

        # Non-interest income (fees, trading, etc.)
        non_interest_income = get_value(income_stmt, [
            "Non Interest Income",
            "Other Non Interest Income",
            "Total Non Interest Income"
        ])

        # Non-interest expense (operating expenses)
        non_interest_expense = get_value(income_stmt, [
            "Non Interest Expense",
            "Total Non Interest Expense"
        ])

        # Provision for loan losses (credit cost)
        provision_for_loan_losses = abs(get_value(income_stmt, [
            "Provision For Loan Losses",
            "Provision For Credit Losses"
        ]))

        # Total loans
        total_loans = get_value(balance_sheet, [
            "Net Loan",
            "Total Net Loans",
            "Gross Loan"
        ])

        # Total deposits
        total_deposits = get_value(balance_sheet, [
            "Total Deposits",
            "Deposits"
        ])

        # Tangible Book Value = Book Value - Goodwill - Intangibles
        goodwill = get_value(balance_sheet, ["Goodwill"])
        intangibles = get_value(balance_sheet, ["Other Intangible Assets", "Intangible Assets"])
        tangible_book_value = book_value_equity_early - goodwill - intangibles

        # PPNR proxy for EBIT (if EBIT still 0)
        if ebit == 0.0:
            ebit = net_interest_income + non_interest_income - non_interest_expense - provision_for_loan_losses

    # For insurance companies, fetch additional data
    if is_insurance:
        # Net premiums earned - use Total Revenue for insurers (mostly premiums)
        premiums_earned = get_value(income_stmt, [
            "Total Revenue",
            "Operating Revenue",
            "Net Premiums Earned",
            "Total Premiums Earned",
        ])

        # Losses incurred (claims and loss adjustment expenses)
        # yfinance uses "Loss Adjustment Expense" or "Net Policyholder Benefits And Claims"
        losses_incurred = abs(get_value(income_stmt, [
            "Loss Adjustment Expense",
            "Net Policyholder Benefits And Claims",
            "Policyholder Benefits Gross",
            "Losses Benefits And Adjustments",
            "Benefits Cost And Expense",
        ]))

        # Total operating expenses
        total_expenses = abs(get_value(income_stmt, ["Total Expenses"]))

        # Underwriting expenses = Total Expenses - Losses - Interest Expense
        interest_exp_ins = abs(get_value(income_stmt, ["Interest Expense"]))
        if total_expenses > 0.0 and losses_incurred > 0.0:
            underwriting_expenses = total_expenses - losses_incurred - interest_exp_ins
        else:
            underwriting_expenses = abs(get_value(income_stmt, [
                "Selling General And Administration",
                "Operating Expense",
                "General And Administrative Expense",
            ]))

        # Investment income - try Other Income or calculate from investments
        investment_income = get_value(income_stmt, [
            "Other Income Expense",
            "Net Investment Income",
            "Investment Income",
        ])
        # If still 0, estimate from investment assets
        if investment_income <= 0.0:
            investments = get_value(balance_sheet, ["Investments And Advances"])
            if investments > 0.0:
                # Assume ~4% yield on investment portfolio
                investment_income = investments * 0.04

        # Float = Total Liabilities - Debt (insurance liabilities are float)
        total_liabilities = get_value(balance_sheet, ["Total Liabilities Net Minority Interest"])
        total_debt = get_value(balance_sheet, ["Total Debt", "Long Term Debt"])
        if total_liabilities > 0.0:
            float_amount = total_liabilities - total_debt
        else:
            float_amount = 0.0

        # Calculate ratios
        if premiums_earned > 0.0:
            loss_ratio = losses_incurred / premiums_earned
            expense_ratio = underwriting_expenses / premiums_earned
            combined_ratio = loss_ratio + expense_ratio

        # Use EBIT proxy for insurance if needed
        if ebit == 0.0:
            # Underwriting income + investment income approximation
            underwriting_income = premiums_earned - losses_incurred - underwriting_expenses
            ebit = underwriting_income + investment_income

    # For Oil & Gas E&P companies, extract available data
    if is_oil_gas:
        # DD&A (Depletion, Depreciation & Amortization) - use depreciation from cash flow
        dd_and_a = abs(get_value(cash_flow, [
            "Depreciation And Amortization",
            "Depreciation",
            "Depletion",
            "Depreciation Amortization Depletion",
        ]))

        # Exploration expense (dry hole costs, etc.)
        exploration_expense = abs(get_value(income_stmt, [
            "Exploration Expense",
            "Exploration Development And Mineral Property Lease Expense",
        ]))

        # EBITDAX = EBITDA + Exploration expense
        # First get EBITDA from info or calculate
        ebitda = info.get("ebitda", 0.0)
        if ebitda == 0.0:
            # Calculate: EBIT + Depreciation
            ebitda = ebit + dd_and_a
        ebitdax = ebitda + exploration_expense

        # Reserve data isn't available in yfinance - would need SEC filings
        # These are typically provided in 10-K filings (supplemental oil & gas info)
        # For now, we'll look for any reserve-related metrics in info
        # Most O&G companies report reserves in their 10-K

        # Estimate production from revenue and commodity prices if available
        # This is a rough proxy - actual production comes from 10-K
        total_revenue = get_value(income_stmt, ["Total Revenue", "Operating Revenue"])
        if total_revenue > 0.0:
            # Very rough estimate assuming $50/BOE average realized price
            # This should be replaced with actual 10-K data
            estimated_annual_boe = total_revenue / 50.0
            production_boe_day = estimated_annual_boe / 365.0

        # Note: The following would typically come from 10-K filings:
        # - proven_reserves (MMBOE)
        # - finding_cost ($/BOE)
        # - lifting_cost ($/BOE)
        # - oil_pct (% oil vs gas)

    # Extract other income statement items
    net_income = get_value(income_stmt, ["Net Income", "Net Income Common Stockholders"])
    interest_expense = abs(get_value(income_stmt, ["Interest Expense"]))  # Make positive
    taxes = abs(get_value(income_stmt, ["Tax Provision"]))  # Make positive

    # Extract cash flow statement items
    capex = abs(get_value(cash_flow, ["Capital Expenditure", "Capital Expenditures"]))  # Make positive
    depreciation = abs(get_value(cash_flow, [
        "Depreciation And Amortization",
        "Depreciation",
        "Reconciled Depreciation"
    ]))

    # Calculate change in working capital
    # ΔWC = Δ(Current Assets - Current Liabilities)
    current_assets = get_value(balance_sheet, ["Current Assets"])
    current_liabilities = get_value(balance_sheet, ["Current Liabilities"])

    # Get prior year balance sheet (column 1 if available)
    if balance_sheet.shape[1] >= 2:
        current_assets_prior = get_value(balance_sheet.iloc[:, [1]], ["Current Assets"])
        current_liabilities_prior = get_value(balance_sheet.iloc[:, [1]], ["Current Liabilities"])
        delta_wc = (current_assets - current_liabilities) - \
                   (current_assets_prior - current_liabilities_prior)
    else:
        # No prior year data, use 0
        delta_wc = 0.0

    # Extract balance sheet items (reuse early extraction)
    book_value_equity = book_value_equity_early

    total_debt = get_value(balance_sheet, ["Total Debt"])
    invested_capital = book_value_equity + total_debt

    financial_data = {
        "ebit": ebit,
        "net_income": net_income,
        "interest_expense": interest_expense,
        "taxes": taxes,
        "capex": capex,
        "depreciation": depreciation,
        "delta_wc": delta_wc,
        "book_value_equity": book_value_equity,
        "invested_capital": invested_capital,
        "is_bank": is_bank,
        # Bank-specific fields (populated only for banks, 0.0 otherwise)
        "net_interest_income": net_interest_income,
        "non_interest_income": non_interest_income,
        "non_interest_expense": non_interest_expense,
        "provision_for_loan_losses": provision_for_loan_losses,
        "tangible_book_value": tangible_book_value,
        "total_loans": total_loans,
        "total_deposits": total_deposits,
        "tier1_capital_ratio": tier1_capital_ratio,  # Would need separate data source
        "npl_ratio": npl_ratio,  # Would need separate data source
        # Insurance-specific fields (populated only for insurers, 0.0 otherwise)
        "is_insurance": is_insurance,
        "premiums_earned": premiums_earned,
        "losses_incurred": losses_incurred,
        "underwriting_expenses": underwriting_expenses,
        "investment_income": investment_income,
        "float_amount": float_amount,
        "loss_ratio": loss_ratio,
        "expense_ratio": expense_ratio,
        "combined_ratio": combined_ratio,
        # Oil & Gas E&P specific fields (populated only for O&G, 0.0 otherwise)
        "is_oil_gas": is_oil_gas,
        "proven_reserves": proven_reserves,
        "production_boe_day": production_boe_day,
        "ebitdax": ebitdax,
        "exploration_expense": exploration_expense,
        "dd_and_a": dd_and_a,
        "finding_cost": finding_cost,
        "lifting_cost": lifting_cost,
        "oil_pct": oil_pct,
    }

    return financial_data


def fetch_og_reserves_from_sec(ticker: str) -> dict:
    """
    Fetch O&G reserve data from SEC 10-K filings using edgartools.
    Returns dict with reserve data or empty dict if unavailable.
    Uses the improved multi-strategy parser from fetch_og_reserves.py.
    """
    try:
        from edgar import Company, set_identity
        from fetch_og_reserves import parse_reserve_table, parse_production_data, parse_cost_data

        edgar_id = os.environ.get("SEC_EDGAR_IDENTITY", "")
        if not edgar_id:
            return {}
        set_identity(edgar_id)
        company = Company(ticker)
        filings = company.get_filings(form="10-K")

        if not filings:
            return {}

        filing = filings[0].obj()

        # Extract text from multiple sections - combine for comprehensive parsing
        text_parts = []

        # Try Item 1 - Business (CVX-style narrative)
        if hasattr(filing, "__getitem__"):
            try:
                item1 = filing["Item 1"]
                if item1:
                    text_parts.append(str(item1))
            except Exception:
                pass

        # Try Item 2 - Properties (XOM-style)
        if hasattr(filing, "__getitem__"):
            try:
                item2 = filing["Item 2"]
                if item2:
                    text_parts.append(str(item2))
            except Exception:
                pass

        # Try Item 8 - Financial Statements (COP/OXY-style tables)
        if hasattr(filing, "__getitem__"):
            try:
                item8 = filing["Item 8"]
                if item8:
                    text_parts.append(str(item8))
            except Exception:
                pass

        text = "\n\n".join(text_parts)

        if not text:
            return {}

        # Use the improved multi-strategy parsers
        reserves = parse_reserve_table(text)
        production = parse_production_data(text)
        costs = parse_cost_data(text)

        return {**reserves, **production, **costs}

    except ImportError as e:
        # edgartools or fetch_og_reserves not available
        print(f"Warning: Import error for SEC data: {e}", file=sys.stderr)
        return {}
    except Exception as e:
        print(f"Warning: Could not fetch SEC reserve data: {e}", file=sys.stderr)
        return {}


def main():
    parser = argparse.ArgumentParser(description="Fetch financial data for DCF valuation")
    parser.add_argument("--ticker", required=True, help="Ticker symbol (e.g., AAPL)")
    parser.add_argument("--output", default="/tmp", help="Output directory for JSON files")
    parser.add_argument("--fetch-sec-reserves", action="store_true",
                       help="Fetch O&G reserves from SEC 10-K filings (requires edgartools)")
    args = parser.parse_args()

    ticker_symbol = args.ticker.upper()
    output_dir = Path(args.output)

    # Add small random delay to reduce parallel request contention (0-500ms)
    initial_delay = random.uniform(0, 0.5)
    time.sleep(initial_delay)

    print(f"Fetching data for {ticker_symbol}...")

    try:
        # Fetch ticker data with retry logic for cookie database conflicts
        ticker = retry_with_backoff(lambda: yf.Ticker(ticker_symbol))

        # Extract data (also wrap in retry for property access)
        market_data = retry_with_backoff(lambda: fetch_market_data(ticker, ticker_symbol))
        financial_data = retry_with_backoff(lambda: fetch_financial_data(ticker))

        # Validate critical fields
        if market_data["shares_outstanding"] == 0.0:
            raise ValueError("Shares outstanding is zero or not available")
        if market_data["price"] == 0.0:
            raise ValueError("Current price is zero or not available")

        # For O&G companies, optionally fetch reserve data from SEC filings
        if financial_data.get("is_oil_gas") and args.fetch_sec_reserves:
            print(f"Fetching O&G reserves from SEC 10-K filings...")
            sec_reserves = fetch_og_reserves_from_sec(ticker_symbol)
            if sec_reserves:
                print(f"Found SEC reserve data: {sec_reserves}")
                # Update financial_data with SEC reserve data
                if sec_reserves.get('proved_reserves_boe_mmboe'):
                    financial_data['proven_reserves'] = sec_reserves['proved_reserves_boe_mmboe']
                if sec_reserves.get('production_boe_day'):
                    financial_data['production_boe_day'] = sec_reserves['production_boe_day']
                if sec_reserves.get('oil_percentage'):
                    financial_data['oil_pct'] = sec_reserves['oil_percentage']
                if sec_reserves.get('lifting_cost_per_boe'):
                    financial_data['lifting_cost'] = sec_reserves['lifting_cost_per_boe']
                if sec_reserves.get('finding_cost_per_boe'):
                    financial_data['finding_cost'] = sec_reserves['finding_cost_per_boe']

        # For O&G companies, selectively fall back to static data for missing fields
        if financial_data.get("is_oil_gas"):
            needs_fallback = any(
                not financial_data.get(f)
                for f in ("proven_reserves", "production_boe_day", "lifting_cost", "finding_cost", "oil_pct")
            )
            if needs_fallback:
                static_file = Path(args.output).parent / "data" / "og_reserves.json"
                if not static_file.exists():
                    static_file = Path(__file__).resolve().parent.parent / "data" / "og_reserves.json"
                if static_file.exists():
                    try:
                        with open(static_file) as f:
                            og_static = json.load(f)
                        company_data = og_static.get("companies", {}).get(ticker_symbol)
                        if company_data and company_data.get("proven_reserves_mmboe", 0) > 0:
                            field_map = {
                                'proven_reserves': 'proven_reserves_mmboe',
                                'production_boe_day': 'production_boe_day',
                                'oil_pct': 'oil_pct',
                                'lifting_cost': 'lifting_cost',
                                'finding_cost': 'finding_cost',
                            }
                            filled = []
                            for fin_key, static_key in field_map.items():
                                if not financial_data.get(fin_key):
                                    financial_data[fin_key] = company_data[static_key]
                                    filled.append(fin_key)
                            if filled:
                                print(f"Filled missing O&G fields from static file: {', '.join(filled)}")
                    except Exception as e:
                        print(f"Warning: Could not load static O&G data: {e}", file=sys.stderr)

        # Write JSON files
        market_data_file = output_dir / f"dcf_market_data_{ticker_symbol}.json"
        financial_data_file = output_dir / f"dcf_financial_data_{ticker_symbol}.json"

        with open(market_data_file, "w") as f:
            json.dump(market_data, f, indent=2)
        print(f"Market data written to: {market_data_file}")

        with open(financial_data_file, "w") as f:
            json.dump(financial_data, f, indent=2)
        print(f"Financial data written to: {financial_data_file}")

        print("Data fetch successful!")

    except Exception as e:
        print(f"Error fetching data: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
