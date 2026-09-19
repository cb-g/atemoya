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
    d = fetch_sec.decide({"facts": {"us-gaap": apple_like()}}, TAGS)
    assert d.xbrl and d.reason == "us-gaap annual filer (10-K, 10-K/A, 20-F, 20-F/A), statements in USD" and "NetIncomeLoss" in d.facts
    assert (d.taxonomy, d.currency) == ("us-gaap", "USD")
    d = fetch_sec.decide({"facts": {"us-gaap": {}, "ifrs-full": sap_like()}}, TAGS)
    assert d.xbrl and (d.taxonomy, d.currency) == ("ifrs-full", "EUR") and d.reason == "ifrs-full annual filer (10-K, 10-K/A, 20-F, 20-F/A), statements in EUR"
    both = fetch_sec.decide({"facts": {"us-gaap": apple_like(), "ifrs-full": sap_like()}}, TAGS)
    assert both.taxonomy == "ifrs-full" and both.reason.endswith("(also us-gaap to 2025-09-27; the newest anchors, 2025-12-31, decide)")
    tie = {**sap_like(), "ProfitLoss": in_unit("EUR", twenty_f("2025-09-27", 1e9, start="2024-09-29")), "ProfitLossAttributableToOwnersOfParent": in_unit("EUR", twenty_f("2025-09-27", 1e9, start="2024-09-29")),
           "Equity": in_unit("EUR", twenty_f("2025-09-27", 1e9)), "EquityAttributableToOwnersOfParent": in_unit("EUR", twenty_f("2025-09-27", 1e9))}
    assert fetch_sec.decide({"facts": {"us-gaap": apple_like(), "ifrs-full": tie}}, TAGS).taxonomy == "us-gaap"  # a tie goes to us-gaap
    six_k = {"facts": {"ifrs-full": {"ProfitLoss": {"units": {"EUR": [fact("2025-12-31", 7e9, start="2025-01-01", form="6-K")]}}}}}
    d = fetch_sec.decide(six_k, TAGS)
    assert (d.xbrl, d.reason) == (False, "facts filed on 6-K only; 10-K or 10-K/A or 20-F or 20-F/A required")
    d = fetch_sec.decide({"facts": {"us-gaap": {"Assets": usd(fact("2025-12-31", 1.0))}}}, TAGS)
    assert not d.xbrl and d.reason == "facts carry no annual net income and equity (us-gaap 1 tags)"
    d = fetch_sec.decide(None, TAGS)
    assert (d.xbrl, d.reason, d.taxonomy, d.currency) == (False, "SEC companyfacts: not found (HTTP 404)", "", None)


def in_unit(unit: str, *facts: dict[str, object]) -> dict[str, object]:
    return {"units": {unit: list(facts)}}


def twenty_f(end: str, val: float, *, start: str | None = None) -> dict[str, object]:
    return fact(end, val, start=start, form="20-F", filed="2026-02-26")


def sap_like() -> dict[str, object]:
    """An ifrs-full 20-F filer in EUR with a USD convenience translation of one fact."""
    return {
        "ProfitLoss": {"units": {"EUR": [twenty_f("2025-12-31", 7.326e9, start="2025-01-01"), twenty_f("2024-12-31", 3.1e9, start="2024-01-01")],
                                 "USD": [twenty_f("2025-12-31", 8.0e9, start="2025-01-01")]}},
        "ProfitLossAttributableToOwnersOfParent": in_unit("EUR", twenty_f("2025-12-31", 7.161e9, start="2025-01-01"), twenty_f("2024-12-31", 3.0e9, start="2024-01-01")),
        "Equity": in_unit("EUR", twenty_f("2025-12-31", 45.073e9), twenty_f("2024-12-31", 45.0e9)),
        "EquityAttributableToOwnersOfParent": in_unit("EUR", twenty_f("2025-12-31", 44.586e9), twenty_f("2024-12-31", 44.5e9)),
        "Revenue": in_unit("EUR", twenty_f("2025-12-31", 36.8e9, start="2025-01-01")),
        "ProfitLossFromOperatingActivities": in_unit("EUR", twenty_f("2025-12-31", 9.617e9, start="2025-01-01")),
        "ProfitLossBeforeTax": in_unit("EUR", twenty_f("2025-12-31", 10.27e9, start="2025-01-01")),
        "AdjustmentsForDepreciationAndAmortisationExpense": in_unit("EUR", twenty_f("2025-12-31", 1.311e9, start="2025-01-01")),
        "PurchaseOfPropertyPlantAndEquipmentIntangibleAssetsOtherThanGoodwillInvestmentPropertyAndOtherNoncurrentAssets": in_unit("EUR", twenty_f("2025-12-31", 0.739e9, start="2025-01-01")),
        "CashAndCashEquivalents": in_unit("EUR", twenty_f("2025-12-31", 8.22e9)),
        "OtherCurrentFinancialAssets": in_unit("EUR", twenty_f("2025-12-31", 1.552e9)),
        "Borrowings": in_unit("EUR", twenty_f("2025-12-31", 6.15e9)),
        "LongtermBorrowings": in_unit("EUR", twenty_f("2025-12-31", 4.55e9)),
        "LeaseLiabilities": in_unit("EUR", twenty_f("2025-12-31", 1.684e9)),
        "DividendsPaidToEquityHoldersOfParentClassifiedAsFinancingActivities": in_unit("EUR", twenty_f("2025-12-31", 2.743e9, start="2025-01-01")),
        "DividendsPaid": in_unit("EUR", twenty_f("2025-12-31", 2.746e9, start="2025-01-01")),
        "AdjustmentsForDecreaseIncreaseInTradeAndOtherReceivables": in_unit("EUR", twenty_f("2025-12-31", -0.388e9, start="2025-01-01")),
        "AdjustmentsForIncreaseDecreaseInContractLiabilities": in_unit("EUR", twenty_f("2025-12-31", 1.336e9, start="2025-01-01")),
        "AccumulatedOtherComprehensiveIncome": in_unit("EUR", twenty_f("2025-12-31", -0.5e9)),
    }


def ifrs_period(gaap: Mapping[str, object], unit: str = "EUR", notes: list[str] | None = None) -> fetch.boundary.FiscalPeriod:
    return fetch_sec.periods_from_facts(gaap, TAGS, DEFS, notes if notes is not None else [], taxonomy="ifrs-full", unit=unit)[0]


def test_ifrs_full_per_period_selection_on_a_20f_in_the_filers_unit() -> None:
    notes: list[str] = []
    periods = fetch_sec.periods_from_facts(sap_like(), TAGS, DEFS, notes, taxonomy="ifrs-full", unit="EUR")
    p25, p24 = periods
    assert (p25.net_income, p25.net_income_row) == (7.161e9, "ProfitLossAttributableToOwnersOfParent")
    assert (p25.book_equity, p25.book_equity_row) == (44.586e9, "EquityAttributableToOwnersOfParent")
    assert (p25.total_revenue, p25.pretax_income, p25.tax_provision) == (36.8e9, 10.27e9, None)
    assert (p25.ebit, p25.ebit_row, p25.ebit_recipe) == (9.617e9, "ProfitLossFromOperatingActivities", "operating_income")
    assert (p25.depreciation_amortization, p25.depreciation_amortization_row) == (1.311e9, "AdjustmentsForDepreciationAndAmortisationExpense")
    assert p25.capex == 0.739e9 and p25.capex_row is not None and p25.capex_row.startswith("PurchaseOfPropertyPlantAndEquipmentIntangible")
    assert (p25.dividends_paid, p25.dividends_paid_row) == (2.743e9, "DividendsPaidToEquityHoldersOfParentClassifiedAsFinancingActivities")
    assert (p25.aoci, p25.aoci_row) == (-0.5e9, "AccumulatedOtherComprehensiveIncome")
    assert p25.filed == "2026-02-26" and p24.net_income == 3.0e9
    # the USD convenience fact is never read: the unit is the filer's
    assert fetch_sec.currency_units(sap_like())[0][0] == "EUR"
    hdb_like = {"NetIncomeLoss": {"units": {"INR": [twenty_f("2025-03-31", 673e9, start="2024-04-01")], "USD": [twenty_f("2025-03-31", 7.9e9, start="2024-04-01")]}},
                "StockholdersEquity": {"units": {"INR": [twenty_f("2025-03-31", 7677e9)], "USD": [twenty_f("2025-03-31", 89.9e9)]}},
                "InterestIncomeExpenseNet": {"units": {"INR": [twenty_f("2025-03-31", 1404e9, start="2024-04-01"), twenty_f("2024-03-31", 1300e9, start="2023-04-01")], "USD": [twenty_f("2025-03-31", 16.4e9, start="2024-04-01")]}}}
    d = fetch_sec.decide({"facts": {"us-gaap": hdb_like}}, TAGS)
    assert (d.taxonomy, d.currency) == ("us-gaap", "INR")  # more INR facts than USD ones


def test_ifrs_cash_debt_and_leases() -> None:
    p = ifrs_period(sap_like())
    assert p.cash is not None and math.isclose(p.cash, 9.772e9) and p.cash_row == "CashAndCashEquivalents + OtherCurrentFinancialAssets"
    assert components(p.cash_composition) == [("cash_equivalents", 8.22e9, "CashAndCashEquivalents"), ("short_term_investments", 1.552e9, "OtherCurrentFinancialAssets")]
    # Borrowings is the aggregate; the lease liability is present and stays out
    assert (p.total_debt, p.total_debt_source) == (6.15e9, "Borrowings")
    assert components(p.total_debt_composition) == [("total", 6.15e9, "Borrowings")]
    assert all(k.row not in DEFS.total_debt.ifrs.excluded for k in (p.total_debt_composition.components if p.total_debt_composition else []))
    # TSMC-like: no Borrowings, debt as bonds plus borrowings by group; current financial assets by category, summed
    tsm = {**{k: v for k, v in sap_like().items() if k not in ("Borrowings", "LongtermBorrowings", "OtherCurrentFinancialAssets")},
           "LongtermBorrowings": in_unit("EUR", twenty_f("2025-12-31", 31.824e9)), "CurrentPortionOfLongtermBorrowings": in_unit("EUR", twenty_f("2025-12-31", 59.858e9)),
           "NoncurrentPortionOfNoncurrentBondsIssued": in_unit("EUR", twenty_f("2025-12-31", 926.605e9)), "CurrentBondsIssuedAndCurrentPortionOfNoncurrentBondsIssued": in_unit("EUR", twenty_f("2025-12-31", 57.148e9)),
           "CurrentFinancialAssetsAtFairValueThroughOtherComprehensiveIncome": in_unit("EUR", twenty_f("2025-12-31", 192.203e9)), "CurrentFinancialAssetsAtAmortisedCost": in_unit("EUR", twenty_f("2025-12-31", 101.971e9)),
           "OtherCurrentFinancialAssets": in_unit("EUR", twenty_f("2025-12-31", 63.138e9))}
    p = ifrs_period(tsm)
    assert p.total_debt is not None and math.isclose(p.total_debt, (31.824 + 926.605 + 57.148 + 59.858) * 1e9)
    assert p.total_debt_source == "LongtermBorrowings + NoncurrentPortionOfNoncurrentBondsIssued + CurrentBondsIssuedAndCurrentPortionOfNoncurrentBondsIssued + CurrentPortionOfLongtermBorrowings"
    assert p.cash is not None and math.isclose(p.cash, (8.22 + 192.203 + 101.971) * 1e9)  # the category alternative wins over the other-financial-assets line
    # a current-borrowings total supersedes the short-term plus current-portion pair
    with_total = {**tsm, "CurrentBorrowingsAndCurrentPortionOfNoncurrentBorrowings": in_unit("EUR", twenty_f("2025-12-31", 70e9)), "ShorttermBorrowings": in_unit("EUR", twenty_f("2025-12-31", 10e9))}
    p = ifrs_period(with_total)
    assert p.total_debt is not None and math.isclose(p.total_debt, (31.824 + 926.605 + 57.148 + 70) * 1e9)
    lease_only = {k: v for k, v in sap_like().items() if k not in ("Borrowings", "LongtermBorrowings")}
    assert ifrs_period(lease_only).total_debt is None


def test_ifrs_delta_nwc_is_cash_flow_signed_for_assets_and_liabilities_alike() -> None:
    """TSMC FY2024 by hand: inventories -36.872 (a build-up, the statement's sign), trade
    payables +17.074 (an increase, an inflow); both flip by -1 into cash absorbed."""
    tsm = {**sap_like(), "AdjustmentsForDecreaseIncreaseInInventories": in_unit("EUR", twenty_f("2025-12-31", -36.872e9, start="2025-01-01")),
           "AdjustmentsForIncreaseDecreaseInTradeAccountPayable": in_unit("EUR", twenty_f("2025-12-31", 17.074e9, start="2025-01-01"))}
    p = ifrs_period(tsm)
    assert p.delta_nwc is not None and math.isclose(p.delta_nwc, -(-0.388 + 1.336 - 36.872 + 17.074) * 1e9)
    parts = components(p.delta_nwc_composition)
    assert all(n == "cash_flow_signed_components" for n, _, _ in parts) and ("cash_flow_signed_components", 36.872e9, "AdjustmentsForDecreaseIncreaseInInventories") in parts
    assert ("cash_flow_signed_components", -17.074e9, "AdjustmentsForIncreaseDecreaseInTradeAccountPayable") in parts
    assert p.delta_nwc_row is not None and p.delta_nwc_row.startswith("-AdjustmentsForDecreaseIncreaseInInventories - ")
    sap = ifrs_period(sap_like())
    assert sap.delta_nwc is not None and math.isclose(sap.delta_nwc, -(-0.388 + 1.336) * 1e9)
    notes: list[str] = []
    bank = ifrs_period({**sap_like(), "AdjustmentsForIncreaseDecreaseInDepositsFromCustomers": in_unit("EUR", twenty_f("2025-12-31", 401e9, start="2025-01-01"))}, notes=notes)
    assert bank.delta_nwc is None and notes == ["delta_nwc 2025-12-31: left null, unclassified working-capital tags: AdjustmentsForIncreaseDecreaseInDepositsFromCustomers"]


def test_ifrs_net_interest_income_recipe_and_ebit_rows() -> None:
    kspi = {**sap_like(), "InterestRevenueCalculatedUsingEffectiveInterestMethod": in_unit("EUR", twenty_f("2025-12-31", 1579.346e9, start="2025-01-01")),
            "InterestExpense": in_unit("EUR", twenty_f("2025-12-31", 825.849e9, start="2025-01-01"))}
    p = ifrs_period(kspi)
    assert p.net_interest_income is not None and math.isclose(p.net_interest_income, (1579.346 - 825.849) * 1e9)
    assert p.net_interest_income_row == "InterestRevenueCalculatedUsingEffectiveInterestMethod - InterestExpense"
    assert ifrs_period(sap_like()).net_interest_income is None  # neither leg: null, not zero
    no_operating = {k: v for k, v in sap_like().items() if k != "ProfitLossFromOperatingActivities"}
    p = ifrs_period({**no_operating, "FinanceCosts": in_unit("EUR", twenty_f("2025-12-31", 1.377e9, start="2025-01-01")), "FinanceIncome": in_unit("EUR", twenty_f("2025-12-31", 1.911e9, start="2025-01-01"))})
    assert p.ebit is not None and math.isclose(p.ebit, (10.27 + 1.377 - 1.911) * 1e9) and p.ebit_recipe == "pretax_plus_interest_less_nonoperating"
    assert p.ebit_row == "ProfitLossBeforeTax + FinanceCosts - FinanceIncome"


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


def submission(filed: str, report: str, form: str = "20-F") -> fetch.boundary.Submission:
    return fetch.boundary.Submission(form=form, filing_date=filed, accession=f"acc-{filed}", report_date=report)


def test_latest_annual_submission_reads_the_newest_10k_or_20f() -> None:
    index = {"filings": {"recent": {"form": ["6-K", "20-F/A", "20-F", "40-F", "20-F"], "filingDate": ["2026-08-01", "2026-07-01", "2026-06-18", "2026-05-01", "2025-06-20"],
                                    "accessionNumber": ["a", "b", "c", "d", "e"], "reportDate": ["2026-06-30", "2025-03-31", "2026-03-31", "2025-12-31", "2025-03-31"]}}}
    got, why = fetch_sec.latest_annual_submission(index)
    assert why is None and got is not None
    assert (got.form, got.filing_date, got.accession, got.report_date) == ("20-F", "2026-06-18", "c", "2026-03-31")
    assert fetch_sec.latest_annual_submission(None) == (None, "submissions: not found (HTTP 404)")
    forty_f = {"filings": {"recent": {"form": ["40-F"], "filingDate": ["2026-03-01"], "accessionNumber": ["x"], "reportDate": ["2025-12-31"]}}}
    assert fetch_sec.latest_annual_submission(forty_f) == (None, "submissions: no 10-K or 20-F in filings.recent")
    assert fetch_sec.latest_annual_submission({"filings": {}})[0] is None


def test_lag_and_vendor_freshness() -> None:
    notes: list[str] = []
    periods = fetch_sec.periods_from_facts(sap_like(), TAGS, DEFS, notes, taxonomy="ifrs-full", unit="EUR")  # facts end 2025-12-31, filed 2026-02-26
    assert fetch.lag_of(submission("2026-02-26", "2025-12-31"), periods) is None  # facts current
    assert fetch.lag_of(submission("2025-02-27", "2024-12-31"), periods) is None  # submissions older: nothing to say
    lag = fetch.lag_of(submission("2027-02-25", "2026-12-31"), periods)
    assert lag is not None and lag.text == "companyfacts lags submissions: 20-F filed 2027-02-25 (period 2026-12-31) not yet in facts; facts end 2025-12-31"
    assert fetch.lag_of(submission("2027-02-25", "2026-12-31"), []) is None and fetch.lag_of(None, periods) is None
    vendor_2026 = [fetch._period(date(2026, 12, 31), None, None, None)]  # pyright: ignore[reportPrivateUsage]
    vendor_2025 = [fetch._period(date(2025, 12, 31), None, None, None)]  # pyright: ignore[reportPrivateUsage]
    assert fetch.vendor_is_fresh(vendor_2026, submission("2027-02-25", "2026-12-31"))
    assert fetch.vendor_is_fresh([fetch._period(date(2026, 11, 30), None, None, None)], submission("2027-02-25", "2026-12-31"))  # pyright: ignore[reportPrivateUsage]
    assert not fetch.vendor_is_fresh(vendor_2025, submission("2027-02-25", "2026-12-31"))
    assert not fetch.vendor_is_fresh([], submission("2027-02-25", "2026-12-31"))
