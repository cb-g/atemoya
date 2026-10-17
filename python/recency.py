"""Recency (84): how far the filed quarters have moved on from the annual base the models read.

Every model's base cash flow and growth history start from the last annual period, and
nothing filed after the last annual report reaches a fair value. On a name that changes
fast the base is up to a year behind the business, and a reader comparing what the price
needs with what was observed is misled on exactly those names. This block does not move
the base; it says how far behind it is, from the same companyfacts the statements come
from, on revenue alone, the one line every quarterly filing carries on the same element as
the annual one.

What it reads. The quarterly filings' revenue (form 10-Q, fiscal periods Q1 to Q3, a
duration of about a quarter) and the annual filings' (form 10-K, FY, a duration of about a
year) under the revenue chain's elements, one element throughout, the one with the most
quarters; the fourth quarter of each fiscal year is the year less its three filed quarters,
marked derived; the element whose quarters run latest is the one read, since a filer that
moved between elements has its current quarters on the newer one. Then the latest quarter
against the quarter ending about a year before it,
and the trailing four quarters against the annual base the models read, with the count of
quarters filed since that base. `base_stale` is the trailing figure beyond the declared
divergence (reference/params.json `recency_divergence`) either way: a collapse is as much a
stale base as a surge.

What it cannot see: a 20-F filer reports half-years on Form 6-K, which companyfacts does
not carry, so it has no block and says so; a filer whose quarterly revenue is tagged under
another element than its annual one, or whose quarters do not chain, carries a block with
the reason in place of the trailing figure. Nothing here feeds a model, a belief or a
signal."""

from __future__ import annotations

from datetime import date
from typing import Mapping

import boundary
import fetch_sec
import reference

QUARTER_DAYS = (80, 100)      # a quarter's duration, days
YEAR_DAYS = (350, 380)        # a year's
QUARTERLY_FORMS = ("10-Q", "10-Q/A")
ANNUAL_FORMS = ("10-K", "10-K/A")
NO_FACTS = "no filed facts: the statements come from another provider"
NO_QUARTERS_IFRS = "no quarterly revenue in the filed facts: a 20-F filer reports half-years on Form 6-K, which companyfacts does not carry"
NO_QUARTERS = "no quarterly revenue in the filed facts under the revenue chain's elements"
NO_BASE = "the statements carry no annual revenue to measure the quarters against"


def _facts(entry: object) -> tuple[str, str, float, str, str, str] | None:
    """(start, end, value, form, fp, filed) of one companyfacts entry, or None."""
    e = fetch_sec._as_dict(entry)  # pyright: ignore[reportPrivateUsage]
    start, end, val, form, fp, filed = e.get("start"), e.get("end"), e.get("val"), e.get("form"), e.get("fp"), e.get("filed")
    if not isinstance(start, str) or not isinstance(end, str) or not isinstance(val, (int, float)) or isinstance(val, bool):
        return None
    return start, end, float(val), str(form or ""), str(fp or ""), str(filed or "")


def _days(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def quarters_of(entries: list[object], *, as_of: date | None = None) -> tuple[dict[str, float], dict[str, tuple[str, float]]]:
    """(quarter end -> revenue, for the filed quarters; fiscal year end -> (start, revenue),
    for the filed years), each the latest filing for its period, filed on or before as_of
    where one is given."""
    quarters: dict[str, tuple[str, float]] = {}
    years: dict[str, tuple[str, str, float]] = {}
    for entry in entries:
        f = _facts(entry)
        if f is None:
            continue
        start, end, val, form, fp, filed = f
        if as_of is not None and (not filed or date.fromisoformat(filed) > as_of):
            continue
        span = _days(start, end)
        if form in QUARTERLY_FORMS and fp in ("Q1", "Q2", "Q3") and QUARTER_DAYS[0] <= span <= QUARTER_DAYS[1]:
            if end not in quarters or filed > quarters[end][0]:
                quarters[end] = (filed, val)
        elif form in ANNUAL_FORMS and fp == "FY" and YEAR_DAYS[0] <= span <= YEAR_DAYS[1]:
            if end not in years or filed > years[end][0]:
                years[end] = (filed, start, val)
    return {end: v for end, (_, v) in quarters.items()}, {end: (start, v) for end, (_, start, v) in years.items()}


def with_fourth_quarters(quarters: dict[str, float], years: dict[str, tuple[str, float]]) -> dict[str, tuple[float, bool]]:
    """The quarters with each fiscal year's fourth derived where its three are filed:
    end -> (revenue, derived)."""
    out: dict[str, tuple[float, bool]] = {end: (v, False) for end, v in quarters.items()}
    for year_end, (year_start, annual) in years.items():
        inside = [v for end, v in quarters.items() if year_start < end < year_end]
        if len(inside) == 3 and year_end not in out:
            out[year_end] = (annual - sum(inside), True)
    return out


def of_record(facts: Mapping[str, object] | None, taxonomy: str, unit: str | None, tags: reference.XbrlTags,
              annual_end: str | None, annual_revenue: float | None, divergence: float | None,
              *, as_of: date | None = None) -> tuple[boundary.Recency | None, str | None]:
    """The block, or None with the reason."""
    if facts is None or not taxonomy or unit is None:
        return None, NO_FACTS
    table = dict(tags.ifrs_full_fields if taxonomy == "ifrs-full" else tags.fields)
    chain = table["total_revenue"].tags if "total_revenue" in table else []
    gaap = fetch_sec._as_dict(fetch_sec._as_dict(facts.get("facts")).get(taxonomy))  # pyright: ignore[reportPrivateUsage]
    # the element whose quarters run latest; among those, the one with the most of them. A
    # filer that moved from one revenue element to another years ago has many old quarters
    # on the first and the current ones on the second, and the current ones are the question.
    best: tuple[str, dict[str, tuple[float, bool]]] | None = None
    for tag in chain:
        quarters, years = quarters_of(fetch_sec._entries(gaap.get(tag), unit), as_of=as_of)  # pyright: ignore[reportPrivateUsage]
        if not quarters:
            continue
        series = with_fourth_quarters(quarters, years)
        if best is None or (max(series), len(series)) > (max(best[1]), len(best[1])):
            best = (tag, series)
    if best is None:
        return None, NO_QUARTERS_IFRS if taxonomy == "ifrs-full" else NO_QUARTERS
    if annual_end is None or annual_revenue is None or annual_revenue <= 0:
        return None, NO_BASE
    tag, series = best
    ends = sorted(series)
    latest = ends[-1]
    latest_revenue = series[latest][0]
    earlier = [e for e in ends if YEAR_DAYS[0] <= _days(e, latest) <= YEAR_DAYS[1]]
    year_earlier = series[earlier[-1]][0] if earlier else None
    quarter_yoy = None if year_earlier is None or year_earlier <= 0 else latest_revenue / year_earlier - 1
    # the trailing four: the latest and the three before it, each ending about a quarter apart
    chain_ends = [latest]
    for e in reversed(ends[:-1]):
        if len(chain_ends) == 4:
            break
        if QUARTER_DAYS[0] <= _days(e, chain_ends[-1]) <= QUARTER_DAYS[1]:
            chain_ends.append(e)
        else:
            break
    quarters_out = [boundary.RecencyQuarter(period_end=e, revenue=series[e][0], derived=series[e][1]) for e in chain_ends]
    trailing = sum(series[e][0] for e in chain_ends) if len(chain_ends) == 4 else None
    trailing_reason = None if trailing is not None else f"the quarters do not chain: {len(chain_ends)} consecutive quarter(s) end at the latest, four are needed"
    trailing_over_annual = None if trailing is None else trailing / annual_revenue - 1
    since = sum(1 for e in ends if e > annual_end)
    stale = trailing_over_annual is not None and divergence is not None and abs(trailing_over_annual) > divergence
    notes = ["revenue only, on one element across the quarters and the year; the fourth quarter is the year less its three filed quarters",
             "describes how far the annual base the models read is behind the filed quarters; the base itself is unchanged"]
    return boundary.Recency(
        tag=tag, latest_quarter_end=latest, latest_quarter_revenue=latest_revenue,
        year_earlier_quarter_revenue=year_earlier, quarter_yoy=quarter_yoy, quarters=quarters_out,
        trailing_four_quarters_revenue=trailing, trailing_reason=trailing_reason,
        annual_base_end=annual_end, annual_base_revenue=annual_revenue, trailing_over_annual=trailing_over_annual,
        quarters_since_base=since, divergence=divergence, base_stale=stale, notes=notes), None


def divergence_of(params: reference.Params) -> float | None:
    return None if params.recency_divergence is None else params.recency_divergence.value
