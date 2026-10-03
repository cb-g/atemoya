"""Tag selection per period, the annual-fact filter, the fields composed per
reference/field_definitions.json (with the sign convention tested, not assumed), the
provider decision and the cross-check, on synthetic companyfacts."""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping
from datetime import date
from typing import cast

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
        "InterestExpense": usd(fact("2024-09-28", 3.0e9, start="2023-10-01")),
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
    # (4) noncurrent alone when nothing current is tagged at all; a lease alone with interest paid is nothing.
    p = period({"LongTermDebtNoncurrent": usd(fact("2025-12-31", 0.745e9)), **lease})
    assert (p.total_debt, p.total_debt_source) == (0.745e9, "LongTermDebtNoncurrent")
    p = period({**lease, "InterestExpense": usd(fact("2025-12-31", 3.5e6, start="2025-01-01"))})
    assert p.total_debt is None and p.total_debt_composition is None


def test_debt_absent_is_zero_only_when_the_filing_says_so_twice() -> None:
    """No debt tag and no interest tag: 0, recorded (Palantir). Either alone: null."""
    p = period({})
    assert p.total_debt == 0.0 and p.total_debt_source == fetch_sec.DEBT_FREE
    assert p.total_debt_composition is not None and p.total_debt_composition.components == []
    for tag in DEFS.total_debt.xbrl.interest_evidence:
        assert period({tag: usd(fact("2025-12-31", 1e6, start="2025-01-01"))}).total_debt is None
    p = period({"LongTermDebtNoncurrent": usd(fact("2025-12-31", 0.745e9))})
    assert p.total_debt == 0.745e9  # debt without interest is the debt
    # a debt tag on another year does not make this year zero: the rule is per period
    p = period({"InterestExpense": usd(fact("2024-12-31", 1e6, start="2024-01-01"))})
    assert p.total_debt == 0.0


def test_interest_evidence_has_a_sign_and_a_size() -> None:
    """(65) A trace of interest is not the filing saying twice that the filer owes nothing.
    Interest is evidence of debt only when it is an expense and when it is large enough
    against operating income to be borrowing rather than a facility's fees."""
    floor = fetch_sec.load_params().interest_evidence_floor.value
    assert floor == 0.005

    def with_interest(interest: float, operating: float | None) -> fetch.boundary.FiscalPeriod:
        gaap: dict[str, object] = {"InterestExpenseNonoperating": usd(fact("2025-12-31", interest, start="2025-01-01"))}
        if operating is not None:
            gaap["OperatingIncomeLoss"] = usd(fact("2025-12-31", operating, start="2025-01-01"))
        return period(gaap)

    # Deckers' shape: no borrowing filed, interest two tenths of a per cent of operating income
    p = with_interest(2.530e6, 1262.903e6)
    assert p.total_debt == 0.0
    assert p.total_debt_source is not None and "below the 0.50% floor" in p.total_debt_source
    assert "InterestExpenseNonoperating" in p.total_debt_source and "0.20%" in p.total_debt_source
    # at the floor exactly, and above it, the interest stands as evidence and the field is null
    assert with_interest(0.005 * 1000e6, 1000e6).total_debt is None
    assert with_interest(0.05 * 1000e6, 1000e6).total_debt is None
    # interest that is income is never evidence, whatever its size
    p = with_interest(-40e6, 1000e6)
    assert p.total_debt == 0.0
    assert p.total_debt_source is not None and "is interest income, not an expense" in p.total_debt_source
    # a filer that tags interest paid at zero paid none
    assert period({"InterestPaidNet": usd(fact("2025-12-31", 0.0, start="2025-01-01"))}).total_debt == 0.0
    # no operating income, or a loss, gives the floor nothing to measure against: evidence stands
    assert with_interest(2.530e6, None).total_debt is None
    assert with_interest(2.530e6, -9169e6).total_debt is None
    # and a filed debt line is still the debt, whatever the interest
    assert period({"LongTermDebtNoncurrent": usd(fact("2025-12-31", 0.745e9)),
                   "InterestExpenseNonoperating": usd(fact("2025-12-31", 1.0, start="2025-01-01")),
                   "OperatingIncomeLoss": usd(fact("2025-12-31", 1000e6, start="2025-01-01"))}).total_debt == 0.745e9


def test_debt_aggregate_is_first_choice_with_convertible_notes_beside_it() -> None:
    """Super Micro FY2026: bank debt as the aggregate, convertible notes beside it; AMD
    tags the aggregate beside a current portion it also tags as short-term borrowings."""
    smci = {"DebtLongtermAndShorttermCombinedAmount": usd(fact("2025-12-31", 4056.1e6)), "ConvertibleLongTermNotesPayable": usd(fact("2025-12-31", 4664.1e6)),
            "OperatingLeaseLiabilityNoncurrent": usd(fact("2025-12-31", 499e6))}
    p = period(smci)
    assert p.total_debt is not None and math.isclose(p.total_debt, 8720.2e6)
    assert p.total_debt_source == "DebtLongtermAndShorttermCombinedAmount + ConvertibleLongTermNotesPayable"
    assert components(p.total_debt_composition) == [("aggregate", 4056.1e6, "DebtLongtermAndShorttermCombinedAmount"), ("convertible", 4664.1e6, "ConvertibleLongTermNotesPayable")]
    amd = {"DebtLongtermAndShorttermCombinedAmount": usd(fact("2025-12-31", 3222e6)), "LongTermDebtNoncurrent": usd(fact("2025-12-31", 2348e6)),
           "LongTermDebtCurrent": usd(fact("2025-12-31", 874e6)), "ShortTermBorrowings": usd(fact("2025-12-31", 874e6))}
    p = period(amd)
    assert (p.total_debt, p.total_debt_source) == (3222e6, "DebtLongtermAndShorttermCombinedAmount")
    # convertible notes without the aggregate are one component, summed on their own (31)
    p = period({"ConvertibleLongTermNotesPayable": usd(fact("2025-12-31", 4664.1e6)), "InterestExpense": usd(fact("2025-12-31", 1e6, start="2025-01-01"))})
    assert (p.total_debt, p.total_debt_source) == (4664.1e6, "ConvertibleLongTermNotesPayable")


def test_debt_component_sum_when_no_aggregate_or_pair_is_filed() -> None:
    """ServiceNow files convertible notes alone; Caterpillar noncurrent plus short-term with no
    current portion (31). The absent-is-zero rule applies only with no component at all."""
    now = {"ConvertibleLongTermNotesPayable": usd(fact("2025-12-31", 1491e6)), "InterestPaidNet": usd(fact("2025-12-31", 22e6, start="2025-01-01"))}
    p = period(now)
    assert (p.total_debt, p.total_debt_source) == (1491e6, "ConvertibleLongTermNotesPayable")
    assert components(p.total_debt_composition) == [("convertible", 1491e6, "ConvertibleLongTermNotesPayable")]
    cat = {"LongTermDebtNoncurrent": usd(fact("2025-12-31", 30696e6)), "ShortTermBorrowings": usd(fact("2025-12-31", 5514e6)), "InterestPaidNet": usd(fact("2025-12-31", 1842e6, start="2025-01-01"))}
    p = period(cat)
    assert p.total_debt is not None and math.isclose(p.total_debt, 36210e6)
    assert p.total_debt_source == "LongTermDebtNoncurrent + ShortTermBorrowings"
    assert components(p.total_debt_composition) == [("noncurrent", 30696e6, "LongTermDebtNoncurrent"), ("short_term_borrowings", 5514e6, "ShortTermBorrowings")]
    # a complete pair still wins over the component sum, and the aggregate over both
    both = {**cat, "LongTermDebtCurrent": usd(fact("2025-12-31", 7120e6))}
    assert period(both).total_debt_source == "LongTermDebtNoncurrent + LongTermDebtCurrent + ShortTermBorrowings"
    assert period({**both, "DebtLongtermAndShorttermCombinedAmount": usd(fact("2025-12-31", 43324e6))}).total_debt == 43324e6
    # no component and no interest: zero, recorded; no component with interest: null
    assert period({}).total_debt_source == fetch_sec.DEBT_FREE
    assert period({"InterestPaidNet": usd(fact("2025-12-31", 22e6, start="2025-01-01"))}).total_debt is None


def test_delta_nwc_batch_one_kinds() -> None:
    """Each tag added from the first growth batch (31) carries its verified kind."""
    d = DEFS.delta_nwc.xbrl
    for tag in ("IncreaseDecreaseInRetailRelatedInventories", "IncreaseDecreaseInMaterialsAndSupplies", "IncreaseDecreaseInFinanceReceivables",
                "IncreaseDecreaseInMarginDepositsOutstanding", "IncreaseDecreaseInRestrictedCashAndInvestmentsForOperatingActivities"):
        assert tag in d.asset_components
    for tag in ("IncreaseDecreaseInAccountsPayableAndOtherOperatingLiabilities", "IncreaseDecreaseInOperatingLiabilities", "IncreaseDecreaseInAccruedSalaries",
                "IncreaseDecreaseInAirTrafficLiability1", "IncreaseDecreaseInFrequentFlyerLiability", "IncreaseDecreaseInInterestPayableNet", "IncreaseDecreaseInCustomerAdvances"):
        assert tag in d.liability_components
    assert "IncreaseDecreaseInPensionAndPostretirementObligations" in d.excluded
    # Home Depot FY2026 by hand: inventory grew 1.498bn (an outflow, added), payables fell (an outflow, added back)
    hd = {"IncreaseDecreaseInRetailRelatedInventories": usd(fact("2025-12-31", 1498e6, start="2025-01-01")),
          "IncreaseDecreaseInAccountsPayable": usd(fact("2025-12-31", -1058e6, start="2025-01-01")),
          "IncreaseDecreaseInPensionAndPostretirementObligations": usd(fact("2025-12-31", 400e6, start="2025-01-01"))}
    p = period(hd)
    assert p.delta_nwc is not None and math.isclose(p.delta_nwc, 1498e6 + 1058e6)  # the pension movement is excluded, not summed, not blocking
    assert components(p.delta_nwc_composition) == [("asset_components", 1498e6, "IncreaseDecreaseInRetailRelatedInventories"), ("liability_components", 1058e6, "IncreaseDecreaseInAccountsPayable")]


def test_aoci_sum_of_components_when_the_aggregate_is_absent() -> None:
    """Aflac FY2025 (31): three components filed, no aggregate."""
    afl = {"AccumulatedOtherComprehensiveIncomeLossAvailableForSaleSecuritiesAdjustmentNetOfTax": usd(fact("2025-12-31", -1809e6)),
           "AccumulatedOtherComprehensiveIncomeLossDefinedBenefitPensionAndOtherPostretirementPlansNetOfTax": usd(fact("2025-12-31", -86e6)),
           "AccumulatedOtherComprehensiveIncomeLossForeignCurrencyTranslationAdjustmentNetOfTax": usd(fact("2025-12-31", -4847e6))}
    p = period(afl)
    assert p.aoci is not None and math.isclose(p.aoci, -6742e6) and p.aoci_recipe == "sum_of_components"
    assert p.aoci_composition is not None and p.aoci_composition.definition == "accumulated_other_comprehensive_income_net_of_tax"
    assert [c.row for c in p.aoci_composition.components] == list(afl)
    # the aggregate wins when filed, recorded as filed; nothing filed leaves it null
    p = period({**afl, "AccumulatedOtherComprehensiveIncomeLossNetOfTax": usd(fact("2025-12-31", -5520e6))})
    assert (p.aoci, p.aoci_recipe, p.aoci_composition) == (-5520e6, "filed", None)
    assert period({}).aoci is None and period({}).aoci_recipe is None


def test_ffo_depreciation_is_the_largest_filed_total() -> None:
    """American Tower files DepreciationAmortizationAndAccretionNet alone; Equinix files two
    totals and the larger is the real-estate depreciation (31)."""
    base = {"NetIncomeLoss": usd(fact("2025-12-31", 2530e6, start="2025-01-01"))}
    p = period({**base, "DepreciationAmortizationAndAccretionNet": usd(fact("2025-12-31", 2042e6, start="2025-01-01"))})
    assert p.ffo is not None and math.isclose(p.ffo, 2530e6 + 2042e6)
    assert p.ffo_composition is not None and [(c.name, c.row) for c in p.ffo_composition.components][:2] == [("net_income", "NetIncomeLoss"), ("real_estate_depreciation", "DepreciationAmortizationAndAccretionNet")]
    p = period({**base, "DepreciationDepletionAndAmortization": usd(fact("2025-12-31", 2050e6, start="2025-01-01")),
                "DepreciationAmortizationAndAccretionNet": usd(fact("2025-12-31", 2066e6, start="2025-01-01"))})
    assert p.ffo is not None and math.isclose(p.ffo, 2530e6 + 2066e6)
    assert p.ffo_composition is not None and p.ffo_composition.components[1].row == "DepreciationAmortizationAndAccretionNet"


def test_interest_recipes_for_the_midcycle_nopat() -> None:
    """Delta files a net non-operating interest figure, Caterpillar only cash paid (31)."""
    p = period({"InterestExpenseDebt": usd(fact("2025-12-31", 1217e6, start="2025-01-01")), "InterestPaidNet": usd(fact("2025-12-31", 942e6, start="2025-01-01"))})
    assert (p.interest_expense, p.interest_expense_row, p.interest_recipe) == (1217e6, "InterestExpenseDebt", "filed")
    p = period({"InterestIncomeExpenseNonoperatingNet": usd(fact("2025-12-31", -679e6, start="2025-01-01")), "InterestPaidNet": usd(fact("2025-12-31", 850e6, start="2025-01-01"))})
    assert (p.interest_expense, p.interest_expense_row, p.interest_recipe) == (679e6, "InterestIncomeExpenseNonoperatingNet", "net_nonoperating_interest")
    p = period({"InterestPaidNet": usd(fact("2025-12-31", 1842e6, start="2025-01-01"))})
    assert (p.interest_expense, p.interest_expense_row, p.interest_recipe) == (1842e6, "InterestPaidNet", "interest_paid_stands_in")
    assert period({}).interest_expense is None and period({}).interest_recipe is None
    definition = DEFS.interest_expense
    assert definition is not None and definition.recipes == ["filed", "net_nonoperating_interest", "interest_paid_stands_in"]


def test_delta_nwc_three_kinds_and_the_excluded_tags() -> None:
    """Each kind's sign on a fixture: an asset grows (outflow, added), a liability grows
    (inflow, subtracted), a net balance grows (outflow, added); excluded tags never sum."""
    three = {
        "IncreaseDecreaseInAccountsReceivable": usd(fact("2025-12-31", 1815e6, start="2025-01-01")),
        "IncreaseDecreaseInAccountsPayableTrade": usd(fact("2025-12-31", -14e6, start="2025-01-01")),
        "IncreaseDecreaseInOtherOperatingCapitalNet": usd(fact("2025-12-31", 1250e6, start="2025-01-01")),
        "IncreaseDecreaseInOtherNoncurrentAssetsAndLiabilitiesNet": usd(fact("2025-12-31", -195e6, start="2025-01-01")),
        "IncreaseDecreaseInEquitySecuritiesFvNi": usd(fact("2025-12-31", 514e6, start="2025-01-01")),
        "IncreaseDecreaseInAssetRetirementObligations": usd(fact("2025-12-31", 12e6, start="2025-01-01")),
    }
    p = period(three)
    assert p.delta_nwc is not None and math.isclose(p.delta_nwc, 1815e6 + 14e6 + 1250e6 - 195e6)
    assert components(p.delta_nwc_composition) == [
        ("asset_components", 1815e6, "IncreaseDecreaseInAccountsReceivable"),
        ("liability_components", 14e6, "IncreaseDecreaseInAccountsPayableTrade"),
        ("net_components", 1250e6, "IncreaseDecreaseInOtherOperatingCapitalNet"),
        ("net_components", -195e6, "IncreaseDecreaseInOtherNoncurrentAssetsAndLiabilitiesNet"),
    ]
    for tag in ("IncreaseDecreaseInPropertyAndOtherTaxesPayable", "IncreaseDecreaseInDueToRelatedParties", "IncreaseDecreaseInOtherAccountsPayable"):
        assert tag in DEFS.delta_nwc.xbrl.liability_components
    # META FY2025 by hand: 1815 + 481 + 89 assets, -14 + 1077 + 437 liabilities -> 885m, the vendor's line
    meta = {
        "IncreaseDecreaseInAccountsReceivable": usd(fact("2025-12-31", 1815e6, start="2025-01-01")),
        "IncreaseDecreaseInOtherOperatingAssets": usd(fact("2025-12-31", 481e6, start="2025-01-01")),
        "IncreaseDecreaseInPrepaidDeferredExpenseAndOtherAssets": usd(fact("2025-12-31", 89e6, start="2025-01-01")),
        "IncreaseDecreaseInAccountsPayableTrade": usd(fact("2025-12-31", -14e6, start="2025-01-01")),
        "IncreaseDecreaseInAccruedLiabilities": usd(fact("2025-12-31", 1077e6, start="2025-01-01")),
        "IncreaseDecreaseInOtherNoncurrentLiabilities": usd(fact("2025-12-31", 437e6, start="2025-01-01")),
    }
    p = period(meta)
    assert p.delta_nwc is not None and math.isclose(p.delta_nwc, 885e6)
    # a tag in none of the four kinds still refuses, naming it
    notes: list[str] = []
    p = period({**meta, "IncreaseDecreaseInTradingSecurities": usd(fact("2025-12-31", 1e6, start="2025-01-01"))}, notes)
    assert p.delta_nwc is None and notes == ["delta_nwc 2025-12-31: left null, unclassified working-capital tags: IncreaseDecreaseInTradingSecurities"]


def test_interest_expense_is_carried_per_period_on_both_providers() -> None:
    p = period({"InterestExpenseDebt": usd(fact("2025-12-31", 1217e6, start="2025-01-01"))})
    assert (p.interest_expense, p.interest_expense_row) == (1217e6, "InterestExpenseDebt")
    assert period({}).interest_expense is None
    rows = fetch._income_values({"Pretax Income": 10.0, "Interest Expense Non Operating": 2.5, "Net Income": 8.0})  # pyright: ignore[reportPrivateUsage]
    assert (rows["interest_expense"], rows["interest_expense_row"]) == (2.5, "Interest Expense Non Operating")


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
    # the third recipe rides beside a derived figure only (invented figures): revenues less the
    # filer's total costs and expenses, plus interest unless it is filed as non-operating
    assert p.ebit_alternative is None and with_operating.ebit_alternative is None   # no total costs filed; and never beside a filed operating income
    totals = {"Revenues": usd(fact("2025-12-31", 100e9, start="2025-01-01")), "CostsAndExpenses": usd(fact("2025-12-31", 70e9, start="2025-01-01"))}
    below = period({**jnj, **totals})
    assert below.ebit_recipe == "pretax_plus_interest_less_nonoperating" and below.ebit_alternative == 30e9   # interest filed as non-operating: not added back
    assert components(below.ebit_alternative_composition) == [("total_revenue", 100e9, "Revenues"), ("costs_and_expenses", -70e9, "CostsAndExpenses")]
    inside = {k: v for k, v in jnj.items() if k != "InterestExpenseNonoperating"}
    inside["InterestExpense"] = usd(fact("2025-12-31", 2e9, start="2025-01-01"))
    within = period({**inside, **totals})
    assert within.ebit_alternative == 32e9   # interest inside the costs: added back
    assert within.ebit_alternative_composition is not None and within.ebit_alternative_composition.definition == "revenues_less_costs_and_expenses"
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


def test_ffo_per_nareit_with_and_without_the_optional_components() -> None:
    """Realty Income FY2025 by hand: 1058.6 + 2524.2 + 471.3 - 177.6; then each optional
    component absent (taken as 0, recorded), then a required one absent (null)."""
    o = {"NetIncomeLossAvailableToCommonStockholdersBasic": usd(fact("2025-12-31", 1058.6e6, start="2025-01-01")),
         "NetIncomeLoss": usd(fact("2025-12-31", 1060.0e6, start="2025-01-01")),
         "DepreciationDepletionAndAmortization": usd(fact("2025-12-31", 2524.2e6, start="2025-01-01")),
         "ImpairmentOfRealEstate": usd(fact("2025-12-31", 471.3e6, start="2025-01-01")),
         "GainLossOnSaleOfProperties": usd(fact("2025-12-31", 177.6e6, start="2025-01-01"))}
    p = period(o)
    assert p.ffo is not None and math.isclose(p.ffo, (1058.6 + 2524.2 + 471.3 - 177.6) * 1e6)
    assert components(p.ffo_composition) == [("net_income", 1058.6e6, "NetIncomeLossAvailableToCommonStockholdersBasic"), ("real_estate_depreciation", 2524.2e6, "DepreciationDepletionAndAmortization"),
                                             ("real_estate_impairment", 471.3e6, "ImpairmentOfRealEstate"), ("gain_on_property_sales", -177.6e6, "GainLossOnSaleOfProperties")]
    assert p.ffo_composition is not None and p.ffo_composition.definition == DEFS.ffo.name
    no_impairment = period({k: v for k, v in o.items() if k != "ImpairmentOfRealEstate"})
    assert no_impairment.ffo is not None and math.isclose(no_impairment.ffo, (1058.6 + 2524.2 - 177.6) * 1e6)
    assert ("real_estate_impairment", 0.0, "not filed, taken as 0") in components(no_impairment.ffo_composition)
    no_gains = period({k: v for k, v in o.items() if k != "GainLossOnSaleOfProperties"})
    assert no_gains.ffo is not None and math.isclose(no_gains.ffo, (1058.6 + 2524.2 + 471.3) * 1e6)
    assert ("gain_on_property_sales", 0.0, "not filed, taken as 0") in components(no_gains.ffo_composition)
    no_depreciation = period({k: v for k, v in o.items() if k != "DepreciationDepletionAndAmortization"})
    assert no_depreciation.ffo is None and no_depreciation.ffo_composition is None  # required, never zero
    # the vendor-style tag order: net income available to common first, NetIncomeLoss second
    assert period({k: v for k, v in o.items() if k != "NetIncomeLossAvailableToCommonStockholdersBasic"}).ffo_composition.components[0].row == "NetIncomeLoss"  # pyright: ignore[reportOptionalMemberAccess]


def test_weighted_average_shares_per_period_diluted_then_basic_recorded() -> None:
    """The flow-per-share count is the period's own weighted-average diluted count; basic
    only when no diluted one is filed, and the tag says so; a count is never a point count."""
    def shares(tag: str, *facts: dict[str, object]) -> dict[str, object]:
        return {tag: {"units": {"shares": list(facts)}}}

    both = {**anchors(), **shares("WeightedAverageNumberOfDilutedSharesOutstanding", fact("2025-12-31", 908.3e6, start="2025-01-01")),
            **shares("WeightedAverageNumberOfSharesOutstandingBasic", fact("2025-12-31", 907.2e6, start="2025-01-01")),
            **shares("CommonStockSharesOutstanding", fact("2025-12-31", 932.4e6))}
    p = period(both)
    assert (p.weighted_shares, p.weighted_shares_tag) == (908.3e6, "WeightedAverageNumberOfDilutedSharesOutstanding")
    basic_only = {**anchors(), **shares("WeightedAverageNumberOfSharesOutstandingBasic", fact("2025-12-31", 907.2e6, start="2025-01-01")),
                  **shares("CommonStockSharesOutstanding", fact("2025-12-31", 932.4e6))}
    p = period(basic_only)
    assert (p.weighted_shares, p.weighted_shares_tag) == (907.2e6, "WeightedAverageNumberOfSharesOutstandingBasic")
    point_only = {**anchors(), **shares("CommonStockSharesOutstanding", fact("2025-12-31", 932.4e6)), **shares("EntityCommonStockSharesOutstanding", fact("2026-02-20", 932.4e6))}
    p = period(point_only)
    assert p.weighted_shares is None and p.weighted_shares_tag is None  # a point count never stands in
    assert DEFS.shares_for_flows.xbrl == ["WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic"]
    assert "CommonStockSharesOutstanding" not in DEFS.shares_for_flows.xbrl and "EntityCommonStockSharesOutstanding" not in DEFS.shares_for_flows.xbrl


def test_depreciation_is_the_largest_filed_total_with_candidates_recorded() -> None:
    """Valero FY2025 (27): three tags present, the sub-line came second in list order."""
    vlo = {
        "DepreciationAndAmortization": usd(fact("2025-12-31", 63e6, start="2025-01-01")),
        "DepreciationAmortizationAndAccretionNet": usd(fact("2025-12-31", 3158e6, start="2025-01-01")),
        "DepreciationDepletionAndAmortization": usd(fact("2025-12-31", 2300e6, start="2025-01-01")),
    }
    p = period(vlo)
    assert (p.depreciation_amortization, p.depreciation_amortization_row) == (3158e6, "DepreciationAmortizationAndAccretionNet")
    assert p.depreciation_amortization_candidates is not None
    assert [(c.name, c.value, c.row) for c in p.depreciation_amortization_candidates] == [
        ("total", 2300e6, "DepreciationDepletionAndAmortization"), ("total", 63e6, "DepreciationAndAmortization"), ("total", 3158e6, "DepreciationAmortizationAndAccretionNet")]
    # one total: taken as before, one candidate
    p = period({"DepreciationDepletionAndAmortization": usd(fact("2025-12-31", 11.7e9, start="2025-01-01"))})
    assert (p.depreciation_amortization, p.depreciation_amortization_row) == (11.7e9, "DepreciationDepletionAndAmortization")
    assert p.depreciation_amortization_candidates is not None and len(p.depreciation_amortization_candidates) == 1
    # the components fallback only when no total is filed, and no candidates then
    p = period({"Depreciation": usd(fact("2025-12-31", 10.76e9, start="2025-01-01")), "AmortizationOfIntangibleAssets": usd(fact("2025-12-31", 0.95e9, start="2025-01-01"))})
    assert p.depreciation_amortization is not None and math.isclose(p.depreciation_amortization, 11.71e9)
    assert p.depreciation_amortization_row == "Depreciation + AmortizationOfIntangibleAssets" and p.depreciation_amortization_candidates is None
    p = period({"Depreciation": usd(fact("2025-12-31", 10.76e9, start="2025-01-01")), "DepreciationAndAmortization": usd(fact("2025-12-31", 63e6, start="2025-01-01"))})
    assert p.depreciation_amortization == 63e6  # a filed total, however small, is the total; the fallback never competes
    # one list of totals: the definition's and the per-period selection's
    definition = DEFS.depreciation_amortization
    assert definition is not None and definition.rule == "largest_filed_total"
    assert definition.xbrl.totals == dict(TAGS.fields)["depreciation_amortization"].tags
    assert definition.ifrs.pure + definition.ifrs.totals == dict(TAGS.ifrs_full_fields)["depreciation_amortization"].tags


def ifrs_dna_period(facts: Mapping[str, object]) -> fetch.boundary.FiscalPeriod:
    anchors = {"ProfitLossAttributableToOwnersOfParent": usd(fact("2025-12-31", 10e9, start="2025-01-01", form="20-F")),
               "EquityAttributableToOwnersOfParent": usd(fact("2025-12-31", 50e9, form="20-F"))}
    return fetch_sec.periods_from_facts({**anchors, **facts}, TAGS, DEFS, [], taxonomy="ifrs-full", unit="USD")[0]


def twenty_f_fact(tag: str, v: float) -> dict[str, object]:
    return {tag: usd(fact("2025-12-31", v, start="2025-01-01", form="20-F"))}


def test_ifrs_depreciation_excludes_impairment_by_recipe() -> None:
    """Shell FY2025 by hand (32): inclusive 25,299 less impairment 3,175 plus reversal 42;
    the pure tag wins when filed (BP); components stand in for an absent total; the plain
    adjustment tag is a total only when neither is filed (SAP)."""
    f = twenty_f_fact
    shell = {**f("DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss", 25299e6),
             **f("AdjustmentsForDepreciationAndAmortisationExpense", 25299e6),
             **f("ImpairmentLossRecognisedInProfitOrLoss", 3175e6), **f("ImpairmentLossRecognisedInProfitOrLossPropertyPlantAndEquipment", 2799e6),
             **f("ReversalOfImpairmentLossRecognisedInProfitOrLoss", 42e6)}
    p = ifrs_dna_period(shell)
    assert p.depreciation_amortization is not None and math.isclose(p.depreciation_amortization, 22166e6)
    assert p.depreciation_amortization_recipe == "inclusive_less_impairment" and p.depreciation_amortization_candidates is None
    assert components(p.depreciation_amortization_composition) == [
        ("inclusive", 25299e6, "DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss"),
        ("impairment", -3175e6, "ImpairmentLossRecognisedInProfitOrLoss"), ("reversal", 42e6, "ReversalOfImpairmentLossRecognisedInProfitOrLoss")]
    # components stand in when the totals are not filed; an untagged impairment is never subtracted
    p = ifrs_dna_period({**f("DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss", 25299e6),
                     **f("ImpairmentLossRecognisedInProfitOrLossPropertyPlantAndEquipment", 2799e6), **f("ImpairmentLossRecognisedInProfitOrLossGoodwill", 161e6),
                     **f("ReversalOfImpairmentLossRecognisedInProfitOrLossPropertyPlantAndEquipment", 42e6)})
    assert p.depreciation_amortization is not None and math.isclose(p.depreciation_amortization, 25299e6 - 2799e6 - 161e6 + 42e6)
    assert [c.name for c in (p.depreciation_amortization_composition.components if p.depreciation_amortization_composition else [])] == ["inclusive", "impairment_component", "impairment_component", "reversal_component"]
    p = ifrs_dna_period(f("DepreciationAmortisationAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss", 25299e6))
    assert p.depreciation_amortization == 25299e6 and p.depreciation_amortization_recipe == "inclusive_less_impairment"
    # the pure tag first, whatever else is filed (BP)
    p = ifrs_dna_period({**shell, **f("DepreciationAndAmortisationExpense", 17822e6)})
    assert (p.depreciation_amortization, p.depreciation_amortization_row, p.depreciation_amortization_recipe) == (17822e6, "DepreciationAndAmortisationExpense", "pure")
    assert p.depreciation_amortization_composition is None
    # the plain adjustment tag stands as a total only when neither is filed (SAP)
    p = ifrs_dna_period(f("AdjustmentsForDepreciationAndAmortisationExpense", 1311e6))
    assert (p.depreciation_amortization, p.depreciation_amortization_recipe) == (1311e6, "total")
    assert ifrs_dna_period({}).depreciation_amortization is None
    # (40) the component sum when no total of any kind is filed (TSMC), both tags required,
    # the right-of-use line never added; a pure tag beats the components when both exist
    p = ifrs_dna_period({**f("DepreciationExpense", 653610.5e6), **f("AmortisationExpense", 9186.1e6), **f("DepreciationRightofuseAssets", 3679.5e6)})
    assert p.depreciation_amortization is not None and math.isclose(p.depreciation_amortization, 662796.6e6)
    assert p.depreciation_amortization_recipe == "sum_of_components_ifrs" and p.depreciation_amortization_candidates is None
    assert components(p.depreciation_amortization_composition) == [("component", 653610.5e6, "DepreciationExpense"), ("component", 9186.1e6, "AmortisationExpense")]
    assert ifrs_dna_period(f("DepreciationExpense", 653610.5e6)).depreciation_amortization is None  # one component alone is not the field
    assert ifrs_dna_period(f("AmortisationExpense", 9186.1e6)).depreciation_amortization is None
    p = ifrs_dna_period({**f("DepreciationExpense", 653610.5e6), **f("AmortisationExpense", 9186.1e6), **f("DepreciationAndAmortisationExpense", 17822e6)})
    assert (p.depreciation_amortization, p.depreciation_amortization_recipe) == (17822e6, "pure")
    # the cash-flow reconciliation's own pair, last and both required (invented figures); the
    # expense pair beats it when both pairs are filed
    p = ifrs_dna_period({**f("AdjustmentsForDepreciationExpense", 700e6), **f("AdjustmentsForAmortisationExpense", 300e6)})
    assert (p.depreciation_amortization, p.depreciation_amortization_recipe) == (1000e6, "sum_of_adjustment_components_ifrs")
    assert components(p.depreciation_amortization_composition) == [("component", 700e6, "AdjustmentsForDepreciationExpense"), ("component", 300e6, "AdjustmentsForAmortisationExpense")]
    assert ifrs_dna_period(f("AdjustmentsForDepreciationExpense", 700e6)).depreciation_amortization is None
    p = ifrs_dna_period({**f("AdjustmentsForDepreciationExpense", 700e6), **f("AdjustmentsForAmortisationExpense", 300e6), **f("DepreciationExpense", 650e6), **f("AmortisationExpense", 250e6)})
    assert (p.depreciation_amortization, p.depreciation_amortization_recipe) == (900e6, "sum_of_components_ifrs")
    p = ifrs_dna_period({**f("DepreciationExpense", 653610.5e6), **f("AmortisationExpense", 9186.1e6), **f("AdjustmentsForDepreciationAndAmortisationExpense", 1311e6)})
    assert (p.depreciation_amortization, p.depreciation_amortization_recipe) == (1311e6, "total")


def test_delta_nwc_batch_two_kinds() -> None:
    """(54) Each tag the second growth batch's gaps needed carries its verified kind, and a
    broker-dealer's operating-section balances sum with the sign the vendor groups them by."""
    d = DEFS.delta_nwc.xbrl
    for tag in ("IncreaseDecreaseInIncomeTaxesReceivable", "IncreaseDecreaseInInventoriesAndOtherOperatingAssets",
                "IncreaseDecreaseInBrokerageReceivables", "IncreaseDecreaseInDepositOtherAssets",
                "IncreaseDecreaseInSecuritiesBorrowed"):
        assert tag in d.asset_components
    for tag in ("IncreaseDecreaseInDeferredCompensation", "IncreaseDecreaseInPayablesToCustomers",
                "IncreaseDecreaseInSecuritiesLoanedTransactions", "IncreaseDecreaseInOtherDeferredLiability"):
        assert tag in d.liability_components
    # HCA FY2025 by hand: receivables and inventories-and-other grew (outflows, added),
    # payables and accrued liabilities grew (an inflow, subtracted).
    hca = {"IncreaseDecreaseInAccountsReceivable": usd(fact("2025-12-31", 94e6, start="2025-01-01")),
           "IncreaseDecreaseInInventoriesAndOtherOperatingAssets": usd(fact("2025-12-31", 154e6, start="2025-01-01")),
           "IncreaseDecreaseInAccountsPayableAndAccruedLiabilities": usd(fact("2025-12-31", 666e6, start="2025-01-01"))}
    p = period(hca)
    assert p.delta_nwc is not None and math.isclose(p.delta_nwc, 94e6 + 154e6 - 666e6)
    # Robinhood FY2025 by hand: the customer and counterparty balances on both sides.
    hood = {"IncreaseDecreaseInAccountsReceivable": usd(fact("2025-12-31", 9106e6, start="2025-01-01")),
            "IncreaseDecreaseInBrokerageReceivables": usd(fact("2025-12-31", -62e6, start="2025-01-01")),
            "IncreaseDecreaseInDepositOtherAssets": usd(fact("2025-12-31", 213e6, start="2025-01-01")),
            "IncreaseDecreaseInSecuritiesBorrowed": usd(fact("2025-12-31", -828e6, start="2025-01-01")),
            "IncreaseDecreaseInPayablesToCustomers": usd(fact("2025-12-31", 3423e6, start="2025-01-01")),
            "IncreaseDecreaseInSecuritiesLoanedTransactions": usd(fact("2025-12-31", 4163e6, start="2025-01-01"))}
    p = period(hood)
    assert p.delta_nwc is not None and math.isclose(p.delta_nwc, (9106 - 62 + 213 - 828 - 3423 - 4163) * 1e6)
    # Okta FY2026 by hand: the deferred-compensation obligation fell, so cash left.
    okta = {"IncreaseDecreaseInAccountsReceivable": usd(fact("2025-12-31", 70e6, start="2025-01-01")),
            "IncreaseDecreaseInDeferredCompensation": usd(fact("2025-12-31", -245e6, start="2025-01-01"))}
    p = period(okta)
    assert p.delta_nwc is not None and math.isclose(p.delta_nwc, 70e6 + 245e6)


def test_debt_convertible_balance_tags_are_appended_after_the_existing_ones() -> None:
    """(54) Okta tags no debt but its convertible notes; a filer tagging the ordinary
    long-term pair takes that pair, because the convertible tags sit after it."""
    okta = {"ConvertibleDebtNoncurrent": usd(fact("2025-12-31", 0.0)),
            "ConvertibleDebtCurrent": usd(fact("2025-12-31", 350e6))}
    p = period(okta)
    assert p.total_debt is not None and math.isclose(p.total_debt, 350e6)
    assert p.total_debt_source == "ConvertibleDebtNoncurrent + ConvertibleDebtCurrent"
    both = {**okta, "LongTermDebtNoncurrent": usd(fact("2025-12-31", 31e9)), "DebtCurrent": usd(fact("2025-12-31", 9e9))}
    p = period(both)
    assert p.total_debt is not None and math.isclose(p.total_debt, 40e9)
    assert p.total_debt_source == "LongTermDebtNoncurrent + DebtCurrent"


def test_interest_on_borrowings_blocks_the_absent_is_zero_rule() -> None:
    """(54) A filer that tags interest on borrowings is not debt-free, so an absent debt
    line stays absent; with neither, debt is 0 as before."""
    assert period({"InterestExpenseBorrowings": usd(fact("2025-12-31", 32e6, start="2025-01-01"))}).total_debt is None
    p = period({})
    assert p.total_debt == 0.0 and p.total_debt_source == fetch_sec.DEBT_FREE
    # evidence only: interest on borrowings is a component on a deposit-taking filer, so it
    # is never the filer's interest-expense line and never derives an EBIT
    assert "InterestExpenseBorrowings" in DEFS.total_debt.xbrl.interest_evidence
    assert "InterestExpenseBorrowings" not in DEFS.ebit.xbrl.interest_expense
    only_borrowings = {"InterestExpenseBorrowings": usd(fact("2025-12-31", 32e6, start="2025-01-01")),
                       "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest": usd(fact("2025-12-31", 2108e6, start="2025-01-01"))}
    assert period(only_borrowings).ebit is None


def test_depreciation_reads_the_cash_flow_lines_before_the_notes() -> None:
    """(54, 62) OtherDepreciationAndAmortization is the filer's own depreciation-and-amortisation
    line in the cash-flow reconciliation, read with the amortisation line beside it and never
    displacing a filed total; the note pair is below both."""
    other = {"OtherDepreciationAndAmortization": usd(fact("2025-12-31", 37.972e6, start="2025-01-01"))}
    p = period(other)
    assert p.depreciation_amortization is not None and math.isclose(p.depreciation_amortization, 37.972e6)
    assert p.depreciation_amortization_row == "OtherDepreciationAndAmortization"
    assert p.depreciation_amortization_recipe == "cash_flow_lines"
    # a filed total wins even when it is smaller, because the line is not a candidate
    p = period({**other, "DepreciationDepletionAndAmortization": usd(fact("2025-12-31", 20e6, start="2025-01-01"))})
    assert p.depreciation_amortization is not None and math.isclose(p.depreciation_amortization, 20e6)
    assert p.depreciation_amortization_recipe is None
    # (62) but the note figures do not: a filer tagging both takes the combined line, with the
    # amortisation line added, and the note pair is not what the reconciliation says
    p = period({**other, "Depreciation": usd(fact("2025-12-31", 6e6, start="2025-01-01")),
                "AmortizationOfIntangibleAssets": usd(fact("2025-12-31", 9e6, start="2025-01-01")),
                "AdjustmentForAmortization": usd(fact("2025-12-31", 22.5e6, start="2025-01-01"))})
    assert p.depreciation_amortization is not None and math.isclose(p.depreciation_amortization, 60.472e6)
    assert p.depreciation_amortization_row == "OtherDepreciationAndAmortization + AdjustmentForAmortization"
    assert components(p.depreciation_amortization_composition) == [
        ("combined_line", 37.972e6, "OtherDepreciationAndAmortization"),
        ("amortization_line", 22.5e6, "AdjustmentForAmortization")]


def test_the_note_pair_needs_both_parts_or_a_filer_with_no_intangibles() -> None:
    """(62) Depreciation alone is a filer's whole D&A only where it has no intangibles to
    amortise. With a finite-lived intangibles balance filed and no amortisation tagged, the
    line exists and is untagged, so the field is missing rather than understated."""
    depreciation = {"Depreciation": usd(fact("2025-12-31", 441e6, start="2025-01-01"))}
    # no intangibles balance: the escape, and the row names the one element read
    p = period(depreciation)
    assert p.depreciation_amortization == 441e6 and p.depreciation_amortization_row == "Depreciation"
    # a finite-lived intangibles balance and no amortisation anywhere: refused
    p = period({**depreciation, "FiniteLivedIntangibleAssetsNet": usd(fact("2025-12-31", 21.143e9))})
    assert p.depreciation_amortization is None and p.depreciation_amortization_row is None
    # the note element completes the pair
    p = period({**depreciation, "FiniteLivedIntangibleAssetsNet": usd(fact("2025-12-31", 21.143e9)),
                "AmortizationOfIntangibleAssets": usd(fact("2025-12-31", 2.8e9, start="2025-01-01"))})
    assert p.depreciation_amortization is not None and math.isclose(p.depreciation_amortization, 3.241e9)
    assert p.depreciation_amortization_row == "Depreciation + AmortizationOfIntangibleAssets"
    # the reconciliation's own amortisation line is preferred over the note element
    p = period({**depreciation, "FiniteLivedIntangibleAssetsNet": usd(fact("2025-12-31", 21.143e9)),
                "AmortizationOfIntangibleAssets": usd(fact("2025-12-31", 2.8e9, start="2025-01-01")),
                "AdjustmentForAmortization": usd(fact("2025-12-31", 1.721e9, start="2025-01-01"))})
    assert p.depreciation_amortization is not None and math.isclose(p.depreciation_amortization, 2.162e9)
    assert p.depreciation_amortization_row == "Depreciation + AdjustmentForAmortization"
    # the gross balance counts as much as the net one
    assert period({**depreciation, "FiniteLivedIntangibleAssetsGross": usd(fact("2025-12-31", 27.5e9))}).depreciation_amortization is None


def test_the_cash_aggregate_that_already_carries_the_investments() -> None:
    """(62) A filer presenting one balance-sheet line for cash, equivalents and short-term
    investments tags CashCashEquivalentsAndShortTermInvestments and nothing beside it; the
    investments component is not added again, and the element never displaces one that resolves."""
    aggregate = {"CashCashEquivalentsAndShortTermInvestments": usd(fact("2025-12-31", 8.261e9))}
    p = period(aggregate)
    assert p.cash is not None and math.isclose(p.cash, 8.261e9)
    assert p.cash_row == "CashCashEquivalentsAndShortTermInvestments"
    assert components(p.cash_composition) == [("cash_and_investments", 8.261e9, "CashCashEquivalentsAndShortTermInvestments")]
    # a short-term investments tag beside it is NOT added: the aggregate already carries it
    p = period({**aggregate, "ShortTermInvestments": usd(fact("2025-12-31", 1.2e9))})
    assert p.cash is not None and math.isclose(p.cash, 8.261e9)
    # and a cash-equivalents element resolves first, with the investments added as before
    p = period({**aggregate, "CashAndCashEquivalentsAtCarryingValue": usd(fact("2025-12-31", 7.0e9)),
                "ShortTermInvestments": usd(fact("2025-12-31", 1.2e9))})
    assert p.cash is not None and math.isclose(p.cash, 8.2e9)
    assert p.cash_row == "CashAndCashEquivalentsAtCarryingValue + ShortTermInvestments"


def test_capex_takes_capitalised_software_only_when_nothing_else_is_filed() -> None:
    """(54) Veeva's only investing capital outflow is capitalised internal-use software."""
    assert period({"PaymentsForSoftware": usd(fact("2025-12-31", 29.131e6, start="2025-01-01"))}).capex == 29.131e6
    both = {"PaymentsForSoftware": usd(fact("2025-12-31", 29.131e6, start="2025-01-01")),
            "PaymentsToAcquirePropertyPlantAndEquipment": usd(fact("2025-12-31", 9.633e6, start="2025-01-01"))}
    assert period(both).capex == 9.633e6


def test_ffo_is_refused_when_the_filers_leases_are_financing_receivables() -> None:
    """(54) VICI: no real-estate depreciation to add back because the properties are net
    investments in leases earning interest. The balance alone is not enough — MetLife holds
    one inside an insurance portfolio and never asks for FFO."""
    vici = {"NetIncomeLoss": usd(fact("2025-12-31", 2775.493e6, start="2025-01-01")),
            "NetInvestmentInLeaseExcludingAccruedInterestAfterAllowanceForCreditLoss": usd(fact("2025-12-31", 23706.563e6)),
            "SalesTypeLeaseInterestIncome": usd(fact("2025-12-31", 2125.367e6, start="2025-01-01"))}
    p = period(vici)
    assert p.ffo is None and p.ffo_composition is None
    assert p.ffo_unavailable == fetch_sec.FINANCING_LEASES
    balance_only = {k: v for k, v in vici.items() if k != "SalesTypeLeaseInterestIncome"}
    assert period(balance_only).ffo_unavailable is None
    # a filer that does file real-estate depreciation computes FFO and carries no reason
    p = period({**vici, "DepreciationDepletionAndAmortization": usd(fact("2025-12-31", 1000e6, start="2025-01-01"))})
    assert p.ffo is not None and p.ffo_unavailable is None


def test_a_derivative_position_is_not_working_capital() -> None:
    """(55) MercadoLibre's one unclassified tag: the net carrying value of derivative
    instruments is a financial position, excluded like equity securities at fair value, so
    it is neither summed nor allowed to leave the field null."""
    assert "IncreaseDecreaseInDerivativeAssetsAndLiabilities" in DEFS.delta_nwc.xbrl.excluded
    meli = {"IncreaseDecreaseInAccountsReceivable": usd(fact("2025-12-31", 1508e6, start="2025-01-01")),
            "IncreaseDecreaseInInventories": usd(fact("2025-12-31", 235e6, start="2025-01-01")),
            "IncreaseDecreaseInOtherOperatingAssets": usd(fact("2025-12-31", 491e6, start="2025-01-01")),
            "IncreaseDecreaseInAccountsPayableAndAccruedLiabilities": usd(fact("2025-12-31", 1487e6, start="2025-01-01")),
            "IncreaseDecreaseInOperatingLeaseLiability": usd(fact("2025-12-31", -408e6, start="2025-01-01")),
            "IncreaseDecreaseInOtherOperatingLiabilities": usd(fact("2025-12-31", 145e6, start="2025-01-01")),
            "IncreaseDecreaseInDerivativeAssetsAndLiabilities": usd(fact("2025-12-31", -117e6, start="2025-01-01"))}
    notes: list[str] = []
    p = period(meli, notes)
    assert p.delta_nwc is not None and math.isclose(p.delta_nwc, (1508 + 235 + 491 - 1487 + 408 - 145) * 1e6)
    assert notes == []  # it no longer leaves the field null naming itself
    rows = [c.row for c in (p.delta_nwc_composition.components if p.delta_nwc_composition else [])]
    assert "IncreaseDecreaseInDerivativeAssetsAndLiabilities" not in rows  # excluded, never summed


# --- one accession per period (61) ---

def two_filings() -> dict[str, object]:
    """The Apple shape: an own-year filing that tags a line standalone, and a later filing
    whose comparative column folds it into another line. Anchors in both so both accessions
    report their own year."""
    own, later = "2022-10-28", "2023-11-03"
    def anchors(end: str, start: str, filed: str) -> dict[str, dict[str, object]]:
        return {"NetIncomeLoss": usd(fact(end, 100e9, start=start, filed=filed)),
                "StockholdersEquity": usd(fact(end, 50e9, filed=filed))}
    a21 = anchors("2021-09-25", "2020-09-27", own)
    a22 = anchors("2022-09-24", "2021-09-26", later)
    def rows(node: dict[str, object]) -> list[dict[str, object]]:
        return cast(list[dict[str, object]], cast(dict[str, object], node["units"])["USD"])

    return {
        "NetIncomeLoss": usd(*rows(a21["NetIncomeLoss"]), *rows(a22["NetIncomeLoss"])),
        "StockholdersEquity": usd(*rows(a21["StockholdersEquity"]), *rows(a22["StockholdersEquity"])),
        # FY2021, as its own filing tags it: the two lines stand apart
        "IncreaseDecreaseInOtherOperatingLiabilities": usd(
            fact("2021-09-25", 5799e6, start="2020-09-27", filed=own),
            fact("2021-09-25", 7475e6, start="2020-09-27", filed=later),   # the later filing folded the next line in
            fact("2022-09-24", 6110e6, start="2021-09-26", filed=later)),
        "IncreaseDecreaseInContractWithCustomerLiability": usd(
            fact("2021-09-25", 1676e6, start="2020-09-27", filed=own)),     # dropped by the later filing
        "IncreaseDecreaseInAccountsReceivable": usd(
            fact("2021-09-25", 10125e6, start="2020-09-27", filed=own),
            fact("2021-09-25", 10125e6, start="2020-09-27", filed=later),
            fact("2022-09-24", 1000e6, start="2021-09-26", filed=later)),
    }


def periods_of(gaap: Mapping[str, object], notes: list[str] | None = None) -> list[fetch.boundary.FiscalPeriod]:
    return fetch_sec.periods_from_facts(dict(gaap), TAGS, DEFS, notes if notes is not None else [])


def test_a_period_is_read_from_one_filing() -> None:
    """(61) The regrouped-line shape. The own-year filing's values are taken and the later
    filing's are not, so the line it folded in is counted once, not twice."""
    ps = {p.period_end: p for p in periods_of(two_filings())}
    fy21 = ps["2021-09-25"]
    assert fy21.accession == "acc-2022-10-28" and fy21.filed == "2022-10-28"
    # 10,125 added, 5,799 and 1,676 subtracted: the own-year presentation
    assert fy21.delta_nwc is not None and math.isclose(fy21.delta_nwc, (10125 - 5799 - 1676) * 1e6)
    # the latest-filed-per-tag rule would have taken 7,475 beside the 1,676 and been 1,676 low
    assert not math.isclose(fy21.delta_nwc, (10125 - 7475 - 1676) * 1e6)
    # and the later filing's disagreement is recorded, never taken
    restated = {r.tag: r for r in fy21.restated_from}
    assert "IncreaseDecreaseInOtherOperatingLiabilities" in restated
    r = restated["IncreaseDecreaseInOtherOperatingLiabilities"]
    assert r.taken == 5799e6 and r.later == 7475e6 and r.filed == "2023-11-03"
    # a tag both filings agree on is not a restatement
    assert "IncreaseDecreaseInAccountsReceivable" not in restated
    # the later filing's own year reads from itself
    assert ps["2022-09-24"].accession == "acc-2023-11-03"


def test_a_restatement_is_recorded_not_taken() -> None:
    """(61) A genuine restatement — the same tag, a different number in a later filing — is
    a finding on the record and never the value."""
    gaap = {
        "NetIncomeLoss": usd(fact("2024-12-31", 10e9, start="2024-01-01", filed="2025-02-20"),
                             fact("2025-12-31", 11e9, start="2025-01-01", filed="2026-02-20")),
        "StockholdersEquity": usd(fact("2024-12-31", 50e9, filed="2025-02-20"), fact("2025-12-31", 55e9, filed="2026-02-20")),
        "IncreaseDecreaseInAccountsReceivable": usd(
            fact("2024-12-31", 500e6, start="2024-01-01", filed="2025-02-20"),
            fact("2024-12-31", 620e6, start="2024-01-01", filed="2026-02-20")),
    }
    fy24 = {p.period_end: p for p in periods_of(gaap)}["2024-12-31"]
    assert fy24.delta_nwc == 500e6, "the own-year value, not the restated one"
    assert [(r.tag, r.taken, r.later) for r in fy24.restated_from] == [
        ("IncreaseDecreaseInAccountsReceivable", 500e6, 620e6)]


def test_the_working_capital_flag_where_the_filer_tags_both() -> None:
    """(61) Where a filer tags its own aggregate AND the components, the two must agree; the
    flag is absent where it tags only one of them, because there is nothing to compare."""
    def build(components_sum_to: float) -> dict[str, object]:
        return {
            "NetIncomeLoss": usd(fact("2025-12-31", 10e9, start="2025-01-01")),
            "StockholdersEquity": usd(fact("2025-12-31", 50e9)),
            "IncreaseDecreaseInOperatingCapital": usd(fact("2025-12-31", 1000e6, start="2025-01-01")),
            "IncreaseDecreaseInAccountsReceivable": usd(fact("2025-12-31", components_sum_to, start="2025-01-01")),
        }
    closes = periods_of(build(1000e6))[0]
    assert closes.working_capital_reconciled is True and closes.working_capital_gap == 0.0
    assert closes.delta_nwc == 1000e6, "the aggregate is still the value; the components only check it"
    gaps = periods_of(build(1400e6))[0]
    assert gaps.working_capital_reconciled is False and gaps.working_capital_gap == 400e6
    # no aggregate: nothing to reconcile against
    alone = periods_of({k: v for k, v in build(1000e6).items() if k != "IncreaseDecreaseInOperatingCapital"})[0]
    assert alone.working_capital_reconciled is None and alone.working_capital_gap is None


def test_point_in_time_takes_the_filing_on_or_before_the_date() -> None:
    """(61) The same rule under a point-in-time date: the chosen filing is the own-year one
    among the filings on or before it, so a later restatement is invisible, as it was."""
    import pit
    gaap = two_filings()
    facts = {"facts": {"us-gaap": gaap}}
    filtered = pit.filed_on_or_before(facts, date(2023, 1, 1))
    before = cast(Mapping[str, object], cast(dict[str, object], filtered["facts"])["us-gaap"])
    fy21 = {p.period_end: p for p in periods_of(before)}["2021-09-25"]
    assert fy21.accession == "acc-2022-10-28"
    assert fy21.delta_nwc is not None and math.isclose(fy21.delta_nwc, (10125 - 5799 - 1676) * 1e6)
    assert fy21.restated_from == [], "the later filing does not exist on that date"


def test_interest_expense_other_and_interest_payable_are_evidence_of_debt() -> None:
    """(72) Ford's two shapes. Its own FY2024 filing tags interest as InterestExpenseOther
    and its own FY2018 filing tags no interest expense at all, only the year-end accrual
    InterestPayableCurrent; either says the filer owes something, under the same sign and
    size test as the interest lines, so debt stays null instead of reading zero."""
    assert "InterestExpenseOther" in DEFS.total_debt.xbrl.interest_evidence
    assert DEFS.total_debt.xbrl.debt_evidence == ["InterestPayableCurrent", "InterestPayableCurrentAndNoncurrent"]
    loss = {"OperatingIncomeLoss": usd(fact("2025-12-31", -9169e6, start="2025-01-01"))}
    assert period({"InterestExpenseOther": usd(fact("2025-12-31", 1115e6, start="2025-01-01")), **loss}).total_debt is None
    assert period({"InterestPayableCurrent": usd(fact("2025-12-31", 988e6))}).total_debt is None
    assert period({"InterestPayableCurrentAndNoncurrent": usd(fact("2025-12-31", 12e6))}).total_debt is None
    # the accrual is read after the interest lines, and under the same floor
    p = period({"InterestPayableCurrent": usd(fact("2025-12-31", 2e6)), "OperatingIncomeLoss": usd(fact("2025-12-31", 1000e6, start="2025-01-01"))})
    assert p.total_debt == 0.0
    assert p.total_debt_source is not None and "the only interest payable filed, InterestPayableCurrent, is 0.20%" in p.total_debt_source
    p = period({"InterestPayableCurrent": usd(fact("2025-12-31", 0.0))})
    assert p.total_debt == 0.0 and p.total_debt_source is not None and "InterestPayableCurrent is not positive" in p.total_debt_source
    # a filed debt line is still the debt, and the accrual never derives an EBIT
    assert period({"LongTermDebtNoncurrent": usd(fact("2025-12-31", 0.745e9)), "InterestPayableCurrent": usd(fact("2025-12-31", 988e6))}).total_debt == 0.745e9
    assert "InterestPayableCurrent" not in DEFS.ebit.xbrl.interest_expense


def three_year_registrant() -> dict[str, object]:
    """Sandisk's shape: a first 10-K (filed 2025-08-15) with FY2025 and the FY2024 comparative
    balance sheet, then a second (filed 2026-08-17) with FY2026, FY2025 and the FY2024 income
    statement only, its FY2024 instants being the opening equity and cash of its statements
    of equity and cash flows, with no FY2024 debt line. FY2024 is nobody's own year."""
    first, second = "2025-08-15", "2026-08-17"
    return {
        "NetIncomeLoss": usd(fact("2025-06-27", -1.6e9, start="2024-06-29", filed=first), fact("2024-06-28", -0.7e9, start="2023-07-01", filed=first),
                             fact("2026-07-03", 11.4e9, start="2025-06-28", filed=second), fact("2025-06-27", -1.6e9, start="2024-06-29", filed=second),
                             fact("2024-06-28", -0.7e9, start="2023-07-01", filed=second)),
        "StockholdersEquity": usd(fact("2025-06-27", 9.6e9, filed=first), fact("2024-06-28", 11.1e9, filed=first),
                                  fact("2026-07-03", 21e9, filed=second), fact("2025-06-27", 9.6e9, filed=second), fact("2024-06-28", 11.1e9, filed=second)),
        "CashAndCashEquivalentsAtCarryingValue": usd(fact("2025-06-27", 1.5e9, filed=first), fact("2024-06-28", 328e6, filed=first),
                                                     fact("2026-07-03", 3e9, filed=second), fact("2025-06-27", 1.5e9, filed=second)),
        "LongTermDebt": usd(fact("2025-06-27", 2.0e9, filed=first), fact("2024-06-28", 0.0, filed=first),
                            fact("2026-07-03", 1.8e9, filed=second), fact("2025-06-27", 2.0e9, filed=second)),
        "InterestExpenseNonoperating": usd(fact("2025-06-27", 100e6, start="2024-06-29", filed=first), fact("2024-06-28", 40e6, start="2023-07-01", filed=first),
                                           fact("2026-07-03", 90e6, start="2025-06-28", filed=second), fact("2025-06-27", 100e6, start="2024-06-29", filed=second),
                                           fact("2024-06-28", 40e6, start="2023-07-01", filed=second)),
    }


def test_a_fallback_period_reads_its_balance_sheet_from_the_filing_that_carries_it() -> None:
    """(72) FY2024 is read from the second filing, which presents no FY2024 balance sheet, so
    its debt and cash would be missing; the first filing carries both, and a period with
    no own year takes them from there, saying so. The two own-year periods are untouched."""
    ps = {p.period_end: p for p in periods_of(three_year_registrant())}
    fy24 = ps["2024-06-28"]
    assert fy24.accession == "acc-2026-08-17"  # the latest filing that carries the period at all (61)
    assert fy24.total_debt == 0.0  # the zero the first filing tagged, not absent-is-zero: the interest blocks that
    assert fy24.total_debt_source is not None and fy24.total_debt_source.startswith("LongTermDebt") and "comparative balance sheet" in fy24.total_debt_source
    assert fy24.total_debt_composition is not None and [c.name for c in fy24.total_debt_composition.components] == ["total_including_current"]
    assert fy24.cash == 328e6 and fy24.cash_row is not None and "comparative balance sheet" in fy24.cash_row
    for end, debt in (("2025-06-27", 2.0e9), ("2026-07-03", 1.8e9)):
        p = ps[end]
        assert p.total_debt == debt and p.total_debt_source == "LongTermDebt" and p.cash_row is not None and "comparative" not in p.cash_row


def test_an_own_year_period_keeps_its_own_presentation() -> None:
    """(72) Enphase FY2015: its own 10-K tags no debt line and does tag interest, and the
    next year's 10-K carries a zero for the comparative. The own year is the presentation,
    so the field stays null; the comparative rule never reaches an own-year period."""
    gaap = {
        "NetIncomeLoss": usd(fact("2015-12-31", -22e6, start="2015-01-01", filed="2016-03-01"),
                             fact("2016-12-31", -67e6, start="2016-01-01", filed="2017-03-01"), fact("2015-12-31", -22e6, start="2015-01-01", filed="2017-03-01")),
        "StockholdersEquity": usd(fact("2015-12-31", 42e6, filed="2016-03-01"), fact("2016-12-31", 5e6, filed="2017-03-01"), fact("2015-12-31", 42e6, filed="2017-03-01")),
        "InterestExpense": usd(fact("2015-12-31", 501e3, start="2015-01-01", filed="2016-03-01")),
        "LongTermDebtNoncurrent": usd(fact("2015-12-31", 0.0, filed="2017-03-01"), fact("2016-12-31", 0.0, filed="2017-03-01")),
    }
    ps = {p.period_end: p for p in periods_of(gaap)}
    assert ps["2015-12-31"].accession == "acc-2016-03-01" and ps["2015-12-31"].total_debt is None
    assert ps["2016-12-31"].total_debt == 0.0 and ps["2016-12-31"].total_debt_source == "LongTermDebtNoncurrent"


def test_ifrs_depreciation_reads_the_inclusive_cash_flow_adjustment_after_the_income_statement() -> None:
    """(73) Novo Nordisk's shape: no depreciation line on the income statement, the cash-flow
    reconciliation's combined depreciation-and-impairment adjustment only. It reads as the
    inclusive recipe, impairment taken out where tagged; the income-statement tag, where
    filed, stays first."""
    adj = "AdjustmentsForDepreciationAndAmortisationExpenseAndImpairmentLossReversalOfImpairmentLossRecognisedInProfitOrLoss"
    ifrs = {"ProfitLoss": usd(fact("2025-12-31", 10e9, start="2025-01-01")), "Equity": usd(fact("2025-12-31", 50e9))}
    ps = fetch_sec.periods_from_facts({**ifrs, adj: usd(fact("2025-12-31", 12e9, start="2025-01-01")),
                                       "ImpairmentLossRecognisedInProfitOrLoss": usd(fact("2025-12-31", 2e9, start="2025-01-01"))},
                                      TAGS, DEFS, [], taxonomy="ifrs-full")
    p = ps[0]
    assert p.depreciation_amortization == 10e9 and p.depreciation_amortization_recipe == "inclusive_less_impairment"
    assert p.depreciation_amortization_row is not None and adj in p.depreciation_amortization_row
    p = fetch_sec.periods_from_facts({**ifrs, adj: usd(fact("2025-12-31", 12e9, start="2025-01-01")),
                                      "DepreciationAndAmortisationExpense": usd(fact("2025-12-31", 9e9, start="2025-01-01"))},
                                     TAGS, DEFS, [], taxonomy="ifrs-full")[0]
    assert p.depreciation_amortization == 9e9 and p.depreciation_amortization_recipe == "pure"
    # with no impairment figure beside it the adjustment is not read at all: the impairment
    # inside it cannot be taken out (Novo Nordisk), and the period carries no depreciation
    p = fetch_sec.periods_from_facts({**ifrs, adj: usd(fact("2025-12-31", 12e9, start="2025-01-01"))}, TAGS, DEFS, [], taxonomy="ifrs-full")[0]
    assert p.depreciation_amortization is None
    # a component impairment beside it is enough
    p = fetch_sec.periods_from_facts({**ifrs, adj: usd(fact("2025-12-31", 12e9, start="2025-01-01")),
                                      "ImpairmentLossRecognisedInProfitOrLossGoodwill": usd(fact("2025-12-31", 0.5e9, start="2025-01-01"))}, TAGS, DEFS, [], taxonomy="ifrs-full")[0]
    assert p.depreciation_amortization == 11.5e9


def test_ifrs_working_capital_aggregate_only_where_no_component_is_tagged() -> None:
    """(73) The filer's own working-capital total, in the boundary's sign as filed (measured on
    Unilever against its components and on TransAlta and Denison against the vendor's line);
    read only when the period carries no tag of the adjustment family, so a filer that tags
    components keeps the component reading and an unclassified family tag still leaves null."""
    ifrs = {"ProfitLoss": usd(fact("2025-12-31", 10e9, start="2025-01-01")), "Equity": usd(fact("2025-12-31", 50e9))}
    p = fetch_sec.periods_from_facts({**ifrs, "IncreaseDecreaseInWorkingCapital": usd(fact("2025-12-31", -116e6, start="2025-01-01"))}, TAGS, DEFS, [], taxonomy="ifrs-full")[0]
    assert p.delta_nwc == -116e6 and p.delta_nwc_row == "IncreaseDecreaseInWorkingCapital"
    assert p.delta_nwc_composition is not None and [c.name for c in p.delta_nwc_composition.components] == ["aggregate"]
    sign = DEFS.delta_nwc.ifrs.sign
    both = {**ifrs, "IncreaseDecreaseInWorkingCapital": usd(fact("2025-12-31", -116e6, start="2025-01-01")),
            "AdjustmentsForDecreaseIncreaseInInventories": usd(fact("2025-12-31", 40e6, start="2025-01-01"))}
    p = fetch_sec.periods_from_facts(both, TAGS, DEFS, [], taxonomy="ifrs-full")[0]
    assert p.delta_nwc == 40e6 * sign and p.delta_nwc_row is not None and "AdjustmentsForDecreaseIncreaseInInventories" in p.delta_nwc_row
    notes: list[str] = []
    odd = {**ifrs, "IncreaseDecreaseInWorkingCapital": usd(fact("2025-12-31", -116e6, start="2025-01-01")),
           "AdjustmentsForDecreaseIncreaseInSomethingNew": usd(fact("2025-12-31", 1e6, start="2025-01-01"))}
    p = fetch_sec.periods_from_facts(odd, TAGS, DEFS, notes, taxonomy="ifrs-full")[0]
    assert p.delta_nwc is None and any("unclassified" in n for n in notes)


def test_ifrs_cash_adds_short_term_deposits_on_top_of_the_investment_alternative() -> None:
    """(74) Samsung's shape: cash equivalents, term deposits outside them, and a current
    financial asset at fair value; the deposits are added on top of the alternative taken,
    and a filer that tags none reads exactly as before."""
    ifrs = {"ProfitLoss": usd(fact("2025-12-31", 10e9, start="2025-01-01")), "Equity": usd(fact("2025-12-31", 50e9))}
    p = fetch_sec.periods_from_facts({**ifrs, "CashAndCashEquivalents": usd(fact("2025-12-31", 57e9)),
                                      "ShorttermDepositsNotClassifiedAsCashEquivalents": usd(fact("2025-12-31", 68e9)),
                                      "CurrentFinancialAssetsAtFairValueThroughProfitOrLoss": usd(fact("2025-12-31", 1e9))}, TAGS, DEFS, [], taxonomy="ifrs-full")[0]
    assert p.cash == 126e9
    assert p.cash_composition is not None and [c.name for c in p.cash_composition.components] == ["cash_equivalents", "short_term_investments", "short_term_deposits"]
    p = fetch_sec.periods_from_facts({**ifrs, "CashAndCashEquivalents": usd(fact("2025-12-31", 57e9)), "CurrentInvestments": usd(fact("2025-12-31", 5e9))}, TAGS, DEFS, [], taxonomy="ifrs-full")[0]
    assert p.cash == 62e9 and [c.name for c in (p.cash_composition.components if p.cash_composition else [])] == ["cash_equivalents", "short_term_investments"]


def test_operating_cash_flow_is_read_as_filed_on_both_taxonomies() -> None:
    """(76) The cash-flow statement's own subtotal, the total first and the continuing-
    operations subtotal after it (Air Products files only the latter); no recipe."""
    p = period({"NetCashProvidedByUsedInOperatingActivities": usd(fact("2025-12-31", -1.5e9, start="2025-01-01"))})
    assert p.operating_cash_flow == -1.5e9 and p.operating_cash_flow_row == "NetCashProvidedByUsedInOperatingActivities"
    p = period({"NetCashProvidedByUsedInOperatingActivitiesContinuingOperations": usd(fact("2025-12-31", 2e9, start="2025-01-01"))})
    assert p.operating_cash_flow == 2e9 and p.operating_cash_flow_row == "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"
    assert period({}).operating_cash_flow is None
    ifrs = {"ProfitLoss": usd(fact("2025-12-31", 1e9, start="2025-01-01")), "Equity": usd(fact("2025-12-31", 5e9)),
            "CashFlowsFromUsedInOperatingActivities": usd(fact("2025-12-31", 3e9, start="2025-01-01"))}
    p = fetch_sec.periods_from_facts(ifrs, TAGS, DEFS, [], taxonomy="ifrs-full")[0]
    assert p.operating_cash_flow == 3e9 and p.operating_cash_flow_row == "CashFlowsFromUsedInOperatingActivities"
