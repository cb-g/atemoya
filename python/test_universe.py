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
    assert len(u.tickers) == len(raw) == 220
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
    assert len(values) == 26
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


def test_mexicos_three_rows_and_its_curve() -> None:
    """(71) Mexico joins the three country tables from the tables' own sources, its curve is
    the OECD monthly tier through FRED as South Korea's is, probed before it was written,
    and the peso names it as the country whose curve and terminal growth a peso price uses."""
    import reference

    erp = reference.CountryTable.from_json_string((ROOT / "reference" / "equity_risk_premiums.json").read_text())
    tax = reference.CountryTable.from_json_string((ROOT / "reference" / "tax_rates.json").read_text())
    params = reference.Params.from_json_string((ROOT / "reference" / "params.json").read_text())
    sources = reference.RateSources.from_json_string((ROOT / "reference" / "rate_sources.json").read_text())
    fx = reference.FxSources.from_json_string((ROOT / "reference" / "fx_sources.json").read_text())

    # Baa2: the mature-market base plus a country risk premium, stored as the total
    assert dict(erp.values)["Mexico"] == 0.0669
    assert round(dict(erp.values)["Mexico"] - params.mature_market_erp.value, 4) == 0.0246
    assert any("Mexico" in n and "Baa2" in n for n in erp.notes)

    assert dict(tax.values)["Mexico"] == 0.3
    assert any("Mexico" in n and "no state taxes" in n for n in tax.notes)

    # the same vintage and series as every other terminal-growth row
    assert dict(params.terminal_growth_rate.values)["Mexico"] == 0.0548
    assert any("Mexico" in n and "2031" in n for n in params.terminal_growth_rate.notes)

    # the curve: the OECD monthly ten-year through FRED, the seven-year substituted
    mx = dict(sources.countries)["Mexico"]
    assert mx.tier == "fred_oecd_10y" and mx.parser == "fred_oecd_10y"
    assert dict(mx.series) == {"10y": "IRLTLT01MXM156N"}
    assert dict(mx.substitute) == {"7y": "10y"} and list(mx.tenors) == ["7y", "10y"]
    assert any("verified" in n or "probed" in n for n in mx.notes)

    # a peso price takes Mexico's curve and terminal growth
    assert dict(fx.currency_countries)["MXN"] == "Mexico"
    assert "MXN" in dict(fx.currencies)


def test_the_holding_company_class_and_the_thirty_two() -> None:
    """(81) A name that fits no class gets a class: HoldingCompany has a row, admits no
    model and names the sum of the parts; Howard Hughes is its one name. Strategy is a
    Wrapper, not a new class. Thales and Saab declare the LEI their own reports carry."""
    import reference

    admissibility = reference.Admissibility.from_json_string((ROOT / "reference" / "admissibility.json").read_text())
    rows = dict(admissibility.classes)
    row = rows["HoldingCompany"]
    assert row.admissible_models == []
    assert "sum of the parts" in row.lens and "consolidated statements" in row.never
    assert any(n.startswith("HoldingCompany (81)") for n in admissibility.notes)

    u = universe.load_text((ROOT / "reference" / "universe.json").read_text())
    by = {e.ticker: e for e in u.tickers}
    assert [t for t, e in by.items() if e.entity_class == "HoldingCompany"] == ["HHH"]
    assert by["MSTR"].entity_class == "Wrapper"
    assert by["HO.PA"].lei == "529900FNDVTQJOVVPZ19"
    assert by["SAAB-B.ST"].lei == "549300ZHO4JCQQI13M69"
    added = "CLS TTD BX OWL PS GOGO IONQ IBM LLY MXT.AX MOT.AX PSUS RDDT NBIS SPOT BKNG EXPE ABNB HHH AEHR LITE BWXT ENB MP ZETA COIN MSTR GD NOC RTX HO.PA SAAB-B.ST".split()
    assert set(added) <= set(by) and len(added) == 32


def test_every_scope_limit_carries_a_declared_code_and_the_guide_names_each() -> None:
    """The codes are what a downstream reader filters on: every limit in the tracked files
    has one, each from the universe's own vocabulary, and docs/run.md lists the vocabulary."""
    root = Path(__file__).resolve().parent.parent
    raw = json.loads((root / "reference" / "universe.json").read_text())
    vocabulary = set(raw["scope_codes"])
    assert "uncoded" not in vocabulary and all(m.strip() for m in raw["scope_codes"].values())
    used: set[str] = set()
    for e in raw["tickers"]:
        limits, codes = e.get("scope_limits", []), e.get("scope_limit_codes", [])
        assert len(limits) == len(codes), e["ticker"]
        used |= set(codes)
    classes = json.loads((root / "reference" / "admissibility.json").read_text())["classes"]
    for name, rule in classes.items():
        limits, codes = rule.get("scope_limits_default", []), rule.get("scope_limit_codes_default", [])
        assert len(limits) == len(codes), name
        used |= set(codes)
    assert used <= vocabulary and vocabulary <= used, (used ^ vocabulary)
    guide = (root / "docs" / "run.md").read_text()
    for code in vocabulary:
        assert f"`{code}`" in guide, code
    by = {e["ticker"]: e for e in raw["tickers"]}
    assert by["ENB"]["entity_class"] == "RegulatedUtility"
    assert by["OKTA"]["scope_limit_codes"] == ["goodwill_heavy"]
    assert by["BKNG"]["scope_limit_codes"] == ["rebound_window"] and by["SAAB-B.ST"]["scope_limit_codes"] == ["build_out"]


def test_the_loader_holds_codes_to_the_limits_and_the_vocabulary() -> None:
    def text(codes: object, vocabulary: dict[str, str] | None = None) -> str:
        entry = {"ticker": "X", "entity_class": "Bank", "why": "a bank", "scope_limits": ["l"], "scope_limit_codes": codes}
        return json.dumps({"scope_codes": vocabulary or {"build_out": "m"}, "tickers": [entry]})

    assert universe.load_text(text(["build_out"])).tickers[0].scope_limit_codes == ["build_out"]
    for codes, needle in ((["build_out", "build_out"], "2 scope_limit_codes for 1 scope_limits"),
                          (["rebound"], "is not in the file's scope_codes"), ("build_out", "must be a list of strings")):
        with pytest.raises(universe.UniverseError, match=needle):
            universe.load_text(text(codes))


def test_map_cik_is_ten_digits_and_spcx_declares_the_company() -> None:
    raw = json.loads((ROOT / "reference" / "universe.json").read_text())["tickers"]
    by = {e["ticker"]: e for e in raw}
    assert by["SPCX"]["map_cik"] == "0001181412" and "map_cik" not in by["SAAB-B.ST"]
    assert sum("map_cik" in e for e in raw) == 189
    bad = json.dumps({"tickers": [{"ticker": "X", "entity_class": "Bank", "why": "a bank", "map_cik": "123"}]})
    with pytest.raises(universe.UniverseError, match="map_cik must be a ten-digit CIK"):
        universe.load_text(bad)


def test_every_table_country_declares_its_own_currency() -> None:
    """A record reporting in a currency that is not its domicile's own discounts on that
    currency's curve, so every country the tables carry names its currency, and every
    currency a domicile names leads to a country whose curve a dollar reporter would not
    be sent to by mistake."""
    import reference

    root = Path(__file__).resolve().parents[1] / "reference"
    fx = reference.FxSources.from_json_string((root / "fx_sources.json").read_text())
    own = dict(fx.country_currencies)
    params = reference.Params.from_json_string((root / "params.json").read_text())
    rates = reference.RateSources.from_json_string((root / "rate_sources.json").read_text())
    countries = {c for c, _ in params.terminal_growth_rate.values} | {c for c, _ in rates.countries} | set(rates.no_curve_fallback)
    for country in countries:
        assert country in own, country
    assert own["United States"] == "USD" and own["Israel"] == "ILS" and own["Singapore"] == "SGD"
    # the euro's members share one currency and the benchmark curve is one of them
    assert own[dict(fx.currency_countries)["EUR"]] == "EUR"
    # a currency's rate country reports in that currency, so it stays on its own curve
    for code, country in fx.currency_countries:
        assert own[country] == code, (code, country)
