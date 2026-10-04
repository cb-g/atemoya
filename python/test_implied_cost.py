"""The consensus-implied cost of capital on invented figures: the formula, each refusal with
its reason, the currency and unit checks, and the table. No network."""

from __future__ import annotations

import math
from datetime import date

import implied_cost as ic

Json = dict[str, object]


def snapshot(this: float | None = 4.0, nxt: float | None = 5.0, currency: str = "USD") -> Json:
    def bar(name: str, mean: float | None, end: str) -> Json:
        return {"period": name, "end_date": end, "eps": {"mean": mean}}

    return {"date": "2026-10-02", "status": "ok", "eps_currency": currency,
            "periods": [bar("0q", 1.0, "2026-09-30"), bar("0y", this, "2026-12-31"), bar("+1y", nxt, "2027-12-31")]}


def boundary(price: float | None = 100.0, currency: str = "USD", unit: str = "major") -> Json:
    return {"price": price, "trading_currency": currency, "price_unit": unit, "as_of": "2026-10-03T00:00:00+00:00"}


def test_the_formula_and_its_refusals() -> None:
    value, why = ic.peg(4.0, 5.0, 100.0)
    assert why is None and value is not None and math.isclose(value, 0.1)
    assert ic.peg(4.0, 5.0, None)[1] == "no price on the boundary record"
    assert ic.peg(None, 5.0, 100.0)[1] == "the snapshot lacks a forecast for one of the two fiscal years"
    assert "not positive" in str(ic.peg(-1.0, 5.0, 100.0)[1])
    assert "not above the current one" in str(ic.peg(5.0, 5.0, 100.0)[1])


def test_a_row_carries_the_figures_the_other_two_returns_and_the_reason() -> None:
    record: Json = {"cost_of_equity_capm": 0.09, "options_expected_return": {"expected_return": 0.07}}
    row = ic.row_of("X", snapshot(), boundary(), record)
    assert math.isclose(float(str(row["implied_cost"])), 0.1) and row["cost_of_equity_capm"] == 0.09 and row["options_expected_return"] == 0.07
    assert math.isclose(float(str(row["forecast_growth"])), 0.25) and row["this_year_end"] == "2026-12-31" and "reason" not in row
    assert ic.row_of("X", None, boundary(), None)["reason"] == "no ok consensus snapshot on disk"
    assert ic.row_of("X", snapshot(), None, None)["reason"] == "no boundary record for the name: no price"
    other = ic.row_of("X", snapshot(currency="EUR"), boundary(), None)
    assert other["implied_cost"] is None and other["reason"] == "the forecasts are in EUR and the price in USD"
    pence = ic.row_of("X", snapshot(currency="GBP"), boundary(currency="GBP", unit="minor"), None)
    assert pence["implied_cost"] is None and "minor unit" in str(pence["reason"])
    flat = ic.row_of("X", snapshot(nxt=3.0), boundary(), None)
    assert flat["implied_cost"] is None and "not above the current one" in str(flat["reason"])


def test_the_table_orders_by_the_figure_and_puts_the_refused_last() -> None:
    rows = [ic.row_of("LOW", snapshot(nxt=4.5), boundary(), None), ic.row_of("NONE", None, None, None), ic.row_of("HIGH", snapshot(nxt=8.0), boundary(), None)]
    text = ic.table(rows, date(2026, 10, 4))
    assert "2 of 3 names" in text
    body = [line.split()[0] for line in text.splitlines()[4:]]
    assert body == ["HIGH", "LOW", "NONE"]
