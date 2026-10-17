"""The discount-rate sweep on the rule panel: the implied premium's parts, the lambda level, the
swing and the rank, on invented records; the binary is not run."""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

import pytest

import rule_discount as rd
from broad_study import Row


def test_the_implied_premium_is_the_aggregate_earnings_yield_plus_growth_plus_inflation_less_the_rate(tmp_path: Path) -> None:
    pit_dir = tmp_path / "2020-06-30"
    pit_dir.mkdir()
    rows: list[dict[str, object]] = []
    for i in range(12):
        # six periods filed, the sixth left out; the mean of the first five is 100 for every name
        (pit_dir / f"N{i}.json").write_text(json.dumps({"periods": [{"net_income": 100.0 + k} for k in (-2, -1, 0, 1, 2)] + [{"net_income": 1e9}]}))
        rows.append({"ticker": f"N{i}", "market_cap": 2000.0})
    (pit_dir / "NONE.json").write_text(json.dumps({"periods": [{"book_equity": 1.0}]}))            # no net income: left out
    rows.append({"ticker": "NONE", "market_cap": 5000.0})
    rows.append({"ticker": "MISSING", "market_cap": 5000.0})                                         # no record on the date
    rows.append({"ticker": "N0", "market_cap": None})                                                # no market value
    ey = rd.aggregate_earnings_yield(pit_dir, rows)
    assert ey is not None and math.isclose(ey[0], 0.05) and ey[1] == 12
    assert rd.aggregate_earnings_yield(pit_dir, rows[:5]) is None                                   # under the small-cell floor
    body = json.dumps({"observations": [{"date": "2010-06-01", "value": "200.0"}, {"date": "2010-07-01", "value": "."},
                                        {"date": "2020-05-01", "value": "268.78"}, {"date": "2020-07-01", "value": "300.0"}]}).encode()
    inflation = rd.trailing_inflation(body, date(2020, 6, 30))
    assert math.isclose(inflation, (268.78 / 200.0) ** 0.1 - 1)                                       # the last on or before each date; "." skipped
    assert math.isclose(rd.implied_premium(0.05, 0.03, 0.02), 0.05 + 0.02 + 0.03 - 0.02)
    assert math.isclose(rd.level_for(0.024, 0.04, 0.3), 0.024 + 0.3 * 0.016) and rd.level_for(0.024, 0.04, 0.0) == 0.024 and rd.level_for(0.024, 0.04, 1.0) == 0.04


def test_the_swing_the_rank_and_the_spread_are_read_off_the_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def rows(scale: float) -> list[Row]:
        out: list[Row] = []
        for year in range(2013, 2026):
            if year == 2022:
                continue
            level = 1.0 if year < 2022 else -0.5
            for i in range(61):                                    # the fifths need fifty rows a year
                margin = scale * (level + 0.001 * i)
                out.append(Row(ticker=f"N{i}", year=year, excess=0.1 * (i / 60) - 0.05, non_financial=True, values={"margin_of_safety": margin}))
        return out
    base = rows(1.0)
    rf = {y: (0.02 if y < 2022 else 0.04) for y in range(2013, 2026)}
    text = rd.swing(base, rf)
    assert "before 2022 +1.03, after -0.47, swing +1.50" in text
    assert "rank correlation of the yearly median with the rate" in text and "over 12 years" in text
    assert rd.rank_against(rows(0.5), base).startswith("median +1.00")                       # a scale keeps the ranks
    assert rd.spread(base, before=True).startswith("+") and rd.spread(base, before=False).startswith("+")   # the margin rises with the excess here
    assert rd.swing([], rf) == "too few years" and rd.rank_against([], base) == "n/a"
    monkeypatch.setattr(rd.rule_panel, "ROOT", tmp_path)                                         # no panel built: the command says what to run
    assert rd.main(["--out", str(tmp_path / "out")]) == 2
