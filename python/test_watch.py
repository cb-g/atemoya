"""The watch on invented records: each section fires on its own change and stays empty
otherwise, and the earlier run is found by its day."""

from __future__ import annotations

import json
from pathlib import Path

import watch

Json = dict[str, object]


def record(ticker: str, *, status: str = "Ok", fair_value: float | None = 100.0, price: float = 90.0, signal: str | None = "Hold",
           end: str = "2025-12-31", reason: str | None = None, low: int = 0, cluster: bool = False, days: int | None = None, day: str = "2026-10-03") -> Json:
    v: Json = {"ticker": ticker, "valued_on": day, "status": status, "price": price, "fair_value": fair_value if status == "Ok" else None,
               "margin_of_safety": (fair_value - price) / price if status == "Ok" and fair_value is not None else None,
               "signal": signal if status == "Ok" else None, "failed_reason": reason,
               "inputs": ["dcf", {"fiscal_period_end": end}] if status == "Ok" else None,
               "stretch": {"stretch_low": low, "stretch_high": 0}, "insiders": {"cluster_buy": cluster}}
    if days is not None:
        v["earnings"] = {"days_to_next": days, "calendar": {"next_date": "2026-10-08"}, "implied": {"implied_move": 0.05}}
    return v


def run(*records: Json) -> dict[str, Json]:
    return {str(r["ticker"]): r for r in records}


def test_each_section_fires_on_its_own_change() -> None:
    before = run(record("SAME"), record("REFUSED"), record("SIGNAL", signal="Buy"), record("CROSS", fair_value=100.0, price=90.0),
                 record("YEAR", end="2024-12-31"), record("VALUE"), record("PRICE", price=90.0), record("LOW"), record("BUY"), record("GONE"))
    after = run(record("SAME"), record("REFUSED", status="Failed", reason="missing statement fields"), record("SIGNAL", signal="Hold"),
                record("CROSS", fair_value=100.0, price=120.0), record("YEAR", end="2025-12-31", fair_value=130.0), record("VALUE", fair_value=80.0),
                record("PRICE", price=120.0), record("LOW", low=3), record("BUY", cluster=True), record("DUE", days=5),
                record("MOVED", status="Failed", reason="ticker identity: SEC's ticker map gives CIK 2 for MOVED"))
    text = watch.report(before, after)
    for needle in ("ticker identity: the ticker no longer names its declared filer (1):", "MOVED: ticker identity",
                   "status changed (1):", "REFUSED: Ok to Failed: missing statement fields",
                   "signal changed (1):", "SIGNAL: Buy to Hold",
                   "CROSS: price 120.00 now above fair value 100.00",
                   "a new fiscal year was read (1):", "YEAR: fiscal year ending 2025-12-31 read, was 2024-12-31",
                   "fair value moved by more than 5% with no new fiscal year (1):", "VALUE: fair value 100.00 to 80.00 (-20%)",
                   "PRICE: price 90.00 to 120.00 (+33%)",
                   "LOW: low side, 0 to 3", "BUY: two or more insiders bought inside fourteen days",
                   "releases due within 7 days (1):", "DUE: 2026-10-08, in 5 day(s), implied move 5.0%",
                   "in the current run and not the previous (2):", "in the previous run and not the current (1):"):
        assert needle in text, needle
    assert "SAME" not in text.replace("the watch", "")
    quiet = watch.report(before, before)
    assert "status changed (0): none" in quiet and "signal changed (0): none" in quiet


def test_the_earlier_run_is_the_newest_valued_on_an_earlier_day(tmp_path: Path) -> None:
    for name, day in (("2026-10-01", "2026-10-01"), ("2026-10-02", "2026-10-02"), ("2026-10-03", "2026-10-03"), ("2026-10-03-2", "2026-10-03")):
        d = tmp_path / name
        d.mkdir()
        (d / "valuations.jsonl").write_text(json.dumps(record("A", day=day)) + "\n")
    found = watch.previous_run("2026-10-03", tmp_path)
    assert found is not None and found.parent.name == "2026-10-02"
    assert watch.previous_run("2026-10-01", tmp_path) is None and watch.previous_run("2026-10-03", tmp_path / "absent") is None
