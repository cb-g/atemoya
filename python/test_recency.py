"""Recency (84) on invented companyfacts: the quarters chained, the fourth derived, the
latest against a year earlier, the trailing four against the annual base, the date cut and
the reasons. Every figure is invented."""

from __future__ import annotations

from datetime import date

import recency
import reference

TAGS = reference.XbrlTags.from_json_string((recency.fetch_sec.REPO_ROOT / "reference" / "xbrl_tags.json").read_text())


def entry(start: str, end: str, val: float, form: str, fp: str, filed: str) -> dict[str, object]:
    return {"start": start, "end": end, "val": val, "form": form, "fp": fp, "filed": filed, "fy": int(end[:4]), "accn": f"a-{end}"}


def facts(entries: list[dict[str, object]], tag: str = "Revenues") -> dict[str, object]:
    return {"facts": {"us-gaap": {tag: {"units": {"USD": entries}}}}}


QUARTERS = [
    entry("2025-01-01", "2025-03-31", 20.0, "10-Q", "Q1", "2025-05-01"),
    entry("2025-04-01", "2025-06-30", 25.0, "10-Q", "Q2", "2025-08-01"),
    entry("2025-07-01", "2025-09-30", 30.0, "10-Q", "Q3", "2025-11-01"),
    entry("2025-01-01", "2025-12-31", 100.0, "10-K", "FY", "2026-02-15"),      # the fourth quarter is 25
    entry("2026-01-01", "2026-03-31", 40.0, "10-Q", "Q1", "2026-05-01"),
    entry("2026-04-01", "2026-06-30", 50.0, "10-Q", "Q2", "2026-08-01"),
    entry("2025-07-01", "2025-09-30", 31.0, "10-Q/A", "Q3", "2025-12-01"),    # an amendment: the later filing wins
    entry("2024-10-01", "2025-09-30", 90.0, "10-Q", "Q3", "2025-11-01"),      # a year-to-date duration: not a quarter
]


def test_the_quarters_chain_the_fourth_is_derived_and_the_base_is_read_as_stale() -> None:
    block, reason = recency.of_record(facts(QUARTERS), "us-gaap", "USD", TAGS, "2025-12-31", 100.0, 0.10)
    assert reason is None and block is not None
    assert block.tag == "Revenues" and block.latest_quarter_end == "2026-06-30" and block.latest_quarter_revenue == 50.0
    assert block.year_earlier_quarter_revenue == 25.0 and block.quarter_yoy == 1.0
    assert [(q.period_end, q.revenue, q.derived) for q in block.quarters] == [("2026-06-30", 50.0, False), ("2026-03-31", 40.0, False), ("2025-12-31", 24.0, True), ("2025-09-30", 31.0, False)]
    assert block.trailing_four_quarters_revenue == 145.0 and abs((block.trailing_over_annual or 0) - 0.45) < 1e-12
    assert block.quarters_since_base == 2 and block.divergence == 0.10 and block.base_stale is True and block.trailing_reason is None
    # under a wider divergence the same figures leave the base standing
    calm, _ = recency.of_record(facts(QUARTERS), "us-gaap", "USD", TAGS, "2025-12-31", 100.0, 0.50)
    assert calm is not None and calm.base_stale is False
    # no declared divergence: described, never flagged
    none, _ = recency.of_record(facts(QUARTERS), "us-gaap", "USD", TAGS, "2025-12-31", 100.0, None)
    assert none is not None and none.base_stale is False and none.divergence is None


def test_the_date_cut_is_on_the_filing_date_and_a_broken_chain_says_so() -> None:
    cut, _ = recency.of_record(facts(QUARTERS), "us-gaap", "USD", TAGS, "2025-12-31", 100.0, 0.10, as_of=date(2026, 5, 15))
    assert cut is not None and cut.latest_quarter_end == "2026-03-31" and cut.quarters_since_base == 1
    assert cut.trailing_four_quarters_revenue == 40.0 + 24.0 + 31.0 + 25.0
    gap = [e for e in QUARTERS if e["end"] != "2026-03-31"]                           # the first quarter of 2026 never filed
    broken, _ = recency.of_record(facts(gap), "us-gaap", "USD", TAGS, "2025-12-31", 100.0, 0.10)
    assert broken is not None and broken.trailing_four_quarters_revenue is None and broken.base_stale is False
    assert broken.trailing_reason == "the quarters do not chain: 1 consecutive quarter(s) end at the latest, four are needed"
    assert broken.quarter_yoy == 1.0                                                   # the year-earlier quarter is still read


def test_the_reasons_name_what_is_missing() -> None:
    assert recency.of_record(None, "us-gaap", "USD", TAGS, "2025-12-31", 100.0, 0.1) == (None, recency.NO_FACTS)
    assert recency.of_record(facts(QUARTERS), "us-gaap", "USD", TAGS, None, None, 0.1) == (None, recency.NO_BASE)
    annual_only = facts([entry("2025-01-01", "2025-12-31", 100.0, "10-K", "FY", "2026-02-15")])
    assert recency.of_record(annual_only, "us-gaap", "USD", TAGS, "2025-12-31", 100.0, 0.1) == (None, recency.NO_QUARTERS)
    ifrs = {"facts": {"ifrs-full": {"Revenue": {"units": {"USD": [entry("2025-01-01", "2025-12-31", 100.0, "20-F", "FY", "2026-03-01")]}}}}}
    assert recency.of_record(ifrs, "ifrs-full", "USD", TAGS, "2025-12-31", 100.0, 0.1) == (None, recency.NO_QUARTERS_IFRS)
    assert recency.of_record(ifrs, "ifrs-full", "USD", TAGS, None, None, 0.1) == (None, recency.NO_QUARTERS_IFRS)   # the filer's cadence before the base
    # the element whose quarters run latest is the one read: many old quarters on an element
    # a filer left years ago do not outrank the current ones on the element it moved to
    old = [entry(f"{y}-01-01", f"{y}-03-31", 5.0, "10-Q", "Q1", f"{y}-05-01") for y in range(2012, 2019)]
    moved = facts(old, "SalesRevenueNet")
    moved["facts"]["us-gaap"]["Revenues"] = facts(QUARTERS[:2])["facts"]["us-gaap"]["Revenues"]  # type: ignore[index]
    block, _ = recency.of_record(moved, "us-gaap", "USD", TAGS, "2025-12-31", 100.0, 0.1)
    assert block is not None and block.tag == "Revenues" and block.latest_quarter_end == "2025-06-30"


def test_the_quarters_are_read_from_the_element_the_annual_base_was_read_from() -> None:
    # a filer tags a wider total and a narrower contract revenue, quarters on both running to
    # the same date: the base's element is the one compared, whichever has more quarters
    narrow = [entry(e["start"], e["end"], float(e["val"]) * 0.7, str(e["form"]), str(e["fp"]), str(e["filed"])) for e in QUARTERS]  # type: ignore[arg-type]
    both = facts(QUARTERS, "Revenues")
    both["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"] = facts(narrow)["facts"]["us-gaap"]["Revenues"]  # type: ignore[index]
    wide, _ = recency.of_record(both, "us-gaap", "USD", TAGS, "2025-12-31", 100.0, 0.10, annual_row="Revenues")
    assert wide is not None and wide.tag == "Revenues" and wide.trailing_four_quarters_revenue == 145.0
    contract, _ = recency.of_record(both, "us-gaap", "USD", TAGS, "2025-12-31", 70.0, 0.10, annual_row="RevenueFromContractWithCustomerExcludingAssessedTax")
    assert contract is not None and contract.tag == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert contract.trailing_four_quarters_revenue is not None and abs(contract.trailing_four_quarters_revenue - 145.0 * 0.7) < 1e-6
    # a base element without quarters falls back to the element whose quarters run latest
    fallback, _ = recency.of_record(both, "us-gaap", "USD", TAGS, "2025-12-31", 100.0, 0.10, annual_row="SalesRevenueNet")
    assert fallback is not None and fallback.tag in ("Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax")


def test_a_base_element_whose_quarters_stopped_years_ago_gives_way_to_one_that_files_the_same_year() -> None:
    # the base's element carries the annual figure and quarters that stopped long before it;
    # the current quarters sit on another element that files the same annual figure: those are read
    old = [entry("2018-01-01", "2018-03-31", 7.0, "10-Q", "Q1", "2018-05-01"),
           entry("2018-04-01", "2018-06-30", 8.0, "10-Q", "Q2", "2018-08-01"),
           entry("2025-01-01", "2025-12-31", 100.0, "10-K", "FY", "2026-02-15")]
    both = facts(old, "Revenues")
    both["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"] = facts(QUARTERS)["facts"]["us-gaap"]["Revenues"]  # type: ignore[index]
    block, _ = recency.of_record(both, "us-gaap", "USD", TAGS, "2025-12-31", 100.0, 0.10, annual_row="Revenues")
    assert block is not None and block.tag == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert block.latest_quarter_end == "2026-06-30" and block.trailing_four_quarters_revenue == 145.0
    # a narrower element whose year is smaller is never taken in the base's place
    narrow = [entry(str(e["start"]), str(e["end"]), float(e["val"]) * 0.7, str(e["form"]), str(e["fp"]), str(e["filed"])) for e in QUARTERS]  # type: ignore[arg-type]
    other = facts(old, "Revenues")
    other["facts"]["us-gaap"]["RevenueFromContractWithCustomerExcludingAssessedTax"] = facts(narrow)["facts"]["us-gaap"]["Revenues"]  # type: ignore[index]
    none, reason = recency.of_record(other, "us-gaap", "USD", TAGS, "2025-12-31", 100.0, 0.10, annual_row="Revenues")
    assert none is None and reason == recency.NO_CURRENT_QUARTERS


def test_the_facts_lag_names_a_later_report_than_the_facts_carry() -> None:
    def index(rows: list[tuple[str, str, str, str]]) -> dict[str, object]:
        return {"filings": {"recent": {"form": [r[0] for r in rows], "filingDate": [r[1] for r in rows],
                                       "accessionNumber": [r[2] for r in rows], "reportDate": [r[3] for r in rows]}}}
    rows = [("10-Q", "2026-07-29", "0000000001-26-000032", "2026-07-05"), ("8-K", "2026-07-29", "x", "2026-07-29"),
            ("10-Q", "2026-04-29", "0000000001-26-000012", "2026-04-05")]
    lag = recency.facts_lag(index(rows), "2026-04-05", date(2026, 10, 19))
    assert lag is not None and "10-Q filed 2026-07-29 for the period ending 2026-07-05 (0000000001-26-000032)" in lag and lag.endswith("end 2026-04-05")
    assert recency.facts_lag(index(rows), "2026-07-05", date(2026, 10, 19)) is None       # the facts are current
    assert recency.facts_lag(index(rows), "2026-04-05", date(2026, 7, 1)) is None         # filed after the fetch date
    assert recency.facts_lag(None, "2026-04-05", date(2026, 10, 19)) is None
