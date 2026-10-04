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
    assert "Total Debt" in DEFS.total_debt.vendor.not_used and "Long Term Capital Lease Obligation" in DEFS.total_debt.vendor.lease_long_term


def test_total_debt_from_the_combined_rows_when_the_vendor_shows_no_long_term_debt_row() -> None:
    lt, cur = "Long Term Debt And Capital Lease Obligation", "Current Debt And Capital Lease Obligation"
    lt_lease, cur_lease = "Long Term Capital Lease Obligation", "Current Capital Lease Obligation"
    debt = fetch._total_debt  # pyright: ignore[reportPrivateUsage]
    # combined less the lease row beside it, each side
    value, source, parts = debt({lt: 50.0, lt_lease: 8.0, cur: 6.0, cur_lease: 1.5, "Total Debt": 56.0}, DEFS)
    assert value is not None and math.isclose(value, 46.5)
    assert source == f"{lt} - {lt_lease} + {cur} - {cur_lease}"
    assert parts is not None and [n for n, _, _ in parts] == ["long_term_debt_and_leases", "long_term_leases", "current_debt_and_leases", "current_leases"]
    # a filer with leases and nothing else owes no debt: nil, read and not assumed
    value, _, _ = debt({lt: 7.0, lt_lease: 7.0, cur: 2.0, cur_lease: 2.0}, DEFS)
    assert value == 0.0
    # a plain current row is preferred to the combined one, and an absent current side adds nothing
    value, source, _ = debt({lt: 50.0, lt_lease: 8.0, "Current Debt": 3.0, cur: 4.5, cur_lease: 1.5}, DEFS)
    assert value is not None and math.isclose(value, 45.0) and source == f"{lt} - {lt_lease} + Current Debt"
    assert debt({lt: 50.0, lt_lease: 8.0}, DEFS)[0] == 42.0
    # no lease row anywhere: the combined rows whole, and the source says what they hold
    value, source, parts = debt({lt: 40.0, cur: 10.0}, DEFS)
    assert value == 50.0 and source is not None and source.count("includes lease liabilities; the vendor shows no lease row") == 2
    assert parts == [("long_term_debt_and_leases", 40.0, lt), ("current_debt_and_leases", 10.0, cur)]
    # what cannot be separated stays missing: a lease row on one side only, a combined row under its leases, no long-term side
    assert debt({lt: 40.0, cur: 10.0, cur_lease: 1.0}, DEFS) == (None, None, None)
    assert debt({lt: 40.0, lt_lease: 5.0, cur: 10.0}, DEFS) == (None, None, None)
    assert debt({lt: 4.0, lt_lease: 5.0}, DEFS) == (None, None, None)
    assert debt({cur: 10.0, cur_lease: 1.0, lt_lease: 3.0}, DEFS) == (None, None, None)
    # the plain row, where the vendor shows it, is read as before and the combined rows are not
    assert debt({"Long Term Debt": 30.0, lt: 38.0, lt_lease: 8.0}, DEFS)[:2] == (30.0, "Long Term Debt")


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


def test_vendor_operating_cash_flow_row_is_read_any_sign() -> None:
    """(76) The vendor's own subtotal, the row recorded; absent stays absent."""
    out = fetch._cashflow_values({"Operating Cash Flow": -497.0e6, "Capital Expenditure": -102.0e6})  # pyright: ignore[reportPrivateUsage]
    assert out["operating_cash_flow"] == -497.0e6 and out["operating_cash_flow_row"] == "Operating Cash Flow"
    out = fetch._cashflow_values({"Cash Flow From Continuing Operating Activities": 12.0e6})  # pyright: ignore[reportPrivateUsage]
    assert out["operating_cash_flow"] == 12.0e6
    assert fetch._cashflow_values({})["operating_cash_flow"] is None  # pyright: ignore[reportPrivateUsage]


def test_the_identity_guard_names_what_the_map_gives_now() -> None:
    table: dict[str, object] = {"0": {"cik_str": 2, "ticker": "TKR", "title": "OTHER CO"}, "1": {"cik_str": 7, "ticker": "SAME", "title": "SAME CO"}}
    assert fetch.identity_mismatch("SAME", table, "0000000007") is None
    assert fetch.identity_mismatch("TKR", table, None) is None
    moved = fetch.identity_mismatch("TKR", table, "0000000001")
    assert moved is not None and "gives CIK 0000000002 (OTHER CO) for TKR, the universe entry declared CIK 0000000001" in moved
    gone = fetch.identity_mismatch("GONE", table, "0000000001")
    assert gone is not None and "no longer lists GONE" in gone


def test_a_nil_debt_from_the_subtraction_needs_the_cash_flows_and_the_interest_to_agree() -> None:
    end = date(2025, 12, 31)
    lt, cur = "Long Term Debt And Capital Lease Obligation", "Current Debt And Capital Lease Obligation"
    leases_only = {lt: 80.0, "Long Term Capital Lease Obligation": 80.0, cur: 20.0, "Current Capital Lease Obligation": 20.0}

    def debt(balance_rows: dict[str, float], cashflow_rows: dict[str, float] | None, interest: float | None) -> float | None:
        balance = fetch.BalanceSheet.model_validate({"period_end": end, **fetch._balance_values(balance_rows)})  # pyright: ignore[reportPrivateUsage]
        income_rows = {"Pretax Income": 50.0} | ({} if interest is None else {"Interest Expense": interest})
        income = fetch.IncomeStatement.model_validate({"period_end": end, **fetch._income_values(income_rows)})  # pyright: ignore[reportPrivateUsage]
        cashflow = None if cashflow_rows is None else fetch.CashFlowStatement.model_validate({"period_end": end, **fetch._cashflow_values(cashflow_rows)})  # pyright: ignore[reportPrivateUsage]
        return fetch._period(end, income, cashflow, balance).total_debt  # pyright: ignore[reportPrivateUsage]

    quiet = {"Operating Cash Flow": 30.0, "Repayment Of Debt": 0.0}
    # nothing borrowed, nothing repaid, and the interest is what a hundred of leases explains: debt-free
    assert debt(leases_only, quiet, 6.0) == 0.0
    assert debt(leases_only, quiet, None) == 0.0
    # a borrowing or a repayment in the period says the vendor's rows miss the debt
    assert debt(leases_only, quiet | {"Issuance Of Debt": 12.0}, 6.0) is None
    assert debt(leases_only, quiet | {"Long Term Debt Payments": -3.0}, None) is None
    # more interest than the leases explain says the same
    assert debt(leases_only, quiet, 16.0) is None
    # no cash-flow statement for the period: nothing to check the nil against
    assert debt(leases_only, None, 6.0) is None
    # the guard is for the nil alone: a positive remainder is read whatever the flows say
    owing = leases_only | {lt: 130.0}
    assert debt(owing, quiet | {"Issuance Of Debt": 12.0}, 16.0) == 50.0
    # and it does not touch the plain rows or the rows taken whole
    assert debt({"Long Term Debt": 0.0}, quiet | {"Issuance Of Debt": 12.0}, 16.0) == 0.0
    assert debt({lt: 40.0, cur: 10.0}, quiet | {"Issuance Of Debt": 12.0}, 16.0) == 50.0
