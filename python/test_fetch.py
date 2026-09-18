"""The vendor-side mappings that are logic rather than a lookup: which row supplied a
value, and that a missing debt row never becomes a zero."""

from __future__ import annotations

import math
from datetime import date

import fetch


def test_first_present_skips_nan_and_records_the_label() -> None:
    rows = {"A": math.nan, "B": 7.0, "C": 9.0}
    assert fetch._first_present(rows, ("A", "B", "C")) == (7.0, "B")  # pyright: ignore[reportPrivateUsage]
    assert fetch._first_present(rows, ("A",)) == (None, None)  # pyright: ignore[reportPrivateUsage]


def test_total_debt_prefers_the_total_row() -> None:
    rows = {"Total Debt": 10.0, "Long Term Debt": 7.0, "Current Debt": 2.0}
    assert fetch._total_debt(rows) == (10.0, "Total Debt")  # pyright: ignore[reportPrivateUsage]


def test_total_debt_sums_components_only_when_both_present() -> None:
    both = {"Total Debt": math.nan, "Long Term Debt": 7.0, "Current Debt": 0.0}
    assert fetch._total_debt(both) == (7.0, "Long Term Debt + Current Debt")  # pyright: ignore[reportPrivateUsage]
    one = {"Long Term Debt": 7.0}
    assert fetch._total_debt(one) == (None, None)  # pyright: ignore[reportPrivateUsage]
    assert fetch._total_debt({}) == (None, None)  # pyright: ignore[reportPrivateUsage]


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


def test_period_carries_the_labels() -> None:
    end = date(2025, 12, 31)
    balance = fetch.BalanceSheet.model_validate(
        {"period_end": end, **fetch._balance_values({"Long Term Debt": 27.93, "Current Debt": 9.3, "Stockholders Equity": 259.39, "Cash Cash Equivalents And Short Term Investments": 1.0})}  # pyright: ignore[reportPrivateUsage]
    )
    period = fetch._period(end, None, None, balance)  # pyright: ignore[reportPrivateUsage]
    assert period.total_debt is not None and math.isclose(period.total_debt, 37.23)
    assert period.total_debt_source == "Long Term Debt + Current Debt"
    assert period.book_equity == 259.39
    assert period.depreciation_amortization is None and period.depreciation_amortization_row is None
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
    inc = fetch.IncomeStatement.model_validate(
        {"period_end": end, **fetch._income_values({"Net Income": 57.05, "Net Interest Income": 95.44})}  # pyright: ignore[reportPrivateUsage]
    )
    assert inc.net_income == 57.05
    assert (inc.provision_for_credit_losses, inc.provision_for_credit_losses_row) == (None, None)
