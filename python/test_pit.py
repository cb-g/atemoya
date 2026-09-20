"""Point-in-time (17): facts filed after the date excluded, the split correction, the last
trading day on or before, cover-page shares by filing date, the FRED observation on or
before the date, and the vendor-path record naming why it has no statements."""

from __future__ import annotations

import dataclasses
import json
import math
from datetime import date

import fetch
import pit
import pytest
import refresh_rates as rr
from test_fetch_sec import DEFS, TAGS, fact, usd


def test_filed_on_or_before_excludes_later_filings() -> None:
    facts = {"cik": 1, "facts": {"us-gaap": {
        "NetIncomeLoss": usd(fact("2024-12-31", 1e9, start="2024-01-01", filed="2025-02-20"), fact("2025-12-31", 2e9, start="2025-01-01", filed="2026-02-20")),
        "StockholdersEquity": usd(fact("2024-12-31", 9e9, filed="2025-02-20"), fact("2025-12-31", 10e9, filed="2026-02-20")),
        "OnlyLater": usd(fact("2025-12-31", 5e9, filed="2026-02-20")),
    }, "dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [fact("2025-01-31", 100.0, filed="2025-02-20"), fact("2026-01-31", 90.0, filed="2026-02-20")]}}}}}
    on = pit.filed_on_or_before(facts, date(2025, 6, 30))
    gaap = on["facts"]["us-gaap"]  # pyright: ignore[reportIndexIssue, reportUnknownVariableType]
    assert "OnlyLater" not in gaap  # pyright: ignore[reportOperatorIssue]
    assert [e["end"] for e in gaap["NetIncomeLoss"]["units"]["USD"]] == ["2024-12-31"]  # pyright: ignore[reportIndexIssue, reportUnknownVariableType]
    d = fetch_sec_decide(on)
    assert d.xbrl and d.currency == "USD"
    p = fetch_sec_periods(on)[0]
    assert p.period_end == "2024-12-31" and p.filed == "2025-02-20"
    # nothing filed by the date: no anchors at all
    assert not fetch_sec_decide(pit.filed_on_or_before(facts, date(2024, 1, 1))).xbrl
    cover = pit.point_count(on, date(2025, 6, 30), DEFS, TAGS)
    assert cover is not None and (cover.shares, cover.source, cover.tag, cover.as_of, cover.filed) == (100.0, "dei cover page", "EntityCommonStockSharesOutstanding", "2025-01-31", "2025-02-20")
    later = pit.point_count(facts, date(2026, 6, 30), DEFS, TAGS)
    assert later is not None and (later.shares, later.as_of) == (90.0, "2026-01-31")
    assert pit.point_count(pit.filed_on_or_before(facts, date(2024, 1, 1)), date(2024, 1, 1), DEFS, TAGS) is None


def fetch_sec_decide(facts: dict[str, object]):  # pyright: ignore[reportUnknownParameterType]
    import fetch_sec
    return fetch_sec.decide(facts, TAGS)


def fetch_sec_periods(facts: dict[str, object]):  # pyright: ignore[reportUnknownParameterType]
    import fetch_sec
    d = fetch_sec.decide(facts, TAGS)
    assert d.currency is not None
    return fetch_sec.periods_from_facts(d.facts, TAGS, DEFS, [], taxonomy=d.taxonomy, unit=d.currency)


def test_dei_shares_sums_share_classes_filed_on_the_same_date() -> None:
    facts = {"facts": {"dei": {"EntityCommonStockSharesOutstanding": {"units": {"shares": [
        fact("2025-01-31", 5.8e9, filed="2025-02-20"), fact("2025-01-31", 0.9e9, filed="2025-02-20"), fact("2025-01-31", 5.4e9, filed="2025-02-20"),
        fact("2025-01-31", 5.8e9, filed="2025-02-20"),  # a duplicate of one class is not counted twice
    ]}}}}}
    got = pit.point_count(facts, date(2025, 3, 31), DEFS, TAGS)
    assert got is not None and math.isclose(got.shares, 12.1e9) and got.source == "dei cover page"


def test_price_on_corrects_for_splits_after_the_date_and_takes_the_last_trading_day() -> None:
    # closes as the vendor serves them: split-adjusted for a 4:1 split on 2020-08-31
    closes = {date(2020, 8, 27): 125.01, date(2020, 8, 28): 124.81, date(2020, 8, 31): 129.04, date(2020, 9, 1): 134.18}
    history = pit.History(closes, {date(2014, 6, 9): 7.0, date(2020, 8, 31): 4.0})
    got = pit.price_on(history, date(2020, 8, 28))
    assert got is not None
    price_date, close, factor = got
    assert (price_date, close, factor) == (date(2020, 8, 28), 124.81, 4.0)
    assert math.isclose(close * factor, 499.24)  # the price actually quoted that day
    # a weekend date takes the Friday before; the split on the date itself is not "after"
    got = pit.price_on(history, date(2020, 8, 30))
    assert got is not None and got[0] == date(2020, 8, 28) and got[2] == 4.0
    got = pit.price_on(history, date(2020, 8, 31))
    assert got is not None and got[0] == date(2020, 8, 31) and got[2] == 1.0
    assert pit.price_on(history, date(2020, 8, 20)) is None  # nothing within the lookback
    assert pit.price_on(history, date(2020, 9, 20)) is None


def test_observation_on_or_before_the_date() -> None:
    body = json.dumps({"observations": [
        {"date": "2025-06-27", "value": "4.10"}, {"date": "2025-06-30", "value": "4.20"}, {"date": "2025-07-01", "value": "4.30"},
        {"date": "2025-06-29", "value": "."}]}).encode()
    assert pit.observation_on_or_before(body, "DGS7", date(2025, 6, 30)) == (date(2025, 6, 30), 4.20)
    assert pit.observation_on_or_before(body, "DGS7", date(2025, 6, 29)) == (date(2025, 6, 27), 4.10)  # the "." is skipped
    try:
        pit.observation_on_or_before(body, "DGS7", date(2025, 6, 1))
        raise AssertionError("expected no observation")
    except rr.RefreshError as e:
        assert "no observation on or before 2025-06-01" in str(e)


def test_vendor_path_record_names_why_it_has_no_statements() -> None:
    class Sec:
        user_agent = "test test@example.com"
        tickers: dict[str, object] = {"0": {"cik_str": 1, "ticker": "OTHER", "title": "x"}}
        tags = TAGS
        definitions = DEFS

    sec = Sec()
    history = pit.History({date(2025, 6, 27): 20.0}, {})
    quote = fetch.Quote.model_validate({"currency": "USD", "financial_currency": "USD", "price": 21.0, "market_cap": 1e9})
    r = pit.record("NOCIK", date(2025, 6, 30), sec, history, quote, None)
    assert r.point_in_time is not None and r.point_in_time.statements_unavailable == "vendor provider carries no filing dates"
    assert r.periods == [] and r.provider == "yfinance" and r.price == 20.0 and r.market_cap is None
    assert r.point_in_time.price_date == "2025-06-27" and r.as_of == "2025-06-30T00:00:00+00:00"
    assert r.point_in_time.shares_unavailable is None  # the statements reason comes first


def test_point_count_falls_back_to_the_balance_sheet_count_then_fails() -> None:
    """Alphabet: no undimensioned cover page, but a balance-sheet count at the newest fiscal
    period end filed by the date; a weighted-average count never stands in for a point."""
    facts = {"facts": {"us-gaap": {
        "CommonStockSharesOutstanding": {"units": {"shares": [fact("2024-12-31", 12211e6, filed="2025-02-05"), fact("2025-12-31", 12088e6, filed="2026-02-05")]}},
        "WeightedAverageNumberOfDilutedSharesOutstanding": {"units": {"shares": [fact("2025-12-31", 12150e6, start="2025-01-01", filed="2026-02-05")]}}}}}
    on = pit.filed_on_or_before(facts, date(2025, 6, 30))
    got = pit.point_count(on, date(2025, 6, 30), DEFS, TAGS)
    assert got is not None and (got.shares, got.source, got.tag, got.as_of, got.filed) == (12211e6, "balance sheet count", "CommonStockSharesOutstanding", "2024-12-31", "2025-02-05")
    newest = pit.point_count(facts, date(2026, 6, 30), DEFS, TAGS)
    assert newest is not None and (newest.shares, newest.as_of) == (12088e6, "2025-12-31")
    weighted_only = {"facts": {"us-gaap": {"WeightedAverageNumberOfDilutedSharesOutstanding": facts["facts"]["us-gaap"]["WeightedAverageNumberOfDilutedSharesOutstanding"]}}}  # pyright: ignore[reportIndexIssue]
    assert pit.point_count(weighted_only, date(2026, 6, 30), DEFS, TAGS) is None
    assert DEFS.shares_for_market_cap.point_in_time.cover_page == ["EntityCommonStockSharesOutstanding"]
    assert DEFS.shares_for_market_cap.point_in_time.balance_sheet == ["CommonStockSharesOutstanding"]


def test_same_period_vendor_check_matches_the_filed_period_or_none() -> None:
    filed = [fetch._period(date(2025, 12, 28), None, None, None)]  # pyright: ignore[reportPrivateUsage]
    vendor = [dataclasses.replace(fetch._period(date(2025, 12, 31), None, None, None), ebit=25.6e9),  # pyright: ignore[reportPrivateUsage]
              dataclasses.replace(fetch._period(date(2024, 12, 31), None, None, None), ebit=21.2e9)]  # pyright: ignore[reportPrivateUsage]
    check = pit.same_period_check(filed, vendor, 0.02)
    assert check is not None and check.secondary_period_end == "2025-12-31" and check.source == "live vendor statements, same fiscal period, fetched after D"
    assert pit.same_period_check([fetch._period(date(2021, 1, 2), None, None, None)], vendor, 0.02) is None  # no column for FY2020  # pyright: ignore[reportPrivateUsage]
    assert pit.same_period_check([], vendor, 0.02) is None and pit.same_period_check(filed, [], 0.02) is None


def test_statements_on_honours_the_declared_cik(monkeypatch: object) -> None:
    """The universe entry's cik reaches the point-in-time fetch (25): a symbol absent from
    the ticker map still resolves through it, exactly as on the live fetch."""
    import fetch_sec
    from _pytest.monkeypatch import MonkeyPatch

    assert isinstance(monkeypatch, MonkeyPatch)
    facts: dict[str, object] = {"cik": 34088, "facts": {"us-gaap": {
        "NetIncomeLoss": usd(fact("2024-12-31", 1e9, start="2024-01-01", filed="2025-02-20")),
        "StockholdersEquity": usd(fact("2024-12-31", 9e9, filed="2025-02-20")),
    }}}
    asked: list[str] = []

    def companyfacts(cik: str, user_agent: str) -> dict[str, object] | None:
        asked.append(cik)
        return facts if cik == "0000034088" else None

    monkeypatch.setattr(fetch_sec, "companyfacts", companyfacts)
    monkeypatch.setattr(fetch_sec, "submissions", lambda cik, user_agent: None)  # pyright: ignore[reportUnknownLambdaType, reportUnknownArgumentType]

    class Sec:
        user_agent = "test test@example.com"
        tickers: dict[str, object] = {"0": {"cik_str": 2115436, "ticker": "XOM", "title": "new holding company"}}
        tags = TAGS
        definitions = DEFS

    notes: list[str] = []
    periods, decision, why, _, _ = pit.statements_on("XOM", date(2025, 6, 30), Sec(), notes, declared_cik="0000034088")
    assert why is None and decision is not None and decision.xbrl and [p.period_end for p in periods] == ["2024-12-31"]
    assert asked == ["0000034088"] and any("declared in the universe entry" in n for n in notes)
    periods, _, why, _, _ = pit.statements_on("XOM", date(2025, 6, 30), Sec(), [])
    assert periods == [] and why is not None and asked[-1] == "0002115436"  # the ticker map's filer, which has no facts here


def test_point_in_time_shares_are_divided_by_the_declared_receipt_ratio(monkeypatch: pytest.MonkeyPatch) -> None:
    """(42) The cover page counts ordinary shares, the price is the receipt's: 2,500 ordinary
    shares at a ratio of 5 are 500 receipts; at 0.5, 5,000; absent means 1 and nothing is
    recorded."""
    class Sec:
        user_agent = "test test@example.com"
        tickers: dict[str, object] = {}
        tags = TAGS
        definitions = DEFS

    def count(facts: object, d: object, defs: object, tags: object) -> pit.PointCount:
        return pit.PointCount(2500.0, "dei cover page", "EntityCommonStockSharesOutstanding", "2025-06-30", "2025-07-01")

    def statements(symbol: object, d: object, sec: object, notes: object, declared_cik: object = None) -> tuple[list[object], None, None, None, dict[str, object]]:
        return [], None, None, None, {"facts": {}}

    monkeypatch.setattr(pit, "point_count", count)
    monkeypatch.setattr(pit, "statements_on", statements)
    def available(country: str) -> bool:
        return True

    monkeypatch.setattr(pit, "rate_history_available", available)
    history = pit.History({date(2025, 6, 30): 10.0}, {})
    quote = fetch.Quote.model_validate({"currency": "USD", "financial_currency": "TWD", "price": 10.0, "market_cap": None})
    for ratio, expected in ((5.0, 500.0), (0.5, 5000.0), (None, 2500.0)):
        r = pit.record("T", date(2025, 6, 30), Sec(), history, quote, None, adr_ratio=ratio)
        assert r.market_cap == expected * 10.0 and r.point_in_time is not None
        assert r.point_in_time.adr_ratio == ratio and r.point_in_time.shares_ordinary == (2500.0 if ratio is not None else None)


def test_universe_loader_accepts_a_positive_receipt_ratio_only() -> None:
    import universe
    u = universe.load_text('{"tickers": [{"ticker": "TSM", "entity_class": "OperatingCompany", "why": "a foundry", "adr_ratio": 5}]}')
    assert u.tickers[0].adr_ratio == 5
    for bad in ("0", "-2", '"5"', "true"):
        with pytest.raises(universe.UniverseError, match="adr_ratio must be a positive number"):
            universe.load_text('{"tickers": [{"ticker": "TSM", "entity_class": "OperatingCompany", "why": "a foundry", "adr_ratio": ' + bad + "}]}")
