"""The panel's market-implied columns (37): a row with and without a block, the reason
carried, the per-date table, and the medians the plot reads."""

from __future__ import annotations

from datetime import date

import build_panel as bp
import plot_market_through_time as plot

BLOCK: dict[str, object] = {"snapshot_date": "2025-06-27", "horizon_years": 1.5, "p_below_anchor_path": 0.2,
         "price_quantiles": [{"p": 0.05, "price": 50.0}, {"p": 0.5, "price": 100.0}],
         "implied_growth_quantiles": [{"p": 0.5, "growth": {"value": 0.03, "reason": None}}], "risk_neutral": True}


def record(ticker: str, *, block: dict[str, object] | None, reason: str | None = None, overpaid: float | None = 1.0) -> dict[str, object]:
    v: dict[str, object] = {"ticker": ticker, "status": "Ok", "fair_value": 80.0, "price": 100.0, "margin_of_safety": -0.2, "signal": "Sell",
                            "failed_reason": None, "implied": {}, "point_in_time": {"price_date": "2025-06-30", "anachronistic_inputs": []}}
    if block is not None:
        v["market_implied"] = block
    else:
        v["market_implied_reason"] = reason
    if overpaid is not None:
        v["belief"] = {"probability_overpaid": overpaid}
    return v


def test_row_with_and_without_a_block() -> None:
    d = date(2025, 6, 30)
    with_block = bp.panel_row(record("A", block=BLOCK), d, 0.1, with_options=True)
    assert with_block["market_snapshot_date"] == "2025-06-27" and with_block["horizon_years"] == 1.5 and with_block["p_below_anchor_path"] == 0.2
    assert with_block["price_quantiles"] == BLOCK["price_quantiles"] and with_block["implied_growth_quantiles"] == BLOCK["implied_growth_quantiles"]
    assert with_block["risk_neutral"] is True and with_block["market_implied_reason"] is None and with_block["probability_overpaid"] == 1.0
    without = bp.panel_row(record("B", block=None, reason="no options snapshot within 7 days before 2025-06-30"), d, None, with_options=True)
    assert without["p_below_anchor_path"] is None and without["price_quantiles"] is None
    assert without["market_implied_reason"] == "no options snapshot within 7 days before 2025-06-30" and without["risk_neutral"] is True
    # a run without the store adds nothing: the pre-existing columns only
    plain = bp.panel_row(record("A", block=BLOCK), d, 0.1, with_options=False)
    assert "p_below_anchor_path" not in plain and set(plain) == set(bp.panel_row(record("B", block=None), d, None, with_options=False))


def test_market_table_states_the_disagreement_count() -> None:
    d = date(2025, 6, 30)
    rows = [bp.panel_row(record("A", block=BLOCK), d, None, with_options=True),
            bp.panel_row(record("B", block={**BLOCK, "p_below_anchor_path": 0.7}), d, None, with_options=True),
            bp.panel_row(record("C", block={**BLOCK, "p_below_anchor_path": 0.1}, overpaid=None), d, None, with_options=True),
            bp.panel_row(record("D", block=None, reason="no options data"), d, None, with_options=True)]
    line = bp.market_table(d, rows)
    assert line.startswith("2025-06-30: 3 names with a market-implied block; median p_below_anchor_path 0.20; median probability_overpaid 1.00 on the 2 with a belief; market below 0.5 while the belief is at 1.0 on 1 of 2")
    blank = bp.market_table(date(2024, 3, 31), [bp.panel_row(record("A", block=None, reason="no options snapshot within 7 days before 2024-03-31"), date(2024, 3, 31), None, with_options=True)])
    assert blank == "2024-03-31: no market-implied block on any name (no options snapshot within 7 days before 2024-03-31)"


def test_plot_medians_leave_the_blank_dates_out() -> None:
    d1, d2 = date(2024, 3, 31), date(2025, 6, 30)
    rows = [bp.panel_row(record("A", block=None, reason="no options snapshot within 7 days before 2024-03-31"), d1, None, with_options=True),
            bp.panel_row(record("A", block=BLOCK), d2, None, with_options=True),
            bp.panel_row(record("B", block={**BLOCK, "p_below_anchor_path": 0.4}, overpaid=0.5), d2, None, with_options=True)]
    points, blank = plot.medians(rows)
    assert blank == [d1] and points == [(d2, 0.30000000000000004, 0.75)]
