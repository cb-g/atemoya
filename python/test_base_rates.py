"""Base rates on invented frames: the largest revenue element per year, the size class at
the start, growth among the companies with both ends, the count of those without an end,
the percentiles and the small-cell rule. No network; every number is invented."""

from __future__ import annotations

from typing import cast

import base_rates as br


def row(cik: int, val: float) -> dict[str, object]:
    return {"cik": cik, "val": val, "entityName": "x"}


def test_revenue_is_the_largest_element_filed_for_the_year() -> None:
    frames = {("Revenues", 2010): [row(1, 200.0), row(2, -5.0)],
              ("RevenueFromContractWithCustomerExcludingAssessedTax", 2010): [row(1, 150.0), row(3, 70.0)]}
    assert br.revenues(frames) == {1: {2010: 200.0}, 3: {2010: 70.0}}


def test_size_classes_are_half_open_and_start_at_ten_million() -> None:
    assert br.bucket_of(9.9e6) is None
    assert br.bucket_of(1e7) == "10m to 100m" and br.bucket_of(1e8) == "100m to 1bn"
    assert br.bucket_of(5e10) == "50bn and above"


def test_percentiles_run_from_the_first_to_the_ninety_ninth() -> None:
    p = br.percentiles([float(i) for i in range(101)])
    assert len(p) == 99 and p[0] == 1.0 and p[49] == 50.0 and p[98] == 99.0


def test_growth_is_counted_at_both_ends_and_the_lost_are_counted_apart() -> None:
    revenue: dict[int, dict[int, float]] = {}
    for cik in range(40):   # forty companies doubling over three years from two billion
        revenue[cik] = {2010: 2e9, 2013: 4e9}
    for cik in range(40, 50):   # ten that stopped filing
        revenue[cik] = {2010: 2e9}
    tables = br.tables(revenue, 2010, 2013)
    assert [(t["horizon_years"], t["bucket"]) for t in tables] == [(3, "1bn to 10bn")]   # 5 and 10 years do not fit; other classes are empty
    t = tables[0]
    assert t["n"] == 40 and t["not_reported_at_end"] == 10
    p = cast(list[float], t["percentiles"])
    assert abs(p[49] - (2 ** (1 / 3) - 1)) < 1e-12
    few = {cik: by for cik, by in list(revenue.items())[: br.MIN_CELL - 1]}
    assert br.tables(few, 2010, 2013) == []
