"""The anchor study (80) on synthetic closes and rows: the forward window in trading days
with the benchmark on the same calendar dates, the null past the last close, the refusal
families, the within-date quintiles, the small-cell rule and the sign count. Every number
is invented."""

from __future__ import annotations

from datetime import date, timedelta

import anchor_study as study


def trading_days(start: date, n: int) -> list[date]:
    days: list[date] = []
    d = start
    while len(days) < n:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


def record(ticker: str, as_of: str, *, status: str = "Ok", mos: float | None = None, signal: str | None = None,
           reason: str | None = None, po: float | None = None, price_date: str | None = None) -> study.Record:
    return study.Record(ticker=ticker, as_of=as_of, status=status, entity_class="OperatingCompany", model="dcf" if status == "Ok" else None,
                        fair_value=None, price=None, margin_of_safety=mos, signal=signal, probability_overpaid=po,
                        failed_reason=reason, family=study.family_of(reason) if status == "Failed" else None, price_date=price_date or as_of)


def test_forward_window_counts_trading_days_and_is_null_past_the_last_close() -> None:
    days = trading_days(date(2024, 1, 1), 300)
    closes = {d: 100.0 * (1.001 ** i) for i, d in enumerate(days)}
    r, end = study.forward_return(closes, days[0], 63)
    assert r is not None and end == days[63] and abs(r - (1.001 ** 63 - 1)) < 1e-9
    # a start on a weekend takes the last close before it
    saturday = days[10] + timedelta(days=(5 - days[10].weekday()) % 7 or 7)
    assert saturday.weekday() == 5
    r2, _ = study.forward_return(closes, saturday, 10)
    i = max(i for i, d in enumerate(days) if d <= saturday)
    assert r2 is not None and abs(r2 - (closes[days[i + 10]] / closes[days[i]] - 1)) < 1e-12
    # past the last close is null, never a shortened horizon
    assert study.forward_return(closes, days[250], 63) == (None, None)
    # a date the history does not reach is null
    assert study.forward_return(closes, date(2023, 1, 1), 63) == (None, None)


def test_benchmark_is_read_on_the_same_calendar_dates() -> None:
    days = trading_days(date(2024, 1, 1), 100)
    own = {d: 100.0 for d in days}
    own[days[40]] = 110.0
    bench = {d: 50.0 for d in days if d != days[40]}   # the benchmark has no close on the name's end day
    bench[days[39]] = 55.0
    r, end = study.forward_return(own, days[0], 40)
    assert r is not None and end is not None and end == days[40]
    # the benchmark leg ends on the last close on or before the same calendar day
    assert study.benchmark_return(bench, days[0], end) == 55.0 / 50.0 - 1.0


def test_refusal_families() -> None:
    assert study.family_of("dcf not admissible for Wrapper; lens: x") == "by class"
    assert study.family_of("no point-in-time statements: vendor provider carries no filing dates") == "point-in-time"
    assert study.family_of("missing statement fields for fiscal period ending 2025-12-31: ebit") == "gate"
    assert study.family_of("risk_free_rate for Taiwan/7y (as_of 2026-06-05) is 116 days old") == "gate"
    assert study.family_of(None) is None


def test_quintiles_are_within_the_date_and_need_five_rows() -> None:
    rows = [record(f"T{i}", "2025-03-31", mos=float(i)) for i in range(10)]
    rows += [record(f"U{i}", "2025-06-30", mos=float(-i)) for i in range(3)]      # too few: no quintile
    rows += [record("F", "2025-03-31", status="Failed", reason="dcf not admissible for Miner; lens: NAV")]
    study.assign_quintiles(rows)
    q = {r.ticker: r.mos_quintile for r in rows}
    assert q["T0"] == 1 and q["T1"] == 1 and q["T4"] == 3 and q["T9"] == 5
    assert all(q[f"U{i}"] is None for i in range(3)) and q["F"] is None


def test_cells_print_a_count_alone_under_the_floor_and_the_sign_count_is_per_date() -> None:
    small = [record(f"S{i}", "2025-03-31", mos=0.1) for i in range(study.MIN_CELL - 1)]
    for r in small:
        r.excess = {"63": 0.05, "126": None, "252": None}
    assert study.cell(small, 63) == f"n={study.MIN_CELL - 1}"
    big = [record(f"B{i}", "2025-03-31", mos=0.1 if i % 2 else -0.1) for i in range(12)]
    for i, r in enumerate(big):
        r.excess = {"63": 0.02 if i % 2 else -0.03, "126": None, "252": None}
    text = study.cell(big, 63)
    assert text.startswith("n=12 median") and "positive 6/12" in text
    lines = study.sign_agreement(big, 63)
    assert lines[-1] == "  all dates: 12/12"   # every positive margin preceded a positive excess and every negative a negative
    assert study.cell(big, 126) == "n=0"
    assert study.po_bucket(0.1) == "below 0.25" and study.po_bucket(0.5) == "0.25 to 0.75" and study.po_bucket(1.0) == "0.75 and above"
