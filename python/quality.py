"""The balance-sheet and margin lines behind the quality block.

Contract. `lines` returns, per fiscal year end the filer's facts carry, the filed total
assets, current assets, current liabilities, gross profit and cost of revenue, each with
the element it was filed under; a line the filer does not file is absent, never derived
here. Newest first, at most MAX_YEARS years, a restated year read from its latest filing
among the facts given, so a point-in-time caller passes facts already cut at its date. The
quality block (ocaml/lib/quality.ml) reads these beside the record's periods and moves no
statement field: the elements live here and not in reference/xbrl_tags.json because every
element named there enters the restatement scan.

A bank or an insurer files no current assets and no gross profit; those lines are absent
and the block's signals that need them are null, which is the honest answer on a balance
sheet that has no current section."""

from __future__ import annotations

from collections.abc import Mapping

import boundary
import fetch_sec
import reference

MAX_YEARS = 4
# (field, instant, elements in order of preference)
LINES: dict[str, tuple[tuple[str, bool, tuple[str, ...]], ...]] = {
    "us-gaap": (
        ("total_assets", True, ("Assets",)),
        ("current_assets", True, ("AssetsCurrent",)),
        ("current_liabilities", True, ("LiabilitiesCurrent",)),
        ("gross_profit", False, ("GrossProfit",)),
        ("cost_of_revenue", False, ("CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold")),
    ),
    "ifrs-full": (
        ("total_assets", True, ("Assets",)),
        ("current_assets", True, ("CurrentAssets",)),
        ("current_liabilities", True, ("CurrentLiabilities",)),
        ("gross_profit", False, ("GrossProfit",)),
        ("cost_of_revenue", False, ("CostOfSales",)),
    ),
}
NO_FACTS = "no filed facts are read for this name: the statements come from another provider"
NO_LINES = "the filer's facts carry none of the lines the quality block reads"


def lines(facts: Mapping[str, object], taxonomy: str, unit: str, tags: reference.XbrlTags) -> list[boundary.QualityLines]:
    gaap = fetch_sec._as_dict(fetch_sec._as_dict(facts.get("facts")).get(taxonomy))  # pyright: ignore[reportPrivateUsage]
    by_end: dict[str, dict[str, tuple[float, str]]] = {}
    for field, instant, elements in LINES.get(taxonomy, ()):
        for tag in elements:
            annual = fetch_sec.annual_facts(fetch_sec._entries(gaap.get(tag), unit), instant=instant, tags=tags, notes=[], tag=tag)  # pyright: ignore[reportPrivateUsage]
            for end, fact in annual.items():
                by_end.setdefault(end.isoformat(), {}).setdefault(field, (float(fact.val), tag))
    out: list[boundary.QualityLines] = []
    for end in sorted(by_end, reverse=True)[:MAX_YEARS]:
        got = by_end[end]

        def value(field: str) -> float | None:
            return got[field][0] if field in got else None

        out.append(boundary.QualityLines(
            period_end=end, total_assets=value("total_assets"), current_assets=value("current_assets"),
            current_liabilities=value("current_liabilities"), gross_profit=value("gross_profit"), cost_of_revenue=value("cost_of_revenue"),
            rows=[(field, got[field][1]) for field, _, _ in LINES[taxonomy] if field in got]))
    return out


def of_record(facts: Mapping[str, object] | None, taxonomy: str, unit: str | None, tags: reference.XbrlTags) -> tuple[list[boundary.QualityLines], str | None]:
    """(lines, reason): the list, or empty with why."""
    if facts is None or not taxonomy or unit is None:
        return [], NO_FACTS
    found = lines(facts, taxonomy, unit, tags)
    return (found, None) if found else ([], NO_LINES)
