"""The quality block's lines on invented facts: one value per fiscal year from its latest
filing, the first element in order, an absent line left absent, instants and durations
read as what they are, and the reasons."""

from __future__ import annotations

import fetch_sec
import quality


def duration(end: str, val: float, filed: str, *, start: str | None = None) -> dict[str, object]:
    return {"start": start or f"{int(end[:4]) - 1}{end[4:]}", "end": end, "val": val, "form": "10-K", "fp": "FY", "filed": filed, "accn": filed}


def instant(end: str, val: float, filed: str) -> dict[str, object]:
    return {"end": end, "val": val, "form": "10-K", "fp": "FY", "filed": filed, "accn": filed}


def facts(tags: dict[str, list[dict[str, object]]]) -> dict[str, object]:
    return {"facts": {"us-gaap": {tag: {"units": {"USD": entries}} for tag, entries in tags.items()}}}


def test_lines_per_year_with_the_element_each_came_from() -> None:
    f = facts({
        "Assets": [instant("2024-12-31", 900.0, "2025-02-01"), instant("2024-12-31", 950.0, "2026-02-01"), instant("2025-12-31", 1000.0, "2026-02-01")],
        "AssetsCurrent": [instant("2025-12-31", 300.0, "2026-02-01")],
        "LiabilitiesCurrent": [instant("2025-12-31", 150.0, "2026-02-01")],
        "GrossProfit": [duration("2025-12-31", 400.0, "2026-02-01", start="2025-01-01")],
        "CostOfGoodsAndServicesSold": [duration("2024-12-31", 650.0, "2025-02-01", start="2024-01-01")],
        "CostOfGoodsSold": [duration("2024-12-31", -1.0, "2025-02-01", start="2024-01-01")],
    })
    found, why = quality.of_record(f, "us-gaap", "USD", fetch_sec.load_tags())
    assert why is None and [x.period_end for x in found] == ["2025-12-31", "2024-12-31"]
    latest, prior = found
    assert (latest.total_assets, latest.current_assets, latest.current_liabilities, latest.gross_profit, latest.cost_of_revenue) == (1000.0, 300.0, 150.0, 400.0, None)
    assert dict(latest.rows) == {"total_assets": "Assets", "current_assets": "AssetsCurrent", "current_liabilities": "LiabilitiesCurrent", "gross_profit": "GrossProfit"}
    # the restated year reads its latest filing; the first cost element in order wins; an unfiled line is absent
    assert prior.total_assets == 950.0 and prior.cost_of_revenue == 650.0 and prior.current_assets is None
    assert dict(prior.rows) == {"total_assets": "Assets", "cost_of_revenue": "CostOfGoodsAndServicesSold"}


def test_the_list_is_capped_and_the_reasons_are_said() -> None:
    tags = fetch_sec.load_tags()
    many = facts({"Assets": [instant(f"{y}-12-31", float(y), f"{y + 1}-02-01") for y in range(2015, 2026)]})
    found, _ = quality.of_record(many, "us-gaap", "USD", tags)
    assert [x.period_end[:4] for x in found] == ["2025", "2024", "2023", "2022"]
    assert quality.of_record(facts({"Revenues": []}), "us-gaap", "USD", tags) == ([], quality.NO_LINES)
    assert quality.of_record(None, "us-gaap", "USD", tags) == ([], quality.NO_FACTS)
