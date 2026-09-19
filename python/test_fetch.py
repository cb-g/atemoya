"""The vendor-side mappings that are logic rather than a lookup: which row supplied a
value, the composed fields per reference/field_definitions.json with their components,
and that a missing debt row never becomes a zero."""

from __future__ import annotations

import math
from datetime import date

import fetch

DEFS = fetch.DEFINITIONS


def test_first_present_skips_nan_and_records_the_label() -> None:
    rows = {"A": math.nan, "B": 7.0, "C": 9.0}
    assert fetch._first_present(rows, ("A", "B", "C")) == (7.0, "B")  # pyright: ignore[reportPrivateUsage]
    assert fetch._first_present(rows, ("A",)) == (None, None)  # pyright: ignore[reportPrivateUsage]


def test_total_debt_with_leases_in_the_vendor_total_is_not_used_as_is() -> None:
    # Microsoft FY2026 as the vendor shows it: Total Debt 56.826 = 31.067 + 9.227 + 16.532,
    # and the 16.532 "capital lease" row is the operating lease liability.
    rows = {"Total Debt": 56.826, "Long Term Debt": 31.067, "Current Debt": 9.227, "Long Term Capital Lease Obligation": 16.532}
    value, source, parts = fetch._total_debt(rows, DEFS)  # pyright: ignore[reportPrivateUsage]
    assert value is not None and math.isclose(value, 40.294)
    assert source == "Long Term Debt + Current Debt"
    assert parts == [("long_term_debt", 31.067, "Long Term Debt"), ("current_debt", 9.227, "Current Debt")]
    assert "Total Debt" in DEFS.total_debt.vendor.not_used and "Long Term Capital Lease Obligation" in DEFS.total_debt.vendor.not_used


def test_total_debt_current_row_or_its_components_never_a_zero() -> None:
    # Current Debt already holds commercial paper: it is not added twice.
    both = {"Long Term Debt": 78.328, "Current Debt": 20.329, "Commercial Paper": 7.979, "Other Current Borrowings": 12.35}
    value, source, parts = fetch._total_debt(both, DEFS)  # pyright: ignore[reportPrivateUsage]
    assert value is not None and math.isclose(value, 98.657) and source == "Long Term Debt + Current Debt"
    assert parts is not None and [n for n, _, _ in parts] == ["long_term_debt", "current_debt"]
    components_only = {"Long Term Debt": 7.0, "Current Debt": math.nan, "Commercial Paper": 1.5, "Other Current Borrowings": 0.25}
    value, source, parts = fetch._total_debt(components_only, DEFS)  # pyright: ignore[reportPrivateUsage]
    assert value is not None and math.isclose(value, 8.75)
    assert source == "Long Term Debt + Commercial Paper + Other Current Borrowings"
    long_term_only = {"Long Term Debt": 46.547}
    assert fetch._total_debt(long_term_only, DEFS)[:2] == (46.547, "Long Term Debt")  # pyright: ignore[reportPrivateUsage]
    assert fetch._total_debt({"Total Debt": 10.0, "Current Debt": 2.0}, DEFS) == (None, None, None)  # pyright: ignore[reportPrivateUsage]
    assert fetch._total_debt({}, DEFS) == (None, None, None)  # pyright: ignore[reportPrivateUsage]


def test_cash_is_equivalents_plus_short_term_investments_with_components() -> None:
    # Apple FY2025: 35.934 + 18.763 = the vendor's own 54.697 subtotal, which is not read.
    rows = {"Cash And Cash Equivalents": 35.934, "Other Short Term Investments": 18.763, "Cash Cash Equivalents And Short Term Investments": 54.697}
    value, row, parts = fetch._cash(rows, DEFS)  # pyright: ignore[reportPrivateUsage]
    assert value is not None and math.isclose(value, 54.697)
    assert row == "Cash And Cash Equivalents + Other Short Term Investments"
    assert parts == [("cash_equivalents", 35.934, "Cash And Cash Equivalents"), ("short_term_investments", 18.763, "Other Short Term Investments")]
    no_investments = {"Cash And Cash Equivalents": 10.681, "Cash Cash Equivalents And Short Term Investments": 10.681}
    assert fetch._cash(no_investments, DEFS) == (10.681, "Cash And Cash Equivalents", [("cash_equivalents", 10.681, "Cash And Cash Equivalents")])  # pyright: ignore[reportPrivateUsage]
    assert fetch._cash({"Cash Cash Equivalents And Short Term Investments": 1.0}, DEFS) == (None, None, None)  # pyright: ignore[reportPrivateUsage]


def test_delta_nwc_is_the_cash_flow_line_with_the_sign_flipped() -> None:
    value, row, parts = fetch._delta_nwc({"Change In Working Capital": -7.208}, DEFS)  # pyright: ignore[reportPrivateUsage]
    assert value is not None and math.isclose(value, 7.208) and row == "Change In Working Capital"
    assert parts is not None and parts[0][0] == "change_in_working_capital" and math.isclose(parts[0][1], 7.208)
    assert fetch._delta_nwc({}, DEFS) == (None, None, None)  # pyright: ignore[reportPrivateUsage]


def test_ebit_recipe_operating_income_else_pretax_plus_interest_less_nonoperating() -> None:
    assert fetch._ebit({"Operating Income": 25.596, "Pretax Income": 32.581, "Interest Expense": 0.971}, DEFS) == (  # pyright: ignore[reportPrivateUsage]
        25.596, "Operating Income", "operating_income", [("operating_income", 25.596, "Operating Income")])
    rows = {"Pretax Income": 32.581, "Interest Expense": 0.971, "Interest Income": 1.056, "Other Non Operating Income Expenses": 1.0, "Earnings From Equity Interest": 3.0}
    value, row, recipe, parts = fetch._ebit(rows, DEFS)  # pyright: ignore[reportPrivateUsage]
    assert value is not None and math.isclose(value, 32.581 + 0.971 - 1.056 - 1.0 - 3.0)
    assert row == "Pretax Income + Interest Expense - Interest Income - Other Non Operating Income Expenses - Earnings From Equity Interest"
    assert recipe == "pretax_plus_interest_less_nonoperating" and recipe in DEFS.ebit.recipes
    assert parts == [("pretax_income", 32.581, "Pretax Income"), ("interest_expense", 0.971, "Interest Expense"), ("interest_income", -1.056, "Interest Income"),
                     ("other_nonoperating", -1.0, "Other Non Operating Income Expenses"), ("equity_method", -3.0, "Earnings From Equity Interest")]
    for absent in ("Interest Income", "Other Non Operating Income Expenses", "Earnings From Equity Interest"):
        without = {k: v for k, v in rows.items() if k != absent}
        value, _, _, parts = fetch._ebit(without, DEFS)  # pyright: ignore[reportPrivateUsage]
        assert value is not None and parts is not None and math.isclose(value, sum(v for _, v, _ in parts)) and len(parts) == 4
    assert fetch._ebit({"Pretax Income": 32.581}, DEFS) == (None, None, None, None)  # pyright: ignore[reportPrivateUsage]
    assert len(DEFS.ebit.recipes) <= 1 + DEFS.refinement_policy.max_refinements_per_field


def test_depreciation_falls_back_across_rows_and_statements() -> None:
    end = date(2025, 12, 31)
    depletion_only = fetch.CashFlowStatement.model_validate(
        {"period_end": end, **fetch._cashflow_values({"Depreciation Amortization Depletion": 25.99, "Capital Expenditure": -1.0, "Change In Working Capital": 0.0})}  # pyright: ignore[reportPrivateUsage]
    )
    assert (depletion_only.depreciation_amortization, depletion_only.depreciation_amortization_row) == (
        25.99,
        "Depreciation Amortization Depletion",
    )
    income = fetch.IncomeStatement.model_validate(
        {"period_end": end, **fetch._income_values({"Reconciled Depreciation": 3.0})}  # pyright: ignore[reportPrivateUsage]
    )
    none_in_cashflow = fetch.CashFlowStatement.model_validate(
        {"period_end": end, **fetch._cashflow_values({"Capital Expenditure": -1.0})}  # pyright: ignore[reportPrivateUsage]
    )
    assert fetch._depreciation(income, none_in_cashflow) == (3.0, "Reconciled Depreciation")  # pyright: ignore[reportPrivateUsage]
    assert fetch._depreciation(income, depletion_only)[1] == "Depreciation Amortization Depletion"  # pyright: ignore[reportPrivateUsage]
    assert fetch._depreciation(None, None) == (None, None)  # pyright: ignore[reportPrivateUsage]


def test_period_carries_the_labels_and_compositions() -> None:
    end = date(2025, 12, 31)
    balance = fetch.BalanceSheet.model_validate(
        {"period_end": end, **fetch._balance_values({"Long Term Debt": 27.93, "Current Debt": 9.3, "Stockholders Equity": 259.39, "Cash And Cash Equivalents": 1.0, "Total Debt": 43.5})}  # pyright: ignore[reportPrivateUsage]
    )
    income = fetch.IncomeStatement.model_validate({"period_end": end, **fetch._income_values({"Pretax Income": 41.268, "Interest Expense": 0.603})})  # pyright: ignore[reportPrivateUsage]
    period = fetch._period(end, income, None, balance)  # pyright: ignore[reportPrivateUsage]
    assert period.total_debt is not None and math.isclose(period.total_debt, 37.23)
    assert period.total_debt_source == "Long Term Debt + Current Debt"
    assert period.total_debt_composition is not None and period.total_debt_composition.definition == DEFS.total_debt.name
    assert [(c.name, c.value, c.row) for c in period.total_debt_composition.components] == [("long_term_debt", 27.93, "Long Term Debt"), ("current_debt", 9.3, "Current Debt")]
    assert period.cash == 1.0 and period.cash_row == "Cash And Cash Equivalents"
    assert period.cash_composition is not None and period.cash_composition.definition == DEFS.cash.name
    assert period.ebit is not None and math.isclose(period.ebit, 41.871) and period.ebit_recipe == "pretax_plus_interest_less_nonoperating"
    assert period.ebit_composition is not None and period.ebit_composition.definition == DEFS.ebit.name
    assert period.book_equity == 259.39
    assert period.depreciation_amortization is None and period.depreciation_amortization_row is None
    assert period.delta_nwc_composition is None
    assert not fetch._is_empty(period)  # pyright: ignore[reportPrivateUsage]
    assert fetch._is_empty(fetch._period(end, None, None, None))  # pyright: ignore[reportPrivateUsage]


def test_dividends_are_flipped_to_cash_paid_and_labelled() -> None:
    end = date(2025, 12, 31)
    cf = fetch.CashFlowStatement.model_validate(
        {"period_end": end, **fetch._cashflow_values({"Cash Dividends Paid": -16.62, "Capital Expenditure": -1.0, "Change In Working Capital": 0.0})}  # pyright: ignore[reportPrivateUsage]
    )
    assert (cf.dividends_paid, cf.dividends_paid_row) == (16.62, "Cash Dividends Paid")
    zero = fetch.CashFlowStatement.model_validate(
        {"period_end": end, **fetch._cashflow_values({"Common Stock Dividend Paid": 0.0, "Capital Expenditure": -1.0})}  # pyright: ignore[reportPrivateUsage]
    )
    assert (zero.dividends_paid, zero.dividends_paid_row) == (0.0, "Common Stock Dividend Paid")
    none = fetch.CashFlowStatement.model_validate(
        {"period_end": end, **fetch._cashflow_values({"Capital Expenditure": -1.0})}  # pyright: ignore[reportPrivateUsage]
    )
    assert (none.dividends_paid, none.dividends_paid_row) == (None, None)


def test_bank_balance_and_income_rows() -> None:
    end = date(2025, 12, 31)
    bs = fetch.BalanceSheet.model_validate(
        {"period_end": end, **fetch._balance_values({"Loans Receivable": 7172.16, "Stockholders Equity": 2491.84, "Total Debt": 1.0})}  # pyright: ignore[reportPrivateUsage]
    )
    assert (bs.net_loans, bs.net_loans_row) == (7172.16, "Loans Receivable")
    assert bs.total_debt is None  # Total Debt alone is not a definition
    inc = fetch.IncomeStatement.model_validate(
        {"period_end": end, **fetch._income_values({"Net Income": 57.05, "Net Interest Income": 95.44})}  # pyright: ignore[reportPrivateUsage]
    )
    assert inc.net_income == 57.05
    assert (inc.provision_for_credit_losses, inc.provision_for_credit_losses_row) == (None, None)


def test_minor_unit_price_is_converted_and_market_cap_kept() -> None:
    q = fetch.Quote.model_validate({"currency": "GBp", "financial_currency": "USD", "price": 12500.0, "market_cap": 1.9e11})
    assert (q.trading_currency, q.price_unit_divisor, q.major_price) == ("GBP", 100.0, 125.0)
    notes: list[str] = []
    f = fetch.quote_fields(q, notes)
    assert f["price"] == 125.0 and f["market_cap"] == 1.9e11 and f["trading_currency"] == "GBP"
    assert f["financial_currency"] == "USD" and f["currency"] is None  # no single basis: cross-currency
    assert f["price_unit_divisor"] == 100.0 and isinstance(f["price_unit"], fetch.boundary.PriceUnit)
    assert any("divided by 100" in n for n in notes)
    same = fetch.Quote.model_validate({"currency": "USD", "financial_currency": "USD", "price": 10.0, "market_cap": 5e3})
    g = fetch.quote_fields(same, [])
    assert (g["currency"], g["price"], g["price_unit_divisor"]) == ("USD", 10.0, 1.0)
