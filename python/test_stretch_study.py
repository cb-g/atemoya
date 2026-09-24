"""(67) Episode detection, the forward windows, the insider cut and the small-cell rule,
on synthetic series. Nothing observed is written down here."""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

import stretch
import stretch_study as study


def series(values: list[float]) -> tuple[dict[date, float], dict[date, float]]:
    start = date(2020, 1, 1)
    closes = {start + timedelta(days=i): v for i, v in enumerate(values)}
    return closes, {d: 1_000_000.0 for d in closes}


def flat_then(n: int, tail: list[float], level: float = 100.0) -> list[float]:
    return [level] * n + tail


def test_an_episode_starts_once_and_needs_twenty_quiet_days() -> None:
    """The first day the count reaches 3 begins an episode; the count staying at 3 does not
    begin another, and it takes twenty days back under 3 before one can."""
    t = stretch.load_thresholds()
    # a long flat run, a crash held for a while, a recovery, then a second crash
    values = flat_then(study.MIN_HISTORY_DAYS + 50, [])
    values += [60.0] * 30                      # deep enough to fire the low side
    values += [100.0] * 60                     # back to quiet for well over twenty days
    values += [60.0] * 30                      # and again
    closes, volumes = series(values)
    found = study.episode_days(closes, volumes, t)
    lows = [i for i, side, _, _, _ in found if side == "low"]
    assert len(lows) == 2, lows                # exactly two starts, not sixty
    assert lows[1] - lows[0] > 60              # the second is the second crash, not a repeat

    # the same crash with only a short break in the middle is one episode, not two
    short = flat_then(study.MIN_HISTORY_DAYS + 50, []) + [60.0] * 30 + [100.0] * 5 + [60.0] * 30
    closes, volumes = series(short)
    assert len([1 for _, side, _, _, _ in study.episode_days(closes, volumes, t) if side == "low"]) == 1


def test_the_counts_are_the_blocks_own() -> None:
    """The walk uses the block's measures_at and counts, so a day the walk calls an episode
    is a day the block would also count at three."""
    t = stretch.load_thresholds()
    closes, volumes = series(flat_then(study.MIN_HISTORY_DAYS + 50, []) + [60.0] * 30)
    found = study.episode_days(closes, volumes, t)
    assert found
    i, _side, _m, low, high = found[0]
    days = sorted(closes)
    block, reason = stretch.compute(closes, volumes, days[i], t)
    assert block is not None, reason
    assert (block.stretch_low, block.stretch_high) == (low, high)


def test_forward_returns_and_the_window_past_the_last_close() -> None:
    closes, _ = series([100.0] * 10 + [110.0] * 200)
    days = sorted(closes)
    out = study.forward_returns(closes, days, 0)
    assert out["20"] is not None and abs(out["20"] - 0.10) < 1e-12
    assert out["120"] is not None
    # a horizon that runs off the end is null, never a shortened window
    out = study.forward_returns(closes, days, len(days) - 5)
    assert out["20"] is None and out["60"] is None and out["120"] is None


def recent_of(rows: list[tuple[str, str]]) -> dict[str, list[str]]:
    """The filings block: one Form 4 per (accession, filing date)."""
    return {
        "form": ["4"] * len(rows),
        "accessionNumber": [a for a, _ in rows],
        "filingDate": [d for _, d in rows],
        "reportDate": [d for _, d in rows],
        "primaryDocument": [f"{a}.xml" for a, _ in rows],
        "acceptanceDateTime": [f"{d}T12:00:00.000Z" for _, d in rows],
    }


def index_of(rows: list[tuple[str, str]]) -> dict[str, object]:
    """A submissions index around that block."""
    return {"filings": {"recent": recent_of(rows)}}


def cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cik: str,
          documents: dict[str, bytes]) -> None:
    """Put the named documents on disk under a cache directory of our own."""
    import insiders

    monkeypatch.setattr(insiders, "CACHE_DIR", tmp_path)
    (tmp_path / cik).mkdir(parents=True, exist_ok=True)
    for accession, body in documents.items():
        (tmp_path / cik / f"{accession}.xml").write_bytes(body)


def test_the_insider_window_is_cut_at_the_day_before_the_episode(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing filed on the episode's own day or after it may be read: the state is what a
    reader had when the episode began. A purchase filed the morning of the episode is the
    case that matters, because reading it would make the study say insiders called a bottom
    they had not yet been seen to call."""
    from test_insiders import form4, line

    cik = "0000000001"
    episode = date(2026, 6, 1)
    rows = [("before", "2026-05-06"), ("same-day", "2026-06-01"), ("after", "2026-06-30")]
    documents = {
        "before": form4(owner="Early", transactions=line("S", "2026-05-04", 100, "10")),
        "same-day": form4(owner="Same", transactions=line("P", "2026-05-30", 100, "10")),
        "after": form4(owner="Late", transactions=line("P", "2026-06-20", 100, "10")),
    }
    cache(tmp_path, monkeypatch, cik, documents)
    state = study.insiders_before(cik, episode, index_of(rows))
    assert state.state == "neither"          # one seller is not selling pressure
    assert state.buyers == 0 and state.sellers == 1
    assert state.reason is None

    # the same window a day later does read the filing made on the episode's own day
    later = study.insiders_before(cik, episode + timedelta(days=1), index_of(rows))
    assert later.state == "bought" and later.buyers == 1


def test_a_window_the_cache_cannot_complete_is_unknown_and_never_counted(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A window missing one filing may be missing the only purchase, so it says unknown
    rather than counting the subset it holds."""
    from test_insiders import form4, line

    cik = "0000000001"
    rows = [("kept", "2026-05-06"), ("absent", "2026-05-20")]
    cache(tmp_path, monkeypatch, cik, {"kept": form4(transactions=line("S", "2026-05-04", 100, "10"))})
    state = study.insiders_before(cik, date(2026, 6, 1), index_of(rows))
    assert state.state == "unknown"
    assert state.reason is not None and "not cached" in state.reason
    assert state.buyers is None and state.net_dollars is None

    # with the missing one on disk the same window counts
    cache(tmp_path, monkeypatch, cik, {"absent": form4(owner="Other", transactions=line("P", "2026-05-18", 100, "10"))})
    assert study.insiders_before(cik, date(2026, 6, 1), index_of(rows)).state == "bought"


def test_an_older_page_that_is_not_cached_is_unknown(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`filings.recent` is a year, not a history. A window reaching past it needs the older
    pages, and an unread page is a quarter the study cannot see -- never a quiet one."""
    import fetch_sec

    cik = "0000000001"
    monkeypatch.setattr(fetch_sec, "CACHE_DIR", tmp_path / "sec")
    cache(tmp_path / "docs", monkeypatch, cik, {})
    index = index_of([("recent-one", "2026-09-01")])
    index["filings"] = {"recent": recent_of([("recent-one", "2026-09-01")]),
                        "files": [{"name": "page-001.json", "filingFrom": "2020-01-01",
                                   "filingTo": "2026-08-31"}]}
    assert "not cached" in (study.insiders_before(cik, date(2026, 6, 1), index).reason or "")

    # the same window with the page on disk reads it, and the filing inside it counts
    from test_insiders import form4, line

    (tmp_path / "sec").mkdir(parents=True, exist_ok=True)
    (tmp_path / "sec" / "page-001.json").write_text(json.dumps(recent_of([("older", "2026-05-06")])))
    cache(tmp_path / "docs", monkeypatch, cik,
          {"older": form4(transactions=line("P", "2026-05-04", 100, "10"))})
    assert study.insiders_before(cik, date(2026, 6, 1), index).state == "bought"

    # and a page whose span does not meet the window is not wanted at all
    index["filings"] = {"recent": recent_of([("recent-one", "2026-09-01")]),
                        "files": [{"name": "far-away.json", "filingFrom": "2005-01-01",
                                   "filingTo": "2010-12-31"}]}
    assert study.insiders_before(cik, date(2026, 6, 1), index).reason is None


def test_an_empty_window_read_in_full_is_zero_and_not_unknown(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Nothing filed in the window is an answer, not an absence: the state is `neither` with
    counts of zero, so a reader can tell it from a window that could not be read."""
    cik = "0000000001"
    cache(tmp_path, monkeypatch, cik, {})
    rows = [("old", "2020-01-02")]                 # on file, but nowhere near the window
    state = study.insiders_before(cik, date(2026, 6, 1), index_of(rows))
    assert state.state == "neither" and state.reason is None
    assert (state.buyers, state.sellers, state.net_dollars) == (0, 0, 0.0)
    assert state.cluster is False and state.chief_bought is False


def test_the_unknown_reasons_name_what_is_missing() -> None:
    """A name off the filing path and a CIK that has never filed a Form 4 are different
    silences, and the study says which."""
    import insiders

    assert study.insiders_before(None, date(2026, 6, 1), None).reason == insiders.NO_CIK
    assert study.insiders_before("0000000001", date(2026, 6, 1), None).state == "unknown"
    empty = index_of([])
    assert study.insiders_before("0000000001", date(2026, 6, 1), empty).reason == study.NO_FORM_4


def test_the_walk_is_cut_at_the_as_of_date() -> None:
    """The vendor serves its history to the present and the present moves, so a walk that
    took it whole would find one more episode in the afternoon than in the morning."""
    t = stretch.load_thresholds()
    values = flat_then(study.MIN_HISTORY_DAYS + 50, []) + [100.0] * 40 + [60.0] * 30
    closes, volumes = series(values)
    days = sorted(closes)
    assert [side for _, side, _, _, _ in study.episode_days(closes, volumes, t)] == ["low"]
    # the same series cut before the crash has no episode at all
    cut = days[len(values) - 31]
    before = {d: c for d, c in closes.items() if d <= cut}
    assert study.episode_days(before, {d: volumes[d] for d in before}, t) == []


def test_a_small_cell_prints_its_count_and_nothing_else() -> None:
    """A median of a handful is a number pretending to be a measurement."""
    def episode(excess: float) -> study.Episode:
        return study.Episode(
            ticker="X", side="low", date="2026-01-01", close=1.0, dd_120=-0.3, above_120_low=0.0,
            vs_ma50=-0.2, vs_ma200=-0.25, rsi_14=20.0, stretch_low=4, stretch_high=0,
            forward={"20": excess, "60": excess, "120": excess},
            benchmark={"20": 0.0, "60": 0.0, "120": 0.0},
            excess={"20": excess, "60": excess, "120": excess},
            insider_state="bought", insider_buyers=1, insider_sellers=0, insider_net_dollars=1.0,
            insider_cluster=False, insider_chief_bought=False, insider_reason=None,
            overlaps_previous=False)

    few = [episode(0.01 * i) for i in range(study.MIN_CELL - 1)]
    assert study.cell(few, 60) == f"n={len(few)}"
    assert "median" not in study.cell(few, 60)
    many = [episode(0.01 * i) for i in range(study.MIN_CELL + 5)]
    assert "median" in study.cell(many, 60) and f"n={len(many)}" in study.cell(many, 60)
    # and the sentence says so too rather than quoting a median it cannot carry
    assert "too few" in study.sentence(few, "low")
    assert "median" in study.sentence(many, "low")


def test_first_per_name_per_year_keeps_one() -> None:
    def episode(ticker: str, when: str) -> study.Episode:
        return study.Episode(
            ticker=ticker, side="low", date=when, close=1.0, dd_120=-0.3, above_120_low=0.0,
            vs_ma50=-0.2, vs_ma200=-0.25, rsi_14=20.0, stretch_low=4, stretch_high=0,
            forward={"20": None, "60": None, "120": None}, benchmark={"20": None, "60": None, "120": None},
            excess={"20": None, "60": None, "120": None}, insider_state="neither",
            insider_buyers=0, insider_sellers=0, insider_net_dollars=0.0, insider_cluster=False,
            insider_chief_bought=False, insider_reason=None, overlaps_previous=False)

    rows = [episode("A", "2024-01-05"), episode("A", "2024-09-05"), episode("A", "2025-02-01"), episode("B", "2024-03-01")]
    kept = study.first_per_name_per_year(rows)
    assert [(e.ticker, e.date) for e in kept] == [("A", "2024-01-05"), ("A", "2025-02-01"), ("B", "2024-03-01")]


def test_the_insider_state_is_the_briefs_three() -> None:
    import boundary

    def w(buyers: int, sellers: int, net: float) -> boundary.InsiderWindow:
        return boundary.InsiderWindow(days=90, buyers=buyers, sellers=sellers, dollars_bought=0.0,
                                      dollars_sold=0.0, net_dollars=net, largest_purchase=None,
                                      ceo_or_cfo_bought=False)

    assert study.state_of(w(1, 0, 10.0)) == "bought"
    assert study.state_of(w(0, 2, -10.0)) == "sold"
    assert study.state_of(w(0, 1, -10.0)) == "neither"   # one seller is not selling pressure
    assert study.state_of(w(0, 2, 10.0)) == "neither"    # two sellers but net buying is not selling
    assert study.state_of(w(0, 0, 0.0)) == "neither"
