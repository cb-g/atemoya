"""The filed research and development history on invented facts: one value per fiscal year,
the first tag carrying a year wins it, a restated year reads its latest filing, quarters
and non-annual forms are left out, and an absent line is a reason."""

from __future__ import annotations

import fetch_sec
import rd


def entry(start: str, end: str, val: float, filed: str, *, form: str = "10-K", fp: str = "FY", accn: str = "a") -> dict[str, object]:
    return {"start": start, "end": end, "val": val, "form": form, "fp": fp, "filed": filed, "accn": accn}


def facts(tags: dict[str, list[dict[str, object]]]) -> dict[str, object]:
    return {"facts": {"us-gaap": {tag: {"units": {"USD": entries}} for tag, entries in tags.items()}}}


def test_one_value_per_year_newest_first_and_the_latest_filing_of_a_restated_year() -> None:
    f = facts({"ResearchAndDevelopmentExpense": [
        entry("2022-10-01", "2023-09-30", 60.0, "2023-11-01"),
        entry("2023-10-01", "2024-09-30", 80.0, "2024-11-01"),
        entry("2023-10-01", "2024-09-30", 85.0, "2025-11-01", accn="b"),   # restated a year later
        entry("2024-10-01", "2025-09-30", 100.0, "2025-11-01", accn="b"),
        entry("2025-07-01", "2025-09-30", 30.0, "2025-11-01", accn="b"),   # a quarter inside the annual report
        entry("2024-10-01", "2025-06-30", 70.0, "2025-08-01", form="10-Q", fp="Q3"),
    ]})
    years, why = rd.of_record(f, "us-gaap", "USD", fetch_sec.load_tags())
    assert why is None
    assert [(y.period_end, y.value, y.filed) for y in years] == [("2025-09-30", 100.0, "2025-11-01"), ("2024-09-30", 85.0, "2025-11-01"), ("2023-09-30", 60.0, "2023-11-01")]


def test_the_excluding_element_wins_a_year_it_carries_and_the_list_is_capped() -> None:
    """A filer on the excluding element may use the plain one for a small separate item; the
    plain element fills only the years the excluding one does not carry."""
    wide = [entry(f"{y - 1}-01-01", f"{y - 1}-12-31", float(y), f"{y}-02-01") for y in range(2005, 2026)]
    f = facts({"ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost": wide[-2:],
               "ResearchAndDevelopmentExpense": [dict(e, val=-1.0) for e in wide]})
    years, _ = rd.of_record(f, "us-gaap", "USD", fetch_sec.load_tags())
    assert len(years) == rd.MAX_YEARS
    assert [(y.value, y.tag) for y in years[:3]] == [(2025.0, "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"),
                                                     (2024.0, "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost"),
                                                     (-1.0, "ResearchAndDevelopmentExpense")]


def test_no_line_and_no_facts_are_reasons() -> None:
    tags = fetch_sec.load_tags()
    assert rd.of_record(facts({"Revenues": []}), "us-gaap", "USD", tags) == ([], rd.NO_LINE)
    assert rd.of_record(None, "us-gaap", "USD", tags) == ([], rd.NO_FACTS)
    assert rd.of_record(facts({}), "", "USD", tags) == ([], rd.NO_FACTS)
