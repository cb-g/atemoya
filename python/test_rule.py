"""The rule panel's rule and its study on invented rows: the industry-code table, the
largest by market value with the held-out names left out, and the study's tables."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import cast

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


def test_a_variant_reference_changes_only_the_two_figures_it_is_given(tmp_path: Path) -> None:
    import rule_variants as rv

    source = tmp_path / "reference"
    source.mkdir()
    (source / "params.json").write_text(json.dumps({"projection_years": {"value": 7}, "terminal_growth_rate": {"values": {"United States": 0.036, "Japan": 0.027}}}))
    (source / "equity_risk_premiums.json").write_text(json.dumps({"values": {"United States": 0.045, "Japan": 0.051}}))
    (source / "risk_free_rates.json").write_text(json.dumps({"countries": {"United States": {"rates": {"7y": 0.02}}}}))
    assert rv.rates_on(source) == (0.02, 0.036, 0.045, "7y")
    rv.variant_reference(source, tmp_path / "both", growth=0.02, premium=0.061)
    assert rv.rates_on(tmp_path / "both") == (0.02, 0.02, 0.061, "7y")
    other = json.loads((tmp_path / "both" / "params.json").read_text())["terminal_growth_rate"]["values"]["Japan"]
    assert other == 0.027                                                      # another country is untouched
    rv.variant_reference(source, tmp_path / "none", growth=None, premium=None)
    assert rv.rates_on(tmp_path / "none") == rv.rates_on(source)
    assert rv.premium_for(2016, {"2015": 0.0612}) == 0.0612 and rv.premium_for(2014, {"2015": 0.0612}) is None


def test_the_tracked_premium_history_covers_every_june_the_rule_panel_forms() -> None:
    import rule_variants as rv

    history = json.loads(rv.ERP_HISTORY.read_text())["implied_premium_at_year_end"]
    assert all(rv.premium_for(year, history) is not None for year in range(2013, 2027))
    assert all(0.03 < v < 0.08 for v in history.values())


def _alpha_fixture(tmp_path: Path, loadings: dict[int, tuple[float, float]]) -> tuple[Path, Path, Path]:
    """Two formations of fifty invented names, ten a fifth by the measure, each name's monthly
    return its fifth's (alpha, beta) on an invented market; a flat invented rate."""
    import rule_alpha as ra

    months = ["2020-06", *ra.months_after(2020), *ra.months_after(2021)]
    market = [0.03 if i % 3 else -0.04 for i in range(len(months) - 1)]
    bars: dict[str, Json] = {"SPY": {"adjusted": {}}}
    level = 100.0
    spy: dict[str, float] = {months[0]: level}
    for month, r in zip(months[1:], market, strict=True):
        level *= 1 + r
        spy[month] = level
    bars["SPY"] = {"adjusted": spy}
    lines: list[Json] = []
    for i in range(50):
        alpha, beta = loadings[1 + i // 10]
        price = 10.0
        adjusted = {months[0]: price}
        for month, r in zip(months[1:], market, strict=True):
            price *= 1 + alpha + beta * (r - 0.001) + 0.001
            adjusted[month] = price
        bars[f"N{i:02d}"] = {"adjusted": adjusted}
        for year in (2020, 2021):
            lines.append({"ticker": f"N{i:02d}", "date": f"{year}-06-30", "status": "Ok", "margin_of_safety": 0.01 * i, "market_cap": 1e9 * (1 + i % 10)})
    lines.append({"ticker": "REF", "date": "2020-06-30", "status": "Failed", "margin_of_safety": None})
    panel, prices, rate = tmp_path / "panel.jsonl", tmp_path / "prices", tmp_path / "DGS1.json"
    panel.write_text("".join(json.dumps(x) + "\n" for x in lines))
    prices.mkdir()
    (prices / "all.json").write_text(json.dumps(bars))
    observations = [{"date": f"{m}-15", "value": "1.2"} for m in ["2020-05", *months]] + [{"date": "2020-08-20", "value": "."}]
    rate.write_text(json.dumps({"observations": sorted(observations, key=lambda o: o["date"])}))
    return panel, prices, rate


def test_a_fifth_that_only_carries_more_market_shows_a_raw_spread_and_no_alpha(tmp_path: Path) -> None:
    import rule_alpha as ra

    loadings = {1: (0.0, 0.5), 2: (0.0, 0.75), 3: (0.0, 1.0), 4: (0.0, 1.25), 5: (0.0, 1.5)}
    panel, prices, rate_path = _alpha_fixture(tmp_path, loadings)
    rows, adjusted, rate = ra.load_rows(panel), ra.load_adjusted(prices), ra.load_rate(rate_path)
    assert len(rows) == 100 and all(r.cap is not None for r in rows)          # the refused row is left out
    assert abs(rate["2020-07"] - 0.012 / 12) < 1e-15 and "2020-05" not in rate            # the month before's yield; a "." is no observation
    text = ra.report(rows, adjusted, rate)
    block = text.split("margin_of_safety, all formations, equal weights")[1].split("\n\n")[0]
    assert "fifth 1: 24 months" in block and "beta +0.50, alpha +0.00% a month" in block
    assert "fifth 5: 24 months" in block and "beta +1.50, alpha +0.00% a month" in block
    spread = next(x for x in block.splitlines() if "highest less lowest" in x)
    assert "beta +1.00, alpha +0.00% a month" in spread and "mean +0.57% a month" in spread and "(t" not in spread   # a raw spread that is all market
    assert "formations from 2022, equal weights: 0 rows" in text and "no formation year carries enough rows" in text
    assert "Jensen, Kelly and Pedersen" in text and "Gormsen and Lazarus" in text


def test_an_alpha_is_found_where_one_is_put_whatever_the_market_carried(tmp_path: Path) -> None:
    import rule_alpha as ra

    loadings = {1: (-0.002, 1.2), 2: (0.0, 1.0), 3: (0.0, 1.0), 4: (0.0, 1.0), 5: (0.003, 0.8)}
    panel, prices, rate_path = _alpha_fixture(tmp_path, loadings)
    text = ra.report(ra.load_rows(panel), ra.load_adjusted(prices), ra.load_rate(rate_path))
    for weights in ("equal weights", "capped value weights"):                # every name in a fifth moves alike, so the weights agree
        block = text.split(f"margin_of_safety, all formations, {weights}")[1].split("\n\n")[0]
        spread = next(x for x in block.splitlines() if "highest less lowest" in x)
        assert "beta -0.40, alpha +0.50% a month" in spread, spread


def test_the_fit_and_the_capped_weights_on_figures_small_enough_to_check_by_hand() -> None:
    import rule_alpha as ra
    from broad_study import Row

    assert ra.months_after(2020)[0] == "2020-07" and ra.months_after(2020)[-1] == "2021-06" and ra.previous("2021-01") == "2020-12"
    assert abs((ra.monthly_return({"2020-06": 10.0, "2020-07": 11.0}, "2020-07") or 0.0) - 0.1) < 1e-12 and ra.monthly_return({"2020-07": 11.0}, "2020-07") is None
    x = [0.01 * ((i % 5) - 2) for i in range(30)]
    noise = [0.001 if i % 2 else -0.001 for i in range(30)]
    f = ra.fit([0.002 + 1.5 * a + e for a, e in zip(x, noise, strict=True)], x)
    assert f is not None and abs(f.beta - 1.5) < 0.02 and abs(f.alpha - 0.002) < 1e-4 and f.t_alpha is not None and f.t_alpha > 5
    assert ra.fit([0.01] * 10, [0.0] * 10) is None and ra.fit([0.01] * 30, [0.02] * 30) is None    # too few months; a market that does not move
    rows = [Row(ticker=f"T{i}", year=2020, excess=None, non_financial=True, values={"m": float(i)}, cap=1.0 if i else 1000.0) for i in range(6)]
    adjusted = {f"T{i}": {"2020-06": 1.0, "2020-07": 1.5 if i == 0 else 1.0} for i in range(6)}
    q = {(r.ticker, 2020): 3 for r in rows}
    assert abs(ra.fifth_returns(rows, q, adjusted, capped_value=False)[3]["2020-07"] - 0.5 / 6) < 1e-12
    capped = ra.fifth_returns(rows, q, adjusted, capped_value=True)[3]["2020-07"]   # the large name counts as one, the cap being the eightieth percentile
    assert abs(capped - 0.5 / 6) < 1e-12


def test_the_alpha_study_names_what_to_run_when_its_inputs_are_missing(tmp_path: Path) -> None:
    import rule_alpha as ra

    assert ra.main(["--panel", str(tmp_path / "none.jsonl"), "--out", str(tmp_path / "out")]) == 2


def _daily_fixture(tmp_path: Path, betas: dict[int, float]) -> Path:
    """Daily closes for the alpha fixture's fifty names and the benchmark over two years to
    each June: each name's daily return its fifth's beta times the invented market's, a
    third of it a day late."""
    from datetime import date, timedelta

    days = [(date(2019, 6, 3) + timedelta(days=i)).isoformat() for i in range(760)]
    market = [0.01 * (((i * 7) % 11) - 5) / 5 for i in range(len(days))]
    histories = tmp_path / "histories"
    histories.mkdir()

    def write(name: str, returns: list[float]) -> None:
        level, closes = 50.0, {}
        for day, r in zip(days, returns, strict=True):
            level *= 1 + r
            closes[day] = level
        (histories / f"{name}.json").write_text(json.dumps({"closes": closes, "splits": {}, "volumes": {}}))

    write("SPY", market)
    for i in range(50):
        b = betas[1 + i // 10]
        write(f"N{i:02d}", [0.0] + [b * (2 / 3 * market[d] + 1 / 3 * market[d - 1]) for d in range(1, len(days))])
    return histories


def test_a_beta_the_market_pays_in_full_shows_no_alpha_and_the_premium_per_unit(tmp_path: Path) -> None:
    import rule_alpha as ra
    import rule_beta as rb

    betas = {1: 0.5, 2: 0.75, 3: 1.0, 4: 1.25, 5: 1.5}
    panel, prices, rate_path = _alpha_fixture(tmp_path, {k: (0.0, b) for k, b in betas.items()})
    histories = _daily_fixture(tmp_path, betas)
    benchmark = rb.load_daily(histories / "SPY.json")
    assert benchmark is not None and rb.load_daily(histories / "NONE.json") is None
    rows, without = rb.load_rows(panel, histories, benchmark)
    assert len(rows) == 100 and without == 1                                   # the refused name has no history
    assert abs(next(r for r in rows if r.ticker == "N00").values["beta"] - 0.75) < 1e-9    # half of 0.5 and half of one, the late third counted
    assert abs(next(r for r in rows if r.ticker == "N49").values["beta"] - 1.25) < 1e-9
    text = rb.report(rows, without, ra.load_adjusted(prices), ra.load_rate(rate_path))
    block = text.split("beta, all formations, equal weights")[1].split("\n\n")[0]
    assert "fifth 1 (beta at formation 0.75): 24 months" in block and "fifth 5 (beta at formation 1.25): 24 months" in block
    assert "highest less lowest: 24 months, mean +0.57% a month, beta +1.00, alpha +0.00% a month" in block
    assert "highest fifth against lowest: +6.8% a year; SPY over the rate in the same months: +6.8% a year" in block
    assert "below zero: -0.57% a month" in block
    assert "1 left out for fewer than 200 daily returns" in text and "Frazzini and Pedersen" in text and "doi:10.3386/w16601" in text


def test_a_beta_the_market_does_not_pay_shows_the_flat_line(tmp_path: Path) -> None:
    import rule_alpha as ra
    import rule_beta as rb

    betas = {1: 0.5, 2: 0.75, 3: 1.0, 4: 1.25, 5: 1.5}
    premium = 0.03 * 16 / 24 - 0.04 * 8 / 24 - 0.001                           # the alpha fixture's market over its rate, a month
    panel, prices, rate_path = _alpha_fixture(tmp_path, {k: ((1 - b) * premium, b) for k, b in betas.items()})   # every fifth earns the market's return
    histories = _daily_fixture(tmp_path, betas)
    benchmark = rb.load_daily(histories / "SPY.json")
    assert benchmark is not None
    rows, without = rb.load_rows(panel, histories, benchmark)
    block = rb.report(rows, without, ra.load_adjusted(prices), ra.load_rate(rate_path)).split("beta, all formations, equal weights")[1].split("\n\n")[0]
    assert "highest less lowest: 24 months, mean +0.00% a month, beta +1.00, alpha -0.57% a month" in block
    assert "highest fifth against lowest: +0.0% a year" in block and "below zero: -0.57% a month" in block


def test_the_beta_estimate_needs_a_year_of_days_and_names_what_to_run(tmp_path: Path) -> None:
    import rule_beta as rb

    days = [f"2020-01-{d:02d}" for d in range(1, 29)]
    market = {day: 0.01 * ((i % 3) - 1) for i, day in enumerate(days)}
    assert rb.beta_of({day: 2 * market[day] for day in days}, days, market) is None          # under two hundred days
    assert rb.daily_returns({"2020-01-01": 10.0, "2020-01-02": 11.0, "2020-01-03": 11.0}, "2020-01-01", "2020-01-02").keys() == {"2020-01-02"}
    assert rb.main(["--panel", str(tmp_path / "none.jsonl"), "--out", str(tmp_path / "out")]) == 2


def test_the_curve_is_shifted_by_a_step_or_moved_to_a_level_and_the_elasticity_read_per_point(tmp_path: Path) -> None:
    import rule_rates as rr

    source = tmp_path / "reference"
    source.mkdir()
    (source / "params.json").write_text(json.dumps({"projection_years": {"value": 7}, "terminal_growth_rate": {"values": {"United States": 0.036}}}))
    (source / "equity_risk_premiums.json").write_text(json.dumps({"values": {"United States": 0.045}}))
    (source / "risk_free_rates.json").write_text(json.dumps({"countries": {"United States": {"rates": {"1y": 0.01, "7y": 0.02, "10y": 0.025}}}}))
    rr.shifted_reference(source, tmp_path / "up", by=0.005)
    up = json.loads((tmp_path / "up" / "risk_free_rates.json").read_text())["countries"]["United States"]["rates"]
    assert all(abs(up[k] - v) < 1e-12 for k, v in {"1y": 0.015, "7y": 0.025, "10y": 0.03}.items())   # every tenor, the same step
    rr.shifted_reference(source, tmp_path / "level", to=0.03)
    level = json.loads((tmp_path / "level" / "risk_free_rates.json").read_text())["countries"]["United States"]["rates"]
    assert abs(level["7y"] - 0.03) < 1e-12 and abs(level["1y"] - 0.02) < 1e-12 and abs(level["10y"] - 0.035) < 1e-12   # the projection tenor at the level, the shape kept
    assert json.loads((tmp_path / "level" / "params.json").read_text())["terminal_growth_rate"]["values"]["United States"] == 0.036   # untouched
    import math
    down: list[Json] = [{"ticker": "A", "status": "Ok", "fair_value": 100.0}, {"ticker": "B", "status": "Ok", "fair_value": 50.0}, {"ticker": "C", "status": "Failed", "fair_value": None}]
    up_r: list[Json] = [{"ticker": "A", "status": "Ok", "fair_value": 100.0 * math.exp(-0.2)}, {"ticker": "B", "status": "Failed", "fair_value": None}, {"ticker": "C", "status": "Failed", "fair_value": None}]
    e, changed = rr.elasticities(up_r, down, 0.005)
    assert len(e) == 1 and abs(e[0] - (-0.2)) < 1e-9 and changed == 1                        # a fifth of value per point; B valued on one side only


def test_the_fifths_are_followed_into_later_event_years_on_the_same_formation(tmp_path: Path) -> None:
    import rule_alpha as ra
    import rule_beta as rb
    from broad_study import quintiles

    assert ra.months_after(2020, 2) == ra.months_after(2021) and ra.months_after(2020, 3)[0] == "2022-07"
    betas = {1: 0.5, 2: 0.75, 3: 1.0, 4: 1.25, 5: 1.5}
    panel, prices, rate_path = _alpha_fixture(tmp_path, {k: (0.0, b) for k, b in betas.items()})
    rows = ra.load_rows(panel)
    q = quintiles(rows, "margin_of_safety")
    adjusted = ra.load_adjusted(prices)
    second = ra.fifth_returns(rows, q, adjusted, capped_value=False, event_year=2)
    assert len(second[5]) == 12 and min(second[5]) == "2021-07"                      # only the 2020 formation has a second year of bars
    first = ra.fifth_returns(rows, q, adjusted, capped_value=False)
    assert second[5]["2021-07"] == first[5]["2021-07"]                                 # the same names, the same month: the 2020 fifth in its second year, the 2021 fifth in its first
    histories = _daily_fixture(tmp_path, betas)
    benchmark = rb.load_daily(histories / "SPY.json")
    assert benchmark is not None
    brows, _ = rb.load_rows(panel, histories, benchmark)
    market = {m: r for m in adjusted["SPY"] if (r := ra.monthly_return(adjusted["SPY"], m)) is not None}
    lines = rb.by_event_year(brows, adjusted, market, ra.load_rate(rate_path), capped_value=False)
    assert lines[2] == "  at formation: beta 0.75 in the lowest fifth, 1.25 in the highest, gap 0.50"
    assert lines[3].startswith("  year 1: 24 months; realised beta 0.50 lowest, 1.50 highest, gap 1.00")
    assert lines[4].startswith("  year 2: fewer than")                                  # twelve months is under the floor


def test_the_beta_estimates_shrink_as_the_papers_have_them_and_the_forecast_is_scored_as_it_is_and_fitted() -> None:
    import rule_betas as rbs

    days = [f"2020-{m:02d}-{d:02d}" for m in range(1, 13) for d in range(1, 29)]           # 336 invented days
    market = {day: 0.01 * (((i * 7) % 11) - 5) / 5 for i, day in enumerate(days)}
    exact = rbs.ols_of({day: 1.5 * market[day] for day in days}, market)
    assert exact is not None and abs(exact.beta - 1.5) < 1e-9 and exact.se < 1e-9 and exact.days == 336
    noisy = rbs.ols_of({day: 1.5 * market[day] + (0.002 if i % 2 else -0.002) for i, day in enumerate(days)}, market)
    assert noisy is not None and abs(noisy.beta - 1.5) < 0.05 and noisy.se > 0
    assert rbs.ols_of({day: 2 * market[day] for day in days[:100]}, market) is None          # under the floor
    assert rbs.ols_of({day: 9.0 * market[day] for day in days}, market).beta == 5.0           # pyright: ignore[reportOptionalMemberAccess]  # winsorised
    assert abs(rbs.vasicek(rbs.Ols(beta=1.5, se=0.0, days=300), mean=1.0, sd=0.5) - 1.5) < 1e-12   # a precise slope keeps itself
    assert abs(rbs.vasicek(rbs.Ols(beta=1.5, se=0.5, days=300), mean=1.0, sd=0.0) - 1.0) < 1e-12   # no dispersion to hold it: the mean
    assert abs(rbs.vasicek(rbs.Ols(beta=1.5, se=0.3, days=300), mean=1.0, sd=0.3) - 1.25) < 1e-12  # equal variances, halfway
    assert abs(rbs.levi_welch(1.4) - 1.3) < 1e-12 and abs(rbs.faded(1.4) - 1.2) < 1e-12
    codes: dict[str, int | None] = {f"T{i}": 3570 + i for i in range(6)} | {"U0": 2800, "U1": 2834, "X": None}
    by = rbs.industry_betas({f"T{i}": 1.0 + 0.1 * i for i in range(6)} | {"U0": 0.5, "U1": 0.7, "X": 2.0}, codes)
    assert abs(by["T0"] - 1.3) < 1e-12 and "U0" not in by and "X" not in by                 # five others; two are too few; no code
    f = rbs.forecast([1.0 + 0.01 * i for i in range(40)], [1.0 + 0.01 * i for i in range(40)])
    assert f is not None and abs(f.r2_as_is - 1) < 1e-9 and f.rmse_as_is < 1e-9 and abs(f.slope - 1) < 1e-9 and abs(f.intercept) < 1e-9
    g = rbs.forecast([1.0] * 40, [1.0 + 0.01 * i for i in range(40)])
    assert g is not None and g.slope == 0.0 and abs(g.r2_fitted) < 1e-9 and g.r2_as_is < 0            # a constant below the mean explains nothing
    assert rbs.forecast([1.0] * 10, [1.0] * 10) is None
    assert rbs.window(2020, "2020-06-30", 0) == ("2019-06-30", "2020-06-30") and rbs.window(2020, "2020-06-30", 3) == ("2022-06-30", "2023-06-30")
    assert rbs.spearman([(float(i), float(-i)) for i in range(12)]) == -1.0 and rbs.spearman([(1.0, 2.0)] * 12) is None


def test_the_betas_of_the_panel_carry_the_year_ahead_and_the_reading_is_written_as_an_industry_table(tmp_path: Path) -> None:
    import rule_beta as rb
    import rule_betas as rbs

    betas = {1: 0.5, 2: 0.75, 3: 1.0, 4: 1.25, 5: 1.5}
    panel, _prices, _rate = _alpha_fixture(tmp_path, {k: (0.0, b) for k, b in betas.items()})
    histories = _daily_fixture(tmp_path, betas)
    universe_dir = tmp_path / "universe"
    universe_dir.mkdir()
    universe_dir.joinpath("2020-06-30.json").write_text(json.dumps([{"ticker": f"N{i:02d}", "sic": 7372 if i < 40 else 2800} for i in range(50)]))
    benchmark = rb.load_daily(histories / "SPY.json")
    assert benchmark is not None
    rows, without = rbs.betas_of(panel, histories, benchmark, universe_dir)
    assert len(rows) == 100 and without == 1
    low, high = (next(r for r in rows if r.ticker == t and r.year == 2020) for t in ("N00", "N49"))
    mean = sum(r.ols.beta for r in rows if r.year == 2020) / 50
    assert low.ols.beta < low.vck < mean < high.vck < high.ols.beta                              # Vasicek pulls each slope toward the date's mean
    assert low.vck < low.lw < 1.0 and high.vck < high.lw < 1.0                                   # the second shrinkage toward one; the fixture's slopes all sit below it
    assert abs(cast(float, low.fp) - 0.75) < 1e-9 and abs(cast(float, high.fp) - 1.25) < 1e-9  # the beta study's estimate, unchanged
    assert low.industry is not None and high.industry is not None and low.industry < high.industry   # forty names in one code, the highest fifth alone in the other
    assert abs(high.industry - high.ols.beta) < 1e-9                                                # the other nine in its code carry the same slope
    assert 1 in low.ahead and abs(low.ahead[1] - low.ols.beta) < 0.01                        # the fixture repeats itself, nearly, a year on
    assert all(r.ahead == {} for r in rows if r.year == 2021)                                 # no bars after June 2021
    assert all(r.industry is None for r in rows if r.year == 2021)                            # no codes for the date
    pit = tmp_path / "pit"
    pit.mkdir()
    (pit / "reference").mkdir()
    (pit / "reference" / "industry_betas.json").write_text("{}")
    (pit / "reference" / "params.json").write_text("{\"kept\": true}")
    (pit / "N00.json").write_text(json.dumps({"ticker": "N00", "industry": None, "price": 1.0}))
    (pit / "N01.json").write_text(json.dumps({"ticker": "N01", "industry": None}))
    records, reference = rbs.reading_inputs(pit, tmp_path / "copy", "2020-06-30", {"N00": 0.8}, "lw")
    assert json.loads((records / "N00.json").read_text()) == {"ticker": "N00", "industry": "N00", "price": 1.0}
    assert json.loads((records / "N01.json").read_text())["industry"] is None                 # no beta, no key: the valuation keeps one
    table = json.loads((reference / "industry_betas.json").read_text())
    assert table["values"] == {"N00": 0.8} and table["as_of"] == "2020-06-30" and "lw" in table["source"]
    assert json.loads((reference / "params.json").read_text()) == {"kept": True} and (pit / "reference" / "industry_betas.json").read_text() == "{}"
    assert rbs.reading_beta(low, "one") == 1.0 and rbs.reading_beta(low, "lw_faded") == rbs.faded(low.lw)
    assert rbs.main(["--panel", str(tmp_path / "none.jsonl"), "--out", str(tmp_path / "out")]) == 2


def _growth_fixture(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Sixty invented names on two Junes with a fundamental estimate rising with the index, frames
    for the seven fiscal years after the first base, and the oddities the matching must handle."""
    import rule_growth as rg

    panel_out, universe_dir, frames = tmp_path / "rule_panel", tmp_path / "universe", tmp_path / "frames"
    frames.mkdir()
    for year, base_end in ((2020, "2019-12-31"), (2021, "2020-12-31")):
        day = f"{year}-06-30"
        (panel_out / day).mkdir(parents=True)
        universe_dir.mkdir(exist_ok=True)
        universe_dir.joinpath(f"{day}.json").write_text(json.dumps([{"ticker": f"N{i:02d}", "cik": f"{1000 + i:010d}"} for i in range(60)] + [{"ticker": "MID", "cik": "0000009999"}]))
        lines: list[Json] = []
        for i in range(60):
            g0 = 0.002 * i
            lines.append({"ticker": f"N{i:02d}", "status": "Ok",
                          "inputs": ["dcf", {"fiscal_period_end": base_end, "growth_source": "fundamental", "g_fundamental": g0, "g_historical": 0.1, "g0": g0,
                                             "growth_path": [g0] * 7, "terminal_growth_rate": {"value": 0.02, "key": "United States"}}],
                          "growth_shadow": {"g0_shadow": max(g0, 0.1)}})
        lines.append({"ticker": "MID", "status": "Ok", "inputs": ["midcycle", {"fcff_mid": 1.0}]})
        lines.append({"ticker": "REF", "status": "Failed", "failed_reason": "invented"})
        (panel_out / day / "valuations.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    for n, year in enumerate(range(2019, 2026)):
        end = f"{year}-12-31"
        revenues: list[Json] = []
        sales: list[Json] = []
        operating: list[Json] = []
        for i in range(60):
            cik, rate = 1000 + i, 0.05 + 0.0005 * i
            revenue, income = 100.0 * (1 + rate) ** n, 10.0 * (1 + rate) ** n
            if i == 1 and year == 2022:
                end_i = "2023-01-02"                                             # a 53-week year: within the tolerance
            else:
                end_i = end
            if i == 2:
                sales.append({"cik": cik, "end": end_i, "val": revenue})         # tagged on the chain's last element only
                revenues.append({"cik": cik, "end": end_i, "val": 999.0}) if year == 2019 else None   # the first element wins where both carry the year
            else:
                revenues.append({"cik": cik, "end": end_i, "val": revenue})
            if i == 3 and year == 2020:
                operating.append({"cik": cik, "end": end_i, "val": -1.0})        # a loss: no rate describes it
            elif not (i == 4 and year == 2024):                                  # a filer gone before its fifth year
                operating.append({"cik": cik, "end": end_i, "val": income})
        for tag, rows in (("Revenues", revenues), ("SalesRevenueNet", sales), ("OperatingIncomeLoss", operating)):
            (frames / f"us-gaap-{tag}-CY{year}.json").write_text(json.dumps({"data": rows}))
    assert rg.OUTCOMES == ("revenue", "operating_income")
    return panel_out, universe_dir, frames


def test_the_growth_estimates_are_read_as_the_model_computed_them_and_scored_against_what_the_filer_then_reported(tmp_path: Path) -> None:
    import rule_growth as rg

    assert rg.path_mean([0.1, 0.1, 0.1], 2) is not None and abs(cast(float, rg.path_mean([0.1, 0.1, 0.1], 2)) - 0.1) < 1e-12
    assert abs(cast(float, rg.path_mean([0.2, 0.0], 2)) - (1.2 ** 0.5 - 1)) < 1e-12 and rg.path_mean([0.1], 2) is None
    assert abs(cast(float, rg.annualised(100.0, 121.0, 2)) - 0.1) < 1e-12 and rg.annualised(0.0, 1.0, 1) is None and rg.annualised(1.0, -1.0, 1) is None
    panel_out, universe_dir, frames_dir = _growth_fixture(tmp_path)
    records = rg.load_records(panel_out, universe_dir)
    assert len(records) == 120 and all(r.source == "fundamental" and r.terminal == 0.02 for r in records)   # the mid-cycle and the refused record carry no growth
    n05 = next(r for r in records if r.ticker == "N05" and r.year == 2020)
    assert n05.cik == 1005 and n05.base_end == "2019-12-31" and abs(n05.headline - 0.01) < 1e-12 and abs(n05.shadow - 0.1) < 1e-12 and n05.historical == 0.1
    frames = rg.load_frames(frames_dir)
    assert frames["revenue"][(1000, "2019-12-31")] == 100.0 and frames["revenue"][(1002, "2019-12-31")] == 999.0   # the chain's first element wins
    assert frames["revenue"][(1002, "2020-12-31")] == 100.0 * 1.051                                             # and the last carries the years it alone has
    rg.realise(records, frames)
    for k in (1, 3, 5):
        assert abs(n05.realised[("revenue", k)] - 0.0525) < 1e-9 and abs(n05.realised[("operating_income", k)] - 0.0525) < 1e-9
    n01 = next(r for r in records if r.ticker == "N01" and r.year == 2020)
    assert abs(n01.realised[("revenue", 3)] - 0.0505) < 1e-9                                           # the 53-week end matched within the tolerance
    n03 = next(r for r in records if r.ticker == "N03" and r.year == 2020)
    assert n03.unmatched[("operating_income", 1)] == "a figure at or below zero" and ("operating_income", 1) not in n03.realised and ("operating_income", 3) in n03.realised
    n04 = next(r for r in records if r.ticker == "N04" and r.year == 2020)
    assert n04.unmatched[("operating_income", 5)] == "no figure at the horizon" and ("revenue", 5) in n04.realised
    later = next(r for r in records if r.ticker == "N05" and r.year == 2021)
    assert ("revenue", 5) in later.realised and later.unmatched == {}                                   # 2020 to 2025: the frames reach it
    pairs, moved = rg.winsorise([(0.01 * i, 0.01 * i) for i in range(99)] + [(5.0, -5.0)])
    assert moved == 4 and max(x for x, _ in pairs) < 5.0 and min(y for _, y in pairs) > -5.0            # the extreme on each side of each column
    assert rg.winsorise([(1.0, 1.0)] * 5) == ([(1.0, 1.0)] * 5, 0)
    assigned = rg.fifths(records)
    assert assigned[("N00", 2020)] == 1 and assigned[("N59", 2020)] == 5 and assigned[("N30", 2021)] == 3 and len(assigned) == 120
    text = rg.report(records)
    assert "120 generic DCF records on 60 names, 2020 to 2021; sources: fundamental 120, historical 0" in text
    assert "operating income, 1 year(s): 118 realised; a figure at or below zero 2" in text              # N03 on both Junes' first year
    assert "operating income, 5 year(s): 118 realised; a figure at or below zero 1, no figure at the horizon 1" in text   # N03's 2021 base is the loss; N04's fifth year is missing from 2020 only
    assert "which estimate forecasts realised revenue growth, every record" in text and "fifth 5 less fifth 1" in text
    assert "realised revenue growth, one year on the year before: 60 pairs" in text
    assert rg.main(["--panel-out", str(tmp_path / "none"), "--out", str(tmp_path / "out")]) == 2
    assert rg.main(["--panel-out", str(panel_out), "--universe-dir", str(universe_dir), "--frames", str(frames_dir), "--out", str(tmp_path / "out")]) == 0
    assert len((tmp_path / "out" / "growth.jsonl").read_text().splitlines()) == 120 and (tmp_path / "out" / "tables.txt").read_text() == text


def test_the_durations_follow_the_papers_worked_examples_and_the_closed_forms_and_are_read_off_the_panel(tmp_path: Path) -> None:
    import rule_duration as rd

    # the paper's Table 2 (pp.31-32): Alaska Air and Amazon.com for 1999, in millions, sales growth 9.70% and 168.90%
    alaska = rd.dss_duration(market_cap=685.90, book=930.70, book_lagged=789.50, sales=1.0970, sales_lagged=1.0, earnings=134.20)
    amazon = rd.dss_duration(market_cap=8905.00, book=266.28, book_lagged=138.75, sales=2.6890, sales_lagged=1.0, earnings=-719.97)
    assert alaska is not None and abs(alaska - 10.01) < 0.01 and amazon is not None and abs(amazon - 23.02) < 0.01
    assert rd.dss_duration(market_cap=100.0, book=-1.0, book_lagged=5.0, sales=1.0, sales_lagged=1.0, earnings=1.0) is None      # negative book equity: dropped
    perpetuity = rd.model_duration(fcff=100.0, wacc=0.08, growth_path=[0.03] * 7, terminal_growth=0.03, net_debt=0.0)
    assert perpetuity is not None and abs(perpetuity - 1.08 / 0.05) < 1e-9                                  # a flat growing perpetuity: (1 + r) / (r - g), whatever the horizon
    pvs, terminal_pv, terminal_duration = rd.model_flows(100.0, 0.08, [0.03] * 7, 0.03)
    enterprise = sum(pvs) + terminal_pv
    levered = rd.model_duration(fcff=100.0, wacc=0.08, growth_path=[0.03] * 7, terminal_growth=0.03, net_debt=0.5 * enterprise)
    assert levered is not None and abs(levered - 2 * perpetuity) < 1e-9 and abs(terminal_duration - (7 + 1.08 / 0.05)) < 1e-12   # net debt at a duration of nought doubles it at half the value
    assert rd.model_duration(fcff=100.0, wacc=0.03, growth_path=[0.03], terminal_growth=0.03, net_debt=0.0) is None            # the rate must exceed terminal growth
    implied = rd.implied_duration(fcff=100.0, wacc=0.08, growth_path=[0.03] * 7, terminal_growth=0.03, net_debt=0.0, market_cap=enterprise)
    assert implied is not None and abs(implied - perpetuity) < 1e-9                                                            # at the model's own value the two agree
    dearer = rd.implied_duration(fcff=100.0, wacc=0.08, growth_path=[0.03] * 7, terminal_growth=0.03, net_debt=0.0, market_cap=2 * enterprise)
    assert dearer is not None and dearer > perpetuity                                                                           # a price above the value puts more on the terminal
    f = rd.fit([[float(i)] for i in range(40)], [2.0 + 3.0 * i for i in range(40)])
    assert f is not None and abs(f[0][0] - 3.0) < 1e-9 and abs(f[1] - 1.0) < 1e-9 and rd.fit([[1.0]] * 10, [1.0] * 10) is None
    closes = {f"2020-{m:02d}-{d:02d}": 100.0 + (1.0 if (m + d) % 2 else -1.0) for m in range(1, 13) for d in range(1, 29)}
    vol = rd.volatility(closes, "2019-12-31", "2020-12-31")
    assert vol is not None and 0.019 < vol < 0.021 and rd.volatility(closes, "2020-10-01", "2020-12-31") is None                 # about two per cent a day; under the floor of days
    # the panel: two valued names, a refused one and a mid-cycle one on one June, with their point-in-time items, the panel's row, betas and shifted runs
    day, panel_out, pit, rates = "2020-06-30", tmp_path / "rule_panel", tmp_path / "pit", tmp_path / "rates"
    (panel_out / day).mkdir(parents=True)
    (pit / day).mkdir(parents=True)
    dcf = {"market_cap": 1000.0, "fcff": 50.0, "wacc": 0.08, "net_debt": 100.0, "growth_path": [0.05] * 7, "terminal_growth_rate": {"value": 0.03}}
    records: list[Json] = [{"ticker": "AAA", "status": "Ok", "inputs": ["dcf", dcf]},
                           {"ticker": "BBB", "status": "Ok", "inputs": ["dcf", dcf | {"market_cap": 4000.0, "fcff": 10.0}]},
                           {"ticker": "REF", "status": "Failed", "inputs": ["dcf", dcf]},
                           {"ticker": "MID", "status": "Ok", "inputs": ["midcycle", {"fcff_mid": 1.0}]}]
    (panel_out / day / "valuations.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    (pit / day / "AAA.json").write_text(json.dumps({"periods": [{"book_equity": 500.0, "total_revenue": 1100.0, "net_income": 80.0}, {"book_equity": 450.0, "total_revenue": 1000.0}]}))
    (pit / day / "BBB.json").write_text(json.dumps({"periods": [{"book_equity": 200.0, "total_revenue": 900.0, "net_income": -20.0}]}))   # one period: no paper's measure
    panel = tmp_path / "panel.jsonl"
    panel.write_text(json.dumps({"ticker": "AAA", "date": day, "margin_of_safety": 0.2, "earnings_yield": 0.08}) + "\n"
                     + json.dumps({"ticker": "BBB", "date": day, "margin_of_safety": -0.5, "earnings_yield": -0.005}) + "\n")
    rows = rd.load_records(panel_out, pit, panel)
    assert [r.ticker for r in rows] == ["AAA", "BBB"]
    aaa, bbb = rows
    expected = rd.dss_duration(market_cap=1000.0, book=500.0, book_lagged=450.0, sales=1100.0, sales_lagged=1000.0, earnings=80.0)
    assert aaa.dss == expected and bbb.dss is None and aaa.book_to_market == 0.5 and aaa.margin == 0.2 and bbb.earnings_yield == -0.005
    assert aaa.model is not None and bbb.model is not None and aaa.modified is not None and abs(aaa.modified - aaa.model / 1.08 / 100) < 1e-12
    assert aaa.implied is not None and bbb.implied is not None and bbb.implied > aaa.implied                   # the dearer name on the same flows carries more terminal
    betas = tmp_path / "betas.jsonl"
    betas.write_text(json.dumps({"ticker": "AAA", "year": 2020, "ols": 0.9, "ahead": {"1": 1.1}}) + "\n" + json.dumps({"ticker": "BBB", "year": 2020, "ols": 1.2, "ahead": {}}) + "\n")
    rd.attach_betas(rows, betas)
    assert aaa.beta == 0.9 and aaa.beta_ahead == 1.1 and bbb.beta == 1.2 and bbb.beta_ahead is None
    for side, factor in (("up", 0.9), ("down", 1.1)):
        (rates / side / day).mkdir(parents=True)
        (rates / side / day / "valuations.jsonl").write_text(json.dumps({"ticker": "AAA", "status": "Ok", "fair_value": 100.0 * factor}) + "\n")
    rd.attach_elasticities(rows, rates, 0.005)
    assert aaa.elasticity is not None and abs(aaa.elasticity - (math.log(90.0) - math.log(110.0)) / 0.01 / 100) < 1e-12 and bbb.elasticity is None
    rd.attach_relative(rows)
    mean = (aaa.model * 1000.0 + bbb.model * 4000.0) / 5000.0
    assert abs(aaa.relative["model"] - aaa.model / mean) < 1e-12 and "dss" not in bbb.relative and abs(aaa.relative["dss"] - 1.0) < 1e-12
    text = rd.report(rows)
    assert "2 generic DCF records on 2 names, 2020 to 2020; with a figure: dss 1, model 2, implied 2" in text
    assert "the paper's Table 5" in text and "beta, dss: fewer than 30 rows" in text and "2020       1   fewer than 10 rows" in text
    assert rd.main(["--panel-out", str(tmp_path / "none"), "--out", str(tmp_path / "out")]) == 2
    assert rd.main(["--panel-out", str(panel_out), "--pit", str(pit), "--panel", str(panel), "--betas", str(betas), "--histories", str(tmp_path / "none"),
                    "--rates-out", str(rates), "--out", str(tmp_path / "out")]) == 0
    assert len((tmp_path / "out" / "durations.jsonl").read_text().splitlines()) == 2 and (tmp_path / "out" / "tables.txt").read_text() == text
