"""Dilution (2026-10-23): the shares a company's options, restricted stock units and warrants
add to the count the price is quoted on, from the filer's own diluted count.

The count the price is quoted on is the shares outstanding, and an award not yet settled is not
among them. Stock compensation is a cost inside operating income, but it charges the awards as
they are earned: what is already earned of the awards outstanding is in no future cash flow.
The treasury-stock method the filer's diluted count follows nets the exercise price and the
compensation not yet recognised against the awards, so its increment over the basic count is
that earned part, and dividing by the count scaled by it pairs with the cash flow.

Contract. `of_facts(...)` and `of_vendor(...)` return (dilution, None) or (None, reason). The
dilution is read from the newest period, a quarter (80 to 100 days) or a fiscal year (350 to
380), that files both a weighted-average diluted and a basic count and a net income above nil:
a loss period's diluted count is its basic count by rule, the awards being antidilutive, so it
says nothing of the awards outstanding. At an equal end the quarter is taken, its average the
nearer. Only periods ending within a year of the newest with both counts are read, so a run of
losses reads none rather than an old year's. The increment is diluted less basic less the
conversion shares of debt and preferred the filer tags apart, at least nil, and the ratio is
that over basic. The vendor's reading is its two average rows on its newest annual column with
a net income above nil, under the same window. Nothing here moves a statement line; the valuer
scales the share count."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, Mapping

import boundary
import fetch_sec
import reference
from trailing import NO_FACTS, _latest, _validated  # pyright: ignore[reportPrivateUsage]

QUARTER_DAYS = (80, 100)
YEAR_DAYS = (350, 380)
WINDOW_DAYS = 366
SHARES = "shares"
FILED_FORMS = ("10-K", "10-K/A", "10-Q", "10-Q/A", "20-F", "20-F/A", "40-F", "40-F/A")
NO_DEFINITION = "reference/field_definitions.json carries no dilution definition"
NO_COUNTS = "no period files both a weighted-average diluted and a basic share count"
NO_PROFIT = ("no period within a year of the newest with both counts reports a net income above nil: a loss period's "
             "diluted count is its basic count by rule, the awards being antidilutive")

Key = tuple[date, str]   # period end, span


def _span(start: date | None, end: date) -> str | None:
    if start is None:
        return None
    days = (end - start).days
    if QUARTER_DAYS[0] <= days <= QUARTER_DAYS[1]:
        return "quarter"
    if YEAR_DAYS[0] <= days <= YEAR_DAYS[1]:
        return "year"
    return None


def _by_span(gaap: Mapping[str, object], tags: Iterable[str], unit: str, as_of: date | None) -> dict[Key, tuple[float, str, str]]:
    """(value, tag, accession) per period end and span, the first tag in order that files the
    period, its latest filed fact."""
    out: dict[Key, tuple[float, str, str]] = {}
    for tag in tags:
        grouped: dict[Key, list[fetch_sec.Fact]] = {}
        for fact in _validated(fetch_sec._entries(gaap.get(tag), unit), as_of):  # pyright: ignore[reportPrivateUsage]
            span = _span(fact.start, fact.end)
            if span is not None and fact.form in FILED_FORMS:
                grouped.setdefault((fact.end, span), []).append(fact)
        for key, facts in grouped.items():
            hit = _latest(facts)
            if key not in out and hit is not None:
                out[key] = (hit.val, tag, hit.accn)
    return out


def _choose(keys: Iterable[Key], profitable: Mapping[Key, bool]) -> Key | None:
    ordered = sorted(keys, key=lambda k: (k[0], k[1] == "quarter"), reverse=True)
    if not ordered:
        return None
    floor = ordered[0][0] - timedelta(days=WINDOW_DAYS)
    return next((k for k in ordered if k[0] >= floor and profitable.get(k, False)), None)


def _dilution(key: Key, diluted: float, basic: float, excluded: list[tuple[float, str]], source: str,
              accession: str | None) -> boundary.Dilution:
    left_out = sum(v for v, _ in excluded)
    return boundary.Dilution(
        period_end=key[0].isoformat(), span=key[1], diluted=diluted, basic=basic, excluded=left_out,
        excluded_rows=" + ".join(t for _, t in excluded) or None,
        ratio=max(0.0, diluted - basic - left_out) / basic, source=source, accession=accession)


def of_facts(facts: Mapping[str, object] | None, taxonomy: str, unit: str | None, defs: reference.FieldDefinitions,
             *, as_of: date | None = None) -> tuple[boundary.Dilution | None, str | None]:
    """The filer's own reading, from its companyfacts."""
    if facts is None or not taxonomy or unit is None:
        return None, NO_FACTS
    if defs.dilution is None:
        return None, NO_DEFINITION
    counts = defs.dilution.ifrs if taxonomy == "ifrs-full" else defs.dilution.xbrl
    gaap = fetch_sec._as_dict(fetch_sec._as_dict(facts.get("facts")).get(taxonomy))  # pyright: ignore[reportPrivateUsage]
    diluted = _by_span(gaap, counts.diluted, SHARES, as_of)
    basic = _by_span(gaap, counts.basic, SHARES, as_of)
    income = _by_span(gaap, counts.net_income, unit, as_of)
    both = [k for k in diluted if k in basic and basic[k][0] > 0.]
    if not both:
        return None, NO_COUNTS
    key = _choose(both, {k: income[k][0] > 0. for k in both if k in income})
    if key is None:
        return None, NO_PROFIT
    excluded = [(by[key][0], tag) for tag in counts.excluded if key in (by := _by_span(gaap, [tag], SHARES, as_of))]
    (d, dtag, accession), (b, btag, _) = diluted[key], basic[key]
    return _dilution(key, d, b, excluded, f"{dtag} / {btag}", accession), None


def of_vendor(columns: Mapping[date, Mapping[str, object]], defs: reference.FieldDefinitions) -> tuple[boundary.Dilution | None, str | None]:
    """The vendor's reading, from its annual income statement's columns."""
    if defs.dilution is None:
        return None, NO_DEFINITION
    v = defs.dilution.vendor

    def row(rows: Mapping[str, object], labels: Iterable[str]) -> tuple[float, str] | None:
        for label in labels:
            value = rows.get(label)
            if isinstance(value, (int, float)) and value == value:
                return float(value), label
        return None

    found: dict[Key, tuple[float, float, str]] = {}
    profitable: dict[Key, bool] = {}
    for end, rows in columns.items():
        d, b, ni = row(rows, v.diluted), row(rows, v.basic), row(rows, v.net_income)
        if d is not None and b is not None and b[0] > 0.:
            found[(end, "year")] = (d[0], b[0], f"{d[1]} / {b[1]}")
            profitable[(end, "year")] = ni is not None and ni[0] > 0.
    if not found:
        return None, NO_COUNTS
    key = _choose(found, profitable)
    if key is None:
        return None, NO_PROFIT
    d, b, source = found[key]
    return _dilution(key, d, b, [], source, None), None
