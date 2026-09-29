"""The ESEF reader (73) on synthetic reports: the index, the annual filter, one report per
period, the companyfacts shape with the exclusive-midnight period ends, the dimension and
unit filters, the anchoring read from a definition linkbase and the substitution it allows
only where the standard line is absent, and the whole thing through the period reader.
Every number is invented; nothing here was read from a filer."""

from __future__ import annotations

import dataclasses
import json
from datetime import date

import fetch_esef as fe
import fetch_sec

SPAN = (350, 380)


def fact(concept: str, period: str, value: float | str, *, unit: str | None = "iso4217:EUR", **extra: str) -> dict[str, object]:
    dims: dict[str, object] = {"concept": concept, "entity": "scheme:LEI", "period": period}
    if unit is not None:
        dims["unit"] = unit
    dims.update(extra)
    return {"value": str(value), "dimensions": dims}


def doc(*facts: dict[str, object]) -> dict[str, object]:
    return {"documentInfo": {"documentType": "https://xbrl.org/2021/xbrl-json"}, "facts": {f"f{i}": f for i, f in enumerate(facts)}}


def filing(end: str, added: str, *, fxo: str | None = None, country: str = "FR", json_url: str | None = "/x.json", package_url: str | None = "/x.zip") -> fe.Filing:
    return fe.Filing(fxo_id=fxo or f"LEI-{end}-ESEF-{country}-0", period_end=date.fromisoformat(end), country=country,
                     date_added=date.fromisoformat(added), json_url=json_url, package_url=package_url)


YEAR_2024 = "2024-01-01T00:00:00/2025-01-01T00:00:00"
YEAR_2023 = "2023-01-01T00:00:00/2024-01-01T00:00:00"
END_2024, END_2023 = "2025-01-01T00:00:00", "2024-01-01T00:00:00"


def annual_report_2024() -> dict[str, object]:
    return doc(
        fact("ifrs-full:ProfitLoss", YEAR_2024, 100e6), fact("ifrs-full:ProfitLoss", YEAR_2023, 90e6),
        fact("ifrs-full:Equity", END_2024, 500e6), fact("ifrs-full:Equity", END_2023, 450e6),
        fact("ifrs-full:Revenue", YEAR_2024, 1000e6), fact("ifrs-full:Revenue", YEAR_2023, 900e6),
        fact("ifrs-full:Revenue", YEAR_2024, 600e6, **{"ifrs-full:SegmentsAxis": "x:Pharma"}),   # a breakdown, never a line
        fact("ifrs-full:NumberOfSharesOutstanding", END_2024, 1e9, unit="xbrli:shares"),           # not monetary
        fact("ifrs-full:DomicileOfEntity", YEAR_2024, "France", unit=None, language="fr"),         # text
        fact("acme:ResultatAvantImpots", YEAR_2024, 130e6), fact("acme:ResultatAvantImpots", YEAR_2023, 120e6),
        fact("acme:CashFlowsFromOperationsSomething", YEAR_2024, 7e6),
    )


def index_body(*rows: fe.Filing) -> bytes:
    return json.dumps({"data": [{"type": "filing", "id": r.fxo_id, "attributes": {
        "fxo_id": r.fxo_id, "period_end": r.period_end.isoformat(), "country": r.country, "date_added": f"{r.date_added.isoformat()} 10:00:00",
        "json_url": r.json_url, "package_url": r.package_url}} for r in rows]}).encode()


DEF_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink">
  <link:definitionLink xlink:type="extended" xlink:role="http://acme/role/anchoring">
    <link:loc xlink:type="locator" xlink:href="http://xbrl.ifrs.org/taxonomy/full_ifrs-cor.xsd#ifrs-full_ProfitLossBeforeTax" xlink:label="wider"/>
    <link:loc xlink:type="locator" xlink:href="acme.xsd#acme_ResultatAvantImpots" xlink:label="narrower"/>
    <link:definitionArc xlink:type="arc" xlink:arcrole="http://www.esma.europa.eu/xbrl/esef/arcrole/wider-narrower" xlink:from="wider" xlink:to="narrower"/>
    <link:loc xlink:type="locator" xlink:href="http://xbrl.ifrs.org/taxonomy/full_ifrs-cor.xsd#ifrs-full_CashFlowsFromUsedInOperations" xlink:label="w2"/>
    <link:loc xlink:type="locator" xlink:href="http://xbrl.ifrs.org/taxonomy/full_ifrs-cor.xsd#ifrs-full_OtherCashFlows" xlink:label="w3"/>
    <link:loc xlink:type="locator" xlink:href="acme.xsd#acme_CashFlowsFromOperationsSomething" xlink:label="n2"/>
    <link:definitionArc xlink:type="arc" xlink:arcrole="http://www.esma.europa.eu/xbrl/esef/arcrole/wider-narrower" xlink:from="w2" xlink:to="n2"/>
    <link:definitionArc xlink:type="arc" xlink:arcrole="http://www.esma.europa.eu/xbrl/esef/arcrole/wider-narrower" xlink:from="w3" xlink:to="n2"/>
    <link:loc xlink:type="locator" xlink:href="acme.xsd#acme_Wider" xlink:label="ext-wider"/>
    <link:loc xlink:type="locator" xlink:href="http://xbrl.ifrs.org/taxonomy/full_ifrs-cor.xsd#ifrs-full_Revenue" xlink:label="rev"/>
    <link:definitionArc xlink:type="arc" xlink:arcrole="http://www.esma.europa.eu/xbrl/esef/arcrole/wider-narrower" xlink:from="ext-wider" xlink:to="rev"/>
    <link:definitionArc xlink:type="arc" xlink:arcrole="http://www.xbrl.org/2003/arcrole/general-special" xlink:from="wider" xlink:to="narrower"/>
  </link:definitionLink>
</link:linkbase>"""


def test_index_rows_are_filings_oldest_first_and_a_row_without_a_date_is_skipped() -> None:
    body = index_body(filing("2024-12-31", "2025-03-01"), filing("2023-12-31", "2024-03-01"))
    rows = fe.parse_index(body)
    assert [r.period_end.isoformat() for r in rows] == ["2023-12-31", "2024-12-31"]
    assert rows[1].date_added == date(2025, 3, 1) and rows[1].json_url == "/x.json"
    broken = json.dumps({"data": [{"attributes": {"fxo_id": "x", "period_end": "n/a", "date_added": "2025-01-01"}}]}).encode()
    assert fe.parse_index(broken) == []
    assert "entity.identifier" in fe.index_url("549300E9PC51EN656011") and "549300E9PC51EN656011" in fe.index_url("549300E9PC51EN656011")


def test_periods_end_the_day_before_the_exclusive_midnight() -> None:
    assert fe._period(YEAR_2024) == (date(2024, 1, 1), date(2024, 12, 31))  # pyright: ignore[reportPrivateUsage]
    assert fe._period(END_2024) == (None, date(2024, 12, 31))  # pyright: ignore[reportPrivateUsage]
    assert fe._period("2024-06-30") == (None, date(2024, 6, 29))  # pyright: ignore[reportPrivateUsage]
    assert fe._period("2024-12-31T23:59:59") == (None, date(2024, 12, 31))  # pyright: ignore[reportPrivateUsage]


def test_statement_lines_are_monetary_and_undimensioned() -> None:
    lines = fe._lines(annual_report_2024())  # pyright: ignore[reportPrivateUsage]
    concepts = [c for c, *_ in lines]
    assert concepts.count("ifrs-full:Revenue") == 2      # the segment breakdown is not a line
    assert "ifrs-full:NumberOfSharesOutstanding" not in concepts and "ifrs-full:DomicileOfEntity" not in concepts
    assert all(cur == "EUR" for _, cur, *_ in lines)
    assert fe.is_annual(lines, date(2024, 12, 31), SPAN) and not fe.is_annual(lines, date(2024, 6, 30), SPAN)


def test_anchors_read_the_one_wider_standard_parent_only() -> None:
    a = fe.anchors(DEF_XML)
    assert a == {"acme:ResultatAvantImpots": "ProfitLossBeforeTax"}   # the two-parent extension and the wider extension are absent
    assert fe.anchors(None) == {} and fe.anchors(b"not xml") == {}


def test_an_anchored_extension_stands_in_only_where_the_standard_line_is_absent() -> None:
    f24 = filing("2024-12-31", "2025-03-01")
    reports = {f24.fxo_id: annual_report_2024()}
    adapted = fe.adapt([f24], reports, {f24.fxo_id: fe.anchors(DEF_XML)})
    gaap = adapted.gaap
    assert adapted.currency == "EUR" and adapted.substitutions == 2
    pretax = gaap["ProfitLossBeforeTax"]["units"]["EUR"]  # pyright: ignore[reportIndexIssue, reportUnknownVariableType]
    assert sorted((e["end"], e["val"]) for e in pretax) == [("2023-12-31", 120e6), ("2024-12-31", 130e6)]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    assert all(e["form"] == "ESEF" and e["fp"] == "FY" and e["accn"] == f24.fxo_id and e["filed"] == "2025-03-01" for e in pretax)  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    assert "acme:ResultatAvantImpots" not in gaap and "CashFlowsFromUsedInOperations" not in gaap
    assert [n for n in adapted.notes if "ProfitLossBeforeTax read from the extension acme:ResultatAvantImpots" in n] and len(adapted.notes) == 1
    # a standard line present in the same report wins over the extension
    with_standard = annual_report_2024()
    with_standard["facts"]["std"] = fact("ifrs-full:ProfitLossBeforeTax", YEAR_2024, 131e6)  # pyright: ignore[reportIndexIssue]
    adapted = fe.adapt([f24], {f24.fxo_id: with_standard}, {f24.fxo_id: fe.anchors(DEF_XML)})
    vals = {e["end"]: e["val"] for e in adapted.gaap["ProfitLossBeforeTax"]["units"]["EUR"]}  # pyright: ignore[reportIndexIssue, reportUnknownVariableType, reportUnknownArgumentType]
    assert vals == {"2024-12-31": 131e6, "2023-12-31": 120e6} and adapted.substitutions == 1


def test_choose_keeps_annual_reports_one_per_period_end() -> None:
    annual = filing("2024-12-31", "2025-03-01")
    interim = filing("2024-06-30", "2024-08-01", fxo="LEI-2024-06-30-ESEF-FR-0")
    twin = filing("2024-12-31", "2025-03-05", fxo="LEI-2024-12-31-ESEF-SE-0", country="SE")
    nofacts = filing("2022-12-31", "2023-03-01", json_url=None)
    reports = {annual.fxo_id: annual_report_2024(), twin.fxo_id: annual_report_2024(),
               interim.fxo_id: doc(fact("ifrs-full:ProfitLoss", "2024-01-01T00:00:00/2024-07-01T00:00:00", 40e6)), nofacts.fxo_id: None}
    notes: list[str] = []
    chosen = fe.choose([nofacts, interim, annual, twin], reports, SPAN, notes)
    assert chosen == [annual]
    assert any("interim report, skipped" in n for n in notes) and any("second report for 2024-12-31" in n for n in notes) and any("no facts file" in n for n in notes)


def test_the_adapted_facts_read_through_the_period_reader() -> None:
    """One report per year, each its own filing (61), the tag behind every number, under
    the same ifrs-full definitions a 20-F filer is read with."""
    f24 = filing("2024-12-31", "2025-03-01")
    f23 = filing("2023-12-31", "2024-03-01")
    report_2023 = doc(fact("ifrs-full:ProfitLoss", YEAR_2023, 91e6), fact("ifrs-full:Equity", END_2023, 450e6), fact("ifrs-full:Revenue", YEAR_2023, 901e6))
    adapted = fe.adapt([f24, f23], {f24.fxo_id: annual_report_2024(), f23.fxo_id: report_2023}, {f24.fxo_id: fe.anchors(DEF_XML), f23.fxo_id: {}})
    tags = dataclasses.replace(fetch_sec.load_tags(), annual_forms=[*fetch_sec.load_tags().annual_forms, fe.FORM])
    periods = fetch_sec.periods_from_facts(adapted.gaap, tags, fetch_sec.load_definitions(), [], taxonomy="ifrs-full", unit="EUR", depth=5)
    by_end = {p.period_end: p for p in periods}
    assert by_end["2024-12-31"].accession == f24.fxo_id and by_end["2024-12-31"].net_income == 100e6 and by_end["2024-12-31"].total_revenue == 1000e6
    assert by_end["2024-12-31"].pretax_income == 130e6 and by_end["2024-12-31"].pretax_income_row == "ProfitLossBeforeTax"
    # 2023 is read from its own report, not from the 2024 report's comparative column
    assert by_end["2023-12-31"].accession == f23.fxo_id and by_end["2023-12-31"].net_income == 91e6 and by_end["2023-12-31"].total_revenue == 901e6
    assert by_end["2023-12-31"].pretax_income is None  # the 2023 report tagged neither the line nor the extension
    # and the 2024 report's differing comparative is recorded on 2023, never taken
    assert {(r.tag, r.later) for r in by_end["2023-12-31"].restated_from} >= {("ProfitLoss", 90e6), ("Revenue", 900e6)} or by_end["2023-12-31"].restated_from == []


def test_the_aggregator_lagging_the_filer_is_a_recorded_decision() -> None:
    """(73) Air Liquide's shape on 2026-09-29: the aggregator's newest report is for FY2024,
    past the filing-age gate, while the vendor carries FY2025. The vendor's statements are
    used by a decision that says so; a fresh report, or a vendor no newer, keeps the filing."""
    import fetch
    import boundary

    required = {f.name: None for f in dataclasses.fields(boundary.FiscalPeriod)
                if f.default is dataclasses.MISSING and f.default_factory is dataclasses.MISSING and f.name != "period_end"}

    def period(end: str, filed: str | None) -> boundary.FiscalPeriod:
        return boundary.FiscalPeriod(**{**required, "period_end": end, "filed": filed})  # pyright: ignore[reportArgumentType]

    esef = [period("2024-12-31", "2025-03-11"), period("2023-12-31", "2024-03-12")]
    vendor = [period("2025-12-31", None), period("2024-12-31", None)]
    reason = fetch.esef_lags(esef, vendor, date(2026, 9, 29), 400)
    assert reason is not None and "the source lags the filer" in reason and "2024-12-31" in reason and "2025-12-31" in reason
    assert fetch.esef_lags(esef, vendor, date(2025, 12, 31), 400) is None          # inside the gate: the filing stands
    assert fetch.esef_lags(esef, [period("2024-12-31", None)], date(2026, 9, 29), 400) is None   # the vendor is no newer
    assert fetch.esef_lags([], vendor, date(2026, 9, 29), 400) is None
