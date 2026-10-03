"""The rule panel's rule and its study on invented rows: the industry-code table, the
largest by market value with the held-out names left out, and the study's tables."""

from __future__ import annotations

import json
from pathlib import Path

import rule_panel as rp
import rule_study as rs

Json = dict[str, object]


def test_the_industry_code_rule_leaves_out_what_the_generic_dcf_misreads() -> None:
    assert rp.excluded_reason(3571) is None and rp.excluded_reason(7372) is None    # computers, software: run
    assert rp.excluded_reason(3674) is None and rp.excluded_reason(6282) is None    # semiconductors and advisers run, by the check
    for sic, word in ((6021, "financial"), (6331, "financial"), (6798, "financial"), (4911, "utility"), (1311, "extractive"), (2911, "extractive"), (3711, "cyclical"), (4512, "cyclical")):
        why = rp.excluded_reason(sic)
        assert why is not None and why.startswith(word), sic
    assert rp.excluded_reason(None) == "no industry code on the filer's SEC record"


def test_the_universe_is_the_largest_on_the_day_and_never_a_held_out_name() -> None:
    rows: list[Json] = [{"ticker": f"T{i}", "cik": i, "formation": "2020-06", "market_cap": float(100 - i), "current_assets": 1.0} for i in range(10)]
    rows.append({"ticker": "BANK", "cik": 50, "formation": "2020-06", "market_cap": 1000.0})                       # no current assets: not a candidate
    rows.append({"ticker": "OLD", "cik": 51, "formation": "2019-06", "market_cap": 1000.0, "current_assets": 1.0})  # another June
    rows.append({"ticker": "NOCAP", "cik": 52, "formation": "2020-06", "current_assets": 1.0})
    top = rp.top_by_cap(rows, 2020, 3, frozenset({"T0"}))
    assert [r["ticker"] for r in top] == ["T1", "T2", "T3"]


def test_the_study_reads_valued_rows_within_the_date_and_keeps_the_refused_apart(tmp_path: Path) -> None:
    lines: list[Json] = []
    for year in (2020, 2023):
        for i in range(100):
            lines.append({"ticker": f"N{i:03d}", "date": f"{year}-06-30", "status": "Ok", "margin_of_safety": 0.01 * i, "shadow_margin": 0.01 * i + 0.1,
                          "earnings_yield": 0.001 * (99 - i), "f_score": i % 10, "forward_12m": 0.002 * i, "spy_12m": 0.05})
        lines.append({"ticker": "REF", "date": f"{year}-06-30", "status": "Failed", "margin_of_safety": None, "forward_12m": 0.3, "spy_12m": 0.05})
    panel = tmp_path / "panel.jsonl"
    panel.write_text("".join(json.dumps(x) + "\n" for x in lines))
    valued, refused, per_date = rs.load(panel)
    assert len(valued) == 200 and len(refused) == 2
    assert per_date[0] == "  2020-06-30: 101 records, 100 valued, median margin of safety +0.49"
    text = rs.report(valued, refused, per_date)
    assert "margin_of_safety, valued rows, formations before 2022: 100 rows over 1 formation years" in text
    assert "highest less lowest, pooled: +0.160" in text                                   # the cheapest fifth ahead by construction
    assert "rank correlation of the margin of safety with the earnings yield, within the date: median -1.00" in text
    assert "refused: n=1" in text and "survivors only" in text
