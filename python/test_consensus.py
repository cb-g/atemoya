"""(82) Consensus and surprise: the snapshot's contract, idempotency per day, gap records, the
filed quarters, the windows and the pooled rate. No network: the vendor is a fake."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

import consensus as c


def _w(x: float) -> dict[str, Any]:
    return {"raw": x, "fmt": str(x)}


def _trend(period: str, end: str, eps: float | None = 1.0, rev: float | None = 100.0) -> dict[str, Any]:
    eps_block: dict[str, Any] = {"earningsCurrency": "USD", "low": _w(0.9), "high": _w(1.1), "numberOfAnalysts": _w(12), "yearAgoEps": _w(0.8)}
    if eps is not None:
        eps_block["avg"] = _w(eps)
    rev_block: dict[str, Any] = {"revenueCurrency": "USD", "numberOfAnalysts": _w(14)}
    if rev is not None:
        rev_block["avg"] = _w(rev)
    return {"period": period, "endDate": end, "earningsEstimate": eps_block, "revenueEstimate": rev_block,
            "epsTrend": {"current": _w(1.0), "7daysAgo": _w(0.99), "30daysAgo": {}, "60daysAgo": _w(0.95)}}


def test_the_trend_parses_with_absent_figures_null_never_zero() -> None:
    raw = [_trend("+1y", "2027-12-31"), _trend("0q", "2026-09-30", rev=None), {"period": "-1q"}, "junk"]
    periods, eps_cur, rev_cur = c.parse_trend(raw)
    assert [p["period"] for p in periods] == ["0q", "+1y"]          # vendor order restored, unknown dropped
    q = periods[0]
    assert q["end_date"] == "2026-09-30"
    assert q["eps"] == {"mean": 1.0, "low": 0.9, "high": 1.1, "analysts": 12, "year_ago": 0.8}
    assert q["revenue"]["mean"] is None and q["revenue"]["analysts"] == 14 and q["revenue"]["low"] is None
    assert q["eps_trend"] == {"current": 1.0, "7d": 0.99, "30d": None, "60d": 0.95, "90d": None}
    assert (eps_cur, rev_cur) == ("USD", "USD")


def test_a_record_is_ok_or_failed_with_why() -> None:
    day = date(2026, 10, 2)
    ok = c.snapshot_record("X", day, "t", [_trend("0q", "2026-09-30")])
    assert ok["status"] == "ok" and ok["date"] == "2026-10-02" and ok["reason"] is None
    boom = c.snapshot_record("X", day, "t", RuntimeError("401"))
    assert boom["status"] == "failed" and boom["reason"] == "vendor failed: RuntimeError: 401" and boom["periods"] == []
    nothing = c.snapshot_record("X", day, "t", [])
    assert nothing["status"] == "none" and nothing["reason"] == "the vendor carries no consensus for this name"
    empty = c.snapshot_record("X", day, "t", [_trend("0q", "2026-09-30", eps=None, rev=None)])
    assert empty["status"] == "none" and "no EPS or revenue estimate" in empty["reason"]


def test_missing_days_are_the_calendar_days_since_the_last_run() -> None:
    today = date(2026, 10, 5)
    assert c.missing_days([], today) == []                                    # a first run calls nothing missing
    assert c.missing_days([date(2026, 10, 4)], today) == []
    assert c.missing_days([date(2026, 10, 1), date(2026, 10, 3)], today) == [date(2026, 10, 2), date(2026, 10, 4)]
    assert c.missing_days([today], today) == []                              # only today on disk: nothing earlier


def test_the_daily_run_is_idempotent_and_writes_gaps(tmp_path: Path) -> None:
    calls: list[str] = []
    fail = {"B"}

    def vendor(t: str) -> object:
        calls.append(t)
        if t in fail:
            raise RuntimeError("busy")
        return [] if t == "F" else [_trend("0q", "2026-09-30")]

    stamps = iter(["first", "second", "third", "fourth", "fifth"])
    def now() -> str:
        return next(stamps)

    def quiet(s: str) -> None:
        return None

    m = c.run_snapshot(["A", "B", "F"], tmp_path, date(2026, 10, 1), vendor, now=now, pace=0, log=quiet)
    assert m["status"] == "partial" and m["failed"] == ["B"] and m["ok"] == 1 and m["none"] == ["F"]
    a_first = json.loads((tmp_path / "days/2026-10-01/A.json").read_text())

    fail.clear()
    calls.clear()
    m = c.run_snapshot(["A", "B", "F"], tmp_path, date(2026, 10, 1), vendor, now=now, pace=0, log=quiet)
    assert calls == ["B"]                                       # neither the ok record nor the no-consensus one is fetched again
    assert json.loads((tmp_path / "days/2026-10-01/A.json").read_text()) == a_first
    assert m["status"] == "complete" and m["failed"] == [] and m["none"] == ["F"]   # a fund with no bar is not a failure

    calls.clear()
    c.run_snapshot(["A", "B"], tmp_path, date(2026, 10, 1), vendor, now=now, pace=0, log=quiet)
    assert calls == []                                                         # a third run the same day fetches nothing

    c.run_snapshot(["A"], tmp_path, date(2026, 10, 4), vendor, now=now, pace=0, log=quiet)
    for d in ("2026-10-02", "2026-10-03"):
        gap = json.loads((tmp_path / "days" / d / "manifest.json").read_text())
        assert gap["status"] == "gap" and gap["reason"] == c.GAP_REASON and gap["names"] == 0
    assert c.day_dirs(tmp_path) == [date(2026, 10, d) for d in (1, 2, 3, 4)]


def _fact(start: str, end: str, val: float, filed: str, form: str = "10-Q") -> dict[str, Any]:
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form}


def _facts(by_tag: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    return {"facts": {"us-gaap": {t: {"units": {"USD": rows}} for t, rows in by_tag.items()}}}


def test_filed_quarters_first_filed_with_a_derived_fourth() -> None:
    facts = _facts({
        "Revenues": [
            _fact("2025-01-01", "2025-03-31", 100, "2025-05-01"),
            _fact("2025-01-01", "2025-03-31", 999, "2026-05-01"),        # the same quarter restated a year later: not taken
            _fact("2025-04-01", "2025-06-30", 110, "2025-08-01"),
            _fact("2025-07-01", "2025-09-30", 120, "2025-11-01"),
            _fact("2025-01-01", "2025-09-30", 330, "2025-11-01"),        # nine months
            _fact("2025-01-01", "2025-12-31", 460, "2026-02-15", "10-K"),  # the year; no three-month Q4 filed
        ],
        "SalesRevenueNet": [_fact("2025-04-01", "2025-06-30", 5, "2025-08-01")],   # a later tag in the list loses
    })
    tags = ["Revenues", "SalesRevenueNet"]
    q = {r["end"]: r for r in c.filed_quarter_revenue(facts, "us-gaap", tags, "USD")}
    assert [q[e]["value"] for e in sorted(q)] == [100, 110, 120, 130]
    assert q["2025-03-31"]["basis"].startswith("three months as first filed (Revenues, filed 2025-05-01)")
    assert q["2025-12-31"]["basis"].startswith("fiscal year less the nine months to 2025-09-30")
    assert c.revenue_unit(facts, "us-gaap", tags) == "USD"
    ends = c.filed_period_ends(facts, "us-gaap", tags, "USD")
    assert date(2025, 12, 31) in ends and date(2025, 9, 30) in ends


def test_a_release_takes_the_latest_period_ending_before_it() -> None:
    ends = [date(2025, 6, 30), date(2025, 9, 30), date(2025, 12, 31)]
    assert c.fiscal_period_of(date(2025, 11, 5), ends) == ("2025-09-30", None)
    assert c.fiscal_period_of(date(2025, 9, 30), ends) == ("2025-06-30", None)  # the same day is not after the end
    assert c.fiscal_period_of(date(2026, 9, 1), ends) == (None, c.NO_PERIOD)
    rows = [(date(2025, 11, 5), "s1", 1.0, 1.1), (date(2026, 11, 5), "s2", 2.0, None), (date(2026, 2, 1), "s0", 1.2, 1.2)]
    out = c.release_rows(rows, date(2026, 10, 2), ends)
    assert [r["report_date"] for r in out] == ["2025-11-05", "2026-02-01"]       # oldest first, the future one dropped
    assert out[1]["fiscal_period_end"] == "2025-12-31"
    assert c.release_rows(rows, date(2026, 10, 2), None)[0]["fiscal_period_reason"] == c.NO_FILER


def test_the_windows_count_beats_and_measure_surprise() -> None:
    pairs = [(1.0, 0.5)] * 4 + [(1.0, 1.1), (1.0, 1.0), (0.0, 0.1), (2.0, 2.5), (1.0, 1.2), (1.0, 0.9), (1.0, 1.3), (4.0, 5.0)]
    w8 = c.window_stats(pairs, 8)
    assert (w8["n"], w8["beats"], w8["meets"], w8["misses"]) == (8, 6, 1, 1)
    assert w8["beat_rate"] == 6 / 8
    assert w8["surprise_pct"]["n"] == 7 and "estimate is zero" in w8["surprise_pct"]["reason"]
    assert round(w8["surprise_pct"]["median"], 6) == 20.0
    w12 = c.window_stats(pairs, 12)
    assert w12["n"] == 12 and w12["beats"] == 6 and w12["misses"] == 5 and w12["surprise_pct"]["reason"] is not None
    short = c.window_stats(pairs[:3], 8)
    assert short["n"] == 3                                                     # fewer than the window: n says so
    assert c.window_stats([], 8)["beat_rate"] is None
    a = c.window_stats([(100.0, 110.0), (100.0, 95.0)], 8, absolute=True)
    assert a["surprise_abs"]["median"] == 2.5


def _snap(day: str, period: str, end: str, mean: float, cur: str = "USD") -> dict[str, Any]:
    return {"ticker": "X", "date": day, "status": "ok", "revenue_currency": cur, "eps_currency": "USD",
            "periods": [{"period": period, "end_date": end, "eps": {"mean": 1.0},
                         "revenue": {"mean": mean, "low": mean - 1, "high": mean + 1, "analysts": 9}}]}


def test_revenue_pairs_take_the_last_bar_before_the_release() -> None:
    releases = [{"report_date": "2026-11-05"}]
    quarters = [{"end": "2026-09-27", "value": 110.0, "currency": "USD", "basis": "three months as first filed"}]
    snaps = [_snap("2026-08-10", "+1q", "2026-09-30", 100.0),
             _snap("2026-10-20", "0q", "2026-09-30", 104.0),
             _snap("2026-11-05", "0q", "2026-09-30", 120.0)]                   # the release day itself: not a bar
    pairs = c.revenue_pairs(snaps, releases, quarters)
    assert len(pairs) == 1
    p = pairs[0]
    assert (p["bar_taken"], p["mean"], p["actual"], p["bar_period"]) == ("2026-10-20", 104.0, 110.0, "0q")
    assert p["bar_age_days"] == 16
    assert round(p["surprise_pct"], 6) == round(6 / 104 * 100, 6) and p["surprise_abs"] == 6.0
    assert c.revenue_pairs([_snap("2026-10-20", "0q", "2026-09-30", 104.0, cur="CAD")], releases, quarters) == []
    assert c.revenue_pairs([], releases, quarters) == []


def test_the_summary_pools_and_says_what_is_missing() -> None:
    history = {"status": "ok", "releases": [
        {"report_date": f"2025-{m:02d}-10", "eps_estimate": 1.0, "eps_reported": r} for m, r in zip(range(1, 13), [1.1] * 9 + [0.9] * 3)],
        "filed_revenue": [], "filed_revenue_reason": c.NO_FILER}
    s = c.summarize("X", history, [])
    assert s["eps"][0]["beat_rate"] == 5 / 8 and s["eps"][1]["beat_rate"] == 9 / 12
    assert s["revenue"] is None and s["revenue_reason"] == c.NO_FILER
    assert s["current"] is None and s["current_reason"] == "no ok snapshot on disk"
    assert s["basis"] == c.BASIS
    other = c.summarize("Y", None, [_snap("2026-10-02", "0q", "2026-12-31", 50.0)])
    assert other["eps"] is None and other["eps_reason"] == "no release history on disk"
    assert other["current"]["as_of"] == "2026-10-02"
    pool = c.pooled([s, other])
    assert pool["windows"][0] == {"window": 8, "names": 1, "releases": 8, "beats": 5, "beat_rate": 5 / 8}
    assert pool["windows"][1]["beat_rate"] == 9 / 12
    text = c.summary_text([s, other], pool, date(2026, 10, 2))
    assert "pooled, last 12: 9 beats in 12 releases over 1 names" in text and "no EPS history" in text


def test_a_history_the_vendor_answers_empty_is_none_and_a_raising_vendor_is_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import fetch
    import fetch_sec
    from types import SimpleNamespace

    def identity() -> str:
        return "t"

    def table(agent: str) -> dict[str, str]:
        return {}

    def tags() -> dict[str, Any]:
        return {}

    def cik_of(ticker: str, table: dict[str, str], cik: str | None) -> tuple[str | None, str]:
        return None, ""

    monkeypatch.setattr(fetch_sec, "identity", identity)
    monkeypatch.setattr(fetch_sec, "tickers_table", table)
    monkeypatch.setattr(fetch_sec, "load_tags", tags)
    monkeypatch.setattr(fetch, "cik_of", cik_of)
    monkeypatch.setattr(c, "PACE_SECONDS", 0)

    def vendor(ticker: str) -> list[tuple[date, str, float | None, float | None]]:
        if ticker == "F":
            raise RuntimeError("down")
        return []

    def quiet(_: str) -> None:
        return None

    monkeypatch.setattr(c, "vendor_releases", vendor)
    entries = [SimpleNamespace(ticker="E", cik=None), SimpleNamespace(ticker="F", cik=None)]
    c.run_history(entries, tmp_path, date(2026, 10, 3), log=quiet)
    empty = json.loads((tmp_path / "history/E.json").read_text())
    assert empty["status"] == "none" and empty["reason"] == c.NO_RELEASES and empty["releases"] == []
    down = json.loads((tmp_path / "history/F.json").read_text())
    assert down["status"] == "failed" and down["reason"].startswith("vendor failed: RuntimeError")


def test_the_chart_names_every_state_the_files_carry() -> None:
    """The record's reasons are held to docs/flow.md by the OCaml suite; the side output's
    states are held to its own table here, so a new state lands in the chart or fails."""
    chart = (Path(__file__).resolve().parent.parent / "docs" / "flow.md").read_text()
    states = [c.GAP_REASON, c.NO_FILER, c.NO_PERIOD, c.NO_REVENUE_PAIRS, c.ZERO_ESTIMATE,
              "vendor failed:", "the vendor carries no consensus for this name",
              "the vendor lists the periods but no EPS or revenue estimate in any",
              "name(s) failed; rerun today to retry them", "no consensus", c.NO_RELEASES]
    source = Path(c.__file__).read_text()
    for s in states:
        assert s in chart, s
        assert s in source or s.startswith("no filed fiscal period"), s
