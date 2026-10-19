"""The trailing period on invented companyfacts: year-to-date plus prior year less prior
year-to-date per line, the balance at the quarter end, the anchor, the date cut, the
quarterly filing's own comparative preferred, a line missing a fact left null, and every
reason. Every figure is invented."""

from __future__ import annotations

from datetime import date

import boundary
import fetch_sec
import trailing

TAGS = fetch_sec.load_tags()
DEFS = fetch_sec.load_definitions()
PARAMS = fetch_sec.load_params()


def entry(start: str | None, end: str, val: float, form: str, fp: str, filed: str, accn: str | None = None) -> dict[str, object]:
    e: dict[str, object] = {"end": end, "val": val, "form": form, "fp": fp, "filed": filed, "fy": int(end[:4]), "accn": accn or f"a-{filed}"}
    if start is not None:
        e["start"] = start
    return e


def duration(tag: str, *, fy2024: float, ytd_q2_2024: float, ytd_q2_2025: float, q2_2025_three_months: float | None = None) -> tuple[str, list[dict[str, object]]]:
    """A line as a filer tags it: the FY2024 annual in the 10-K, the 2025 Q2 10-Q carrying
    its own year-to-date and the prior year's comparative, and (for an income line) the
    three-month figure beside it, which is not a year-to-date."""
    rows = [
        entry("2024-01-01", "2024-12-31", fy2024, "10-K", "FY", "2025-02-15", "k-2024"),
        entry("2024-01-01", "2024-06-30", ytd_q2_2024, "10-Q", "Q2", "2024-08-01", "q2-2024"),   # the filing of its own time
        entry("2024-01-01", "2024-06-30", ytd_q2_2024, "10-Q", "Q2", "2025-08-01", "q2-2025"),   # the comparative in the 2025 filing
        entry("2025-01-01", "2025-06-30", ytd_q2_2025, "10-Q", "Q2", "2025-08-01", "q2-2025"),
    ]
    if q2_2025_three_months is not None:
        rows.append(entry("2025-04-01", "2025-06-30", q2_2025_three_months, "10-Q", "Q2", "2025-08-01", "q2-2025"))
    return tag, rows


def instant(tag: str, *, at_2024: float, at_q2_2025: float) -> tuple[str, list[dict[str, object]]]:
    return tag, [
        entry(None, "2024-06-30", at_2024, "10-Q", "Q2", "2024-08-01", "q2-2024"),   # the 2024 filing's own balance sheet
        entry(None, "2024-12-31", at_2024, "10-K", "FY", "2025-02-15", "k-2024"),
        entry(None, "2024-12-31", at_2024, "10-Q", "Q2", "2025-08-01", "q2-2025"),
        entry(None, "2025-06-30", at_q2_2025, "10-Q", "Q2", "2025-08-01", "q2-2025"),
    ]


def facts(lines: list[tuple[str, list[dict[str, object]]]]) -> dict[str, object]:
    return {"facts": {"us-gaap": {tag: {"units": {"USD": rows}} for tag, rows in lines}}}


LINES = [
    duration("Revenues", fy2024=1000.0, ytd_q2_2024=450.0, ytd_q2_2025=600.0, q2_2025_three_months=320.0),   # trailing 1150
    duration("OperatingIncomeLoss", fy2024=200.0, ytd_q2_2024=90.0, ytd_q2_2025=130.0, q2_2025_three_months=70.0),  # 240
    duration("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest", fy2024=190.0, ytd_q2_2024=85.0, ytd_q2_2025=125.0),  # 230
    duration("IncomeTaxExpenseBenefit", fy2024=40.0, ytd_q2_2024=18.0, ytd_q2_2025=26.0),   # 48
    duration("NetIncomeLoss", fy2024=150.0, ytd_q2_2024=67.0, ytd_q2_2025=99.0),            # 182
    duration("DepreciationDepletionAndAmortization", fy2024=50.0, ytd_q2_2024=24.0, ytd_q2_2025=27.0),   # 53: cash-flow lines carry year-to-date only
    duration("PaymentsToAcquirePropertyPlantAndEquipment", fy2024=60.0, ytd_q2_2024=30.0, ytd_q2_2025=45.0),   # 75
    duration("IncreaseDecreaseInOperatingCapital", fy2024=10.0, ytd_q2_2024=4.0, ytd_q2_2025=9.0),   # 15
    duration("NetCashProvidedByUsedInOperatingActivities", fy2024=210.0, ytd_q2_2024=95.0, ytd_q2_2025=140.0),  # 255
    instant("CashAndCashEquivalentsAtCarryingValue", at_2024=300.0, at_q2_2025=340.0),
    instant("LongTermDebt", at_2024=500.0, at_q2_2025=480.0),
    instant("StockholdersEquity", at_2024=900.0, at_q2_2025=980.0),
]

ANNUAL = [boundary.FiscalPeriod(period_end="2024-12-31", ebit=200.0, pretax_income=190.0, tax_provision=40.0, total_revenue=1000.0,
                                net_interest_income=None, premiums_earned=None, premiums_earned_row=None, depreciation_amortization=50.0,
                                depreciation_amortization_row="DepreciationDepletionAndAmortization", capex=60.0, delta_nwc=10.0, cash=300.0,
                                total_debt=500.0, total_debt_source="LongTermDebt", book_equity=900.0, net_income=150.0, dividends_paid=None,
                                dividends_paid_row=None, provision_for_credit_losses=None, provision_for_credit_losses_row=None, net_loans=None,
                                net_loans_row=None, total_revenue_row="Revenues")]


def test_each_line_is_year_to_date_plus_prior_year_less_prior_year_to_date_and_each_balance_the_quarter_ends() -> None:
    period, basis, reason = trailing.of_record(facts(LINES), "us-gaap", "USD", TAGS, DEFS, PARAMS, ANNUAL)
    assert reason is None and period is not None and basis is not None
    assert period.period_end == "2025-06-30"
    assert period.total_revenue == 1150.0 and period.ebit == 240.0 and period.ebit_recipe == "operating_income"
    assert period.pretax_income == 230.0 and period.tax_provision == 48.0 and period.net_income == 182.0
    assert period.depreciation_amortization == 53.0 and period.capex == 75.0 and period.delta_nwc == 15.0
    assert period.operating_cash_flow == 255.0
    assert period.cash == 340.0 and period.total_debt == 480.0 and period.book_equity == 980.0
    assert period.filed == "2025-08-01" and period.accession == "q2-2025"
    assert basis.quarter_end == "2025-06-30" and basis.year_to_date_start == "2025-01-01" and basis.prior_year_end == "2024-12-31"
    assert basis.prior_year_to_date_end == "2024-06-30" and basis.quarters_in_year_to_date == 2
    assert period.ffo is None and period.ffo_unavailable == "not read on a trailing period" and period.restated_from == []
    assert any("trailing" in n for n in basis.notes)


def test_the_quarterly_filings_own_comparative_is_preferred_and_a_line_missing_a_fact_is_null() -> None:
    # the 2025 filing restates the prior year-to-date in its comparative column: its own figure
    # is the one subtracted, not the 2024 filing's
    lines = [l for l in LINES if l[0] != "Revenues"]
    tag, rows = duration("Revenues", fy2024=1000.0, ytd_q2_2024=450.0, ytd_q2_2025=600.0)
    rows = [r for r in rows if not (r["accn"] == "q2-2025" and r["end"] == "2024-06-30")]
    rows.append(entry("2024-01-01", "2024-06-30", 460.0, "10-Q", "Q2", "2025-08-01", "q2-2025"))   # restated comparative
    period, _, _ = trailing.of_record(facts(lines + [(tag, rows)]), "us-gaap", "USD", TAGS, DEFS, PARAMS, ANNUAL)
    assert period is not None and period.total_revenue == 1000.0 + 600.0 - 460.0
    # a line without its prior year-to-date is null, never scaled from the quarters
    lines = [l for l in LINES if l[0] != "PaymentsToAcquirePropertyPlantAndEquipment"]
    tag, rows = duration("PaymentsToAcquirePropertyPlantAndEquipment", fy2024=60.0, ytd_q2_2024=30.0, ytd_q2_2025=45.0)
    rows = [r for r in rows if r["end"] != "2024-06-30"]
    period, _, _ = trailing.of_record(facts(lines + [(tag, rows)]), "us-gaap", "USD", TAGS, DEFS, PARAMS, ANNUAL)
    assert period is not None and period.capex is None and period.total_revenue == 1150.0


def test_a_component_the_annual_recipe_read_without_a_trailing_fact_leaves_the_line_null() -> None:
    # the 10-K tags the working-capital change as receivables and payables; the 10-Q folds
    # payables into another tag, so payables have no trailing fact: the sum is not the asset
    # side alone, it is null, and the notes name the row
    lines = [l for l in LINES if l[0] != "IncreaseDecreaseInOperatingCapital"]
    lines.append(duration("IncreaseDecreaseInAccountsReceivable", fy2024=30.0, ytd_q2_2024=12.0, ytd_q2_2025=20.0))
    tag, rows = duration("IncreaseDecreaseInAccountsPayable", fy2024=20.0, ytd_q2_2024=8.0, ytd_q2_2025=11.0)
    lines.append((tag, [r for r in rows if r["form"] == "10-K"]))   # the annual fact alone
    base = boundary.FiscalPeriod.from_json_string(ANNUAL[0].to_json_string())
    base.delta_nwc_row = "IncreaseDecreaseInAccountsReceivable - IncreaseDecreaseInAccountsPayable"
    base.delta_nwc_composition = boundary.Composition(definition="delta_nwc", components=[
        boundary.Component(name="asset_components", value=30.0, row="IncreaseDecreaseInAccountsReceivable"),
        boundary.Component(name="liability_components", value=-20.0, row="IncreaseDecreaseInAccountsPayable")])
    period, basis, reason = trailing.of_record(facts(lines), "us-gaap", "USD", TAGS, DEFS, PARAMS, [base])
    assert reason is None and period is not None and basis is not None
    assert period.delta_nwc is None and period.delta_nwc_row is None and period.delta_nwc_composition is None
    assert any("delta_nwc: the annual period's recipe reads IncreaseDecreaseInAccountsPayable, which has no trailing fact" in n for n in basis.notes)
    # with both components carrying trailing facts the sum is read: 38 of receivables less 23 of payables
    lines[-1] = duration("IncreaseDecreaseInAccountsPayable", fy2024=20.0, ytd_q2_2024=8.0, ytd_q2_2025=11.0)
    period, _, _ = trailing.of_record(facts(lines), "us-gaap", "USD", TAGS, DEFS, PARAMS, [base])
    assert period is not None and period.delta_nwc == 38.0 - 23.0
    # the same rule on the balance sheet: short-term investments the annual read and the
    # quarter does not tag leave cash null rather than smaller
    base.cash_row = "CashAndCashEquivalentsAtCarryingValue + ShortTermInvestments"
    base.cash_composition = boundary.Composition(definition="cash", components=[
        boundary.Component(name="cash_equivalents", value=300.0, row="CashAndCashEquivalentsAtCarryingValue"),
        boundary.Component(name="short_term_investments", value=50.0, row="ShortTermInvestments")])
    period, basis, _ = trailing.of_record(facts(lines), "us-gaap", "USD", TAGS, DEFS, PARAMS, [base])
    assert period is not None and basis is not None and period.cash is None
    assert any("cash: the annual period's recipe reads short_term_investments" in n for n in basis.notes)   # cash compares by role, since the tag may differ


def test_a_debt_recipe_is_whole_by_its_rank_and_zero_by_absence_only_where_the_annual_was_zero() -> None:
    def debt_of(annual_lines: list[tuple[str, list[dict[str, object]]]], base_debt: float, base_rows: list[tuple[str, str]]) -> tuple[float | None, list[str]]:
        base = boundary.FiscalPeriod.from_json_string(ANNUAL[0].to_json_string())
        base.total_debt = base_debt
        base.total_debt_source = " + ".join(r for _, r in base_rows)
        base.total_debt_composition = boundary.Composition(definition="total_debt", components=[boundary.Component(name=n, value=1.0, row=r) for n, r in base_rows])
        lines = [l for l in LINES if l[0] != "LongTermDebt"] + annual_lines
        period, basis, reason = trailing.of_record(facts(lines), "us-gaap", "USD", TAGS, DEFS, PARAMS, [base])
        assert reason is None and period is not None and basis is not None
        return period.total_debt, [n for n in basis.notes if n.startswith("total_debt")]
    components = [("noncurrent", "LongTermDebtNoncurrent"), ("current_long_term", "LongTermDebtCurrent"), ("short_term_borrowings", "CommercialPaper")]
    # the 10-Q tags the filer's total where the 10-K tagged three components: whole by rank
    value, notes = debt_of([instant("LongTermDebt", at_2024=500.0, at_q2_2025=480.0)], 500.0, components)
    assert value == 480.0 and notes == []
    # a complete pair on the 10-Q: whole
    value, notes = debt_of([instant("LongTermDebtNoncurrent", at_2024=400.0, at_q2_2025=390.0), instant("DebtCurrent", at_2024=100.0, at_q2_2025=90.0)], 500.0, components)
    assert value == 480.0 and notes == []
    # a lone component where the 10-K had three: partial, null
    value, notes = debt_of([instant("LongTermDebtNoncurrent", at_2024=400.0, at_q2_2025=390.0)], 500.0, components)
    assert value is None and notes and "CommercialPaper, LongTermDebtCurrent" in notes[0]
    # no debt line and no interest on the quarter where the 10-K carried debt: not zero, null
    value, notes = debt_of([], 500.0, components)
    assert value is None and notes and "no trailing fact" in notes[0]
    # and where the annual was zero by the same absence, zero stands
    value, notes = debt_of([], 0.0, [])
    assert value == 0.0 and notes == []


def test_the_date_cut_is_on_the_filing_date() -> None:
    # before the 2025 Q2 filing nothing ends after the annual base, so there is no trailing period
    _, _, reason = trailing.of_record(facts(LINES), "us-gaap", "USD", TAGS, DEFS, PARAMS, ANNUAL, as_of=date(2025, 7, 15))
    assert reason == trailing.NOT_AFTER_BASE
    period, basis, reason = trailing.of_record(facts(LINES), "us-gaap", "USD", TAGS, DEFS, PARAMS, ANNUAL, as_of=date(2025, 8, 1))
    assert reason is None and period is not None and basis is not None and basis.filed == "2025-08-01"


def test_the_reasons_name_what_is_missing() -> None:
    assert trailing.of_record(None, "us-gaap", "USD", TAGS, DEFS, PARAMS, ANNUAL) == (None, None, trailing.NO_FACTS)
    assert trailing.of_record(facts(LINES), "ifrs-full", "USD", TAGS, DEFS, PARAMS, ANNUAL) == (None, None, trailing.NO_QUARTERLY_IFRS)
    assert trailing.of_record(facts(LINES), "us-gaap", "USD", TAGS, DEFS, PARAMS, []) == (None, None, trailing.NO_ANNUAL)
    # no book equity at the quarter end: nothing anchors the period
    no_equity = [l for l in LINES if l[0] != "StockholdersEquity"]
    assert trailing.of_record(facts(no_equity), "us-gaap", "USD", TAGS, DEFS, PARAMS, ANNUAL) == (None, None, trailing.NO_ANCHOR)
    # the annual base is not the year before the quarter's fiscal year
    older = [boundary.FiscalPeriod.from_json_string(ANNUAL[0].to_json_string())]
    older[0].period_end = "2023-12-31"
    assert trailing.of_record(facts(LINES), "us-gaap", "USD", TAGS, DEFS, PARAMS, older) == (None, None, trailing.NO_PRIOR_YEAR)
    # a three-month figure alone is not a year-to-date: a Q2 filing with only the quarter's
    # revenue leaves the line null
    lines = [l for l in LINES if l[0] != "Revenues"]
    tag, rows = duration("Revenues", fy2024=1000.0, ytd_q2_2024=450.0, ytd_q2_2025=600.0, q2_2025_three_months=320.0)
    rows = [r for r in rows if not (r["start"] == "2025-01-01")]
    period, _, _ = trailing.of_record(facts(lines + [(tag, rows)]), "us-gaap", "USD", TAGS, DEFS, PARAMS, ANNUAL)
    assert period is not None and period.total_revenue is None


def year_to_date(tag: str, ytd_q2_2025: float, ytd_q2_2024: float | None = None) -> tuple[str, list[dict[str, object]]]:
    """A cash-flow line in the 2025 Q2 10-Q, with the prior year's comparative beside it."""
    rows = [entry("2025-01-01", "2025-06-30", ytd_q2_2025, "10-Q", "Q2", "2025-08-01", "q2-2025")]
    if ytd_q2_2024 is not None:
        rows.append(entry("2024-01-01", "2024-06-30", ytd_q2_2024, "10-Q", "Q2", "2025-08-01", "q2-2025"))
    return tag, rows


def test_distributions_since_the_base_are_the_quarterly_filings_year_to_date_lines() -> None:
    """(2026-10-19) The equity bridge's date line, every figure invented: buybacks and common
    dividends less shares issued, each the 2025 Q2 10-Q's year-to-date figure from the day
    after the base, an absent line nil; payments to buy minority interests out less the book
    they removed, at least nil; the reasons where no quarterly filing is read."""
    lines = LINES + [year_to_date("PaymentsForRepurchaseOfCommonStock", 70.0, ytd_q2_2024=999.0),
                     year_to_date("PaymentsOfDividendsCommonStock", 30.0),
                     year_to_date("ProceedsFromIssuanceOfCommonStock", 5.0),
                     year_to_date("PaymentsToMinorityShareholders", 40.0),
                     year_to_date("MinorityInterestDecreaseFromRedemptions", 15.0)]
    d, reason = trailing.distributions_of(facts(lines), "us-gaap", "USD", TAGS, DEFS, ANNUAL)
    assert reason is None and d is not None
    assert (d.since, d.through, d.accession) == ("2024-12-31", "2025-06-30", "q2-2025")
    assert (d.repurchases, d.repurchases_row) == (70.0, "PaymentsForRepurchaseOfCommonStock")
    assert d.net == 70.0 + 30.0 - 5.0
    assert (d.minority_buyouts, d.minority_buyouts_book, d.minority_net) == (40.0, 15.0, 25.0)
    # the fallback tag, the absent lines nil, and a book above the payment adding nothing
    sparse = LINES + [year_to_date("PaymentsOfDividends", 12.0), year_to_date("PaymentsToMinorityShareholders", 10.0),
                      year_to_date("MinorityInterestDecreaseFromRedemptions", 15.0)]
    d, _ = trailing.distributions_of(facts(sparse), "us-gaap", "USD", TAGS, DEFS, ANNUAL)
    assert d is not None and (d.repurchases, d.issuance, d.dividends_row, d.net, d.minority_net) == (None, None, "PaymentsOfDividends", 12.0, 0.0)
    ordinary = LINES + [year_to_date("PaymentsOfOrdinaryDividends", 9.0)]
    d, _ = trailing.distributions_of(facts(ordinary), "us-gaap", "USD", TAGS, DEFS, ANNUAL)
    assert d is not None and (d.dividends, d.dividends_row) == (9.0, "PaymentsOfOrdinaryDividends")
    d, _ = trailing.distributions_of(facts(LINES), "us-gaap", "USD", TAGS, DEFS, ANNUAL)
    assert d is not None and (d.net, d.minority_buyouts, d.minority_net) == (0.0, None, None)
    assert trailing.distributions_of(None, "", None, TAGS, DEFS, ANNUAL) == (None, trailing.NO_FACTS)
    assert trailing.distributions_of(facts(LINES), "ifrs-full", "EUR", TAGS, DEFS, ANNUAL) == (None, trailing.NO_QUARTERLY_IFRS)
    # the filing date cut: a 10-Q filed after the date is not read
    assert trailing.distributions_of(facts(lines), "us-gaap", "USD", TAGS, DEFS, ANNUAL, as_of=date(2025, 7, 1))[0] is None


def test_the_trailing_period_carries_the_bridge_lines_at_the_quarter_end() -> None:
    lines = LINES + [instant("MinorityInterest", at_2024=60.0, at_q2_2025=65.0)]
    period, _, reason = trailing.of_record(facts(lines), "us-gaap", "USD", TAGS, DEFS, PARAMS, ANNUAL)
    assert reason is None and period is not None
    assert (period.minority_interest, period.minority_interest_row) == (65.0, "MinorityInterest")
