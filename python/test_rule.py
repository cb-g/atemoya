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
