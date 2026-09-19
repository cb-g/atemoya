"""Point-in-time (17): facts filed after the date excluded, the split correction, the last
trading day on or before, cover-page shares by filing date, the FRED observation on or
before the date, and the vendor-path record naming why it has no statements."""

from __future__ import annotations

import json
import math
from datetime import date

import fetch
import pit
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
    assert pit.dei_shares(on, date(2025, 6, 30)) == (100.0, "EntityCommonStockSharesOutstanding", "2025-01-31", "2025-02-20")
    assert pit.dei_shares(facts, date(2026, 6, 30)) == (90.0, "EntityCommonStockSharesOutstanding", "2026-01-31", "2026-02-20")
    assert pit.dei_shares(facts, date(2024, 1, 1)) is None


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
    got = pit.dei_shares(facts, date(2025, 3, 31))
    assert got is not None and math.isclose(got[0], 12.1e9)


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
