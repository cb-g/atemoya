"""The options bound against what followed: the paper's sum on invented chains, delta, and a
small store read end to end with the holdout aside."""

from __future__ import annotations

import json
import math
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import anchor_study as study
import bound_study as bs


def test_the_discrete_sum_takes_the_cheaper_side_at_each_strike_and_the_smaller_neighbour() -> None:
    # at each strike both sides quoted; the out-of-the-money side is the cheaper one
    quotes: list[dict[str, Any]] = []
    for k, put, call in ((80.0, 1.0, 22.0), (90.0, 3.0, 13.0), (100.0, 6.0, 6.0), (110.0, 13.0, 3.0), (120.0, 22.0, 1.0)):
        quotes.append({"expiration": "2027-01-15", "strike": k, "right": "put", "bid": 0.9 * put, "ask": 1.1 * put, "mid": put})
        quotes.append({"expiration": "2027-01-15", "strike": k, "right": "call", "bid": 0.9 * call, "ask": 1.1 * call, "mid": call})
    quotes.append({"expiration": "2027-01-15", "strike": 70.0, "right": "put", "bid": 0.5, "ask": 0.7, "mid": 0.6})        # no call at 70: left out
    quotes.append({"expiration": "2027-01-15", "strike": 130.0, "right": "call", "bid": 0.0, "ask": 0.5, "mid": 0.25})     # no bid: left out
    quotes.append({"expiration": "2027-01-15", "strike": 130.0, "right": "put", "bid": 30.0, "ask": 31.0, "mid": 30.5})
    points = bs.otm_prices(quotes, "2027-01-15")
    assert points == [(80.0, 1.0), (90.0, 3.0), (100.0, 6.0), (110.0, 3.0), (120.0, 1.0)]
    assert bs.integral(points) == 10 * 1 + 10 * 3 + 10 * 3 + 10 * 1          # the step times the smaller neighbour, C.2
    assert math.isclose(bs.bound_of(points, 100.0, 2.0), 2 * 80 / 10_000 / 2)   # 2 I / S^2 over the years
    inside, reaches = bs.cut(points, 100.0, (0.85, 1.15))
    assert inside == [(90.0, 3.0), (100.0, 6.0), (110.0, 3.0)] and reaches
    assert bs.cut(points, 100.0, (0.5, 1.15))[1] is False                    # the chain stops at 0.8 of spot


def chain(ticker: str, day: str, spot: float, *, expiries: tuple[tuple[str, float], ...], width: float = 0.5) -> dict[str, Any]:
    """A chain with strikes from (1 - width) to (1 + width) of spot in steps of a twentieth, each
    expiry's prices a flat time value times its years, so the bound scales with the level given."""
    quotes: list[dict[str, Any]] = []
    for expiry, level in expiries:
        for i in range(-10, 11):
            k = round(spot * (1 + width * i / 10), 4)
            put, call = max(k - spot, 0.0) + level, max(spot - k, 0.0) + level
            for right, p in (("put", put), ("call", call)):
                quotes.append({"expiration": expiry, "strike": k, "right": right, "bid": p, "ask": p * 1.2, "mid": p * 1.1})
    return {"ticker": ticker, "snapshot_date": day, "underlying_close": spot, "quotes": quotes}


def test_the_expiry_is_the_shortest_at_least_a_year_out_with_eight_strikes_each_side(tmp_path: Path) -> None:
    c = chain("AAA", "2025-06-30", 100.0, expiries=(("2025-12-19", 1.0), ("2026-07-17", 2.0), ("2027-06-18", 3.0)))
    assert bs.usable_expiries(c["quotes"], 100.0, "2025-06-30") == [("2026-07-17", 382), ("2027-06-18", 718)]
    path = tmp_path / "AAA.json"
    path.write_text(json.dumps(c))
    b = bs.bound_of_chain(path)
    assert b is not None and b.expiry == "2026-07-17" and b.days == 382 and b.strikes == 21 and (b.low, b.high) == (0.5, 1.5) and b.reaches
    # the longer expiry's level of three over two years is less per year than two over one: the record's choice differs from this one
    assert 0 < b.longest < b.bound and b.common < b.bound
    thin = chain("BBB", "2025-06-30", 100.0, expiries=(("2026-07-17", 2.0),), width=0.1)          # ten strikes a side, but all within a tenth of spot
    thin["quotes"] = [q for q in thin["quotes"] if q["strike"] < 100 or q["right"] == "put" or q["strike"] > 107]   # fewer than eight calls above
    assert bs.usable_expiries(thin["quotes"], 100.0, "2025-06-30") == []


def test_delta_is_the_variance_over_the_covariance_and_needs_two_hundred_days() -> None:
    days = [date(2024, 1, 1) + timedelta(days=i) for i in range(400)]
    market = {d: 100.0 * (1 + 0.001 * math.sin(i)) for i, d in enumerate(days)}
    stock = {d: 50.0 * (1 + 0.002 * math.sin(i)) for i, d in enumerate(days)}       # twice the market's move: var 4x, cov 2x
    d = bs.delta_of(stock, market, days[-1])
    assert d is not None and math.isclose(d[0], 2.0, rel_tol=1e-4) and d[1]
    against = {d: 50.0 * (1 - 0.002 * math.sin(i)) for i, d in enumerate(days)}
    d = bs.delta_of(against, market, days[-1])
    assert d is not None and d[1] is False
    assert bs.delta_of({d: v for d, v in stock.items() if d > days[-150]}, market, days[-1]) is None
    rates = [("2025-01-02", 0.04), ("2025-01-03", 0.05)]
    assert bs.rate_on(rates, "2025-01-02") == 0.04 and bs.rate_on(rates, "2025-06-30") == 0.05 and bs.rate_on(rates, "2024-12-31") is None


def test_a_small_store_is_read_end_to_end_with_the_holdout_aside(tmp_path: Path) -> None:
    store, closes, out = tmp_path / "options", tmp_path / "closes", tmp_path / "out"
    store.mkdir()
    closes.mkdir()
    # fourteen month-end store days from 2025-01 to 2026-02, two of them with a mid-month day too; SPY, two names and a held-out one
    days = [f"{y}-{m:02d}-28" for y in (2025, 2026) for m in range(1, 13) if (y, m) <= (2026, 2)] + ["2025-03-14", "2025-07-15"]
    for day in days:
        (store / day).mkdir()
        expiry = (date.fromisoformat(day) + timedelta(days=400)).isoformat()
        for ticker, spot, level in (("SPY", 500.0, 4.0), ("AAA", 100.0, 2.0), ("BBB", 100.0, 1.0), ("HELD", 100.0, 1.0)):
            (store / day / f"{ticker}.json").write_text(json.dumps(chain(ticker, day, spot, expiries=((expiry, level),))))
    (store / "2025-02-28" / "SPY.json").unlink()                     # a day without a benchmark chain is skipped
    # closes over 2024-01 to 2026-12: the market wobbles a hundredth around a slow drift, AAA wobbles twice as much on a faster
    # drift, BBB wobbles the other way
    series = [date(2024, 1, 1) + timedelta(days=i) for i in range(1100)]
    for ticker, drift, wobble in (("SPY", 0.0002, 0.01), ("AAA", 0.001, 0.02), ("BBB", 0.0, -0.01), ("HELD", 0.0002, 0.01)):
        (closes / f"{ticker}-2026-12-31.json").write_text(json.dumps({d.isoformat(): 100.0 * (1 + drift) ** i * (1 + wobble * math.sin(i)) for i, d in enumerate(series)}))
    rates = tmp_path / "DGS1.json"
    rates.write_text(json.dumps({"observations": [{"date": "2024-01-02", "value": "4.0"}, {"date": "2025-06-02", "value": "."}, {"date": "2025-07-01", "value": "3.0"}]}))
    holdout = tmp_path / "holdout.json"
    holdout.write_text(json.dumps({"names": ["HELD"], "dates_after": "2025-12-31"}))

    rows, line, skipped = bs.rows_of(store, bs.load_rates(rates), study.load_holdout(holdout), opened=False)
    assert skipped == 1 and "set aside" in line
    assert {r.bound.ticker for r in rows} == {"AAA", "BBB"} and max(r.bound.day for r in rows) == "2025-12-28"
    assert len(rows) == 2 * (len(days) - 1 - 2)                     # fifteen days left after the skip and the two 2026 days held
    a = next(r for r in rows if r.bound.ticker == "AAA" and r.bound.day == "2025-01-28")
    b = next(r for r in rows if r.bound.ticker == "BBB" and r.bound.day == "2025-01-28")
    assert a.kt > b.kt and math.isclose(a.mean, (a.kt + b.kt) / 2) and math.isclose(a.mw, a.market + (a.kt - a.mean) / 2) and a.rf == 0.04
    assert next(r for r in rows if r.bound.day == "2025-07-28").rf == 0.03
    attached = bs.attach(rows, closes)
    assert attached == len(rows) and all(r.delta is not None and r.beta_positive for r in rows if r.bound.ticker == "AAA")
    assert all(math.isclose(r.delta, 2.0, rel_tol=0.05) for r in rows if r.bound.ticker == "AAA" and r.delta is not None)   # twice the market's move
    assert all(r.beta_positive is False and r.group == "other" for r in rows if r.bound.ticker == "BBB")                    # moves against the market
    assert all(252 in r.excess and r.excess[252] > 0.2 for r in rows if r.bound.ticker == "AAA")       # a thousandth a day compounds past the bound
    ends = bs.month_ends(rows)
    assert {r.bound.day for r in ends} == {d for d in days if d.endswith("-28") and d < "2026" and d != "2025-02-28"}
    text = bs.report(rows, line, skipped, attached)
    assert "the tables read the" in text and "AAA" in text and "liberal" not in text.split("per name")[0].split("the slack")[0]
    assert "KT met" in text and "fewer than 10" in text
    # the command, writing both files; and the reasons when nothing is there
    assert bs.main(["--store", str(store), "--closes", str(closes), "--rates", str(rates), "--holdout-file", str(holdout), "--out", str(out)]) == 0
    assert (out / "tables.txt").exists() and len((out / "rows.jsonl").read_text().splitlines()) == len(rows)
    first = json.loads((out / "rows.jsonl").read_text().splitlines()[0])
    assert {"ticker", "day", "kadan_tang", "martin_wagner", "demeaned", "delta", "group", "excess", "low_over_spot", "high_over_spot", "reaches_window"} <= set(first)
    assert bs.main(["--store", str(tmp_path / "nowhere"), "--rates", str(rates)]) == 2
    assert bs.main(["--store", str(store), "--rates", str(tmp_path / "nowhere.json")]) == 2
