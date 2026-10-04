"""Earnings reactions on invented releases: the match by date, the outcome, the medians on
each side with their floor, the beats sold, and the reasons. No network."""

from __future__ import annotations

from datetime import date

import earnings_reactions as er

Json = dict[str, object]


def event(filed: str, excess: float) -> Json:
    return {"filed": filed, "before": filed, "after": filed, "own": excess, "benchmark": 0.0, "excess": excess}


def release(report_date: str, estimate: float | None, reported: float | None) -> Json:
    return {"report_date": report_date, "eps_estimate": estimate, "eps_reported": reported}


def record(events: list[Json], implied: float | None = None) -> Json:
    block: Json = {"calendar": {"next_date": "2026-10-28", "events": events, "realised_median_abs_excess": 0.03}, "days_to_next": 24}
    if implied is not None:
        block["implied"] = {"implied_move": implied}
        block["implied_over_realised"] = implied / 0.03
    return {"earnings": block}


def test_releases_match_by_date_and_carry_the_outcome() -> None:
    events = [event("2026-01-28", 0.05), event("2026-04-30", -0.02), event("2026-07-29", 0.01), event("2025-10-29", 0.03)]
    releases = [release("2026-01-28", 1.0, 1.2), release("2026-04-29", 1.0, 1.1),      # filed a day after the vendor's date
                release("2026-07-20", 1.0, 0.9),                                       # nine days off: not this release
                release("2025-10-29", 1.0, None)]                                      # no reported figure
    matched = er.match(events, releases)
    assert [(m["filed"], m["outcome"]) for m in matched] == [("2026-01-28", "beat"), ("2026-04-30", "beat")]
    assert abs(float(str(matched[0]["surprise_pct"])) - 20.0) < 1e-9
    assert er.outcome(1.0, 1.0) == "meet" and er.outcome(1.0, 0.5) == "miss"


def test_a_row_summarises_each_side_and_counts_the_beats_sold() -> None:
    events = [event(f"2025-0{i}-15", x) for i, x in enumerate((0.04, -0.01, 0.02, -0.03, 0.05), start=1)]
    releases = [release(str(e["filed"]), 1.0, r) for e, r in zip(events, (1.1, 1.2, 1.3, 0.9, 0.8))]
    row = er.row_of("X", record(events, implied=0.06), {"status": "ok", "releases": releases})
    assert row["beats"] == {"n": 3, "median_excess": 0.02} and row["misses"] == {"n": 2, "median_excess": None}   # two is under the floor: a count alone
    assert row["beats_sold"] == 1 and row["misses_bought"] == 1
    assert row["implied_move"] == 0.06 and row["days_to_next"] == 24 and row["next_date"] == "2026-10-28"
    assert er.row_of("X", None, None)["reason"] == "no record for the name in the run"
    assert er.row_of("X", {"status": "Failed"}, None)["reason"] == "the record carries no earnings calendar"
    assert "run python/consensus.py" in str(er.row_of("X", record(events), None)["reason"])
    assert er.row_of("X", record(events), {"status": "none", "reason": "no past release", "releases": []})["reason"] == "no past release"
    assert "matches a consensus bar" in str(er.row_of("X", record(events), {"status": "ok", "releases": []})["reason"])


def test_the_table_pools_every_matched_release_and_sorts_by_the_next_one() -> None:
    events = [event(f"2025-0{i}-15", x) for i, x in enumerate((0.04, -0.01, 0.02), start=1)]
    releases = [release(str(e["filed"]), 1.0, 1.1) for e in events]
    soon = er.row_of("SOON", {"earnings": {"calendar": {"next_date": "2026-10-08", "events": events}, "days_to_next": 4}}, {"status": "ok", "releases": releases})
    later = er.row_of("LATER", record(events), {"status": "ok", "releases": releases})
    text = er.table([later, er.row_of("NONE", None, None), soon], date(2026, 10, 4))
    assert "2 of 3 names with a matched release, 6 releases" in text and "on 6 beats the median excess move was +2.0%" in text and "2 beats were sold" in text
    assert [line.split()[0] for line in text.splitlines()[5:]] == ["SOON", "LATER", "NONE"]
