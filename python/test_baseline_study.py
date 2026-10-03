"""The naive baseline and the holdout on invented rows: the three ratios on one currency
basis, the nulls with their reasons, the within-date quintiles, the rank correlation with
ties, and the rows a study may not read. Every number is invented."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import anchor_study as study
import baseline_study as base
import universe as universe_file

FX: dict[str, object] = {"currencies": {"EUR": {"usd_per_unit": 1.25}, "GBP": {"usd_per_unit": 2.0}}}


def boundary(**over: Any) -> dict[str, object]:
    period = {"net_income": 50.0, "book_equity": 200.0, "ebit": 80.0, "total_debt": 300.0, "cash": 100.0}
    period.update(over.pop("period", {}))
    return {"market_cap": 1000.0, "financial_currency": "USD", "trading_currency": "USD", "periods": [period], **over}


def record(ticker: str, as_of: str, mos: float | None = None, excess: float | None = None) -> study.Record:
    r = study.Record(ticker=ticker, as_of=as_of, status="Ok", entity_class="OperatingCompany", model="dcf", fair_value=None, price=None,
                     margin_of_safety=mos, signal=None, probability_overpaid=None, failed_reason=None, family=None, price_date=as_of)
    r.excess = {str(h): excess for h in study.HORIZONS}
    return r


def test_the_three_ratios_on_one_basis() -> None:
    m = base.measures_of(boundary(), FX)
    assert m.earnings_yield == 0.05 and m.book_to_price == 0.2 and m.ebit_to_ev == 80.0 / 1200.0 and m.reason is None


def test_statements_in_another_currency_convert_through_usd_on_the_date() -> None:
    m = base.measures_of(boundary(financial_currency="EUR", trading_currency="GBP"), FX)
    assert m.earnings_yield == 50.0 * 0.625 / 1000.0
    assert m.ebit_to_ev == 80.0 * 0.625 / (1000.0 + 200.0 * 0.625)
    missing = base.measures_of(boundary(financial_currency="KZT"), FX)
    assert missing.earnings_yield is None and missing.reason == "no rate on the date to bring KZT statements to the USD price"


def test_a_loss_is_a_negative_yield_and_nonpositive_book_or_ev_is_null() -> None:
    m = base.measures_of(boundary(period={"net_income": -50.0, "book_equity": -1.0, "total_debt": 0.0, "cash": 5000.0}), FX)
    assert m.earnings_yield == -0.05 and m.book_to_price is None and m.ebit_to_ev is None
    bank = base.measures_of(boundary(period={"ebit": None}), FX)
    assert bank.ebit_to_ev is None and bank.earnings_yield == 0.05


def test_no_cap_and_no_statements_say_so() -> None:
    assert base.measures_of(boundary(market_cap=None), FX).reason == "no market cap on the date"
    assert base.measures_of({"market_cap": 10.0, "periods": []}, FX).reason == "no statements known on the date"


def test_quintiles_are_cut_within_the_date_and_a_thin_date_gets_none() -> None:
    rows = [(record(f"N{i}", "2024-03-31"), float(i)) for i in range(10)] + [(record(f"M{i}", "2024-06-30"), float(i)) for i in range(4)]
    q = base.quintiles_within_date(rows)
    assert [q[(f"N{i}", "2024-03-31")] for i in range(10)] == [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
    assert not any(d == "2024-06-30" for _, d in q)


def test_rank_correlation_with_ties_and_its_nulls() -> None:
    assert base.ranks([10.0, 20.0, 20.0, 30.0]) == [1.0, 2.5, 2.5, 4.0]
    assert base.spearman([1.0, 2.0, 3.0, 4.0, 5.0], [10.0, 20.0, 30.0, 40.0, 50.0]) == 1.0
    rho = base.spearman([1.0, 2.0, 3.0, 4.0, 5.0], [5.0, 4.0, 3.0, 2.0, 1.0])
    assert rho is not None and abs(rho + 1.0) < 1e-12
    assert base.spearman([1.0, 2.0], [1.0, 2.0]) is None
    assert base.spearman([1.0, 2.0, 3.0, 4.0, 5.0], [7.0] * 5) is None


def test_the_spread_is_the_cheapest_median_less_the_dearest_and_a_thin_end_is_a_count() -> None:
    rows = [record(f"N{i}", "2024-03-31", excess=0.10 if i >= 50 else -0.10) for i in range(100)]
    q = {(r.ticker, r.as_of): (5 if i >= 50 else 1) for i, r in enumerate(rows)}
    assert base.spread_line("x", rows, q) == "  x: +63d +0.200, +126d +0.200, +252d +0.200"
    assert "n under 10" in base.spread_line("x", rows[:55], q)


def test_held_out_rows_are_not_read_unless_opened() -> None:
    holdout = study.Holdout(names=frozenset({"H"}), dates_after="2024-06-30")
    rows = [record("A", "2024-03-31"), record("H", "2024-03-31"), record("A", "2024-09-30")]
    kept, line = study.set_aside(rows, holdout, opened=False)
    assert [(r.ticker, r.as_of) for r in kept] == [("A", "2024-03-31")]
    assert line.startswith("Holdout (reference/holdout.json): 2 rows set aside")
    opened, loud = study.set_aside(rows, holdout, opened=True)
    assert len(opened) == 3 and loud.startswith("HOLDOUT OPENED: 2 held-out rows")
    assert "Holdout" in study.report(kept, study.date(2026, 1, 1), line).splitlines()[2]


def test_the_declared_holdout_names_universe_entries_and_is_unopened() -> None:
    raw = json.loads(study.HOLDOUT.read_text())
    holdout = study.load_holdout()
    tickers = {e.ticker for e in universe_file.load(Path(study.REPO_ROOT / "reference" / "universe.json")).tickers}
    assert len(raw["names"]) == len(holdout.names) == 32 and holdout.names <= tickers
    assert holdout.dates_after == "2026-06-30" and raw["opened"] == []


def test_the_expected_return_section_reads_every_status_and_says_when_there_is_none(tmp_path: Path) -> None:
    day = tmp_path / "2026-03-31"
    day.mkdir()
    rows = [record(f"N{i}", "2026-03-31", mos=float(i), excess=0.01 * i) for i in range(10)]
    rows[0].status = "Failed"
    (day / "valuations.jsonl").write_text("".join(json.dumps({"ticker": r.ticker, "options_expected_return": {"expected_return": 0.05 + 0.01 * i}}) + "\n" for i, r in enumerate(rows)))
    expected = base.load_expected_returns(rows, tmp_path)
    assert len(expected) == 10 and expected[("N9", "2026-03-31")] == 0.05 + 0.09
    measures = {(r.ticker, r.as_of): base.Measures(earnings_yield=0.01 * i) for i, r in enumerate(rows)}
    text = "\n".join(base.expected_return_section(rows, expected, measures))
    assert "10 rows on 10 names over 1 dates carry one" in text
    assert "rank correlation with the earnings yield, within the date: median +1.00 over 1 dates" in text
    assert "rank correlation with the margin of safety" in text
    assert "none: the panel's dates precede the options store" in "\n".join(base.expected_return_section(rows, {}, measures))


def test_the_shadow_section_reads_blocks_from_the_dates_own_valuations(tmp_path: Path) -> None:
    day = tmp_path / "2024-03-31"
    day.mkdir()
    rows = [record(f"N{i}", "2024-03-31", mos=float(i), excess=0.01 * i) for i in range(10)]
    lines = [{"ticker": r.ticker, "growth_shadow": {"margin_of_safety": float(9 - i)}} for i, r in enumerate(rows)]
    lines.append({"ticker": "NONE"})
    (day / "valuations.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    shadow = base.load_shadow_margins(rows, tmp_path)
    assert len(shadow) == 10 and shadow[("N0", "2024-03-31")] == 9.0
    measures = {(r.ticker, r.as_of): base.Measures(earnings_yield=0.05) for r in rows}
    text = "\n".join(base.shadow_section(rows, shadow, measures))
    assert "the growth shadow: 10 generic-DCF rows on 10 names carry one" in text
    assert "median -1.00 over 1 dates" in text and "rows whose quintile differs between the two: 8 of 10" in text
    assert "none: the panel was built before the shadow existed" in "\n".join(base.shadow_section(rows, {}, measures))
