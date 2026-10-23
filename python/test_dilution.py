"""The dilution reader (2026-10-23), every figure invented: the newest quarter or year with both
weighted-average counts and a profit, the quarter at an equal end, a loss skipped within the
window and nothing beyond it, the conversion shares tagged apart left out, and the vendor's two
average rows."""
from __future__ import annotations

from datetime import date

import dilution
import fetch_sec

DEFS = fetch_sec.load_definitions()


def entry(start: str, end: str, val: float, form: str, filed: str) -> dict[str, object]:
    return {"start": start, "end": end, "val": val, "form": form, "fp": "Q", "filed": filed, "fy": int(end[:4]), "accn": f"a-{filed}"}


def facts(lines: dict[str, list[dict[str, object]]], unit_of: dict[str, str] | None = None) -> dict[str, object]:
    units = unit_of or {}
    return {"facts": {"us-gaap": {tag: {"units": {units.get(tag, "shares"): rows}} for tag, rows in lines.items()}}}


DILUTED, BASIC, NI = "WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasic", "NetIncomeLoss"


def filer(*, q_income: float, y_income: float = 500.0, conversion: float | None = None) -> dict[str, object]:
    """A fiscal year to 2025-12-31 and the first quarter of 2026 after it."""
    lines: dict[str, list[dict[str, object]]] = {
        DILUTED: [entry("2025-01-01", "2025-12-31", 1030.0, "10-K", "2026-02-20"), entry("2026-01-01", "2026-03-31", 1060.0, "10-Q", "2026-05-01")],
        BASIC: [entry("2025-01-01", "2025-12-31", 1000.0, "10-K", "2026-02-20"), entry("2026-01-01", "2026-03-31", 1000.0, "10-Q", "2026-05-01")],
        NI: [entry("2025-01-01", "2025-12-31", y_income, "10-K", "2026-02-20"), entry("2026-01-01", "2026-03-31", q_income, "10-Q", "2026-05-01")],
    }
    if conversion is not None:
        lines["IncrementalCommonSharesAttributableToConversionOfDebtSecurities"] = [entry("2026-01-01", "2026-03-31", conversion, "10-Q", "2026-05-01")]
    return facts(lines, {NI: "USD"})


def test_the_newest_profitable_period_and_the_conversions_left_out() -> None:
    d, reason = dilution.of_facts(filer(q_income=120.0), "us-gaap", "USD", DEFS)
    assert reason is None and d is not None
    assert (d.period_end, d.span, d.diluted, d.basic, d.excluded) == ("2026-03-31", "quarter", 1060.0, 1000.0, 0.0)
    assert abs(d.ratio - 0.06) < 1e-12 and d.source == f"{DILUTED} / {BASIC}"
    # a loss quarter's diluted count is its basic count by rule: the year before is read
    loss, _ = dilution.of_facts(filer(q_income=-40.0), "us-gaap", "USD", DEFS)
    assert loss is not None and (loss.period_end, loss.span) == ("2025-12-31", "year") and abs(loss.ratio - 0.03) < 1e-12
    # conversion shares tagged apart are left out: the convertible stays in the debt
    conv, _ = dilution.of_facts(filer(q_income=120.0, conversion=45.0), "us-gaap", "USD", DEFS)
    assert conv is not None and conv.excluded == 45.0 and abs(conv.ratio - 0.015) < 1e-12
    assert conv.excluded_rows == "IncrementalCommonSharesAttributableToConversionOfDebtSecurities"
    # losses throughout the window: nothing, with the reason
    none, why = dilution.of_facts(filer(q_income=-40.0, y_income=-10.0), "us-gaap", "USD", DEFS)
    assert none is None and why == dilution.NO_PROFIT
    assert dilution.of_facts(None, "us-gaap", "USD", DEFS) == (None, dilution.NO_FACTS)


def test_the_window_reads_no_old_year() -> None:
    """A profitable year more than a year before the newest period with both counts is not read."""
    lines = {
        DILUTED: [entry("2023-01-01", "2023-12-31", 1050.0, "10-K", "2024-02-20"), entry("2025-01-01", "2025-12-31", 1000.0, "10-K", "2026-02-20")],
        BASIC: [entry("2023-01-01", "2023-12-31", 1000.0, "10-K", "2024-02-20"), entry("2025-01-01", "2025-12-31", 1000.0, "10-K", "2026-02-20")],
        NI: [entry("2023-01-01", "2023-12-31", 80.0, "10-K", "2024-02-20"), entry("2025-01-01", "2025-12-31", -5.0, "10-K", "2026-02-20")],
    }
    assert dilution.of_facts(facts(lines, {NI: "USD"}), "us-gaap", "USD", DEFS) == (None, dilution.NO_PROFIT)


def test_the_vendor_rows() -> None:
    columns = {date(2025, 12, 31): {"Diluted Average Shares": 2040.0, "Basic Average Shares": 2000.0, "Net Income": 300.0},
               date(2024, 12, 31): {"Diluted Average Shares": 2100.0, "Basic Average Shares": 2000.0, "Net Income": 250.0}}
    d, _ = dilution.of_vendor(columns, DEFS)
    assert d is not None and d.period_end == "2025-12-31" and abs(d.ratio - 0.02) < 1e-12
    assert d.source == "Diluted Average Shares / Basic Average Shares"
    assert dilution.of_vendor({date(2025, 12, 31): {"Net Income": 300.0}}, DEFS) == (None, dilution.NO_COUNTS)
