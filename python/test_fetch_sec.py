"""Tag selection per period, the annual-fact filter, the fields composed per
reference/field_definitions.json (with the sign convention tested, not assumed), the
provider decision and the cross-check, on synthetic companyfacts."""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping
from datetime import date

import fetch
import fetch_sec


def fact(end: str, val: float, *, start: str | None = None, filed: str = "2026-02-20", form: str = "10-K", fp: str = "FY") -> dict[str, object]:
    d: dict[str, object] = {"end": end, "val": val, "form": form, "fp": fp, "filed": filed, "accn": f"acc-{filed}"}
    if start:
        d["start"] = start
    return d


def usd(*facts: dict[str, object]) -> dict[str, object]:
    return {"units": {"USD": list(facts)}}


TAGS = fetch_sec.load_tags()
DEFS = fetch_sec.load_definitions()
END = date(2025, 12, 31)


def anchors(end: str = "2025-12-31", start: str = "2025-01-01") -> dict[str, object]:
    return {"NetIncomeLoss": usd(fact(end, 10e9, start=start)), "StockholdersEquity": usd(fact(end, 50e9))}


def period(gaap: Mapping[str, object], notes: list[str] | None = None) -> fetch.boundary.FiscalPeriod:
    return fetch_sec.periods_from_facts({**anchors(), **gaap}, TAGS, DEFS, notes if notes is not None else [])[0]


def components(c: fetch.boundary.Composition | None) -> list[tuple[str, float, str]]:
    assert c is not None
    return [(k.name, k.value, k.row) for k in c.components]


def test_annual_filter_drops_quarters_marked_fy_and_keeps_latest_filing() -> None:
    notes: list[str] = []
    out = fetch_sec.annual_facts(
        [fact("2025-12-31", 0.49e9, start="2025-10-01"),          # a quarter marked FY
         fact("2025-12-31", 1.58e9, start="2025-01-01", filed="2026-02-20"),
         fact("2025-12-31", 1.60e9, start="2025-01-01", filed="2026-03-01"),  # restated later: wins
         fact("2025-12-31", 9e9, start="2025-01-01", form="10-Q"),
         fact("2025-12-31", 8e9, start="2025-01-01", form="20-F"),
         {"end": "bad"}],
        instant=False, tags=TAGS, notes=notes, tag="NetIncomeLoss")
    assert out[date(2025, 12, 31)].val == 1.60e9
    assert notes == ["NetIncomeLoss: 1 companyfacts entries rejected at validation"]
    balances = fetch_sec.annual_facts([fact("2025-12-31", 30e9), fact("2025-12-31", 31e9, start="2025-01-01")],
                                      instant=True, tags=TAGS, notes=notes, tag="StockholdersEquity")
    assert balances[date(2025, 12, 31)].val == 30e9


def apple_like() -> dict[str, object]:
    """Revenues stops after FY2024; the newer tag carries FY2025. Long-term debt filed with
    the current portion plus commercial paper; working capital as components; an operating
    lease liability that must not enter debt."""
    return {
        "NetIncomeLoss": usd(fact("2025-09-27", 112e9, start="2024-09-29"), fact("2024-09-28", 94e9, start="2023-10-01"), fact("2023-09-30", 97e9, start="2022-10-02")),
        "StockholdersEquity": usd(fact("2025-09-27", 74e9), fact("2024-09-28", 57e9), fact("2023-09-30", 62e9)),
        "Revenues": usd(fact("2024-09-28", 391e9, start="2023-10-01"), fact("2023-09-30", 383e9, start="2022-10-02")),
        "RevenueFromContractWithCustomerExcludingAssessedTax": usd(fact("2025-09-27", 416e9, start="2024-09-29"), fact("2024-09-28", 391e9, start="2023-10-01")),
        "OperatingIncomeLoss": usd(fact("2025-09-27", 133e9, start="2024-09-29")),
        "DepreciationDepletionAndAmortization": usd(fact("2025-09-27", 11.7e9, start="2024-09-29")),
        "PaymentsToAcquirePropertyPlantAndEquipment": usd(fact("2025-09-27", 12.7e9, start="2024-09-29")),
        "CashAndCashEquivalentsAtCarryingValue": usd(fact("2025-09-27", 36e9), fact("2024-09-28", 30e9), fact("2023-09-30", 30e9)),
        "MarketableSecuritiesCurrent": usd(fact("2025-09-27", 18.7e9)),
        "LongTermDebt": usd(fact("2025-09-27", 90.7e9)),
        "CommercialPaper": usd(fact("2025-09-27", 8e9)),
        "OperatingLeaseLiability": usd(fact("2025-09-27", 12.5e9), fact("2024-09-28", 12e9)),
        "IncreaseDecreaseInAccountsReceivable": usd(fact("2025-09-27", 6.682e9, start="2024-09-29"), fact("2024-09-28", 3.788e9, start="2023-10-01")),
        "IncreaseDecreaseInAccountsPayable": usd(fact("2025-09-27", 0.902e9, start="2024-09-29"), fact("2024-09-28", 6.02e9, start="2023-10-01")),
        "PaymentsOfDividendsCommonStock": usd(fact("2017-09-30", 12.6e9, start="2016-09-25")),
        "PaymentsOfDividends": usd(fact("2025-09-27", 15.4e9, start="2024-09-29")),
    }


def test_tag_selection_changes_between_years_and_records_the_tag() -> None:
    notes: list[str] = []
    periods = fetch_sec.periods_from_facts(apple_like(), TAGS, DEFS, notes)
    p25, p24, p23 = periods
    assert (p25.total_revenue, p25.total_revenue_row) == (416e9, "RevenueFromContractWithCustomerExcludingAssessedTax")
    assert (p24.total_revenue, p24.total_revenue_row) == (391e9, "Revenues")  # the older tag wins where it exists
    assert (p25.dividends_paid, p25.dividends_paid_row) == (15.4e9, "PaymentsOfDividends")
    assert p25.filed == "2026-02-20" and p25.accession == "acc-2026-02-20"
    assert (p25.depreciation_amortization, p25.depreciation_amortization_row) == (11.7e9, "DepreciationDepletionAndAmortization")
    assert (p25.ebit, p25.ebit_row, p25.ebit_recipe) == (133e9, "OperatingIncomeLoss", "operating_income")
    assert (p25.total_debt, p25.total_debt_source) == (98.7e9, "LongTermDebt + CommercialPaper")
    assert p24.total_debt is None and p24.total_debt_source is None and p24.total_debt_composition is None  # no silent zero
    assert (p25.cash, p25.cash_row) == (54.7e9, "CashAndCashEquivalentsAtCarryingValue + MarketableSecuritiesCurrent")
    assert (p24.cash, p24.cash_row) == (30e9, "CashAndCashEquivalentsAtCarryingValue")
    assert p25.delta_nwc is not None and math.isclose(p25.delta_nwc, 5.78e9)  # 6.682 - 0.902
    assert p24.delta_nwc is not None and math.isclose(p24.delta_nwc, -2.232e9)
    assert p23.delta_nwc is None and p23.delta_nwc_composition is None
    assert fetch_sec.latest_filing(periods) == "2026-02-20"


def test_delta_nwc_sign_convention_by_hand() -> None:
    """An asset that grew absorbed cash; a liability that grew released it. Verified on
    Coca-Cola's FY2025 filing, where the aggregate and the components are both tagged."""
    receivable_grew = {"IncreaseDecreaseInAccountsReceivable": usd(fact("2025-12-31", 6.682e9, start="2025-01-01"))}
    payable_grew = {"IncreaseDecreaseInAccountsPayable": usd(fact("2025-12-31", 0.902e9, start="2025-01-01"))}
    p = period({**receivable_grew, **payable_grew})
    assert p.delta_nwc is not None and math.isclose(p.delta_nwc, 6.682e9 - 0.902e9)
    assert p.delta_nwc_row == "IncreaseDecreaseInAccountsReceivable - IncreaseDecreaseInAccountsPayable"
    assert components(p.delta_nwc_composition) == [("asset_components", 6.682e9, "IncreaseDecreaseInAccountsReceivable"), ("liability_components", -0.902e9, "IncreaseDecreaseInAccountsPayable")]
    assert p.delta_nwc_composition is not None and p.delta_nwc_composition.definition == DEFS.delta_nwc.name
    # Coca-Cola FY2025: the components reproduce the filed aggregate under this convention.
    ko = {
        "IncreaseDecreaseInAccountsReceivable": usd(fact("2025-12-31", -0.334e9, start="2025-01-01")),
        "IncreaseDecreaseInInventories": usd(fact("2025-12-31", 0.154e9, start="2025-01-01")),
        "IncreaseDecreaseInPrepaidDeferredExpenseAndOtherAssets": usd(fact("2025-12-31", 0.388e9, start="2025-01-01")),
        "IncreaseDecreaseInAccountsPayableAndAccruedLiabilities": usd(fact("2025-12-31", -6.612e9, start="2025-01-01")),
        "IncreaseDecreaseInAccruedIncomeTaxesPayable": usd(fact("2025-12-31", -0.558e9, start="2025-01-01")),
        "IncreaseDecreaseInOtherNoncurrentLiabilities": usd(fact("2025-12-31", 0.170e9, start="2025-01-01")),
    }
    p = period(ko)
    assert p.delta_nwc is not None and math.isclose(p.delta_nwc, 7.208e9)
    # ... and the aggregate wins when filed, recorded as the one component.
    p = period({**ko, "IncreaseDecreaseInOperatingCapital": usd(fact("2025-12-31", 7.208e9, start="2025-01-01"))})
    assert (p.delta_nwc, p.delta_nwc_row) == (7.208e9, "IncreaseDecreaseInOperatingCapital")
    assert components(p.delta_nwc_composition) == [("aggregate", 7.208e9, "IncreaseDecreaseInOperatingCapital")]
    # Costco FY2025: the net "other operating capital" tag is a net asset, added.
    cost = {
        "IncreaseDecreaseInInventories": usd(fact("2025-08-31", -0.559e9, start="2024-09-02")),
        "IncreaseDecreaseInAccountsPayable": usd(fact("2025-08-31", 0.404e9, start="2024-09-02")),
        "IncreaseDecreaseInOtherOperatingCapitalNet": usd(fact("2025-08-31", -0.801e9, start="2024-09-02")),
    }
    p = fetch_sec.periods_from_facts({**anchors("2025-08-31", "2024-09-02"), **cost}, TAGS, DEFS, [])[0]
    assert p.delta_nwc is not None and math.isclose(p.delta_nwc, -1.764e9)


def test_delta_nwc_is_null_when_a_working_capital_tag_is_unclassified() -> None:
    """A bank's deposits or an insurer's reserves never become a partial number."""
    notes: list[str] = []
    bank = {
        "IncreaseDecreaseInAccountsPayable": usd(fact("2025-12-31", 50.7e9, start="2025-01-01")),
        "IncreaseDecreaseInDeposits": usd(fact("2025-12-31", 39.1e9, start="2025-01-01")),
    }
    p = period(bank, notes)
    assert p.delta_nwc is None and p.delta_nwc_row is None and p.delta_nwc_composition is None
    assert notes == ["delta_nwc 2025-12-31: left null, unclassified working-capital tags: IncreaseDecreaseInDeposits"]
    excluded = {"IncreaseDecreaseInInventories": usd(fact("2025-12-31", 1e9, start="2025-01-01")),
                "IncreaseDecreaseInDeferredIncomeTaxes": usd(fact("2025-12-31", 8.9e9, start="2025-01-01"))}
    p = period(excluded)
    assert p.delta_nwc == 1e9  # recognised as outside working capital, not summed, not blocking
    assert period({}).delta_nwc is None


def test_cash_composition_with_and_without_the_optional_tags() -> None:
    both = {"CashAndCashEquivalentsAtCarryingValue": usd(fact("2025-12-31", 20.935e9)), "ShortTermInvestments": usd(fact("2025-12-31", 55.908e9)),
            "MarketableSecuritiesCurrent": usd(fact("2025-12-31", 1e9))}  # first present wins, not summed
    p = period(both)
    assert p.cash is not None and math.isclose(p.cash, 76.843e9)
    assert components(p.cash_composition) == [("cash_equivalents", 20.935e9, "CashAndCashEquivalentsAtCarryingValue"), ("short_term_investments", 55.908e9, "ShortTermInvestments")]
    only = period({"CashAndCashEquivalentsAtCarryingValue": usd(fact("2025-12-31", 0.245e9))})
    assert (only.cash, only.cash_row) == (0.245e9, "CashAndCashEquivalentsAtCarryingValue")
    assert components(only.cash_composition) == [("cash_equivalents", 0.245e9, "CashAndCashEquivalentsAtCarryingValue")]
    # Chevron FY2025: only the restricted-inclusive total is tagged; the restricted parts come out.
    cvx = {"CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents": usd(fact("2025-12-31", 7.285e9)),
           "RestrictedCashCurrent": usd(fact("2025-12-31", 0.174e9)), "RestrictedCashNoncurrent": usd(fact("2025-12-31", 0.818e9)),
           "MarketableSecuritiesCurrent": usd(fact("2025-12-31", 0.0))}
    p = period(cvx)
    assert p.cash is not None and math.isclose(p.cash, 6.293e9)
    assert p.cash_row == "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents - RestrictedCashCurrent - RestrictedCashNoncurrent + MarketableSecuritiesCurrent"
    assert [n for n, _, _ in components(p.cash_composition)] == ["cash_equivalents", "restricted_cash", "restricted_cash", "short_term_investments"]
    assert period({"ShortTermInvestments": usd(fact("2025-12-31", 1e9))}).cash is None


def test_debt_recipes_exclude_operating_leases_and_keep_folded_finance_leases() -> None:
    lease = {"OperatingLeaseLiability": usd(fact("2025-12-31", 21.9e9)), "OperatingLeaseLiabilityNoncurrent": usd(fact("2025-12-31", 16.5e9))}
    # (1) noncurrent + all current debt as one tag; the lease is present and stays out.
    jnj = {"LongTermDebtNoncurrent": usd(fact("2025-12-31", 39.438e9)), "DebtCurrent": usd(fact("2025-12-31", 8.5e9)),
           "LongTermDebt": usd(fact("2025-12-31", 41.438e9)), "LongTermDebtCurrent": usd(fact("2025-12-31", 2.0e9)),
           "ShortTermBorrowings": usd(fact("2025-12-31", 8.495e9)), **lease}
    p = period(jnj)
    assert p.total_debt is not None and math.isclose(p.total_debt, 47.938e9)
    assert p.total_debt_source == "LongTermDebtNoncurrent + DebtCurrent"
    assert components(p.total_debt_composition) == [("noncurrent", 39.438e9, "LongTermDebtNoncurrent"), ("current_total", 8.5e9, "DebtCurrent")]
    assert all(k.row not in DEFS.total_debt.xbrl.excluded for k in (p.total_debt_composition.components if p.total_debt_composition else []))
    # (2) noncurrent + current portion + short-term borrowings; a folded finance lease stays (Coca-Cola).
    ko = {"LongTermDebtAndCapitalLeaseObligations": usd(fact("2025-12-31", 42.119e9)), "LongTermDebtAndCapitalLeaseObligationsCurrent": usd(fact("2025-12-31", 1.822e9)),
          "CommercialPaper": usd(fact("2025-12-31", 1.495e9)), **lease}
    p = period(ko)
    assert p.total_debt is not None and math.isclose(p.total_debt, 45.436e9)
    assert p.total_debt_source == "LongTermDebtAndCapitalLeaseObligations + LongTermDebtAndCapitalLeaseObligationsCurrent + CommercialPaper"
    # (2) without short-term borrowings (Microsoft).
    p = period({"LongTermDebtNoncurrent": usd(fact("2025-12-31", 31.067e9)), "LongTermDebtCurrent": usd(fact("2025-12-31", 9.227e9)), **lease})
    assert p.total_debt is not None and math.isclose(p.total_debt, 40.294e9) and p.total_debt_source == "LongTermDebtNoncurrent + LongTermDebtCurrent"
    # (3) long-term debt filed with its current portion, plus commercial paper (Apple).
    p = period({"LongTermDebt": usd(fact("2025-12-31", 90.678e9)), "CommercialPaper": usd(fact("2025-12-31", 7.979e9)), **lease})
    assert p.total_debt is not None and math.isclose(p.total_debt, 98.657e9) and p.total_debt_source == "LongTermDebt + CommercialPaper"
    # (4) noncurrent alone when nothing current is tagged at all; a lease alone is nothing.
    p = period({"LongTermDebtNoncurrent": usd(fact("2025-12-31", 0.745e9)), **lease})
    assert (p.total_debt, p.total_debt_source) == (0.745e9, "LongTermDebtNoncurrent")
    p = period(lease)
    assert p.total_debt is None and p.total_debt_composition is None


def test_ebit_recipe_from_filed_tags_when_operating_income_is_absent() -> None:
    """Pretax + interest expense - interest income - other non-operating - equity method,
    each subtracted as filed (income-positive); Johnson & Johnson FY2025 by hand."""
    jnj = {"IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": usd(fact("2025-12-31", 32.581e9, start="2025-01-01")),
           "InterestExpenseNonoperating": usd(fact("2025-12-31", 0.971e9, start="2025-01-01")),
           "InvestmentIncomeInterest": usd(fact("2025-12-31", 1.056e9, start="2025-01-01")),
           "OtherNonoperatingIncomeExpense": usd(fact("2025-12-31", 7.209e9, start="2025-01-01")),
           "IncomeLossFromEquityMethodInvestments": usd(fact("2025-12-31", 3.0e9, start="2025-01-01"))}
    p = period(jnj)
    assert p.ebit is not None and math.isclose(p.ebit, (32.581 + 0.971 - 1.056 - 7.209 - 3.0) * 1e9)
    assert p.ebit_recipe == "pretax_plus_interest_less_nonoperating" and p.ebit_recipe in DEFS.ebit.recipes
    assert p.ebit_row == ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest + InterestExpenseNonoperating"
                          " - InvestmentIncomeInterest - OtherNonoperatingIncomeExpense - IncomeLossFromEquityMethodInvestments")
    assert components(p.ebit_composition) == [
        ("pretax_income", 32.581e9, "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest"),
        ("interest_expense", 0.971e9, "InterestExpenseNonoperating"), ("interest_income", -1.056e9, "InvestmentIncomeInterest"),
        ("other_nonoperating", -7.209e9, "OtherNonoperatingIncomeExpense"), ("equity_method", -3.0e9, "IncomeLossFromEquityMethodInvestments")]
    assert p.ebit_composition is not None and p.ebit_composition.definition == DEFS.ebit.name
    for absent in ("InvestmentIncomeInterest", "OtherNonoperatingIncomeExpense", "IncomeLossFromEquityMethodInvestments"):
        q = period({k: v for k, v in jnj.items() if k != absent})
        parts = components(q.ebit_composition)
        assert q.ebit is not None and len(parts) == 4 and math.isclose(q.ebit, sum(v for _, v, _ in parts)) and absent not in [r for _, _, r in parts]
    # a negative other non-operating figure (an expense) is subtracted as filed, so it adds back
    q = period({**jnj, "OtherNonoperatingIncomeExpense": usd(fact("2025-12-31", -2.0e9, start="2025-01-01"))})
    assert q.ebit is not None and math.isclose(q.ebit, (32.581 + 0.971 - 1.056 + 2.0 - 3.0) * 1e9)
    with_operating = period({**jnj, "OperatingIncomeLoss": usd(fact("2025-12-31", 25.6e9, start="2025-01-01"))})
    assert (with_operating.ebit, with_operating.ebit_recipe, with_operating.ebit_row) == (25.6e9, "operating_income", "OperatingIncomeLoss")
    no_interest = period({"IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": usd(fact("2025-12-31", 1e9, start="2025-01-01"))})
    assert no_interest.ebit is None and no_interest.ebit_recipe is None and no_interest.ebit_composition is None
    assert len(DEFS.ebit.recipes) == 1 + DEFS.refinement_policy.max_refinements_per_field


def test_dividend_tag_order_reaches_bank_of_america() -> None:
    bac = {"PaymentsOfDividends": usd(fact("2013-12-31", 1.68e9, start="2013-01-01")),
           "PaymentsOfOrdinaryDividends": usd(fact("2025-12-31", 9.56e9, start="2025-01-01")),
           "DividendsCommonStockCash": usd(fact("2025-12-31", 8.08e9, start="2025-01-01"))}
    p = period(bac)
    assert (p.dividends_paid, p.dividends_paid_row) == (9.56e9, "PaymentsOfOrdinaryDividends")


def test_depreciation_composite() -> None:
    notes: list[str] = []
    ms_like = {
        "NetIncomeLoss": usd(fact("2026-06-30", 133e9, start="2025-07-01")),
        "StockholdersEquity": usd(fact("2026-06-30", 442e9)),
        "Depreciation": usd(fact("2026-06-30", 34.3e9, start="2025-07-01")),
        "AmortizationOfIntangibleAssets": usd(fact("2026-06-30", 4.7e9, start="2025-07-01")),
    }
    p = fetch_sec.periods_from_facts(ms_like, TAGS, DEFS, notes)[0]
    assert p.depreciation_amortization is not None and abs(p.depreciation_amortization - 39.0e9) < 1
    assert p.depreciation_amortization_row == "Depreciation + AmortizationOfIntangibleAssets"
    ko_like = {
        "NetIncomeLoss": usd(fact("2025-12-31", 13e9, start="2025-01-01")),
        "StockholdersEquity": usd(fact("2025-12-31", 32e9)),
        "AmortizationOfIntangibleAssets": usd(fact("2025-12-31", 0.1e9, start="2025-01-01")),  # no Depreciation: composite needs its first component
    }
    p = fetch_sec.periods_from_facts(ko_like, TAGS, DEFS, notes)[0]
    assert p.depreciation_amortization is None and p.depreciation_amortization_row is None


def test_provider_decision() -> None:
    xbrl, reason, gaap = fetch_sec.decide({"facts": {"us-gaap": apple_like()}}, TAGS)
    assert xbrl and reason == "us-gaap annual filer (10-K, 10-K/A)" and "NetIncomeLoss" in gaap
    xbrl, reason, _ = fetch_sec.decide({"facts": {"us-gaap": {}, "ifrs-full": {"ProfitLoss": usd(fact("2025-12-31", 1.0, start="2025-01-01"))}}}, TAGS)
    assert (xbrl, reason) == (False, "ifrs filer, not in scope")
    twenty_f = {"facts": {"us-gaap": {"NetIncomeLoss": usd(fact("2026-03-31", 7e9, start="2025-04-01", form="20-F"))}}}
    xbrl, reason, _ = fetch_sec.decide(twenty_f, TAGS)
    assert (xbrl, reason) == (False, "us-gaap facts filed on 20-F only; 10-K or 10-K/A required")
    xbrl, reason, _ = fetch_sec.decide({"facts": {"us-gaap": {"Assets": usd(fact("2025-12-31", 1.0))}}}, TAGS)
    assert not xbrl and reason.startswith("us-gaap facts carry no annual net income")
    xbrl, reason, _ = fetch_sec.decide(None, TAGS)
    assert (xbrl, reason) == (False, "SEC companyfacts: not found (HTTP 404)")


def test_cross_check_arithmetic_and_period_matching() -> None:
    notes: list[str] = []
    primary = fetch_sec.periods_from_facts(apple_like(), TAGS, DEFS, notes)[0]
    vendor = dataclasses.replace(fetch._period(date(2025, 9, 30), None, None, None),  # pyright: ignore[reportPrivateUsage]
                                 total_revenue=416.16e9, cash=54.7e9, total_debt=98.66e9, net_income=112e9)
    matched = fetch.match_period(primary, [vendor, fetch._period(date(2024, 9, 30), None, None, None)])  # pyright: ignore[reportPrivateUsage]
    assert matched is vendor  # 3 days apart
    assert fetch.match_period(primary, [fetch._period(date(2025, 6, 30), None, None, None)]) is None  # pyright: ignore[reportPrivateUsage]
    check = fetch.cross_check(primary, vendor, 0.02, "yfinance")
    by = {f.field: f for f in check.fields}
    assert by["net_income"].agree is True and by["net_income"].relative_difference == 0.0
    assert by["total_revenue"].agree is True  # 416 vs 416.16: 0.04%
    assert by["cash"].agree is True  # 54.7 vs 54.7 under one definition
    assert by["total_debt"].agree is True  # 98.7 vs 98.66
    assert by["capex"].agree is None and by["capex"].secondary is None  # vendor side missing: no verdict
    assert check.disagreements == 0 and check.period_end == "2025-09-27" and check.secondary_period_end == "2025-09-30"
    disagreeing = fetch.cross_check(primary, dataclasses.replace(vendor, cash=36e9), 0.02, "yfinance")
    cash = next(f for f in disagreeing.fields if f.field == "cash")
    assert cash.agree is False and cash.relative_difference is not None and abs(cash.relative_difference - (54.7 - 36) / 54.7) < 1e-9
    assert disagreeing.disagreements == 1


def test_cik_lookup_is_exact() -> None:
    table = {"0": {"cik_str": 1034670, "ticker": "ALV", "title": "AUTOLIV INC"},
             "1": {"cik_str": 1099219, "ticker": "MET", "title": "METLIFE INC"}}
    assert fetch_sec.cik_for("MET", table) == "0001099219"
    assert fetch_sec.cik_for("met", table) == "0001099219"
    assert fetch_sec.cik_for("ALV.DE", table) is None
