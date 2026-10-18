"""The owed measurements' study on invented rows: the fifths within the year, the spread,
the maintenance margin and the ex-goodwill estimate as defined, the four-quarter section's
anticipation test, and the sections' answers with no readout on the panel. Every figure is
invented."""

from __future__ import annotations

import rule_shadow as rs


def row(ticker: str, year: int, margin: float, excess: float | None = 0.0, **kw: object) -> rs.Row:
    base: dict[str, object] = dict(ticker=ticker, year=year, excess=excess, margin=margin, fair_value=100.0 * (1 + margin), price=100.0)
    base.update(kw)
    return rs.Row(**base)  # type: ignore[arg-type]


def test_fifths_are_cut_within_the_year_and_a_thin_year_is_skipped() -> None:
    rows = [row(f"N{i}", 2020, margin=i / 10) for i in range(10)] + [row("X", 2021, margin=0.5)]
    f = rs.fifths_within_year([(r, r.margin) for r in rows])
    assert f[("N0", 2020)] == 1 and f[("N9", 2020)] == 5 and f[("N4", 2020)] == 3
    assert ("X", 2021) not in f


def test_the_spread_is_the_top_fifth_less_the_bottom_and_a_thin_cell_is_a_count() -> None:
    # fifty rows in one year: the margin orders them and the excess rises with it, 1 point per rank
    rows = [row(f"N{i}", 2023, margin=i / 50, excess=i / 100) for i in range(50)]
    f = rs.fifths_within_year([(r, r.margin) for r in rows])
    line = rs.spread("by margin", rows, f)
    assert "from 2022" in line and "+0.400" in line                      # medians 0.445 and 0.045
    assert "n=0/0" in line                                                # nothing before the split year
    thin = rows[:12]
    assert "n=" in rs.spread("thin", thin, rs.fifths_within_year([(r, r.margin) for r in thin])).split("pooled")[1]


def test_the_maintenance_margin_and_the_ex_goodwill_estimate_are_as_defined() -> None:
    r = row("A", 2024, margin=0.2, fcff=100.0, fcff_maintenance=150.0)
    assert r.maintenance_margin is not None and abs(r.maintenance_margin - (120.0 * 1.5 / 100.0 - 1.0)) < 1e-12
    assert row("B", 2024, margin=0.2, fcff=-5.0, fcff_maintenance=10.0).maintenance_margin is None
    g = row("C", 2024, margin=0.0, roic_ex_goodwill=0.30, reinvestment_rate=0.5, nopat=10.0)
    assert g.g_ex_goodwill is not None and abs(g.g_ex_goodwill - 0.15) < 1e-12
    assert row("D", 2024, margin=0.0, roic_ex_goodwill=0.30, reinvestment_rate=-0.1, nopat=10.0).g_ex_goodwill is None
    assert row("E", 2024, margin=0.0, roic_ex_goodwill=0.30, reinvestment_rate=0.5, nopat=-1.0).g_ex_goodwill is None


def test_the_four_quarter_section_counts_direction_and_anticipation() -> None:
    rows: list[rs.Row] = []
    for i in range(12):
        # at 2023 the shadow's fair value equals the 2024 headline exactly: nearer on every row
        rows.append(row(f"N{i}", 2023, margin=-0.1 + i / 100, four_quarter_margin=0.1 + i / 100, four_quarter_fair_value=110.0 + i))
        rows.append(row(f"N{i}", 2024, margin=(110.0 + i) / 100 - 1))
    lines = rs.four_quarter_section(rows)
    assert lines[0].startswith("1. the four-quarter shadow against the headline: 12 of 24")
    assert any("disagree on direction: 11 of 12" in l for l in lines)   # margins -0.10 .. +0.01 against +0.10 .. +0.21: a zero margin is not positive
    assert any("the shadow nearer on 12 (100%)" in l for l in lines)
    assert any("the shadow higher on 12 of 12" in l for l in lines)


def test_the_sections_say_so_when_the_panel_carries_no_readout() -> None:
    rows = [row("A", 2020, margin=0.1), row("B", 2021, margin=-0.1)]
    assert rs.four_quarter_section(rows)[-1].startswith("  none")
    assert rs.intensity_section(rows)[-1].startswith("  none")
    assert rs.maintenance_section(rows)[-1].startswith("  none")
    assert rs.goodwill_section(rows, rs.broad_panel.FRAMES, rs.rule_panel.ROOT / "universe")[-1].startswith("  none")


def test_the_intensity_section_sorts_the_excess_by_fifths_of_spending() -> None:
    rows = [row(f"N{i}", 2023, margin=0.0, excess=i / 100, capex_over_depreciation=0.5 + i / 10) for i in range(50)]
    lines = rs.intensity_section(rows)
    assert any("at or above two on 35 rows" in l for l in lines)
    assert any(l.strip().startswith("fifth 5:") and "median" in l for l in lines)
    assert any("heaviest fifth less lightest" in l and "+0.400" in l for l in lines)
