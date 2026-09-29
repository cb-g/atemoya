"""Each curve parser on a fixture in its source's format, and the validation that stands
between a parsed observation and the rate file. Every number in a fixture is synthetic:
nothing here was observed at any source."""

from __future__ import annotations

import json
from datetime import date

import pytest

import reference
import refresh_rates as rr


def rule(**kw: object) -> reference.RateSource:
    base: dict[str, object] = {"tier": "official", "source": "s", "parser": "x", "tenors": ["7y"]}
    base.update(kw)
    return reference.RateSource.from_json(base)


def test_fred_series_skips_dots_and_reads_decimal() -> None:
    body = json.dumps({"observations": [
        {"date": "2026-09-17", "value": "."}, {"date": "2026-09-16", "value": "4.50"}]}).encode()
    assert rr.parse_fred_series(body, "DGS7") == (date(2026, 9, 16), 0.045)
    with pytest.raises(rr.RefreshError):
        rr.parse_fred_series(json.dumps({"observations": [{"date": "2026-09-17", "value": "."}]}).encode(), "DGS7")


def test_boc_valet_takes_the_latest_complete_observation() -> None:
    body = json.dumps({"observations": [
        {"d": "2026-09-16", "BD.CDN.7YR.DQ.YLD": {"v": "3.50"}, "BD.CDN.10YR.DQ.YLD": {"v": "3.70"}},
        {"d": "2026-09-17", "BD.CDN.7YR.DQ.YLD": {"v": "3.40"}}]}).encode()
    f = rr.parse_boc_valet(body, {"7y": "BD.CDN.7YR.DQ.YLD", "10y": "BD.CDN.10YR.DQ.YLD"})
    assert (f.as_of, f.rates) == (date(2026, 9, 16), {"7y": 0.035, "10y": 0.037})


def test_ecb_sdmx_csv_groups_keys_by_period() -> None:
    body = (b"KEY,FREQ,TIME_PERIOD,OBS_VALUE\n"
            b"YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_7Y,B,2026-09-17,3.1234567890\n"
            b"YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y,B,2026-09-17,3.3456789012\n"
            b"YC.B.U2.EUR.4F.G_N_A.SV_C_YM.SR_7Y,B,2026-09-16,3.10\n")
    f = rr.parse_ecb_yc(body, {"7y": "SR_7Y", "10y": "SR_10Y"})
    assert f.as_of == date(2026, 9, 17)
    assert f.rates == {"7y": 0.031235, "10y": 0.033457}


def test_bundesbank_csv_reads_decimal_comma_after_metadata() -> None:
    body = ('﻿"";BBSIS.D.I...;FLAGS\n"";Zinsstrukturkurve;\nEinheit;Prozent;\n'
            "2026-09-17;2,90;\n2026-09-18;2,80;\n").encode("utf-8")
    assert rr.parse_bundesbank_lines(body, "R07XX") == (date(2026, 9, 18), 0.028)


def test_bundesbank_csv_skips_the_missing_observation_placeholder() -> None:
    """The Bundesbank marks a day with no observation as `.`; the refresh of 2026-09-29 fell
    over on one. Such a row is skipped and the newest numeric row is the observation, so the
    age check downstream sees that row's date and not the placeholder's."""
    body = ('\ufeff"";BBSIS.D.I...;FLAGS\n"";Zinsstrukturkurve;\nEinheit;Prozent;\n'
            "2026-09-17;2,90;\n2026-09-18;2,80;\n2026-09-21;.;\n2026-09-22;.;\n").encode("utf-8")
    assert rr.parse_bundesbank_lines(body, "R07XX") == (date(2026, 9, 18), 0.028)
    # a response that is placeholders only carries no observation at all
    with pytest.raises(rr.RefreshError, match="no dated observation"):
        rr.parse_bundesbank_lines(b"2026-09-21;.;\n2026-09-22;.;\n", "R07XX")
    # anything else that is not a number is still an error, named
    with pytest.raises(rr.RefreshError, match="is not a number"):
        rr.parse_bundesbank_lines(b"2026-09-21;n/a;\n", "R07XX")


def test_mof_csv_takes_the_last_dated_row() -> None:
    body = (b"Interest Rate (September 2026),,,(Unit : %)\r\nDate,1Y,2Y,3Y,5Y,7Y,10Y\r\n"
            b"2026/9/16,1.5,1.7,1.9,2.2,2.4,2.8\r\n2026/9/17,1.6,1.9,2.0,2.3,2.6,3.0\r\n"
            b",,,,,,\r\n\"  If you cannot download\",,,,,,\r\n")
    f = rr.parse_mof_jgb(body, {"1y": "1Y", "7y": "7Y", "10y": "10Y"})
    assert f.as_of == date(2026, 9, 17)
    assert f.rates == {"1y": 0.016, "7y": 0.026, "10y": 0.03}


def test_tesouro_direto_interpolates_between_bracketing_bonds() -> None:
    header = "Tipo Titulo;Data Vencimento;Data Base;Taxa Compra Manha;Taxa Venda Manha;PU Compra Manha;PU Venda Manha;PU Base Manha"
    rows = [
        "Tesouro Selic;01/03/2031;17/09/2026;0,07;0,08;1;1;1",              # not fixed-rate: ignored
        "Tesouro Prefixado;01/01/2032;17/09/2026;12,00;12,20;1;1;1",         # 5.29y, mid 12.10
        "Tesouro Prefixado com Juros Semestrais;01/01/2035;17/09/2026;12,40;12,60;1;1;1",  # 8.29y, mid 12.50
        "Tesouro Prefixado;01/01/2028;16/09/2026;99,00;99,00;1;1;1",         # older base date: ignored
    ]
    body = ("\n".join([header, *rows]) + "\n").encode("latin-1")
    f = rr.parse_tesouro_direto(body, ["7y"])
    assert f.as_of == date(2026, 9, 17)
    y0 = (date(2032, 1, 1) - date(2026, 9, 17)).days / 365.25
    y1 = (date(2035, 1, 1) - date(2026, 9, 17)).days / 365.25
    expected = 0.1210 + (0.1250 - 0.1210) * (7 - y0) / (y1 - y0)
    assert abs(f.rates["7y"] - expected) < 1e-6
    assert f.estimated == ["7y"]
    with pytest.raises(rr.RefreshError):
        rr.parse_tesouro_direto(body, ["10y"])  # nothing brackets 10y


def test_oecd_substitution_is_recorded_and_dated_at_month_end() -> None:
    r = rule(parser="fred_oecd_10y", tier="fred_oecd_10y", series={"10y": "IRLTLT01KRM156N"},
             substitute={"7y": "10y"}, tenors=["7y", "10y"])
    f = rr._substituted(rr.Fetched(as_of=rr._month_end(date(2026, 8, 1)), rates={"10y": 0.045}), r)  # pyright: ignore[reportPrivateUsage]
    assert f.as_of == date(2026, 8, 31)
    assert f.rates == {"10y": 0.045, "7y": 0.045}
    assert f.tenor_used == {"7y": "10y"}
    curve = rr.to_curve(f, r)
    assert curve.tier == "fred_oecd_10y" and curve.tenor_used == [("7y", "10y")]
    assert [t for t, _ in curve.rates] == ["7y", "10y"]


def test_validation_rejects_bad_range_future_stale_and_missing() -> None:
    r = rule(tenors=["7y", "10y"])
    today = date(2026, 9, 18)
    ok = rr.Fetched(as_of=date(2026, 9, 17), rates={"7y": 0.04, "10y": 0.041})
    rr.validate(ok, r, today)
    with pytest.raises(rr.RefreshError, match="outside the plausible range"):
        rr.validate(rr.Fetched(as_of=date(2026, 9, 17), rates={"7y": 0.45, "10y": 0.041}), r, today)
    with pytest.raises(rr.RefreshError, match="in the future"):
        rr.validate(rr.Fetched(as_of=date(2026, 9, 19), rates={"7y": 0.04, "10y": 0.041}), r, today)
    with pytest.raises(rr.RefreshError, match="days old"):
        rr.validate(rr.Fetched(as_of=date(2026, 6, 1), rates={"7y": 0.04, "10y": 0.041}), r, today)
    with pytest.raises(rr.RefreshError, match="missing tenor"):
        rr.validate(rr.Fetched(as_of=date(2026, 9, 17), rates={"7y": 0.04}), r, today)


def test_fx_normalisation_follows_the_quote_direction() -> None:
    import refresh_fx
    assert refresh_fx.normalise(1.25, "usd_per_unit") == 1.25
    assert abs(refresh_fx.normalise(5.0, "units_per_usd") - 1 / 5.0) < 1e-12
    with pytest.raises(rr.RefreshError):
        refresh_fx.normalise(1.0, "sideways")
    assert rr.parse_fred_latest(json.dumps({"observations": [{"date": "2026-09-11", "value": "5.0"}]}).encode(), "DEXBZUS") == (date(2026, 9, 11), "5.0")


def test_chinabond_curve_is_picked_by_id_and_read_at_whole_year_points() -> None:
    """(75) A list of curves with a grid of (years, per cent); the requested curve by its id,
    the tenors at their exact grid points, a missing point an error rather than an
    interpolation, and a wrong id an error naming the count. Every number is synthetic."""
    grid = [[0.0, 0.9], [0.5, 1.0], [1.0, 1.1], [2.0, 1.2], [3.0, 1.3], [5.0, 1.5], [7.0, 1.7], [10.0, 2.0]]
    body = json.dumps([{"ycDefId": "other", "ycDefName": "x", "worktime": "2026-09-29", "seriesData": grid},
                       {"ycDefId": "cgb", "ycDefName": "China Government Bond", "worktime": "2026-09-29", "seriesData": grid}]).encode()
    f = rr.parse_chinabond_czb(body, "cgb", ["1y", "3y", "5y", "7y", "10y"])
    assert f.as_of == date(2026, 9, 29)
    assert f.rates == {"1y": 0.011, "3y": 0.013, "5y": 0.015, "7y": 0.017, "10y": 0.02}
    with pytest.raises(rr.RefreshError, match="no 15y point"):
        rr.parse_chinabond_czb(body, "cgb", ["15y"])
    with pytest.raises(rr.RefreshError, match="not in the answer"):
        rr.parse_chinabond_czb(body, "missing", ["10y"])
    with pytest.raises(rr.RefreshError, match="malformed"):
        rr.parse_chinabond_czb(json.dumps([{"ycDefId": "cgb", "worktime": "n/a", "seriesData": []}]).encode(), "cgb", ["10y"])


def test_mas_page_reads_the_newest_dated_row_by_tenor() -> None:
    """(77) The closing-levels table: bills carry a yield alone, bonds a price then a yield;
    the newest dated row is the observation, a missing tenor an error. Synthetic numbers."""
    def row(*cells: str) -> str:
        return "<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>"
    table = ('<table id="ContentPlaceHolder1_ClosingLevelsTable">'
             + row("", "Treasury Bills", "Bonds")
             + row("", "6-Mth", "1-Year", "2-Year", "5-Year", "10-Year")
             + row("Issue", "BS1", "BY1", "N1 2% 2028", "NX 1% 2031", "NZ 2% 2036")
             + row("Yield", "Yield", "Price", "Yield", "Price", "Yield", "Price", "Yield")
             + row("29 Sep 2026", "1.10", "1.20", "99.0", "1.30", "98.0", "1.50", "97.0", "1.70")
             + row("30 Sep 2026", "1.11", "1.21", "99.1", "1.31", "98.1", "1.51", "97.1", "1.71")
             + row("28 Sep 2026", "1.09", "1.19", "99.2", "1.29", "98.2", "1.49", "97.2", "1.69")
             + "</table>")
    body = ("<html><body>" + table + "</body></html>").encode()
    f = rr.parse_mas_sgs_html(body, ["1y", "5y", "10y"])
    assert f.as_of == date(2026, 9, 30) and f.rates == {"1y": 0.0121, "5y": 0.0151, "10y": 0.0171}
    with pytest.raises(rr.RefreshError, match="no 7y benchmark"):
        rr.parse_mas_sgs_html(body, ["7y"])
    with pytest.raises(rr.RefreshError, match="not on the page"):
        rr.parse_mas_sgs_html(b"<html></html>", ["10y"])


def test_hkgb_benchmark_rows_read_the_newest_date_by_tenor() -> None:
    """(78) The benchmark sheet as rows: the Tenor row names the benchmarks over a price and
    a yield column each, the one-year floating note quotes no yield, the newest dated row is
    the observation, a missing tenor an error. Synthetic numbers."""
    rows: list[list[object]] = [
        ["Daily HKD Institutional Government Bond Closing Reference Pricings", "", ""],
        ["Tenor", "1-year*", "", "3-year", "", "5-year", "", "7-year", "", "10-year", ""],
        ["Issue code", "01GH", "", "05GB", "", "05GB", "", "07GB", "", "10GB", ""],
        ["", "Price", "Yield", "Price", "Yield", "Price", "Yield", "Price", "Yield", "Price", "Yield"],
        ["Date", "", "(%)", "", "(%)", "", "(%)", "", "(%)", "", "(%)"],
        ["2026-09-29 00:00:00", 100, "-", 99.2, 1.21, 98.2, 1.41, 97.2, 1.61, 96.2, 1.81],
        ["2026-09-30 00:00:00", 100, "-", 99.1, 1.22, 98.1, 1.42, 97.1, 1.62, 96.1, 1.82],
        ["Notes:", "", ""],
    ]
    f = rr.parse_hkgb_rows(rows, ["3y", "5y", "7y", "10y"])
    assert f.as_of == date(2026, 9, 30)
    assert f.rates == {"3y": 0.0122, "5y": 0.0142, "7y": 0.0162, "10y": 0.0182}
    with pytest.raises(rr.RefreshError, match="is not a number"):
        rr.parse_hkgb_rows(rows, ["1y"])   # the floating-rate note carries no yield
    with pytest.raises(rr.RefreshError, match="no 15y column"):
        rr.parse_hkgb_rows(rows, ["15y"])
    with pytest.raises(rr.RefreshError, match="no Tenor row"):
        rr.parse_hkgb_rows([["nothing"]], ["10y"])
