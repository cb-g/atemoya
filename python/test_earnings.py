"""(68) Item 2.02 detection, the cadence projection, the session rule and the gate, on
synthetic indexes and synthetic series. Nothing observed is written down here."""

from __future__ import annotations

from datetime import date

import boundary
import earnings
import hedge


def index_of(rows: list[tuple[str, str, str]], *, flat: bool = False) -> dict[str, object]:
    """(form, filing date, items) per filing. [flat] gives the shape of an older submissions
    page, whose arrays sit at the top level rather than under `filings.recent`."""
    block: dict[str, object] = {
        "form": [f for f, _, _ in rows],
        "filingDate": [d for _, d, _ in rows],
        "items": [i for _, _, i in rows],
        "acceptanceDateTime": [f"{d}T20:30:00.000Z" for _, d, _ in rows],
    }
    return block if flat else {"filings": {"recent": block}}


def test_item_202_needs_the_form_and_the_component() -> None:
    """A form gate is not optional: ABS-15G numbers its own items 1.01 to 2.03, so a
    shape-only match would read an asset-backed due-diligence item as an earnings release."""
    rows = [
        ("8-K", "2026-01-29", "2.02,9.01"),      # the ordinary shape
        ("8-K", "2026-04-30", "2.02"),           # and on its own
        ("8-K", "2026-05-02", "8.01,9.01"),      # an 8-K that is not a release
        ("8-K", "2026-05-03", "5.02,5.03,9.01"),
        ("ABS-15G", "2026-05-04", "2.02"),       # the trap: another form's item 2.02
        ("8-K/A", "2026-05-05", "2.02,9.01"),    # an amendment restates a release already dated
        ("EFFECT", "2026-05-06", ",,"),          # every part of an empty split matches nothing
        ("D", "2026-05-07", "06b"),
    ]
    found = [d for d, _ in earnings.results_filings(index_of(rows))]
    assert found == [date(2026, 1, 29), date(2026, 4, 30)]
    # an 8-K whose items merely CONTAIN the digits is not one either
    assert earnings.results_filings(index_of([("8-K", "2026-06-01", "12.02")])) == []
    # and an older page, whose arrays sit at the top level, reads the same
    assert [d for d, _ in earnings.results_filings(index_of(rows, flat=True))] == found


def test_the_cadence_is_the_median_of_the_last_eight() -> None:
    quarterly = [date(2024, 1, 25), date(2024, 4, 25), date(2024, 7, 25), date(2024, 10, 24),
                 date(2025, 1, 30), date(2025, 5, 1), date(2025, 7, 31), date(2025, 10, 30)]
    cadence = earnings.cadence_days(quarterly)
    assert cadence is not None and 88 <= cadence <= 94
    projected = earnings.project_next(quarterly, date(2026, 9, 24))
    assert projected is not None
    # the step repeats until it is in the future, so a stale history still projects forward
    assert projected[0] > date(2026, 9, 24)
    assert earnings.project_next([], date(2026, 9, 24)) is None
    assert earnings.project_next([date(2026, 1, 1)], date(2026, 9, 24)) is None   # one date is no interval
    # a filer that reports operating statistics under 2.02 as well has half the interval,
    # and the number says so rather than the projection hiding it
    twice = sorted(quarterly + [d.replace(day=2) for d in quarterly])
    noisy = earnings.cadence_days(twice)
    assert noisy is not None and noisy < 60


def test_the_session_decides_which_two_closes_bracket_a_release() -> None:
    """A release after the close on D moves D to D+1; one before the open moves D-1 to D.
    The index carries the acceptance time, so this is read and not assumed."""
    assert earnings.session_of("2026-07-30T20:30:28.000Z") == "after_close"
    assert earnings.session_of("2026-07-30T11:00:00.000Z") == "before_open"
    assert earnings.session_of("2026-07-30T17:00:00.000Z") == "intraday"
    assert earnings.session_of("") == "after_close"

    closes = {date(2026, 7, 29): 100.0, date(2026, 7, 30): 110.0, date(2026, 7, 31): 121.0}
    assert earnings.bracketing_closes(closes, date(2026, 7, 30), "after_close") == (date(2026, 7, 30), date(2026, 7, 31))
    assert earnings.bracketing_closes(closes, date(2026, 7, 30), "before_open") == (date(2026, 7, 29), date(2026, 7, 30))
    # a release with no close on one side of it is not an event, never a shortened one
    assert earnings.bracketing_closes(closes, date(2026, 7, 31), "after_close") is None


def test_the_event_move_is_excess_over_the_benchmark() -> None:
    closes = {date(2026, 7, 30): 100.0, date(2026, 7, 31): 110.0}
    market = {date(2026, 7, 30): 50.0, date(2026, 7, 31): 51.0}
    e = earnings.event_of(closes, market, date(2026, 7, 30), "after_close")
    assert isinstance(e, boundary.EarningsEvent)
    assert abs(e.own - 0.10) < 1e-12
    assert abs(e.benchmark - 0.02) < 1e-12
    assert abs(e.excess - 0.08) < 1e-12
    assert (e.before, e.after) == ("2026-07-30", "2026-07-31")
    assert earnings.event_of(closes, {}, date(2026, 7, 30), "after_close") is None


def gate(next_date: str | None = "2026-10-29", move: float | None = 0.05) -> hedge.EarningsGate:
    return hedge.EarningsGate(next_date, next_source="vendor calendar", implied_move=move,
                              reason=None if next_date else "no record in the run")


def candidate(expiry: str) -> hedge.Candidate:
    return hedge.Candidate("protective_put", expiry, 60, 100.0, None, None, 2.0, 1.9, 0.02, 0.95,
                           None, 100.0, hedge.Greeks(1.0, 0.0, 0.0, 0.0))


def test_a_candidate_across_the_date_is_marked_and_one_before_it_is_not() -> None:
    g = gate()
    before = candidate("2026-10-23").to_json(g)
    after = candidate("2026-10-30").to_json(g)
    on_the_day = candidate("2026-10-29").to_json(g)
    assert before["spans_earnings"] is False
    assert after["spans_earnings"] is True
    # an option expiring ON the release date is exposed to one made before the open
    assert on_the_day["spans_earnings"] is True
    assert after["earnings_date"] == "2026-10-29" and after["earnings_implied_move"] == 0.05


def test_no_date_is_null_with_a_reason_and_never_false() -> None:
    """`false` would say the expiry is clear of a release; silence is not that claim."""
    j = candidate("2026-10-30").to_json(gate(None, None))
    assert j["spans_earnings"] is None
    assert j["spans_earnings_reason"] == "no record in the run"
    assert "earnings_date" not in j


def test_the_gate_cannot_exclude_or_re_rank() -> None:
    """The flag lives at the serialisation boundary, so the key, the Pareto set and the
    constraint cannot see it: the candidate is the same object marked or unmarked."""
    c = candidate("2026-10-30")
    assert c.key() == candidate("2026-10-30").key()
    marked, unmarked = c.to_json(gate()), c.to_json()
    assert {k: v for k, v in marked.items() if not k.startswith("spans_") and not k.startswith("earnings_")} == unmarked
    assert "spans_earnings" not in unmarked
    # and the ordering of a set of candidates is untouched by the gate
    cands = [candidate("2026-12-18"), candidate("2026-10-23"), candidate("2026-10-30")]
    assert [x.expiry for x in sorted(cands, key=hedge.Candidate.key)] == \
           [x.expiry for x in sorted(cands, key=hedge.Candidate.key)]
    assert len(hedge.pareto(cands)) == len(hedge.pareto(cands))


def test_the_gate_from_a_record_carries_the_reason_through() -> None:
    assert hedge.earnings_gate(None, ticker="AAPL").reason == "no record in the run for AAPL"
