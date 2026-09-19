"""Tag selection per period, the annual-fact filter, the derived fields, the provider
decision and the cross-check, on synthetic companyfacts."""

from __future__ import annotations

import dataclasses
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
    """Revenues stops after FY2024; the newer tag carries FY2025. LongTermDebt is filed with
    the current portion; Depreciation only as an aggregate."""
    return {
        "NetIncomeLoss": usd(fact("2025-09-27", 112e9, start="2024-09-29"), fact("2024-09-28", 94e9, start="2023-10-01"), fact("2023-09-30", 97e9, start="2022-10-02")),
        "StockholdersEquity": usd(fact("2025-09-27", 74e9), fact("2024-09-28", 57e9), fact("2023-09-30", 62e9)),
        "Revenues": usd(fact("2024-09-28", 391e9, start="2023-10-01"), fact("2023-09-30", 383e9, start="2022-10-02")),
        "RevenueFromContractWithCustomerExcludingAssessedTax": usd(fact("2025-09-27", 416e9, start="2024-09-29"), fact("2024-09-28", 391e9, start="2023-10-01")),
        "OperatingIncomeLoss": usd(fact("2025-09-27", 133e9, start="2024-09-29")),
        "DepreciationDepletionAndAmortization": usd(fact("2025-09-27", 11.7e9, start="2024-09-29")),
        "PaymentsToAcquirePropertyPlantAndEquipment": usd(fact("2025-09-27", 12.7e9, start="2024-09-29")),
        "AssetsCurrent": usd(fact("2025-09-27", 148e9), fact("2024-09-28", 153e9), fact("2023-09-30", 143e9)),
        "LiabilitiesCurrent": usd(fact("2025-09-27", 166e9), fact("2024-09-28", 176e9), fact("2023-09-30", 145e9)),
        "CashAndCashEquivalentsAtCarryingValue": usd(fact("2025-09-27", 36e9), fact("2024-09-28", 30e9), fact("2023-09-30", 30e9)),
        "LongTermDebt": usd(fact("2025-09-27", 90.7e9)),
        "DebtCurrent": usd(fact("2025-09-27", 8e9)),
        "PaymentsOfDividendsCommonStock": usd(fact("2017-09-30", 12.6e9, start="2016-09-25")),
        "PaymentsOfDividends": usd(fact("2025-09-27", 15.4e9, start="2024-09-29")),
    }


def test_tag_selection_changes_between_years_and_records_the_tag() -> None:
    notes: list[str] = []
    periods = fetch_sec.periods_from_facts(apple_like(), TAGS, notes)
    p25, p24, p23 = periods
    assert (p25.total_revenue, p25.total_revenue_row) == (416e9, "RevenueFromContractWithCustomerExcludingAssessedTax")
    assert (p24.total_revenue, p24.total_revenue_row) == (391e9, "Revenues")  # the older tag wins where it exists
    assert (p25.dividends_paid, p25.dividends_paid_row) == (15.4e9, "PaymentsOfDividends")
    assert p25.filed == "2026-02-20" and p25.accession == "acc-2026-02-20"
    assert (p25.depreciation_amortization, p25.depreciation_amortization_row) == (11.7e9, "DepreciationDepletionAndAmortization")
    assert (p25.total_debt, p25.total_debt_source) == (98.7e9, "LongTermDebt + DebtCurrent")
    assert p24.total_debt is None and p24.total_debt_source is None  # no silent zero
    # delta_nwc: (148-36) - (166-8) = -46 vs (153-30) - 176 = -53 -> +7e9 ; oldest period has no prior
    assert p25.delta_nwc is not None and abs(p25.delta_nwc - 7e9) < 1e-6
    assert p25.delta_nwc_row == "change in (AssetsCurrent - CashAndCashEquivalentsAtCarryingValue) - (LiabilitiesCurrent - DebtCurrent) from 2024-09-28"
    assert p24.delta_nwc_row == "change in (AssetsCurrent - CashAndCashEquivalentsAtCarryingValue) - (LiabilitiesCurrent) from 2023-09-30"
    assert p23.delta_nwc is None
    assert fetch_sec.latest_filing(periods) == "2026-02-20"


def test_depreciation_composite_and_debt_recipes() -> None:
    notes: list[str] = []
    ms_like = {
        "NetIncomeLoss": usd(fact("2026-06-30", 133e9, start="2025-07-01")),
        "StockholdersEquity": usd(fact("2026-06-30", 442e9)),
        "Depreciation": usd(fact("2026-06-30", 34.3e9, start="2025-07-01")),
        "AmortizationOfIntangibleAssets": usd(fact("2026-06-30", 4.7e9, start="2025-07-01")),
        "LongTermDebtNoncurrent": usd(fact("2026-06-30", 31.07e9)),
        "LongTermDebtCurrent": usd(fact("2026-06-30", 9.23e9)),
    }
    p = fetch_sec.periods_from_facts(ms_like, TAGS, notes)[0]
    assert p.depreciation_amortization is not None and abs(p.depreciation_amortization - 39.0e9) < 1
    assert p.depreciation_amortization_row == "Depreciation + AmortizationOfIntangibleAssets"
    assert p.total_debt is not None and abs(p.total_debt - 40.3e9) < 1
    assert p.total_debt_source == "LongTermDebtNoncurrent + LongTermDebtCurrent"
    ko_like = {
        "NetIncomeLoss": usd(fact("2025-12-31", 13e9, start="2025-01-01")),
        "StockholdersEquity": usd(fact("2025-12-31", 32e9)),
        "LongTermDebtAndCapitalLeaseObligations": usd(fact("2025-12-31", 42.12e9)),
        "AmortizationOfIntangibleAssets": usd(fact("2025-12-31", 0.1e9, start="2025-01-01")),  # no Depreciation: composite needs its first component
    }
    p = fetch_sec.periods_from_facts(ko_like, TAGS, notes)[0]
    assert (p.total_debt, p.total_debt_source) == (42.12e9, "LongTermDebtAndCapitalLeaseObligations")
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
    primary = fetch_sec.periods_from_facts(apple_like(), TAGS, notes)[0]
    vendor = dataclasses.replace(fetch._period(date(2025, 9, 30), None, None, None),  # pyright: ignore[reportPrivateUsage]
                                 total_revenue=416.16e9, cash=54.7e9, total_debt=98.66e9, net_income=112e9)
    matched = fetch.match_period(primary, [vendor, fetch._period(date(2024, 9, 30), None, None, None)])  # pyright: ignore[reportPrivateUsage]
    assert matched is vendor  # 3 days apart
    assert fetch.match_period(primary, [fetch._period(date(2025, 6, 30), None, None, None)]) is None  # pyright: ignore[reportPrivateUsage]
    check = fetch.cross_check(primary, vendor, 0.02, "yfinance")
    by = {f.field: f for f in check.fields}
    assert by["net_income"].agree is True and by["net_income"].relative_difference == 0.0
    assert by["total_revenue"].agree is True  # 416 vs 416.16: 0.04%
    assert by["cash"].agree is False and by["cash"].relative_difference is not None and abs(by["cash"].relative_difference - (54.7 - 36) / 54.7) < 1e-9
    assert by["total_debt"].agree is True  # 98.7 vs 98.66
    assert by["ebit"].agree is None and by["ebit"].secondary is None  # vendor side missing: no verdict
    assert check.disagreements == 1 and check.period_end == "2025-09-27" and check.secondary_period_end == "2025-09-30"


def test_cik_lookup_is_exact() -> None:
    table = {"0": {"cik_str": 1034670, "ticker": "ALV", "title": "AUTOLIV INC"},
             "1": {"cik_str": 1099219, "ticker": "MET", "title": "METLIFE INC"}}
    assert fetch_sec.cik_for("MET", table) == "0001099219"
    assert fetch_sec.cik_for("met", table) == "0001099219"
    assert fetch_sec.cik_for("ALV.DE", table) is None
