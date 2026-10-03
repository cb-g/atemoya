"""The filed research and development history behind the R&D shadow.

Contract: `history` returns the annual research and development expense per fiscal year
end as the filer's facts carry it, newest first, at most MAX_YEARS years, each with the
element it was filed under and the date of the filing read; a restated year reads its
latest filing among the facts given, so a point-in-time caller passes facts already cut at
its date. The tag lists are ordered: the first tag carrying a year wins that year. The
element that excludes acquired in-process research comes first, for two reasons: bought
research is an acquisition and not the recurring spend the schedule capitalises, and a
filer that reports under it may use the plain element for a small separate item (Johnson &
Johnson files its research spend under the excluding element and a figure a hundredth of
the size under the plain one), which read first would build an asset from the wrong line. No
value is derived, summed or estimated; a filer with no such line gets an empty list and the
caller records the reason. The tags live here and not in reference/xbrl_tags.json because
every element named there enters the restatement scan, which would make this a measured
change to existing records; the shadow reads beside the statements and moves none of them."""

from __future__ import annotations

from collections.abc import Mapping

import boundary
import fetch_sec
import reference

MAX_YEARS = 12
TAGS: dict[str, tuple[str, ...]] = {
    "us-gaap": ("ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
                "ResearchAndDevelopmentExpense",
                "ResearchAndDevelopmentExpenseSoftwareExcludingAcquiredInProcessCost"),
    "ifrs-full": ("ResearchAndDevelopmentExpense",),
}
NO_FACTS = "no filed facts are read for this name: the statements come from another provider, which carries too few years to capitalise"
NO_LINE = "the filer's facts carry no annual research and development expense"


def history(facts: Mapping[str, object], taxonomy: str, unit: str, tags: reference.XbrlTags) -> list[boundary.RdYear]:
    gaap = fetch_sec._as_dict(fetch_sec._as_dict(facts.get("facts")).get(taxonomy))  # pyright: ignore[reportPrivateUsage]
    chosen: dict[str, boundary.RdYear] = {}
    for tag in TAGS.get(taxonomy, ()):
        annual = fetch_sec.annual_facts(fetch_sec._entries(gaap.get(tag), unit), instant=False, tags=tags, notes=[], tag=tag)  # pyright: ignore[reportPrivateUsage]
        for end, fact in annual.items():
            chosen.setdefault(end.isoformat(), boundary.RdYear(period_end=end.isoformat(), value=float(fact.val), tag=tag, filed=fact.filed.isoformat()))
    return [chosen[k] for k in sorted(chosen, reverse=True)][:MAX_YEARS]


def of_record(facts: Mapping[str, object] | None, taxonomy: str, unit: str | None, tags: reference.XbrlTags) -> tuple[list[boundary.RdYear], str | None]:
    """(history, reason): the list, or empty with why."""
    if facts is None or not taxonomy or unit is None:
        return [], NO_FACTS
    years = history(facts, taxonomy, unit, tags)
    return (years, None) if years else ([], NO_LINE)
