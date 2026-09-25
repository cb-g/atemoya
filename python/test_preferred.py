"""(69) Preferred dividends are not common distributions: the retention evidence test, the
preferred carrying value, and the common-dividend recipe. Every fixture here is invented."""

from __future__ import annotations

from datetime import date

import fetch
import fetch_sec

END = date(2025, 12, 31)


def facts_of(tags: dict[str, float]) -> fetch_sec.Facts:
    """A filer's us-gaap facts carrying exactly the named duration elements, annual."""
    gaap = {
        tag: {"units": {"USD": [{"start": "2025-01-01", "end": END.isoformat(), "val": value,
                                 "fp": "FY", "form": "10-K", "accn": "x", "filed": "2026-02-01"}]}}
        for tag, value in tags.items()
    }
    return fetch_sec.Facts(gaap, fetch.SecContext().tags, [])


def rule(tags: dict[str, float]) -> bool | None:
    sec = fetch.SecContext()
    return fetch_sec.no_distributions_filed(facts_of(tags), sec.tags, END)


FINANCING = {"NetCashProvidedByUsedInFinancingActivities": -100.0}


def test_a_preferred_dividend_is_not_a_common_distribution() -> None:
    """The case the brief was written for. SoFi files a preferred dividend and no common one:
    with the financing section filed, the filing has said it distributed nothing to common
    holders, and a claim senior to them saying otherwise is not evidence about them."""
    assert rule(FINANCING | {"PaymentsOfDividendsPreferredStockAndPreferenceStock": 16_500_000.0}) is True
    assert rule(FINANCING | {"DividendsPreferredStockCash": 370.0}) is True
    assert rule(FINANCING | {"DividendsPreferredStock": 194.0}) is True
    # and a preferred dividend filed at ZERO is the same: presence, not magnitude, is the test,
    # and SoFi's FY2025 figure is exactly 0.0 while its FY2021-24 figures are not
    assert rule(FINANCING | {"PaymentsOfDividendsPreferredStockAndPreferenceStock": 0.0}) is True


def test_a_common_or_combined_distribution_still_blocks_it() -> None:
    """Only the unambiguously preferred elements moved out of the list."""
    assert rule(FINANCING | {"PaymentsOfDividendsCommonStock": 1.0}) is None
    assert rule(FINANCING | {"PaymentsOfDividends": 1.0}) is None
    assert rule(FINANCING | {"PaymentsOfOrdinaryDividends": 1.0}) is None
    # a COMBINED element is not preferred-only: a filer paying its common dividend under this
    # one tag would otherwise read as having distributed nothing
    assert rule(FINANCING | {"DividendsPaidCommonAndPreferredStock": 1.0}) is None
    # and minority and affiliate distributions are neither preferred nor common; they stay
    assert rule(FINANCING | {"PaymentsOfDividendsMinorityInterest": 1.0}) is None
    assert rule(FINANCING | {"PaymentsOfDistributionsToAffiliates": 1.0}) is None


def test_the_financing_section_is_still_required() -> None:
    """An absent dividend tag cannot distinguish none from not filed; the financing subtotal
    is what settles it, and without it the rule says nothing (65)."""
    assert rule({}) is None
    assert rule({"PaymentsOfDividendsPreferredStockAndPreferenceStock": 1.0}) is None
    assert rule(FINANCING) is True


def test_a_zero_par_line_is_not_a_carrying_value() -> None:
    """PNC, MetLife and UnitedHealth file PreferredStockValue at exactly 0.0, and PNC and
    MetLife carry real preferred: the tag is the par line for authorised shares. Deducting
    the zero would report a deduction that did not happen."""
    assert fetch_sec.preferred_equity_of(200.0, "PreferredStockValue") == (200.0, "PreferredStockValue")
    assert fetch_sec.preferred_equity_of(0.0, "PreferredStockValue") == (None, None)
    assert fetch_sec.preferred_equity_of(-1.0, "PreferredStockValue") == (None, None)
    assert fetch_sec.preferred_equity_of(None, None) == (None, None)


def test_common_dividends_are_filed_then_computed() -> None:
    """JPMorgan, Goldman Sachs and Morgan Stanley file PaymentsOfDividends, common AND
    preferred, so the common figure is the total less the filed preferred dividends where no
    common element is filed, and the recipe is recorded either way."""
    assert fetch_sec.common_dividends_of(40.0, "PaymentsOfDividendsCommonStock", 55.0, 15.0) == \
        (40.0, "PaymentsOfDividendsCommonStock")
    assert fetch_sec.common_dividends_of(None, None, 55.0, 15.0) == \
        (40.0, "dividends_paid - preferred_dividends")
    # nothing to subtract from, or nothing to subtract: no common figure rather than a guess
    assert fetch_sec.common_dividends_of(None, None, None, 15.0) == (None, None)
    assert fetch_sec.common_dividends_of(None, None, 55.0, None) == (None, None)
    # and a preferred dividend larger than the total does not make a negative distribution
    assert fetch_sec.common_dividends_of(None, None, 10.0, 15.0)[0] == 0.0
