"""The strict universe loader: exactly four fields, why required, nothing remembered."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import universe

ROOT = Path(__file__).resolve().parent.parent


def test_tracked_universe_is_a_declaration_only() -> None:
    text = (ROOT / "reference" / "universe.json").read_text()
    u = universe.load_text(text)
    raw = json.loads(text)["tickers"]
    assert len(u.tickers) == len(raw) == 153
    for entry in raw:
        assert set(entry) <= set(universe.ALLOWED) and all(k in entry for k in universe.REQUIRED)
        # no number followed by a unit, no percentage or multiple, no four-digit year, in a why
        assert not re.search(r"\d+(\.\d+)?\s*(bn|m|%|x)\b|\b(19|20)\d\d\b", entry["why"]), entry


def test_loader_rejects_anything_beyond_the_declaration() -> None:
    ok = {"tickers": [{"ticker": "X", "entity_class": "Bank", "why": "a bank"}]}
    assert universe.load_text(json.dumps(ok)).tickers[0].why == "a bank"
    with pytest.raises(universe.UniverseError, match="unknown field\\(s\\) outcome"):
        universe.load_text(json.dumps({"tickers": [{**ok["tickers"][0], "outcome": "Ok"}]}))
    with pytest.raises(universe.UniverseError, match="unknown field\\(s\\) note, finding"):
        universe.load_text(json.dumps({"tickers": [{**ok["tickers"][0], "note": "n", "finding": "f"}]}))
    with pytest.raises(universe.UniverseError, match="lacks why"):
        universe.load_text(json.dumps({"tickers": [{"ticker": "X", "entity_class": "Bank"}]}))
    with pytest.raises(universe.UniverseError, match="lacks why"):
        universe.load_text(json.dumps({"tickers": [{"ticker": "X", "entity_class": "Bank", "why": " "}]}))
    with pytest.raises(universe.UniverseError, match="no tickers list"):
        universe.load_text(json.dumps({"names": []}))


def test_a_second_universe_file_is_the_same_format() -> None:
    """Any universe file given as --universe goes through the same strict loader: the
    four fields, and an unknown field is rejected the same way."""
    private = {"tickers": [
        {"ticker": "PRIV.A", "entity_class": "OperatingCompany", "why": "a plain operating company"},
        {"ticker": "PRIV.B", "entity_class": "HighGrowthSoftware", "why": "software compounding revenue, profitable", "scope_limits": ["nothing the models see"]},
    ]}
    loaded = universe.load_text(json.dumps(private))
    assert [e.ticker for e in loaded.tickers] == ["PRIV.A", "PRIV.B"]
    assert loaded.tickers[1].scope_limits == ["nothing the models see"]
    private["tickers"][0]["position"] = "held"
    with pytest.raises(universe.UniverseError, match="universe entry PRIV.A carries unknown field\\(s\\) position"):
        universe.load_text(json.dumps(private))


def test_periods_needed_and_the_declared_cik() -> None:
    """Period depth is the model's (22): the mid-cycle window for a class routed to
    dcf_midcycle, five otherwise; a declared cik wins over the ticker map."""
    import fetch
    import reference

    admissibility = reference.Admissibility.from_json_string((ROOT / "reference" / "admissibility.json").read_text())
    params = reference.Params.from_json_string((ROOT / "reference" / "params.json").read_text())
    assert fetch.periods_needed("Cyclical", admissibility, params) == params.midcycle_window_years.value == 15
    assert fetch.periods_needed("OperatingCompany", admissibility, params) == 5
    assert fetch.periods_needed("Wrapper", admissibility, params) == 5
    assert fetch.periods_needed(None, admissibility, params) == 5
    table = {"0": {"cik_str": 34088, "ticker": "XOM", "title": "x"}}
    assert fetch.cik_of("XOM", table, None) == ("0000034088", "SEC's ticker map")
    assert fetch.cik_of("XOM", table, "0000000001") == ("0000000001", "declared in the universe entry, not the ticker map")
    assert fetch.cik_of("NOPE", table, None) == (None, "SEC's ticker map")
    entry = universe.load_text(json.dumps({"tickers": [{"ticker": "X", "entity_class": "Cyclical", "why": "cyclical", "cik": "0000000001"}]})).tickers[0]
    assert entry.cik == "0000000001"
    with pytest.raises(universe.UniverseError, match="unknown field"):
        universe.load_text(json.dumps({"tickers": [{"ticker": "X", "entity_class": "Cyclical", "why": "cyclical", "CIK": "1"}]}))


def test_uruguay_rows_and_the_declared_scale_floor() -> None:
    """(55) MercadoLibre's domicile needs two of the three country tables, each row carrying
    its source; the terminal-growth table has no Uruguay row by decision and says why. The
    mid-cycle scale floor is a dated declaration beside the window it trims."""
    import reference

    erp = reference.CountryTable.from_json_string((ROOT / "reference" / "equity_risk_premiums.json").read_text())
    tax = reference.CountryTable.from_json_string((ROOT / "reference" / "tax_rates.json").read_text())
    params = reference.Params.from_json_string((ROOT / "reference" / "params.json").read_text())

    # the total premium, as every other row is stored: the mature base plus the country's own
    assert dict(erp.values)["Uruguay"] == 0.063
    mature = params.mature_market_erp.value
    assert round(dict(erp.values)["Uruguay"] - mature, 4) == 0.0207
    assert any("Uruguay" in n and "6.30%" in n for n in erp.notes)

    assert dict(tax.values)["Uruguay"] == 0.25
    assert any("Uruguay" in n and "PwC" in n for n in tax.notes)

    # (57) the third row exists now that the table has a source
    assert dict(params.terminal_growth_rate.values)["Uruguay"] == 0.0750

    floor = params.midcycle_scale_floor
    assert floor.value == 0.10 and floor.as_of == "2026-09-23"
    assert "different business" in floor.source
    assert any("reinvestment rate is untouched" in n for n in floor.notes)


def test_terminal_growth_is_sourced_with_no_default() -> None:
    """(57) The table names its vintage and its series, carries no default row, and holds
    one row per country the other two country tables carry, less the one the World Economic
    Outlook has no series for."""
    import reference

    params = reference.Params.from_json_string((ROOT / "reference" / "params.json").read_text())
    erp = reference.CountryTable.from_json_string((ROOT / "reference" / "equity_risk_premiums.json").read_text())
    tg = params.terminal_growth_rate
    values = dict(tg.values)

    assert "default" not in values  # a table with a source has no default
    assert "IMF World Economic Outlook" in tg.source and "April 2026" in tg.source
    assert "NGDP" in tg.source and "national currency" in tg.source and "2031" in tg.source
    assert tg.as_of == "2026-04-14" and tg.max_age_days == 400

    # every country the ERP table carries, except the one with no WEO series
    assert set(values) == set(dict(erp.values)) - {"British Virgin Islands"}
    assert len(values) == 25
    assert any("not an IMF member" in n for n in tg.notes)

    # nominal growth, so every row sits above the old declared judgements it replaced
    assert values["United States"] == 0.0359 and values["Japan"] == 0.0271
    assert all(0.0 < v < 0.15 for v in values.values())


def test_denmarks_three_rows_and_its_curve() -> None:
    """(65) Denmark joins the three country tables from the tables' own sources, and its
    curve is an official-tier entry that was probed before it was written, never hand-copied."""
    import reference

    erp = reference.CountryTable.from_json_string((ROOT / "reference" / "equity_risk_premiums.json").read_text())
    tax = reference.CountryTable.from_json_string((ROOT / "reference" / "tax_rates.json").read_text())
    params = reference.Params.from_json_string((ROOT / "reference" / "params.json").read_text())
    sources = reference.RateSources.from_json_string((ROOT / "reference" / "rate_sources.json").read_text())

    # Aaa, so the mature-market base with a zero country risk premium, as every Aaa row is
    assert dict(erp.values)["Denmark"] == params.mature_market_erp.value == 0.0423
    assert any("Denmark" in n and "Aaa" in n for n in erp.notes)
    for peer in ("Germany", "Netherlands", "Sweden", "Switzerland"):
        assert dict(erp.values)[peer] == dict(erp.values)["Denmark"]

    assert dict(tax.values)["Denmark"] == 0.22
    assert any("Denmark" in n and "no local corporate income tax" in n for n in tax.notes)

    # the same vintage and series as every other terminal-growth row
    assert dict(params.terminal_growth_rate.values)["Denmark"] == 0.0335
    assert any("Denmark" in n and "2031" in n for n in params.terminal_growth_rate.notes)

    # the curve: official tier, keyless, ten-year only with the seven-year substituted
    dk = dict(sources.countries)["Denmark"]
    assert dk.tier == "official" and dk.parser == "dst_statbank"
    assert "statbank.dk" in dk.url and "api_key" not in dk.url
    assert dict(dk.series) == {"10y": "10-years central government bond (redemption yield)"}
    assert dict(dk.substitute) == {"7y": "10y"} and list(dk.tenors) == ["7y", "10y"]
    assert any("probed" in n or "verified" in n for n in dk.notes)


def test_the_danish_parser_reads_the_newest_month() -> None:
    """(65) StatBank BULK CSV: semicolon-separated, a YYYYMmm period and a decimal comma;
    the newest month wins and is dated at that month's end, because it is a monthly average."""
    import refresh_rates
    from datetime import date

    body = (
        "TYPE;TID;INDHOLD\n"
        "10 \u00e5rig statsobligation;2025M02;1,11\n"
        "10 \u00e5rig statsobligation;2025M04;2,22\n"     # out of order on purpose
        "10 \u00e5rig statsobligation;2025M03;3,33\n"
    ).encode("utf-8")
    observed, rate = refresh_rates.parse_dst_statbank(body, "10y")
    assert observed == date(2025, 4, 30) and rate == 0.0222
    # a row whose period is not a month, and the header, are skipped
    assert refresh_rates.parse_dst_statbank(b"TYPE;TID;INDHOLD\nx;2026;1,00\ny;2026M02;1,50\n", "10y") == (date(2026, 2, 28), 0.015)
    with pytest.raises(refresh_rates.RefreshError, match="no monthly observation"):
        refresh_rates.parse_dst_statbank(b"TYPE;TID;INDHOLD\n", "10y")
